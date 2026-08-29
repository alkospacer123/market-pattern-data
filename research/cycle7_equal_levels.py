from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

DISC_END = pd.Timestamp("2026-05-16 00:00:00")
VARIANTS = [
    {"tolerance_ticks": tol, "touch_lookback_bars": lb, "rejection_ticks": rej}
    for tol in (0, 1) for lb in (1, 3, 6) for rej in (0, 1)
]
GATES = {
    "base_pf_min": 1.5,
    "stress_pf_min": 1.2,
    "expectancy_positive": True,
    "minimum_trades": 25,
    "minimum_unique_days": 15,
    "minimum_positive_months": 3,
    "largest_winner_share_max": 0.25,
}
RR = 3.0


def load_v3():
    spec = importlib.util.spec_from_file_location("v3", "research/autonomous_search_v3.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def session_id(ts: pd.Timestamp) -> int:
    mins = ts.hour * 60 + ts.minute
    if 600 <= mins <= 775:   # 10:00 .. 12:55 start time
        return 1
    if 840 <= mins <= 1010:  # 14:00 .. 16:50 start time
        return 2
    return 0


def nearest_round(px: float, step: float) -> float:
    return round(px / step) * step


def generate_signals(m5: pd.DataFrame, inst: str, variant: dict[str, int], v3) -> list[dict[str, Any]]:
    tick = float(v3.SPECS[inst]["tick"])
    step = float(v3.SPECS[inst]["round_step"])
    tol = int(variant["tolerance_ticks"]) * tick + 1e-12
    rej = int(variant["rejection_ticks"]) * tick
    lb = int(variant["touch_lookback_bars"])
    signals: list[dict[str, Any]] = []

    times = m5.time.tolist()
    highs = m5.high.to_numpy(float)
    lows = m5.low.to_numpy(float)
    closes = m5.close.to_numpy(float)
    dates = m5.date.to_numpy()
    sess = np.array([session_id(t) for t in times], dtype=int)

    prev_qual_short = False
    prev_short_level = math.nan
    prev_short_date = None
    prev_short_session = 0
    prev_qual_long = False
    prev_long_level = math.nan
    prev_long_date = None
    prev_long_session = 0

    for i in range(len(m5)):
        sid = int(sess[i])
        if sid == 0:
            prev_qual_short = prev_qual_long = False
            continue

        # SHORT: current high and at least one earlier high touch same round level.
        sh_level = nearest_round(highs[i], step)
        sh_current_touch = abs(highs[i] - sh_level) <= tol
        sh_reject = closes[i] <= sh_level - rej + 1e-12
        sh_prior_touch = False
        if sh_current_touch and sh_reject:
            for j in range(max(0, i - lb), i):
                if dates[j] != dates[i] or sess[j] != sid:
                    continue
                if abs(highs[j] - sh_level) <= tol:
                    sh_prior_touch = True
                    break
        sh_qual = bool(sh_current_touch and sh_reject and sh_prior_touch)
        sh_contiguous = (
            prev_qual_short
            and i > 0
            and dates[i] == prev_short_date
            and sid == prev_short_session
            and abs(sh_level - prev_short_level) <= 1e-12
            and (times[i] - times[i - 1]) == pd.Timedelta(minutes=5)
        )
        if sh_qual and not sh_contiguous:
            signals.append({
                "signal_index": i,
                "signal_time": str(times[i]),
                "side": -1,
                "level": float(sh_level),
                "session": sid,
            })
        prev_qual_short = sh_qual
        prev_short_level = sh_level
        prev_short_date = dates[i]
        prev_short_session = sid

        # LONG: symmetric low touch.
        lo_level = nearest_round(lows[i], step)
        lo_current_touch = abs(lows[i] - lo_level) <= tol
        lo_reject = closes[i] >= lo_level + rej - 1e-12
        lo_prior_touch = False
        if lo_current_touch and lo_reject:
            for j in range(max(0, i - lb), i):
                if dates[j] != dates[i] or sess[j] != sid:
                    continue
                if abs(lows[j] - lo_level) <= tol:
                    lo_prior_touch = True
                    break
        lo_qual = bool(lo_current_touch and lo_reject and lo_prior_touch)
        lo_contiguous = (
            prev_qual_long
            and i > 0
            and dates[i] == prev_long_date
            and sid == prev_long_session
            and abs(lo_level - prev_long_level) <= 1e-12
            and (times[i] - times[i - 1]) == pd.Timedelta(minutes=5)
        )
        if lo_qual and not lo_contiguous:
            signals.append({
                "signal_index": i,
                "signal_time": str(times[i]),
                "side": 1,
                "level": float(lo_level),
                "session": sid,
            })
        prev_qual_long = lo_qual
        prev_long_level = lo_level
        prev_long_date = dates[i]
        prev_long_session = sid

    signals.sort(key=lambda z: (z["signal_time"], -z["side"]))
    return signals


def execute(m5: pd.DataFrame, m1: pd.DataFrame, signals: list[dict[str, Any]], inst: str, friction_ticks: int, v3) -> list[dict[str, Any]]:
    tick = float(v3.SPECS[inst]["tick"])
    cost = friction_ticks * tick
    times_ns = m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    lookup = {int(t): i for i, t in enumerate(times_ns)}
    op = m1.open.to_numpy(float)
    hi = m1.high.to_numpy(float)
    lo = m1.low.to_numpy(float)
    cl = m1.close.to_numpy(float)
    dates = m1.date.to_numpy()
    out: list[dict[str, Any]] = []
    busy_until = -1

    for sig in signals:
        st = pd.Timestamp(sig["signal_time"])
        entry_time = st + pd.Timedelta(minutes=5)
        ei = lookup.get(int(entry_time.value))
        if ei is None or ei <= busy_until:
            continue
        signal_date = m5.date.iloc[int(sig["signal_index"])]
        if dates[ei] != signal_date:
            continue

        side = int(sig["side"])
        level = float(sig["level"])
        entry = float(op[ei])
        stop = level - tick if side == 1 else level + tick
        if (side == 1 and entry <= stop) or (side == -1 and entry >= stop):
            continue
        risk = side * (entry - stop)
        if not np.isfinite(risk) or risk <= 0:
            continue
        target = entry + side * RR * risk

        # Force exit at 17:00 open when present; otherwise the last M1 close before 17:00.
        force_time = pd.Timestamp(entry_time.date()) + pd.Timedelta(hours=17)
        fi = lookup.get(int(force_time.value))
        if fi is not None and fi >= ei and dates[fi] == dates[ei]:
            last_intrabar = fi - 1
            force_index = fi
            force_price = float(op[fi])
            force_reason = "FORCE_1700_OPEN"
        else:
            cutoff = int(force_time.value)
            last_intrabar = int(np.searchsorted(times_ns, cutoff, side="left") - 1)
            if last_intrabar < ei or dates[last_intrabar] != dates[ei]:
                continue
            force_index = last_intrabar
            force_price = float(cl[last_intrabar])
            force_reason = "FORCE_LAST_CLOSE"

        xi = force_index
        raw_exit = force_price
        reason = force_reason
        for j in range(ei, last_intrabar + 1):
            o, h, l = float(op[j]), float(hi[j]), float(lo[j])
            if side == 1:
                if o <= stop:
                    xi, raw_exit, reason = j, o, "STOP_GAP"
                    break
                if o >= target:
                    xi, raw_exit, reason = j, o, "TARGET_GAP"
                    break
                # STOP_FIRST for an intrabar tie.
                if l <= stop:
                    xi, raw_exit, reason = j, stop, "STOP"
                    break
                if h >= target:
                    xi, raw_exit, reason = j, target, "TARGET"
                    break
            else:
                if o >= stop:
                    xi, raw_exit, reason = j, o, "STOP_GAP"
                    break
                if o <= target:
                    xi, raw_exit, reason = j, o, "TARGET_GAP"
                    break
                if h >= stop:
                    xi, raw_exit, reason = j, stop, "STOP"
                    break
                if l <= target:
                    xi, raw_exit, reason = j, target, "TARGET"
                    break

        busy_until = xi
        adjusted_entry = entry + side * cost
        adjusted_exit = raw_exit - side * cost
        pnl = side * (adjusted_exit - adjusted_entry)
        bps = 10000.0 * pnl / entry
        out.append({
            "instrument": inst,
            "timeframe": "M5",
            "date": str(dates[ei]),
            "month": str(pd.Timestamp(dates[ei]).to_period("M")),
            "side": side,
            "signal_time": str(st),
            "entry_time": str(m1.time.iloc[ei]),
            "exit_time": str(m1.time.iloc[xi]),
            "level": level,
            "entry": entry,
            "stop": stop,
            "target": target,
            "raw_exit": raw_exit,
            "friction_ticks_per_side": friction_ticks,
            "bps": float(bps),
            "reason": reason,
        })
    return out


def month_breakdown(trades: list[dict[str, Any]], v3) -> dict[str, Any]:
    months = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    return {m: v3.metrics([t for t in trades if t["date"].startswith(m)]) for m in months}


def gate(base: dict[str, Any], stress: dict[str, Any]) -> tuple[bool, list[str]]:
    fail = []
    if base["pf"] < GATES["base_pf_min"]:
        fail.append("BASE_PF")
    if stress["pf"] < GATES["stress_pf_min"]:
        fail.append("STRESS_PF")
    if base["expectancy_bps"] is None or base["expectancy_bps"] <= 0:
        fail.append("BASE_EXPECTANCY")
    if stress["expectancy_bps"] is None or stress["expectancy_bps"] <= 0:
        fail.append("STRESS_EXPECTANCY")
    if base["trades"] < GATES["minimum_trades"]:
        fail.append("TRADES")
    if base["unique_days"] < GATES["minimum_unique_days"]:
        fail.append("UNIQUE_DAYS")
    if base["positive_months"] < GATES["minimum_positive_months"]:
        fail.append("POSITIVE_MONTHS")
    if base["largest_winner_share"] is None or base["largest_winner_share"] > GATES["largest_winner_share_max"]:
        fail.append("CONCENTRATION")
    return not fail, fail


def score(row: dict[str, Any]) -> float:
    b, s = row["base"], row["stress"]
    if b["expectancy_bps"] is None or s["expectancy_bps"] is None:
        return -1e9
    return (
        math.log(max(min(b["pf"], 10.0), 1e-9))
        + 0.65 * math.log(max(min(s["pf"], 10.0), 1e-9))
        + 0.03 * b["expectancy_bps"]
        + 0.02 * s["expectancy_bps"]
        + 0.08 * b["positive_months"]
    )


def run_inst(root: Path, inst: str, v3) -> dict[str, Any]:
    m5, p5 = v3.load_prefix(root, inst, "M5")
    m1, p1 = v3.load_prefix(root, inst, "M1")
    if m5.time.max() >= DISC_END or m1.time.max() >= DISC_END:
        raise PermissionError("Cycle 7 data fence violated")

    rows = []
    for variant in VARIANTS:
        signals = generate_signals(m5, inst, variant, v3)
        gross_trades = execute(m5, m1, signals, inst, 0, v3)
        base_trades = execute(m5, m1, signals, inst, 1, v3)
        stress_trades = execute(m5, m1, signals, inst, 2, v3)
        gross, base, stress = v3.metrics(gross_trades), v3.metrics(base_trades), v3.metrics(stress_trades)
        passed, failures = gate(base, stress)
        row = {
            "variant": variant,
            "signals": len(signals),
            "gross": gross,
            "base": base,
            "stress": stress,
            "base_months": month_breakdown(base_trades, v3),
            "stress_months": month_breakdown(stress_trades, v3),
            "trade_count_conserved": len(gross_trades) == len(base_trades) == len(stress_trades),
            "gate_pass": passed,
            "gate_failures": failures,
            "signals_detail": signals,
            "base_trades": base_trades,
            "stress_trades": stress_trades,
        }
        row["rank_score"] = score(row)
        rows.append(row)

    rows.sort(key=lambda r: (r["gate_pass"], r["rank_score"]), reverse=True)
    survivors = [r for r in rows if r["gate_pass"]]
    best = rows[0] if rows else None
    return {
        "instrument": inst,
        "variants_tested": len(rows),
        "survivors": len(survivors),
        "best": best,
        "rows": rows,
        "provenance": p5 + p1,
    }


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in ("signals_detail", "base_trades", "stress_trades")}


