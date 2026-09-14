from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp("2026-01-05")
DISC_END = pd.Timestamp("2026-03-01")
FORWARD_END = pd.Timestamp("2026-05-16")

STRUCTURE = "ROLL30"
EVENT = "REJECTION"
ANCHOR_MODES = ("EVENT_EXTREME", "LEVEL")
SESSION_WINDOWS = ("MORNING_09_12", "EXTENDED_09_15", "FULL_09_1630")
STOP_POINTS = {
    "CNYRUBF": (6, 8, 10),
    "USDRUBF": (9, 12, 15),
}
TARGET_RS = (3.0, 4.0, 5.0)
SHORTLIST_CAP = 30
BUCKET_CAP = 3


def mod(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


c27 = mod("research/cycle27_fixed_stop_structural_event.py", "c27_for_c36")
c24 = c27.c24
v3 = c27.v3


def jsonable(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period, date, datetime)):
        return str(v)
    return c27.jsonable(v)


def session_mask(f: pd.DataFrame, name: str) -> np.ndarray:
    mins = (f.time.dt.hour * 60 + f.time.dt.minute).to_numpy()
    if name == "MORNING_09_12":
        return (mins >= 9 * 60) & (mins < 12 * 60)
    if name == "EXTENDED_09_15":
        return (mins >= 9 * 60) & (mins < 15 * 60)
    if name == "FULL_09_1630":
        return (mins >= 9 * 60) & (mins <= 16 * 60 + 30)
    raise ValueError(name)


def adjacent(values, current):
    vals = list(values)
    i = vals.index(current)
    out = []
    if i > 0:
        out.append(vals[i - 1])
    if i + 1 < len(vals):
        out.append(vals[i + 1])
    return out


def rank_key(c):
    d = c["discovery"]
    jan = d["january_stress"]["expectancy_r"]
    feb = d["february_stress"]["expectancy_r"]
    jan = -1e9 if jan is None else float(jan)
    feb = -1e9 if feb is None else float(feb)
    ds = d["discovery_stress"]
    db = d["discovery_base"]
    er = ds["expectancy_r"]
    er = -1e9 if er is None else float(er)
    return (
        -min(jan, feb),
        -float(ds["pf"]),
        -float(db["pf"]),
        -er,
        -int(ds["days"]),
        c["candidate_id"],
    )


def execute(f, m1, cache, trade_cache, inst, sig, side, sp, tr, friction, window_mask):
    ix = np.flatnonzero(sig & window_mask)
    return c27.execute_indices(
        f, m1, cache, trade_cache, inst, ix, side, int(sp), float(tr), int(friction)
    )


def strict_forward_eval(gross, base, stress):
    _, fw = c27.forward_eval(gross, base, stress)
    mg = fw["gross"]
    mb = fw["base"]
    ms = fw["stress"]
    ratio = ms["n"] / mb["n"] if mb["n"] else 0.0
    ok = (
        mb["pf"] >= 2.0
        and ms["pf"] >= 1.5
        and mb["expectancy_r"] is not None
        and mb["expectancy_r"] >= 0.30
        and ms["expectancy_r"] is not None
        and ms["expectancy_r"] >= 0.10
        and fw["bootstrap_p10_base_r"] is not None
        and fw["bootstrap_p10_base_r"] > 0
        and mb["n"] >= 30
        and mb["days"] >= 15
        and ms["n"] >= 20
        and ratio >= 0.50
        and fw["all_base_blocks_positive"]
        and fw["all_stress_blocks_positive"]
        and mb["largest_winner_share"] is not None
        and mb["largest_winner_share"] <= 0.25
        and mg["total_bps"] + 1e-9 >= mb["total_bps"] >= ms["total_bps"] - 1e-9
    )
    fw = dict(fw)
    fw["stress_base_trade_ratio"] = float(ratio)
    return bool(ok), fw


def positive_stress(metrics: dict) -> bool:
    return bool(
        metrics["n"] >= 10
        and metrics["expectancy_r"] is not None
        and metrics["expectancy_r"] > 0
    )


def session_support(
    f, m1, cache, trade_cache, inst, base_event, anchor, entries, side,
    anchor_mode, session_name, sp, tr, tick, fw_mask,
):
    rows = []
    valid = base_event & c27.stop_valid(entries, anchor, tick, int(sp), side)
    for alt in adjacent(SESSION_WINDOWS, session_name):
        sig = valid & session_mask(f, alt)
        b = execute(f, m1, cache, trade_cache, inst, sig, side, sp, tr, 1, fw_mask)
        s = execute(f, m1, cache, trade_cache, inst, sig, side, sp, tr, 2, fw_mask)
        mb = c24.metrics(b)
        ms = c24.metrics(s)
        rows.append({
            "session_window": alt,
            "anchor_mode": anchor_mode,
            "stop_points": int(sp),
            "target_r": float(tr),
            "base": mb,
            "stress": ms,
            "positive_stress_support": positive_stress(ms),
        })
    return rows


