from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

BOOTSTRAP_SEED = 20260401
BOOTSTRAP_REPS = 1000


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


v3 = mod("research/autonomous_search_v3.py", "v3")


def layer_metrics(trades):
    m = v3.metrics(trades)
    r = np.asarray([float(t["realized_r"]) for t in trades], float) if trades else np.array([], float)
    m["mean_realized_r"] = float(r.mean()) if len(r) else None
    m["target_r_levels"] = sorted({float(t["target_r"]) for t in trades})
    return m


def bootstrap_q10(trades):
    if not trades:
        return None
    dates = np.asarray([t["date"] for t in trades], dtype=object)
    vals = np.asarray([float(t["realized_r"]) for t in trades], float)
    ud = np.asarray(sorted(set(dates)), dtype=object)
    if len(ud) < 2:
        return None
    by = {d: vals[dates == d] for d in ud}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_REPS, float)
    for i in range(BOOTSTRAP_REPS):
        sample = rng.choice(ud, size=len(ud), replace=True)
        means[i] = np.concatenate([by[d] for d in sample]).mean()
    return float(np.quantile(means, 0.10))


def positive_months(trades):
    months = sorted({t["date"][:7] for t in trades})
    rows = {}
    n = 0
    for mo in months:
        z = [t for t in trades if t["date"].startswith(mo)]
        m = layer_metrics(z)
        rows[mo] = m
        if m["total_bps"] > 0:
            n += 1
    return n, rows


def instrument_gate(base, stress, q10, base_pos, stress_pos):
    fail = []
    if stress["pf"] < 1.50: fail.append("STRESS_PF")
    if stress["mean_realized_r"] is None or stress["mean_realized_r"] < 0.15: fail.append("STRESS_MEAN_R")
    if base["pf"] < 2.00: fail.append("BASE_PF")
    if base["mean_realized_r"] is None or base["mean_realized_r"] < 0.30: fail.append("BASE_MEAN_R")
    if q10 is None or q10 <= 0: fail.append("BOOTSTRAP_STRESS_P10")
    if base["trades"] < 20: fail.append("TRADES")
    if base["unique_days"] < 12: fail.append("UNIQUE_DAYS")
    if stress_pos < 2: fail.append("STRESS_MONTHS")
    if base_pos < 2: fail.append("BASE_MONTHS")
    if stress["largest_winner_share"] is None or stress["largest_winner_share"] > 0.30: fail.append("STRESS_CONCENTRATION")
    if len(stress["target_r_levels"]) < 2: fail.append("TARGET_DIVERSITY")
    return not fail, fail


def run(root: Path, out: Path):
    fs = sorted(root.rglob("block_result.json"))
    if len(fs) != 11:
        raise RuntimeError(f"expected 11 blocks, got {len(fs)}")
    blocks = sorted([json.loads(p.read_text()) for p in fs], key=lambda x: x["block_index"])
    if [b["block_index"] for b in blocks] != list(range(11)):
        raise RuntimeError("block index mismatch")
    agg = {k: {"g": [], "b": [], "s": []} for k in ("CNYRUBF", "USDRUBF")}
    block_summary = []
    for bl in blocks:
        if bl.get("retired_internal_confirmation_accessed") or bl.get("true_oos_2025_accessed"):
            raise PermissionError("data fence violation")
        block_summary.append({
            "block_index": bl["block_index"], "start": bl["block_start"], "end_exclusive": bl["block_end_exclusive"],
            "enabled_models": sum(1 for d in bl["model_diagnostics"] if d.get("qualified_configs", 0) > 0),
            "prediction_summary": bl["prediction_summary"],
        })
        for row in bl["instruments"]:
            k = row["instrument"]
            agg[k]["g"] += row["gross_trades"]
            agg[k]["b"] += row["base_trades"]
            agg[k]["s"] += row["stress_trades"]

    instruments = []
    any_pass = False
    all_g, all_b, all_s = [], [], []
    for inst, z in agg.items():
        gm, bm, sm = layer_metrics(z["g"]), layer_metrics(z["b"]), layer_metrics(z["s"])
        q10 = bootstrap_q10(z["s"])
        bp, bmonths = positive_months(z["b"])
        sp, smonths = positive_months(z["s"])
        passed, fail = instrument_gate(bm, sm, q10, bp, sp)
        any_pass = any_pass or passed
        instruments.append({
            "instrument": inst, "gate_pass": passed, "gate_failures": fail,
            "gross": gm, "base": bm, "stress": sm, "bootstrap_p10_stress_mean_r": q10,
            "positive_base_months": bp, "positive_stress_months": sp,
            "base_months": bmonths, "stress_months": smonths,
        })
        all_g += z["g"]; all_b += z["b"]; all_s += z["s"]

    cg, cb, cs = layer_metrics(all_g), layer_metrics(all_b), layer_metrics(all_s)
    result = {
        "engine": "cycle22-stress-first-cost-margin-v1",
        "status": "STRESS_HIGH_R_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if any_pass else "NO_STRESS_HIGH_R_RESEARCH_SURVIVOR",
        "block_count": 11, "data_start": "2026-03-02", "data_end_exclusive": "2026-05-16",
        "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False, "commission_excluded": True,
        "instruments": instruments, "combined": {"gross": cg, "base": cb, "stress": cs}, "blocks": block_summary,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2, default=v3.jsonable) + "\n")
    (out / "base_trades.json").write_text(json.dumps(all_b, indent=2, default=v3.jsonable) + "\n")
    (out / "stress_trades.json").write_text(json.dumps(all_s, indent=2, default=v3.jsonable) + "\n")
    lines = ["# Cycle 22 — Stress-First High-R Cost-Margin", "", f"Status: **{result['status']}**", ""]
    for r in instruments:
        lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f}, meanR={r['base']['mean_realized_r']}, N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f}, meanR={r['stress']['mean_realized_r']}; bootP10={r['bootstrap_p10_stress_mean_r']}; gate={r['gate_pass']} fail={r['gate_failures']}")
    lines += ["", f"Combined BASE PF={cb['pf']:.3f}, meanR={cb['mean_realized_r']}; STRESS PF={cs['pf']:.3f}, meanR={cs['mean_realized_r']}", "", "Research-only. Retired May16-Jul1 and 2025 were not read."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--block-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.block_root, a.output)
