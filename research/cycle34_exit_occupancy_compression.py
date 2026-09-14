from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp("2026-01-05")
DISC_END = pd.Timestamp("2026-03-01")
FORWARD_END = pd.Timestamp("2026-05-16")

STOP_POINTS = {"CNYRUBF": (8, 10), "USDRUBF": (9, 12)}
BUFFERS = (1, 2, 3)
TTLS = (15, 30)
TARGET_HOLD = {1.5: 60, 2.0: 90, 3.0: 120}
CONTEXT_NAME = "eff_60m:HIGH25"
ANCHOR_MODES = ("LEVEL", "EVENT_EXTREME")


def mod(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


c29 = mod("research/cycle29_structure_aligned_passive.py", "c29_for_c34")
c27 = c29.c27
c24 = c29.c24
v3 = c29.v3

# Cycle29 execution already defines the causal order mechanics. Cycle34 changes only
# the preregistered target -> max-hold map.
c29.HOLD_MINUTES.update(TARGET_HOLD)


def jsonable(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)):
        return str(v)
    return c29.jsonable(v)


def context_mask(f: pd.DataFrame):
    contexts, cuts = c29.allowed_contexts(f)
    mapping = {name: np.asarray(mask, bool) for name, mask in contexts}
    if CONTEXT_NAME not in mapping:
        raise RuntimeError(f"required context not found: {CONTEXT_NAME}")
    return mapping[CONTEXT_NAME], cuts


def passive_signal(f: pd.DataFrame, event_mask: np.ndarray, anchors: np.ndarray, side: int,
                   stop_points: int, buffer_ticks: int, tick: float, ctx: np.ndarray):
    limits = anchors + side * (stop_points - buffer_ticks) * tick
    close = f.close.to_numpy(float)
    passive = np.isfinite(limits) & ((close > limits) if side == 1 else (close < limits))
    return np.asarray(event_mask, bool) & passive & np.asarray(ctx, bool)


def execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, mode_ticks, window):
    ix = np.flatnonzero(np.asarray(sig, bool) & np.asarray(window, bool))
    return c29.execute_candidate(f, m1, cache, inst, ix, anchors, side, sp, buf, ttl, target_r, mode_ticks)


def rank_key(c):
    d = c["discovery"]
    jan_s = d["january_stress"]["expectancy_r"]
    feb_s = d["february_stress"]["expectancy_r"]
    jan_s = -1e9 if jan_s is None else float(jan_s)
    feb_s = -1e9 if feb_s is None else float(feb_s)
    ds = d["discovery_stress"]
    db = d["discovery_base"]
    ds_exp = ds["expectancy_r"]
    ds_exp = -1e9 if ds_exp is None else float(ds_exp)
    return (-min(jan_s, feb_s), -float(ds["pf"]), -float(db["pf"]), -ds_exp, -int(db["days"]), c["candidate_id"])


def adjacent(values, current):
    vals = list(values)
    i = vals.index(current)
    out = []
    if i > 0:
        out.append(vals[i - 1])
    if i + 1 < len(vals):
        out.append(vals[i + 1])
    return out


def exit_neighbor_support(f, m1, cache, inst, base_event, anchors, side, sp, buf, ttl,
                          target_r, tick, ctx, fw_mask):
    rows = []
    targets = tuple(TARGET_HOLD)
    for tr in adjacent(targets, target_r):
        sig = passive_signal(f, base_event, anchors, side, sp, buf, tick, ctx)
        b = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, tr, 1, fw_mask)
        s = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, tr, 2, fw_mask)
        mb, ms = c24.metrics(b), c24.metrics(s)
        positive = bool(ms["n"] >= 10 and ms["expectancy_r"] is not None and ms["expectancy_r"] > 0)
        rows.append({"target_r": tr, "hold_minutes": TARGET_HOLD[tr], "base": mb, "stress": ms,
                     "positive_stress_neighbor": positive})
    return rows


