from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

TRAIN_START = pd.Timestamp("2026-01-05 00:00:00")
TRAIN_END = pd.Timestamp("2026-03-01 00:00:00")
DISC_END = pd.Timestamp("2026-05-16 00:00:00")
FOLDS = [
    ("MARCH", pd.Timestamp("2026-03-01"), pd.Timestamp("2026-04-01")),
    ("APRIL", pd.Timestamp("2026-04-01"), pd.Timestamp("2026-05-01")),
    ("MAY15", pd.Timestamp("2026-05-01"), pd.Timestamp("2026-05-16")),
]
STOP_BUFFERS = (3, 5, 8, 13)
TARGET_RRS = (2.0, 3.0, 4.0)
EXEC_GRID = [(b, r) for b in STOP_BUFFERS for r in TARGET_RRS]
GATES = {
    "base_pf_min": 1.50,
    "stress_pf_min": 1.20,
    "base_expectancy_positive": True,
    "stress_expectancy_positive": True,
    "minimum_base_trades": 20,
    "minimum_unique_days": 12,
    "minimum_positive_base_folds": 3,
    "minimum_positive_stress_folds": 2,
    "largest_winner_share_max": 0.25,
    "minimum_stable_execution_neighbors": 1,
}


def load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v3 = load_module("research/autonomous_search_v3.py", "v3")
v7 = load_module("research/cycle7_equal_levels.py", "v7")


def signal_subset(signals: list[dict[str, Any]], start: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, Any]]:
    return [s for s in signals if start <= pd.Timestamp(s["signal_time"]) < end]


def session_order_expiry(st: pd.Timestamp) -> pd.Timestamp:
    close_time = st + pd.Timedelta(minutes=5)
    if st.hour < 14:
        session_end = pd.Timestamp(st.date()) + pd.Timedelta(hours=13)
    else:
        session_end = pd.Timestamp(st.date()) + pd.Timedelta(hours=17)
    return min(close_time + pd.Timedelta(minutes=15), session_end)