def execution_support(
    f, m1, cache, trade_cache, inst, base_event, anchor, entries, side,
    anchor_mode, session_name, sp, tr, tick, fw_mask,
):
    rows = []
    smask = session_mask(f, session_name)

    for nsp in adjacent(STOP_POINTS[inst], sp):
        sig = base_event & c27.stop_valid(entries, anchor, tick, int(nsp), side) & smask
        b = execute(f, m1, cache, trade_cache, inst, sig, side, nsp, tr, 1, fw_mask)
        s = execute(f, m1, cache, trade_cache, inst, sig, side, nsp, tr, 2, fw_mask)
        mb = c24.metrics(b)
        ms = c24.metrics(s)
        rows.append({
            "axis": "stop",
            "session_window": session_name,
            "anchor_mode": anchor_mode,
            "stop_points": int(nsp),
            "target_r": float(tr),
            "base": mb,
            "stress": ms,
            "positive_stress_support": positive_stress(ms),
        })

    for ntr in adjacent(TARGET_RS, tr):
        sig = base_event & c27.stop_valid(entries, anchor, tick, int(sp), side) & smask
        b = execute(f, m1, cache, trade_cache, inst, sig, side, sp, ntr, 1, fw_mask)
        s = execute(f, m1, cache, trade_cache, inst, sig, side, sp, ntr, 2, fw_mask)
        mb = c24.metrics(b)
        ms = c24.metrics(s)
        rows.append({
            "axis": "target",
            "session_window": session_name,
            "anchor_mode": anchor_mode,
            "stop_points": int(sp),
            "target_r": float(ntr),
            "base": mb,
            "stress": ms,
            "positive_stress_support": positive_stress(ms),
        })

    return rows


