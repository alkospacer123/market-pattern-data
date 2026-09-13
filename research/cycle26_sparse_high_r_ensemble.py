from __future__ import annotations

import argparse
import importlib.util
import json
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp("2026-01-05")
JAN_END = pd.Timestamp("2026-02-01")
FEB_END = pd.Timestamp("2026-03-01")
FORWARD_END = pd.Timestamp("2026-05-16")
PROFILES = {
    "E1": (0.75, 4.0, 90),
    "E2": (0.75, 5.0, 120),
    "E3": (0.75, 6.0, 120),
    "E4": (1.00, 4.0, 120),
    "E5": (1.00, 5.0, 480),
}
BOOTSTRAP_SEED = 20260401
BOOTSTRAP_REPS = 1000


def jsonable(v):
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return c21.jsonable(v)


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c21 = mod("research/cycle21_direct_high_r_rules.py", "c21")
c18 = c21.c18
v3 = c21.v3
c21.PROFILES = PROFILES


def layer_stats(trades: list[dict]):
    if not trades:
        return {"n": 0, "pf": 0.0, "expectancy_bps": None, "expectancy_r": None, "days": 0,
                "largest_winner_share": None, "total_bps": 0.0, "target_hit_rate": None,
                "components": 0, "target_r_levels": []}
    b = np.asarray([float(t["bps"]) for t in trades], float)
    r = np.asarray([float(t["r"]) for t in trades], float)
    gp = float(b[b > 0].sum()); gl = float(-b[b < 0].sum())
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
    wins = b[b > 0]
    share = float(wins.max() / wins.sum()) if len(wins) else None
    return {
        "n": len(trades), "pf": float(pf), "expectancy_bps": float(b.mean()), "expectancy_r": float(r.mean()),
        "days": len({t["date"] for t in trades}), "largest_winner_share": share, "total_bps": float(b.sum()),
        "target_hit_rate": float(np.mean([bool(t["target_hit"]) for t in trades])),
        "components": len({t["component_id"] for t in trades}),
        "target_r_levels": sorted({float(t["target_r"]) for t in trades}),
    }


def atomic_january_stats(on: np.ndarray, cols: dict[str, np.ndarray], f: pd.DataFrame, layer: str):
    mask = on & ((f.time >= DISC_START) & (f.time < JAN_END)).to_numpy()
    return c21.stats_for(np.flatnonzero(mask), cols, f, layer)


def qualify_components(f: pd.DataFrame, rules: list[dict], outcomes: dict):
    components = []
    for ri, rule in enumerate(rules, 1):
        on = c21.onsets(f, rule["mask"])
        jan_on = on & ((f.time >= DISC_START) & (f.time < JAN_END)).to_numpy()
        jan_dates = sorted(set(f.date.iloc[np.flatnonzero(jan_on)].tolist()))
        if len(jan_dates) < 4:
            continue
        for pid, profile in PROFILES.items():
            target_r = float(profile[1])
            be = 1.0 / (target_r + 1.0) + 0.04
            for side_name in ("LONG", "SHORT"):
                cols = outcomes[(pid, side_name)]
                b = atomic_january_stats(on, cols, f, "base")
                s = atomic_january_stats(on, cols, f, "stress")
                good = (
                    b["n"] >= 6 and b["dates"] >= 4 and b["pf"] >= 2.0 and s["pf"] >= 1.5
                    and b["expectancy_r"] is not None and b["expectancy_r"] >= 0.35
                    and s["expectancy_r"] is not None and s["expectancy_r"] >= 0.15
                    and b["target_hit_rate"] is not None and b["target_hit_rate"] >= be
                    and b["largest_winner_share"] is not None and b["largest_winner_share"] <= 0.40
                )
                if not good:
                    continue
                cid = f"{rule['rule_id']}|{side_name}|{pid}"
                score = (float(s["expectancy_r"]), float(min(b["pf"], s["pf"])), int(b["dates"]))
                components.append({
                    "component_id": cid, "rule_id": rule["rule_id"], "mask_digest": rule["mask_digest"],
                    "side_name": side_name, "side": 1 if side_name == "LONG" else -1,
                    "profile": pid, "profile_tuple": profile, "january_base": b, "january_stress": s,
                    "score": score, "onset": on, "jan_onset": jan_on, "jan_dates": jan_dates,
                })
        if ri % 300 == 0:
            print("JAN_RULES", ri, "/", len(rules), "qualified", len(components), flush=True)
    components.sort(key=lambda x: (-x["score"][0], -x["score"][1], -x["score"][2], x["component_id"]))
    return components[:60]


def jaccard(a: np.ndarray, b: np.ndarray):
    union = int((a | b).sum())
    return float((a & b).sum() / union) if union else 0.0