def execute_passive(
    m5: pd.DataFrame,
    m1: pd.DataFrame,
    signals: list[dict[str, Any]],
    inst: str,
    stop_buffer_ticks: int,
    target_rr: float,
    mode: str,
) -> list[dict[str, Any]]:
    tick = float(v3.SPECS[inst]["tick"])
    if mode == "GROSS":
        fill_through = 0
        exit_slip_ticks = 0
    elif mode == "BASE":
        fill_through = 1
        exit_slip_ticks = 1
    elif mode == "STRESS":
        fill_through = 2
        exit_slip_ticks = 2
    else:
        raise ValueError(mode)

    times_ns = m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64)
    lookup = {int(t): i for i, t in enumerate(times_ns)}
    op = m1.open.to_numpy(float)
    hi = m1.high.to_numpy(float)
    lo = m1.low.to_numpy(float)
    cl = m1.close.to_numpy(float)
    dates = m1.date.to_numpy()
    busy_until = -1
    out: list[dict[str, Any]] = []

    for sig in signals:
        st = pd.Timestamp(sig["signal_time"])
        order_time = st + pd.Timedelta(minutes=5)
        expiry = session_order_expiry(st)
        start_i = int(np.searchsorted(times_ns, int(order_time.value), side="left"))
        end_i = int(np.searchsorted(times_ns, int(expiry.value), side="left"))
        start_i = max(start_i, busy_until + 1)
        if start_i >= len(m1) or start_i >= end_i:
            continue
        signal_date = m5.date.iloc[int(sig["signal_index"])]
        if dates[start_i] != signal_date:
            continue

        side = int(sig["side"])
        level = float(sig["level"])
        threshold = level - fill_through * tick if side == 1 else level + fill_through * tick
        fill_i = None
        for j in range(start_i, min(end_i, len(m1))):
            if dates[j] != signal_date:
                break
            if side == 1:
                if float(op[j]) <= threshold or float(lo[j]) <= threshold:
                    fill_i = j
                    break
            else:
                if float(op[j]) >= threshold or float(hi[j]) >= threshold:
                    fill_i = j
                    break
        if fill_i is None:
            continue

        entry = level  # no favorable improvement credited
        stop = level - stop_buffer_ticks * tick if side == 1 else level + stop_buffer_ticks * tick
        risk = stop_buffer_ticks * tick
        target = level + side * target_rr * risk

        force_time = pd.Timestamp(signal_date) + pd.Timedelta(hours=17)
        fi = lookup.get(int(force_time.value))
        if fi is not None and fi >= fill_i and dates[fi] == signal_date:
            last_intrabar = fi - 1
            force_index = fi
            force_price = float(op[fi])
            force_reason = "FORCE_1700_OPEN"
        else:
            last_intrabar = int(np.searchsorted(times_ns, int(force_time.value), side="left") - 1)
            if last_intrabar < fill_i or dates[last_intrabar] != signal_date:
                continue
            force_index = last_intrabar
            force_price = float(cl[last_intrabar])
            force_reason = "FORCE_LAST_CLOSE"

        xi = force_index
        raw_exit = force_price
        reason = force_reason
        for j in range(fill_i, last_intrabar + 1):
            o, h, l = float(op[j]), float(hi[j]), float(lo[j])
            # If the first fill-eligible bar opens beyond the protective stop,
            # conservatively book the gap from level to that open.
            if side == 1:
                if o <= stop:
                    xi, raw_exit, reason = j, o, "STOP_GAP_ON_FILL" if j == fill_i else "STOP_GAP"
                    break
                if o >= target:
                    xi, raw_exit, reason = j, o, "TARGET_GAP"
                    break
                if l <= stop:  # STOP_FIRST
                    xi, raw_exit, reason = j, stop, "STOP"
                    break
                if h >= target:
                    xi, raw_exit, reason = j, target, "TARGET"
                    break
            else:
                if o >= stop:
                    xi, raw_exit, reason = j, o, "STOP_GAP_ON_FILL" if j == fill_i else "STOP_GAP"
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
        adjusted_exit = raw_exit - side * exit_slip_ticks * tick
        pnl = side * (adjusted_exit - entry)
        bps = 10000.0 * pnl / entry
        out.append({
            "instrument": inst,
            "date": str(dates[fill_i]),
            "month": str(pd.Timestamp(dates[fill_i]).to_period("M")),
            "side": side,
            "signal_time": str(st),
            "order_time": str(order_time),
            "fill_time": str(m1.time.iloc[fill_i]),
            "exit_time": str(m1.time.iloc[xi]),
            "level": level,
            "entry": entry,
            "stop": stop,
            "target": target,
            "stop_buffer_ticks": stop_buffer_ticks,
            "target_rr": target_rr,
            "mode": mode,
            "fill_through_ticks": fill_through,
            "exit_slip_ticks": exit_slip_ticks,
            "raw_exit": raw_exit,
            "bps": float(bps),
            "reason": reason,
        })
    return out


def train_execution(m5, m1, signals, inst):
    train_signals = signal_subset(signals, TRAIN_START, TRAIN_END)
    eligible = []
    all_rows = []
    for buffer_ticks, rr in EXEC_GRID:
        gross_t = execute_passive(m5, m1, train_signals, inst, buffer_ticks, rr, "GROSS")
        base_t = execute_passive(m5, m1, train_signals, inst, buffer_ticks, rr, "BASE")
        stress_t = execute_passive(m5, m1, train_signals, inst, buffer_ticks, rr, "STRESS")
        g, b, s = v3.metrics(gross_t), v3.metrics(base_t), v3.metrics(stress_t)
        ok = (
            b["trades"] >= 12
            and b["pf"] > 1.0 and s["pf"] > 1.0
            and b["expectancy_bps"] is not None and b["expectancy_bps"] > 0
            and s["expectancy_bps"] is not None and s["expectancy_bps"] > 0
        )
        min_pf = min(b["pf"], s["pf"])
        row = {
            "stop_buffer_ticks": buffer_ticks,
            "target_rr": rr,
            "gross": g,
            "base": b,
            "stress": s,
            "eligible": bool(ok),
            "selection_primary": float(min_pf),
            "selection_secondary": float(s["expectancy_bps"]) if s["expectancy_bps"] is not None else -1e9,
        }
        all_rows.append(row)
        if ok:
            eligible.append(row)
    eligible.sort(key=lambda x: (x["selection_primary"], x["selection_secondary"]), reverse=True)
    return (eligible[0] if eligible else None), all_rows