def execution_neighbor_support(f, m1, cache, inst, base_event, anchors, side, sp, buf, ttl,
                               target_r, tick, ctx, fw_mask):
    variants = set()
    for x in adjacent(STOP_POINTS[inst], sp):
        if buf < x:
            variants.add((x, buf, ttl, "stop"))
    for x in adjacent(BUFFERS, buf):
        if x < sp:
            variants.add((sp, x, ttl, "buffer"))
    for x in adjacent(TTLS, ttl):
        variants.add((sp, buf, x, "ttl"))

    rows = []
    for nsp, nbuf, nttl, axis in sorted(variants):
        sig = passive_signal(f, base_event, anchors, side, nsp, nbuf, tick, ctx)
        b = execute(f, m1, cache, inst, sig, anchors, side, nsp, nbuf, nttl, target_r, 1, fw_mask)
        s = execute(f, m1, cache, inst, sig, anchors, side, nsp, nbuf, nttl, target_r, 2, fw_mask)
        mb, ms = c24.metrics(b), c24.metrics(s)
        positive = bool(ms["n"] >= 10 and ms["expectancy_r"] is not None and ms["expectancy_r"] > 0)
        rows.append({"axis": axis, "stop_points": nsp, "buffer": nbuf, "ttl": nttl,
                     "target_r": target_r, "hold_minutes": TARGET_HOLD[target_r],
                     "base": mb, "stress": ms, "positive_stress_neighbor": positive})
    return rows