def diversity_filter(components: list[dict]):
    kept = []
    covered = {"LONG": set(), "SHORT": set()}
    for c in components:
        if any(np.array_equal(c["jan_onset"], k["jan_onset"]) for k in kept):
            continue
        if any(jaccard(c["jan_onset"], k["jan_onset"]) > 0.50 for k in kept):
            continue
        new_dates = set(c["jan_dates"]) - covered[c["side_name"]]
        if kept and len(new_dates) < 3:
            continue
        c = dict(c)
        c["priority"] = len(kept)
        c["new_january_dates"] = len(new_dates)
        kept.append(c)
        covered[c["side_name"]].update(c["jan_dates"])
        if len(kept) >= 12:
            break
    return kept


def raw_events(f: pd.DataFrame, components: list[dict], start: pd.Timestamp, end: pd.Timestamp):
    by_bar: dict[int, list[dict]] = {}
    window = ((f.time >= start) & (f.time < end)).to_numpy()
    for c in components:
        ix = np.flatnonzero(c["onset"] & window)
        for i in ix:
            by_bar.setdefault(int(i), []).append(c)
    events = []
    for i in sorted(by_bar):
        fired = by_bar[i]
        sides = {c["side"] for c in fired}
        if len(sides) != 1:
            continue
        chosen = min(fired, key=lambda c: c["priority"])
        events.append((i, chosen))
    return events


def execute_ensemble(f: pd.DataFrame, m1: pd.DataFrame, inst: str, events: list[tuple[int, dict]]):
    gross, base, stress = [], [], []
    busy_until = None
    for i, c in events:
        available = pd.Timestamp(f.time.iloc[i]) + pd.Timedelta(minutes=5)
        if busy_until is not None and available <= busy_until:
            continue
        raw = c18.raw_trade(f, m1, int(i), inst, int(c["side"]), tuple(c["profile_tuple"]))
        if raw is None:
            continue
        busy_until = pd.Timestamp(raw["exit_time"])
        common = {
            "component_id": c["component_id"], "rule_id": c["rule_id"], "profile": c["profile"],
            "side": int(c["side"]), "target_r": float(c["profile_tuple"][1]),
            "date": str(pd.Timestamp(raw["entry_time"]).date()), "signal_time": str(f.time.iloc[i]),
            "entry_time": str(raw["entry_time"]), "exit_time": str(raw["exit_time"]),
            "target_hit": bool(raw["target_hit"]), "reason": raw["reason"],
        }
        for friction, bucket in ((0, gross), (1, base), (2, stress)):
            bps, rval = c18.frictionize(raw, inst, friction)
            bucket.append({**common, "friction_ticks_per_side": friction, "bps": float(bps), "r": float(rval)})
    return gross, base, stress


def february_gate(g, b, s):
    gm, bm, sm = layer_stats(g), layer_stats(b), layer_stats(s)
    monotone = gm["total_bps"] + 1e-9 >= bm["total_bps"] >= sm["total_bps"] - 1e-9
    fail = []
    if bm["n"] < 8: fail.append("TRADES")
    if bm["days"] < 5: fail.append("DAYS")
    if bm["components"] < 2: fail.append("COMPONENTS")
    if bm["pf"] < 1.5: fail.append("BASE_PF")
    if sm["pf"] < 1.2: fail.append("STRESS_PF")
    if bm["expectancy_r"] is None or bm["expectancy_r"] < 0.20: fail.append("BASE_R")
    if sm["expectancy_r"] is None or sm["expectancy_r"] <= 0: fail.append("STRESS_R")
    if bm["largest_winner_share"] is None or bm["largest_winner_share"] > 0.35: fail.append("CONCENTRATION")
    if not monotone: fail.append("FRICTION")
    return not fail, fail, {"gross": gm, "base": bm, "stress": sm, "friction_monotonicity": monotone}


def bootstrap_q10(trades):
    if not trades:
        return None
    dates = np.asarray([t["date"] for t in trades], dtype=object)
    vals = np.asarray([t["r"] for t in trades], float)
    ud = np.asarray(sorted(set(dates)), dtype=object)
    if len(ud) < 2:
        return None
    by = {d: vals[dates == d] for d in ud}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_REPS)
    for k in range(BOOTSTRAP_REPS):
        sample = rng.choice(ud, size=len(ud), replace=True)
        means[k] = np.concatenate([by[d] for d in sample]).mean()
    return float(np.quantile(means, 0.10))


def positive_months(trades):
    months = sorted({t["date"][:7] for t in trades})
    rows = {}; n = 0
    for mo in months:
        z = [t for t in trades if t["date"].startswith(mo)]
        m = layer_stats(z); rows[mo] = m
        if m["total_bps"] > 0: n += 1
    return n, rows