def eval_folds(m5, m1, signals, inst, buffer_ticks, rr):
    fold_rows = []
    all_base, all_stress, all_gross = [], [], []
    for fold_id, start, end in FOLDS:
        fs = signal_subset(signals, start, end)
        gt = execute_passive(m5, m1, fs, inst, buffer_ticks, rr, "GROSS")
        bt = execute_passive(m5, m1, fs, inst, buffer_ticks, rr, "BASE")
        st = execute_passive(m5, m1, fs, inst, buffer_ticks, rr, "STRESS")
        gm, bm, sm = v3.metrics(gt), v3.metrics(bt), v3.metrics(st)
        fold_rows.append({"fold_id": fold_id, "gross": gm, "base": bm, "stress": sm})
        all_gross += gt
        all_base += bt
        all_stress += st
    g, b, s = v3.metrics(all_gross), v3.metrics(all_base), v3.metrics(all_stress)
    b["positive_folds"] = sum(x["base"]["expectancy_bps"] is not None and x["base"]["expectancy_bps"] > 0 for x in fold_rows)
    s["positive_folds"] = sum(x["stress"]["expectancy_bps"] is not None and x["stress"]["expectancy_bps"] > 0 for x in fold_rows)
    return {"gross": g, "base": b, "stress": s, "folds": fold_rows, "base_trades": all_base, "stress_trades": all_stress}


def execution_neighbors(buffer_ticks: int, rr: float):
    out = []
    bi = STOP_BUFFERS.index(buffer_ticks)
    ri = TARGET_RRS.index(rr)
    for j in (bi - 1, bi + 1):
        if 0 <= j < len(STOP_BUFFERS):
            out.append((STOP_BUFFERS[j], rr))
    for j in (ri - 1, ri + 1):
        if 0 <= j < len(TARGET_RRS):
            out.append((buffer_ticks, TARGET_RRS[j]))
    return out


def forward_gate(ev, stable_neighbors):
    b, s = ev["base"], ev["stress"]
    fail = []
    if b["pf"] < GATES["base_pf_min"]: fail.append("BASE_PF")
    if s["pf"] < GATES["stress_pf_min"]: fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"] <= 0: fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"] <= 0: fail.append("STRESS_EXPECTANCY")
    if b["trades"] < GATES["minimum_base_trades"]: fail.append("TRADES")
    if b["unique_days"] < GATES["minimum_unique_days"]: fail.append("UNIQUE_DAYS")
    if b.get("positive_folds", 0) < GATES["minimum_positive_base_folds"]: fail.append("BASE_FOLDS")
    if s.get("positive_folds", 0) < GATES["minimum_positive_stress_folds"]: fail.append("STRESS_FOLDS")
    if b["largest_winner_share"] is None or b["largest_winner_share"] > GATES["largest_winner_share_max"]: fail.append("CONCENTRATION")
    if stable_neighbors < GATES["minimum_stable_execution_neighbors"]: fail.append("EXECUTION_PLATEAU")
    return not fail, fail


def run_inst(root: Path, inst: str):
    m5, p5 = v3.load_prefix(root, inst, "M5")
    m1, p1 = v3.load_prefix(root, inst, "M1")
    if m5.time.max() >= DISC_END or m1.time.max() >= DISC_END:
        raise PermissionError("Cycle 8 data fence violation")

    variants = []
    for variant in v7.VARIANTS:
        signals = v7.generate_signals(m5, inst, variant, v3)
        selected, training_grid = train_execution(m5, m1, signals, inst)
        row = {"variant": variant, "signals": len(signals), "training_grid": training_grid, "selected_execution": selected}
        if selected is None:
            row.update({"status": "NO_TRAIN_ELIGIBLE_EXECUTION", "gate_pass": False, "gate_failures": ["TRAIN_SELECTION"]})
            variants.append(row)
            continue
        bfr = int(selected["stop_buffer_ticks"]); rr = float(selected["target_rr"])
        ev = eval_folds(m5, m1, signals, inst, bfr, rr)
        neighbor_rows = []
        stable = 0
        for nb, nr in execution_neighbors(bfr, rr):
            nev = eval_folds(m5, m1, signals, inst, nb, nr)
            nbase, nstress = nev["base"], nev["stress"]
            is_stable = (
                nbase["pf"] >= 1.25 and nstress["pf"] >= 1.0
                and nbase["expectancy_bps"] is not None and nbase["expectancy_bps"] > 0
                and nstress["expectancy_bps"] is not None and nstress["expectancy_bps"] > 0
            )
            stable += int(is_stable)
            neighbor_rows.append({"stop_buffer_ticks": nb, "target_rr": nr, "base": nbase, "stress": nstress, "stable": bool(is_stable)})
        passed, failures = forward_gate(ev, stable)
        row.update({
            "status": "FORWARD_RESEARCH_PASS" if passed else "FORWARD_RESEARCH_FAIL",
            "validation": {k: v for k, v in ev.items() if k not in ("base_trades", "stress_trades")},
            "execution_neighbors": neighbor_rows,
            "stable_execution_neighbors": stable,
            "gate_pass": passed,
            "gate_failures": failures,
            "base_trades": ev["base_trades"],
            "stress_trades": ev["stress_trades"],
        })
        variants.append(row)

    def rank(x):
        if not x.get("selected_execution") or "validation" not in x: return -1e9
        b, s = x["validation"]["base"], x["validation"]["stress"]
        if b["expectancy_bps"] is None or s["expectancy_bps"] is None: return -1e9
        return math.log(max(min(b["pf"], 10), 1e-9)) + 0.65 * math.log(max(min(s["pf"], 10), 1e-9)) + 0.03*b["expectancy_bps"] + 0.02*s["expectancy_bps"] + 0.12*x["stable_execution_neighbors"]

    for x in variants: x["rank_score"] = rank(x)
    variants.sort(key=lambda x: (x.get("gate_pass", False), x["rank_score"]), reverse=True)
    survivors = [x for x in variants if x.get("gate_pass")]
    return {"instrument": inst, "variants": variants, "survivors": len(survivors), "provenance": p5+p1}