def run(root: Path, inst: str, outdir: Path):
    f, m1, provenance = c24.load_context(root, inst)
    _, _, _, cache = c24.structural_arrays(f, m1, inst)
    levels = c27.build_levels(f, inst)
    ctx, cuts = context_mask(f)
    tick = float(v3.SPECS[inst]["tick"])
    disc_mask = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    fw_mask = ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy()

    generated = 0
    seen = {}
    candidates = []

    for side_name, side in (("SHORT", -1), ("LONG", 1)):
        for anchor_mode in ANCHOR_MODES:
            event_mask, anchors = c27.event_and_anchor(f, inst, "ROUND", "REJECTION", side, anchor_mode, levels)
            event_mask = np.asarray(event_mask, bool)
            anchors = np.asarray(anchors, float)
            if not event_mask.any():
                continue

            for sp in STOP_POINTS[inst]:
                for buf in BUFFERS:
                    if buf >= sp:
                        continue
                    base_sig = passive_signal(f, event_mask, anchors, side, sp, buf, tick, ctx)
                    if int(base_sig[disc_mask].sum()) < 5:
                        continue

                    for ttl in TTLS:
                        for target_r in TARGET_HOLD:
                            sig = base_sig
                            generated += 1
                            digest = hashlib.sha256(np.packbits(sig[disc_mask].astype(np.uint8)).tobytes()).hexdigest()
                            key = (side_name, digest, sp, buf, ttl, float(target_r))
                            cid = (f"{inst}|{side_name}|REJECTION|ROUND|{anchor_mode}|SL{sp}|B{buf}|TTL{ttl}|"
                                   f"TP{target_r:g}R|H{TARGET_HOLD[target_r]}|{CONTEXT_NAME}")
                            if key in seen:
                                continue
                            seen[key] = cid

                            g = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 0, disc_mask)
                            b = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 1, disc_mask)
                            s = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 2, disc_mask)
                            passed, diag = c29.discovery_pass(g, b, s)
                            if passed:
                                candidates.append({
                                    "candidate_id": cid, "direction": side_name, "side": side,
                                    "structure": "ROUND", "event": "REJECTION", "anchor_mode": anchor_mode,
                                    "stop_points": sp, "anchor_buffer_ticks": buf, "ttl_minutes": ttl,
                                    "target_r": float(target_r), "hold_minutes": int(TARGET_HOLD[target_r]),
                                    "context": CONTEXT_NAME, "discovery_mask_digest": digest,
                                    "discovery": diag, "signal_mask": sig, "anchors": anchors,
                                    "base_event": event_mask,
                                })

    candidates.sort(key=rank_key)
    shortlisted = []
    bucket_count = {}
    for c in candidates:
        bucket = (c["direction"], c["anchor_mode"], c["target_r"])
        if bucket_count.get(bucket, 0) >= 3:
            continue
        bucket_count[bucket] = bucket_count.get(bucket, 0) + 1
        shortlisted.append(c)
        if len(shortlisted) >= 60:
            break

    results = []
    survivors = []
    for c in shortlisted:
        sig = c.pop("signal_mask")
        anchors = c.pop("anchors")
        base_event = c.pop("base_event")
        side = int(c["side"])
        sp = int(c["stop_points"])
        buf = int(c["anchor_buffer_ticks"])
        ttl = int(c["ttl_minutes"])
        target_r = float(c["target_r"])

        g = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 0, fw_mask)
        b = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 1, fw_mask)
        s = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 2, fw_mask)
        strict_ok, fw = c29.forward_eval(g, b, s)

        exit_neighbors = exit_neighbor_support(f, m1, cache, inst, base_event, anchors, side, sp, buf, ttl,
                                               target_r, tick, ctx, fw_mask)
        execution_neighbors = execution_neighbor_support(f, m1, cache, inst, base_event, anchors, side, sp, buf,
                                                         ttl, target_r, tick, ctx, fw_mask)
        exit_ok = any(x["positive_stress_neighbor"] for x in exit_neighbors)
        execution_ok = any(x["positive_stress_neighbor"] for x in execution_neighbors)
        final_ok = bool(strict_ok and exit_ok and execution_ok)

        row = dict(c)
        row["forward"] = fw
        row["exit_neighbor_support"] = exit_neighbors
        row["execution_neighbor_support"] = execution_neighbors
        row["cycle29_gate_pass"] = bool(strict_ok)
        row["exit_neighbor_gate_pass"] = bool(exit_ok)
        row["execution_neighbor_gate_pass"] = bool(execution_ok)
        row["survivor"] = final_ok
        results.append(row)
        if final_ok:
            survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    status = ("EXIT_OCCUPANCY_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if survivors
              else "NO_EXIT_OCCUPANCY_RESEARCH_SURVIVOR")
    manifest = {
        "engine": "cycle34-exit-occupancy-compression-v1", "instrument": inst, "status": status,
        "primary_hypothesis_instrument": "CNYRUBF", "replication_control_instrument": "USDRUBF",
        "structure": "ROUND", "event": "REJECTION", "anchor_modes": ANCHOR_MODES,
        "context": CONTEXT_NAME, "stop_points": STOP_POINTS[inst], "buffers": BUFFERS,
        "ttls": TTLS, "target_hold_map": TARGET_HOLD,
        "generated_candidate_evaluations": generated, "deduped_discovery_candidates": len(seen),
        "discovery_passes": len(candidates), "shortlisted": len(shortlisted), "survivors": len(survivors),
        "research_forward_is_not_untouched_confirmation": True,
        "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False,
        "commission_excluded": True, "quantile_cutpoints": cuts, "provenance": provenance,
    }

    (outdir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=jsonable) + "\n", encoding="utf-8")
    (outdir / "shortlist.json").write_text(json.dumps(results, indent=2, default=jsonable) + "\n", encoding="utf-8")
    (outdir / "survivors.json").write_text(json.dumps(survivors, indent=2, default=jsonable) + "\n", encoding="utf-8")

    report = [
        f"# Cycle 34 — {inst} Exit/Occupancy Compression", "", f"Status: **{status}**",
        f"Generated={generated}; deduped={len(seen)}; discovery passes={len(candidates)}; shortlist={len(shortlisted)}; survivors={len(survivors)}",
        "", "Frozen entry: M5 ROUND REJECTION, eff_60m:HIGH25, passive causal M1 execution.",
        "Only target/max-hold changed: 1.5R/60m, 2R/90m, 3R/120m.",
        "Mar-May15 is research-only; May16-Jul1 and TRUE OOS 2025 were not accessed.", "", "## Top forward candidates",
    ]
    for r in results[:20]:
        b = r["forward"]["base"]
        s = r["forward"]["stress"]
        report.append(
            f"- `{r['candidate_id']}` — survivor={r['survivor']}; BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}, N={b['n']}; "
            f"STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}, N={s['n']}; P10={r['forward']['bootstrap_p10_base_r']}; "
            f"exit-neighbor={r['exit_neighbor_gate_pass']}; execution-neighbor={r['execution_neighbor_gate_pass']}"
        )
    (outdir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(json.dumps({"instrument": inst, "status": status, "generated": generated,
                      "passes": len(candidates), "shortlist": len(shortlisted), "survivors": len(survivors)}, indent=2), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=Path("."))
    p.add_argument("--instrument", choices=("CNYRUBF", "USDRUBF"), required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    run(a.data_root, a.instrument, a.output)