def forward_gate(g, b, s, feb_passed):
    gm, bm, sm = layer_stats(g), layer_stats(b), layer_stats(s)
    q10 = bootstrap_q10(b); bp, bmonths = positive_months(b); sp, smonths = positive_months(s)
    monotone = gm["total_bps"] + 1e-9 >= bm["total_bps"] >= sm["total_bps"] - 1e-9
    fail = []
    if not feb_passed: fail.append("FEBRUARY_GATE")
    if bm["pf"] < 2.0: fail.append("BASE_PF")
    if sm["pf"] < 1.5: fail.append("STRESS_PF")
    if bm["expectancy_r"] is None or bm["expectancy_r"] < 0.30: fail.append("BASE_R")
    if sm["expectancy_r"] is None or sm["expectancy_r"] < 0.10: fail.append("STRESS_R")
    if q10 is None or q10 <= 0: fail.append("BOOTSTRAP")
    if bm["n"] < 25: fail.append("TRADES")
    if bm["days"] < 15: fail.append("DAYS")
    if bp < 2: fail.append("BASE_MONTHS")
    if sp < 2: fail.append("STRESS_MONTHS")
    if bm["largest_winner_share"] is None or bm["largest_winner_share"] > 0.25: fail.append("CONCENTRATION")
    if bm["components"] < 3: fail.append("COMPONENT_DIVERSITY")
    if len(bm["target_r_levels"]) < 2: fail.append("TARGET_DIVERSITY")
    if not monotone: fail.append("FRICTION")
    return not fail, fail, {"gross": gm, "base": bm, "stress": sm, "bootstrap_p10_base_mean_r": q10,
                            "positive_base_months": bp, "positive_stress_months": sp,
                            "base_months": bmonths, "stress_months": smonths, "friction_monotonicity": monotone}


def component_contributions(trades):
    out = {}
    for cid in sorted({t["component_id"] for t in trades}):
        z = [t for t in trades if t["component_id"] == cid]
        out[cid] = layer_stats(z)
    return out


def run(root: Path, out: Path, inst: str):
    out.mkdir(parents=True, exist_ok=True)
    f, m1, numeric, provenance = c21.load_context(root, inst)
    states, cuts = c21.fit_state_masks(f, numeric)
    rules, inventory = c21.build_rules(f, states)
    outcomes = c21.make_outcomes(f, m1, inst)
    qualified = qualify_components(f, rules, outcomes)
    frozen = diversity_filter(qualified)
    print("COMPONENTS", inst, "qualified", len(qualified), "frozen", len(frozen), flush=True)

    feb_events = raw_events(f, frozen, JAN_END, FEB_END)
    fg, fb, fs = execute_ensemble(f, m1, inst, feb_events)
    feb_pass, feb_fail, feb = february_gate(fg, fb, fs)

    fw_events = raw_events(f, frozen, FEB_END, FORWARD_END)
    gg, gb, gs = execute_ensemble(f, m1, inst, fw_events)
    passed, fail, forward = forward_gate(gg, gb, gs, feb_pass)

    frozen_public = []
    for c in frozen:
        frozen_public.append({k: v for k, v in c.items() if k not in ("onset", "jan_onset", "score")})
    result = {
        "engine": "cycle26-sparse-high-r-ensemble-v1", "instrument": inst,
        "status": "SPARSE_HIGH_R_ENSEMBLE_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if passed else "NO_SPARSE_HIGH_R_ENSEMBLE_RESEARCH_SURVIVOR",
        "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False, "commission_excluded": True,
        "profiles": PROFILES, "rule_inventory": inventory, "january_qualified_top60": len(qualified),
        "frozen_component_count": len(frozen), "frozen_components": frozen_public,
        "february_gate_pass": feb_pass, "february_gate_failures": feb_fail, "february": feb,
        "forward_gate_pass": passed, "forward_gate_failures": fail, "forward": forward,
        "forward_component_contributions": component_contributions(gb), "january_cutpoints": cuts, "provenance": provenance,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2, default=jsonable) + "\n", encoding="utf-8")
    (out / "forward_base_trades.json").write_text(json.dumps(gb, indent=2, default=jsonable) + "\n", encoding="utf-8")
    report = [f"# Cycle 26 — {inst}", "", f"Status: **{result['status']}**",
              f"January qualified top60: {len(qualified)}", f"Frozen diverse components: {len(frozen)}",
              f"February gate: {feb_pass}; fail={feb_fail}",
              f"February BASE PF={feb['base']['pf']:.3f}, meanR={feb['base']['expectancy_r']}, N={feb['base']['n']}; STRESS PF={feb['stress']['pf']:.3f}, meanR={feb['stress']['expectancy_r']}",
              f"Forward BASE PF={forward['base']['pf']:.3f}, meanR={forward['base']['expectancy_r']}, N={forward['base']['n']}, days={forward['base']['days']}",
              f"Forward STRESS PF={forward['stress']['pf']:.3f}, meanR={forward['stress']['expectancy_r']}",
              f"Forward gate: {passed}; fail={fail}", "", "## Components"]
    for c in frozen_public:
        report.append(f"- P{c['priority']}: `{c['component_id']}` newJanDates={c['new_january_dates']} Jan BASE PF={c['january_base']['pf']:.3f} STRESS PF={c['january_stress']['pf']:.3f}")
    report += ["", "Research-only. Retired May16-Jul1 and 2025 were not read."]
    (out / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("STATUS", result["status"], "FEB", feb_pass, "FORWARD", passed, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=Path("."))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--instrument", choices=["CNYRUBF", "USDRUBF"], required=True)
    a = p.parse_args()
    run(a.data_root, a.output, a.instrument)