def run(root: Path, out: Path):
    v3 = load_v3()
    out.mkdir(parents=True, exist_ok=True)
    results = [run_inst(root, inst, v3) for inst in ("CNYRUBF", "USDRUBF")]

    compact_results = []
    for r in results:
        cr = {k: v for k, v in r.items() if k not in ("rows", "best")}
        cr["rows"] = [compact_row(x) for x in r["rows"]]
        cr["best"] = compact_row(r["best"]) if r["best"] else None
        compact_results.append(cr)

        inst = r["instrument"]
        if r["best"]:
            (out / f"best_{inst}_signals.json").write_text(json.dumps(r["best"]["signals_detail"], indent=2, default=v3.jsonable) + "\n")
            (out / f"best_{inst}_base_trades.json").write_text(json.dumps(r["best"]["base_trades"], indent=2, default=v3.jsonable) + "\n")
            (out / f"best_{inst}_stress_trades.json").write_text(json.dumps(r["best"]["stress_trades"], indent=2, default=v3.jsonable) + "\n")

    status = "RESEARCH_SURVIVOR_FOUND_AWAITING_NEW_CONFIRMATION_DATA" if any(r["survivors"] for r in results) else "NO_RESEARCH_SURVIVOR"
    manifest = {
        "engine": "cycle7-equal-high-low-round-level-v1",
        "status": status,
        "data_end_exclusive": str(DISC_END),
        "retired_internal_confirmation_accessed": False,
        "true_oos_2025_accessed": False,
        "commission_excluded": True,
        "rr": RR,
        "variants": VARIANTS,
        "gates": GATES,
        "results": compact_results,
    }
    (out / "result.json").write_text(json.dumps(manifest, indent=2, default=v3.jsonable) + "\n")

    lines = ["# Cycle 7 — Equal High/Low at Round Level", "", f"Status: **{status}**", ""]
    for r in results:
        lines.append(f"## {r['instrument']}")
        lines.append(f"Survivors: {r['survivors']} / {r['variants_tested']}")
        for x in r["rows"]:
            b, s = x["base"], x["stress"]
            lines.append(
                f"- {x['variant']} | signals={x['signals']} | BASE PF={b['pf']:.3f}, exp={b['expectancy_bps']}, N={b['trades']}, days={b['unique_days']}, +months={b['positive_months']} | "
                f"STRESS PF={s['pf']:.3f}, exp={s['expectancy_bps']} | gate={x['gate_pass']} fail={x['gate_failures']}"
            )
        lines.append("")
    lines += [
        "Retired May16-Jul1 confirmation was not read. 2025 TRUE OOS was not read.",
        "A Cycle 7 survivor remains research-only until genuinely new untouched confirmation data exists.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(manifest, indent=2, default=v3.jsonable))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, default=Path("."))
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()
    run(a.data_root, a.output)