def compact_variant(x):
    return {k:v for k,v in x.items() if k not in ("base_trades","stress_trades")}


def run(root: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    results = [run_inst(root, "CNYRUBF"), run_inst(root, "USDRUBF")]
    status = "RESEARCH_ONLY_AWAITING_NEW_CONFIRMATION_DATA" if any(r["survivors"] for r in results) else "NO_RESEARCH_SURVIVOR"
    compact = []
    for r in results:
        cr = {"instrument": r["instrument"], "survivors": r["survivors"], "provenance": r["provenance"], "variants": [compact_variant(x) for x in r["variants"]]}
        compact.append(cr)
        if r["variants"] and "base_trades" in r["variants"][0]:
            best = r["variants"][0]
            (out/f"best_{r['instrument']}_base_trades.json").write_text(json.dumps(best["base_trades"], indent=2, default=v3.jsonable)+"\n")
            (out/f"best_{r['instrument']}_stress_trades.json").write_text(json.dumps(best["stress_trades"], indent=2, default=v3.jsonable)+"\n")
    manifest = {
        "engine": "cycle8-passive-retest-v1",
        "status": status,
        "data_end_exclusive": str(DISC_END),
        "retired_internal_confirmation_accessed": False,
        "true_oos_2025_accessed": False,
        "commission_excluded": True,
        "stop_buffers": STOP_BUFFERS,
        "target_rrs": TARGET_RRS,
        "gates": GATES,
        "results": compact,
    }
    (out/"result.json").write_text(json.dumps(manifest, indent=2, default=v3.jsonable)+"\n")
    lines = ["# Cycle 8 — Equal-Level Passive Retest", "", f"Status: **{status}**", ""]
    for r in results:
        lines += [f"## {r['instrument']}", f"Survivors: {r['survivors']} / {len(r['variants'])}"]
        for x in r["variants"]:
            if "validation" not in x:
                lines.append(f"- {x['variant']} | no Jan-Feb eligible execution")
                continue
            sel=x["selected_execution"]; b=x["validation"]["base"]; s=x["validation"]["stress"]
            lines.append(f"- {x['variant']} -> stop={sel['stop_buffer_ticks']}t RR={sel['target_rr']} | BASE PF={b['pf']:.3f} exp={b['expectancy_bps']} N={b['trades']} folds={b.get('positive_folds')} | STRESS PF={s['pf']:.3f} exp={s['expectancy_bps']} N={s['trades']} folds={s.get('positive_folds')} | neighbors={x['stable_execution_neighbors']} gate={x['gate_pass']} fail={x['gate_failures']}")
        lines.append("")
    lines += ["March-May is retrospective robustness data, not untouched OOS.", "Retired May16-Jul1 data and 2025 TRUE OOS were not read."]
    (out/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(manifest, indent=2, default=v3.jsonable))


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--data-root",type=Path,default=Path(".")); ap.add_argument("--output",type=Path,required=True); a=ap.parse_args(); run(a.data_root,a.output)