def run(root: Path, inst: str, outdir: Path):
    f, m1, provenance = c24.load_context(root, inst)
    entries, _, _, cache = c24.structural_arrays(f, m1, inst)
    levels = c27.build_levels(f, inst)
    tick = float(v3.SPECS[inst]["tick"])
    disc_mask = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    fw_mask = ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy()

    generated = 0
    seen = {}
    candidates = []
    trade_cache = {}

    for side_name, side in (("SHORT", -1), ("LONG", 1)):
        for anchor_mode in ANCHOR_MODES:
            base_event, anchor = c27.event_and_anchor(
                f, inst, STRUCTURE, EVENT, side, anchor_mode, levels
            )
            if not base_event.any():
                continue

            for session_name in SESSION_WINDOWS:
                smask = session_mask(f, session_name)

                for sp in STOP_POINTS[inst]:
                    sig0 = base_event & c27.stop_valid(entries, anchor, tick, int(sp), side) & smask
                    if sig0[disc_mask].sum() < 5:
                        continue

                    for tr in TARGET_RS:
                        generated += 1
                        digest = hashlib.sha256(
                            np.packbits(sig0[disc_mask].astype(np.uint8)).tobytes()
                        ).hexdigest()
                        key = (
                            side_name, anchor_mode, session_name, digest,
                            int(sp), float(tr),
                        )
                        cid = (
                            f"{inst}|{side_name}|REJECTION|ROLL30|{anchor_mode}|"
                            f"{session_name}|SL{sp}|TP{tr:g}R|NONE"
                        )
                        if key in seen:
                            continue
                        seen[key] = cid

                        gross = execute(
                            f, m1, cache, trade_cache, inst, sig0, side, sp, tr, 0, disc_mask
                        )
                        base = execute(
                            f, m1, cache, trade_cache, inst, sig0, side, sp, tr, 1, disc_mask
                        )
                        stress = execute(
                            f, m1, cache, trade_cache, inst, sig0, side, sp, tr, 2, disc_mask
                        )
                        passed, diag = c27.discovery_pass(gross, base, stress)
                        if passed:
                            candidates.append({
                                "candidate_id": cid,
                                "direction": side_name,
                                "side": int(side),
                                "event": EVENT,
                                "structure": STRUCTURE,
                                "anchor_mode": anchor_mode,
                                "session_window": session_name,
                                "stop_points": int(sp),
                                "target_r": float(tr),
                                "context": "NONE",
                                "discovery_mask_digest": digest,
                                "discovery": diag,
                                "signal_mask": sig0,
                                "base_event": base_event,
                                "anchor": anchor,
                            })

    candidates.sort(key=rank_key)

    shortlisted = []
    bucket_count = {}
    for c in candidates:
        bucket = (c["direction"], c["session_window"], c["anchor_mode"])
        if bucket_count.get(bucket, 0) >= BUCKET_CAP:
            continue
        bucket_count[bucket] = bucket_count.get(bucket, 0) + 1
        shortlisted.append(c)
        if len(shortlisted) >= SHORTLIST_CAP:
            break

    results = []
    survivors = []

    for c in shortlisted:
        sig = c.pop("signal_mask")
        base_event = c.pop("base_event")
        anchor = c.pop("anchor")
        side = int(c["side"])
        sp = int(c["stop_points"])
        tr = float(c["target_r"])
        session_name = c["session_window"]
        anchor_mode = c["anchor_mode"]

        gross = execute(f, m1, cache, trade_cache, inst, sig, side, sp, tr, 0, fw_mask)
        base = execute(f, m1, cache, trade_cache, inst, sig, side, sp, tr, 1, fw_mask)
        stress = execute(f, m1, cache, trade_cache, inst, sig, side, sp, tr, 2, fw_mask)

        strict_ok, fw = strict_forward_eval(gross, base, stress)

        sw = session_support(
            f, m1, cache, trade_cache, inst, base_event, anchor, entries, side,
            anchor_mode, session_name, sp, tr, tick, fw_mask,
        )
        ew = execution_support(
            f, m1, cache, trade_cache, inst, base_event, anchor, entries, side,
            anchor_mode, session_name, sp, tr, tick, fw_mask,
        )
        session_positive = sum(1 for x in sw if x["positive_stress_support"])
        execution_positive = sum(1 for x in ew if x["positive_stress_support"])
        robustness_ok = bool(session_positive >= 1 and execution_positive >= 1)
        final_ok = bool(strict_ok and robustness_ok)

        row = dict(c)
        row["forward"] = fw
        row["session_support"] = sw
        row["execution_support"] = ew
        row["positive_session_neighbors"] = int(session_positive)
        row["positive_execution_neighbors"] = int(execution_positive)
        row["strict_forward_gate_pass"] = bool(strict_ok)
        row["generalization_gate_pass"] = bool(robustness_ok)
        row["survivor"] = bool(final_ok)
        results.append(row)
        if final_ok:
            survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    status = (
        "ROLL30_REJECTION_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION"
        if survivors
        else "NO_ROLL30_REJECTION_RESEARCH_SURVIVOR"
    )

    manifest = {
        "engine": "cycle36-roll30-rejection-generalization-v1",
        "instrument": inst,
        "status": status,
        "primary_hypothesis_instrument": "USDRUBF",
        "replication_control_instrument": "CNYRUBF",
        "structure": STRUCTURE,
        "event": EVENT,
        "anchor_modes": ANCHOR_MODES,
        "session_windows": SESSION_WINDOWS,
        "stop_points": STOP_POINTS[inst],
        "target_rs": TARGET_RS,
        "context": "NONE",
        "generated_candidate_evaluations": generated,
        "deduped_discovery_candidates": len(seen),
        "discovery_passes": len(candidates),
        "shortlisted": len(shortlisted),
        "survivors": len(survivors),
        "research_forward_is_not_untouched_confirmation": True,
        "retired_internal_confirmation_accessed": False,
        "true_oos_2025_accessed": False,
        "commission_excluded": True,
        "provenance": provenance,
    }

    (outdir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=jsonable) + "\n", encoding="utf-8"
    )
    (outdir / "shortlist.json").write_text(
        json.dumps(results, indent=2, default=jsonable) + "\n", encoding="utf-8"
    )
    (outdir / "survivors.json").write_text(
        json.dumps(survivors, indent=2, default=jsonable) + "\n", encoding="utf-8"
    )

    report = [
        f"# Cycle 36 — {inst} ROLL30 Rejection Generalization",
        "",
        f"Status: **{status}**",
        f"Generated={generated}; deduped={len(seen)}; discovery passes={len(candidates)}; shortlist={len(shortlisted)}; survivors={len(survivors)}",
        "",
        "Mar-May15 is research-only and is not untouched confirmation.",
        "Retired May16-Jul1 and TRUE OOS 2025 were not accessed.",
        "",
        "## Top forward candidates",
    ]
    for r in results[:15]:
        b = r["forward"]["base"]
        s = r["forward"]["stress"]
        report.append(
            f"- `{r['candidate_id']}` — survivor={r['survivor']}; "
            f"BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}, N={b['n']}; "
            f"STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}, N={s['n']}; "
            f"P10={r['forward']['bootstrap_p10_base_r']}; "
            f"session_neighbors+={r['positive_session_neighbors']}; "
            f"execution_neighbors+={r['positive_execution_neighbors']}"
        )

    (outdir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, default=jsonable), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=Path("."))
    p.add_argument("--instrument", choices=("CNYRUBF", "USDRUBF"), required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run(args.data_root, args.instrument, args.output)
