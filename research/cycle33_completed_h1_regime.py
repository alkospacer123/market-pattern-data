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

ANCHOR_MODES = ("LEVEL", "EVENT_EXTREME")
BUFFERS = (1, 2, 3)
TTLS = (15, 30)
TARGET_RS = (4.0, 5.0, 6.0)
STOP_POINTS = {"CNYRUBF": (8, 10), "USDRUBF": (9, 12)}
H1_CONTEXTS = {
    "SHORT": ("H1_RET2_LOW25", "H1_BEAR_EFF75"),
    "LONG": ("H1_RET2_HIGH75", "H1_BULL_EFF75"),
}


def mod(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


c29 = mod("research/cycle29_structure_aligned_passive.py", "c29_for_c33")
c27 = c29.c27
c24 = c29.c24
v3 = c29.v3


def jsonable(value):
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (pd.Timestamp, pd.Period, datetime, date)):
        return str(value)
    try:
        return c29.jsonable(value)
    except TypeError:
        return str(value)


def completed_h1_features(f: pd.DataFrame):
    """Build H1 features and map only completed H1 bars to each M5 setup row."""
    x = f[["time", "close"]].copy()
    x["time"] = pd.to_datetime(x["time"])
    x["trade_date"] = x["time"].dt.date.astype(str)
    x["hour_start"] = x["time"].dt.floor("h")

    h1 = (
        x.sort_values("time")
        .groupby(["trade_date", "hour_start"], as_index=False)
        .agg(close=("close", "last"), m5_rows=("close", "size"))
    )
    h1["end_time"] = h1["hour_start"] + pd.Timedelta(hours=1)
    h1["h1_ret_2h"] = np.nan
    h1["h1_eff_3h"] = np.nan

    for _, idx in h1.groupby("trade_date", sort=False).groups.items():
        idx = np.asarray(list(idx), dtype=int)
        closes = h1.loc[idx, "close"].to_numpy(float)
        ret2 = np.full(len(idx), np.nan, dtype=float)
        eff3 = np.full(len(idx), np.nan, dtype=float)
        if len(idx) >= 3:
            ret2[2:] = closes[2:] / closes[:-2] - 1.0
        if len(idx) >= 4:
            moves = np.diff(closes)
            for j in range(3, len(idx)):
                recent = moves[j - 3:j]
                denom = float(np.abs(recent).sum())
                eff3[j] = abs(float(closes[j] - closes[j - 3])) / denom if denom > 0 else 0.0
        h1.loc[idx, "h1_ret_2h"] = ret2
        h1.loc[idx, "h1_eff_3h"] = eff3

    selection_h1 = h1[(h1["end_time"] >= DISC_START) & (h1["end_time"] < DISC_END)].copy()
    ret_values = selection_h1["h1_ret_2h"].dropna().to_numpy(float)
    eff_values = selection_h1["h1_eff_3h"].dropna().to_numpy(float)
    if len(ret_values) == 0 or len(eff_values) == 0:
        raise RuntimeError("insufficient completed H1 bars for Jan-Feb cutpoints")

    cuts = {
        "h1_ret_2h_q25": float(np.quantile(ret_values, 0.25)),
        "h1_ret_2h_q75": float(np.quantile(ret_values, 0.75)),
        "h1_eff_3h_q75": float(np.quantile(eff_values, 0.75)),
        "selection_h1_bars_ret": int(len(ret_values)),
        "selection_h1_bars_eff": int(len(eff_values)),
    }

    ret_map = np.full(len(f), np.nan, dtype=float)
    eff_map = np.full(len(f), np.nan, dtype=float)
    f_times = pd.to_datetime(f["time"])
    f_dates = f_times.dt.date.astype(str).to_numpy()

    for trade_date, positions in pd.Series(np.arange(len(f)), index=f_dates).groupby(level=0):
        pos = positions.to_numpy(dtype=int)
        hh = h1[h1["trade_date"] == trade_date].sort_values("end_time")
        if hh.empty:
            continue
        ends = hh["end_time"].astype("int64").to_numpy()
        query = f_times.iloc[pos].astype("int64").to_numpy()
        j = np.searchsorted(ends, query, side="right") - 1
        ok = j >= 0
        if ok.any():
            ret_vals = hh["h1_ret_2h"].to_numpy(float)
            eff_vals = hh["h1_eff_3h"].to_numpy(float)
            ret_map[pos[ok]] = ret_vals[j[ok]]
            eff_map[pos[ok]] = eff_vals[j[ok]]

    contexts = {
        "H1_RET2_LOW25": np.isfinite(ret_map) & (ret_map <= cuts["h1_ret_2h_q25"]),
        "H1_BEAR_EFF75": np.isfinite(ret_map) & np.isfinite(eff_map) & (ret_map < 0) & (eff_map >= cuts["h1_eff_3h_q75"]),
        "H1_RET2_HIGH75": np.isfinite(ret_map) & (ret_map >= cuts["h1_ret_2h_q75"]),
        "H1_BULL_EFF75": np.isfinite(ret_map) & np.isfinite(eff_map) & (ret_map > 0) & (eff_map >= cuts["h1_eff_3h_q75"]),
    }
    diagnostics = {
        "h1_bars_total": int(len(h1)),
        "mapped_m5_rows_with_ret2": int(np.isfinite(ret_map).sum()),
        "mapped_m5_rows_with_eff3": int(np.isfinite(eff_map).sum()),
    }
    return contexts, cuts, diagnostics


def passive_signal(f, event_mask, anchors, side, stop_points, buffer_ticks, tick, context_mask):
    limits = anchors + side * (stop_points - buffer_ticks) * tick
    close = f.close.to_numpy(float)
    passive = np.isfinite(limits) & ((close > limits) if side == 1 else (close < limits))
    return np.asarray(event_mask, bool) & passive & np.asarray(context_mask, bool)


def execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, mode_ticks, window_mask):
    indices = np.flatnonzero(np.asarray(sig, bool) & np.asarray(window_mask, bool))
    return c29.execute_candidate(f, m1, cache, inst, indices, anchors, side, sp, buf, ttl, target_r, mode_ticks)


def adjacent(values, current):
    values = list(values)
    i = values.index(current)
    out = []
    if i > 0:
        out.append(values[i - 1])
    if i + 1 < len(values):
        out.append(values[i + 1])
    return out


def one_axis_neighbors(inst, sp, buf, ttl, target_r):
    rows = set()
    for x in adjacent(STOP_POINTS[inst], sp):
        if buf < x:
            rows.add((x, buf, ttl, target_r, "stop"))
    for x in adjacent(BUFFERS, buf):
        if x < sp:
            rows.add((sp, x, ttl, target_r, "buffer"))
    for x in adjacent(TTLS, ttl):
        rows.add((sp, buf, x, target_r, "ttl"))
    for x in adjacent(TARGET_RS, target_r):
        rows.add((sp, buf, ttl, x, "target"))
    return sorted(rows)


def neighbor_support(f, m1, cache, inst, event_mask, anchors, side, context_mask, sp, buf, ttl, target_r, tick, forward_mask):
    rows = []
    for nsp, nbuf, nttl, ntarget, axis in one_axis_neighbors(inst, sp, buf, ttl, target_r):
        sig = passive_signal(f, event_mask, anchors, side, nsp, nbuf, tick, context_mask)
        base = execute(f, m1, cache, inst, sig, anchors, side, nsp, nbuf, nttl, ntarget, 1, forward_mask)
        stress = execute(f, m1, cache, inst, sig, anchors, side, nsp, nbuf, nttl, ntarget, 2, forward_mask)
        mb = c24.metrics(base)
        ms = c24.metrics(stress)
        positive = bool(ms["n"] >= 5 and ms["expectancy_r"] is not None and ms["expectancy_r"] > 0)
        rows.append({"axis": axis, "stop_points": int(nsp), "buffer": int(nbuf), "ttl": int(nttl), "target_r": float(ntarget), "base": mb, "stress": ms, "positive_stress_neighbor": positive})
    return rows


def alternate_context_support(f, m1, cache, inst, event_mask, anchors, side, alt_mask, sp, buf, ttl, target_r, tick, forward_mask, alt_name):
    sig = passive_signal(f, event_mask, anchors, side, sp, buf, tick, alt_mask)
    base = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 1, forward_mask)
    stress = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 2, forward_mask)
    mb = c24.metrics(base)
    ms = c24.metrics(stress)
    positive = bool(ms["n"] >= 5 and ms["expectancy_r"] is not None and ms["expectancy_r"] > 0)
    return {"context": alt_name, "base": mb, "stress": ms, "positive_stress_alternate_context": positive}


def rank_key(candidate):
    d = candidate["discovery"]
    jan = d["january_stress"]["expectancy_r"]
    feb = d["february_stress"]["expectancy_r"]
    jan = -1e9 if jan is None else float(jan)
    feb = -1e9 if feb is None else float(feb)
    ds = d["discovery_stress"]
    db = d["discovery_base"]
    ds_er = ds["expectancy_r"] if ds["expectancy_r"] is not None else -1e9
    return (-min(jan, feb), -float(ds["pf"]), -float(db["pf"]), -float(ds_er), -int(db["days"]), candidate["candidate_id"])


def run(root: Path, inst: str, outdir: Path):
    if (root / "2025").exists():
        raise PermissionError("TRUE OOS 2025 must remain sealed")

    f, m1, provenance = c24.load_context(root, inst)
    if len(f) and pd.Timestamp(f.time.max()) >= FORWARD_END:
        raise PermissionError("Cycle33 data root exposes retired rows on/after 2026-05-16")

    _, _, _, cache = c24.structural_arrays(f, m1, inst)
    levels = c27.build_levels(f, inst)
    tick = float(v3.SPECS[inst]["tick"])
    h1_contexts, h1_cuts, h1_diag = completed_h1_features(f)

    discovery_mask = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    forward_mask = ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy()
    generated = 0
    seen = {}
    discovery_candidates = []

    for side_name, side in (("SHORT", -1), ("LONG", 1)):
        context_names = H1_CONTEXTS[side_name]
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
                    for ttl in TTLS:
                        for target_r in TARGET_RS:
                            for context_name in context_names:
                                context_mask = h1_contexts[context_name]
                                sig = passive_signal(f, event_mask, anchors, side, sp, buf, tick, context_mask)
                                if int(sig[discovery_mask].sum()) < 5:
                                    continue
                                generated += 1
                                digest = hashlib.sha256(np.packbits(sig[discovery_mask].astype(np.uint8)).tobytes()).hexdigest()
                                key = (side_name, digest, int(sp), int(buf), int(ttl), float(target_r))
                                candidate_id = f"{inst}|{side_name}|REJECTION|ROUND|{anchor_mode}|SL{sp}|B{buf}|TTL{ttl}|TP{target_r:g}R|{context_name}"
                                if key in seen:
                                    continue
                                seen[key] = candidate_id
                                gross = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 0, discovery_mask)
                                base = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 1, discovery_mask)
                                stress = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 2, discovery_mask)
                                passed, diag = c29.discovery_pass(gross, base, stress)
                                if passed:
                                    discovery_candidates.append({"candidate_id": candidate_id, "direction": side_name, "side": int(side), "event": "REJECTION", "structure": "ROUND", "anchor_mode": anchor_mode, "stop_points": int(sp), "anchor_buffer_ticks": int(buf), "ttl_minutes": int(ttl), "target_r": float(target_r), "h1_context": context_name, "discovery_mask_digest": digest, "discovery": diag, "_signal_mask": sig, "_anchors": anchors, "_event_mask": event_mask, "_context_mask": context_mask})

    discovery_candidates.sort(key=rank_key)
    shortlisted = []
    bucket_count = {}
    for candidate in discovery_candidates:
        bucket = (candidate["direction"], candidate["anchor_mode"], candidate["h1_context"])
        if bucket_count.get(bucket, 0) >= 3:
            continue
        bucket_count[bucket] = bucket_count.get(bucket, 0) + 1
        shortlisted.append(candidate)
        if len(shortlisted) >= 60:
            break

    results = []
    survivors = []
    for candidate in shortlisted:
        sig = candidate.pop("_signal_mask")
        anchors = candidate.pop("_anchors")
        event_mask = candidate.pop("_event_mask")
        context_mask = candidate.pop("_context_mask")
        side = int(candidate["side"])
        sp = int(candidate["stop_points"])
        buf = int(candidate["anchor_buffer_ticks"])
        ttl = int(candidate["ttl_minutes"])
        target_r = float(candidate["target_r"])

        gross = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 0, forward_mask)
        base = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 1, forward_mask)
        stress = execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, target_r, 2, forward_mask)
        strict_ok, forward = c29.forward_eval(gross, base, stress)

        neighbors = neighbor_support(f, m1, cache, inst, event_mask, anchors, side, context_mask, sp, buf, ttl, target_r, tick, forward_mask)
        positive_neighbors = sum(1 for row in neighbors if row["positive_stress_neighbor"])
        direction = candidate["direction"]
        primary_context = candidate["h1_context"]
        alternatives = [x for x in H1_CONTEXTS[direction] if x != primary_context]
        if len(alternatives) != 1:
            raise RuntimeError(f"expected exactly one alternate H1 context for {direction}")
        alternate_name = alternatives[0]
        alternate = alternate_context_support(f, m1, cache, inst, event_mask, anchors, side, h1_contexts[alternate_name], sp, buf, ttl, target_r, tick, forward_mask, alternate_name)
        robustness_ok = bool(positive_neighbors >= 2 and alternate["positive_stress_alternate_context"])
        final_ok = bool(strict_ok and robustness_ok)

        row = dict(candidate)
        row["forward"] = forward
        row["neighbor_support"] = neighbors
        row["positive_stress_neighbors"] = int(positive_neighbors)
        row["alternate_h1_context_support"] = alternate
        row["cycle29_gate_pass"] = bool(strict_ok)
        row["h1_robustness_pass"] = bool(robustness_ok)
        row["survivor"] = final_ok
        results.append(row)
        if final_ok:
            survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    status = "COMPLETED_H1_REGIME_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if survivors else "NO_COMPLETED_H1_REGIME_RESEARCH_SURVIVOR"
    manifest = {
        "engine": "cycle33-completed-h1-regime-v1", "instrument": inst, "status": status,
        "primary_hypothesis_instrument": "CNYRUBF", "replication_control_instrument": "USDRUBF",
        "structure": "ROUND", "event": "REJECTION", "anchor_modes": ANCHOR_MODES,
        "stop_points": STOP_POINTS[inst], "buffers": BUFFERS, "ttls": TTLS, "target_rs": TARGET_RS,
        "h1_contexts": H1_CONTEXTS, "h1_cutpoints": h1_cuts, "h1_diagnostics": h1_diag,
        "generated_candidate_evaluations": int(generated), "deduped_discovery_candidates": int(len(seen)),
        "discovery_passes": int(len(discovery_candidates)), "shortlisted": int(len(shortlisted)), "survivors": int(len(survivors)),
        "research_forward_is_not_untouched_confirmation": True,
        "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False,
        "commission_excluded": True, "provenance": provenance,
    }
    (outdir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, default=jsonable) + "\n", encoding="utf-8")
    (outdir / "shortlist.json").write_text(json.dumps(results, indent=2, default=jsonable) + "\n", encoding="utf-8")
    (outdir / "survivors.json").write_text(json.dumps(survivors, indent=2, default=jsonable) + "\n", encoding="utf-8")

    report = [
        f"# Cycle 33 — {inst} Completed-H1 Regime Context", "", f"Status: **{status}**",
        f"Generated={generated}; deduped={len(seen)}; discovery passes={len(discovery_candidates)}; shortlist={len(shortlisted)}; survivors={len(survivors)}", "",
        "Frozen event family: M5 ROUND REJECTION with passive causal M1 execution.",
        "H1 states use completed H1 bars only; Jan-Feb cutpoints only.",
        "Mar-May15 is research-only, not untouched confirmation.",
        "Retired May16-Jul1 and TRUE OOS 2025 were not accessed.", "", "## Top forward candidates",
    ]
    for row in results[:20]:
        b = row["forward"]["base"]
        s = row["forward"]["stress"]
        alt = row["alternate_h1_context_support"]["stress"]
        report.append(f"- `{row['candidate_id']}` — survivor={row['survivor']}; BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}, N={b['n']}; STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}, N={s['n']}; P10={row['forward']['bootstrap_p10_base_r']}; positive neighbors={row['positive_stress_neighbors']}; alternate H1 STRESS PF={alt['pf']:.3f}, E[R]={alt['expectancy_r']}, N={alt['n']}")
    (outdir / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps({"instrument": inst, "status": status, "generated": generated, "deduped": len(seen), "passes": len(discovery_candidates), "shortlist": len(shortlisted), "survivors": len(survivors)}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path("."))
    parser.add_argument("--instrument", choices=("CNYRUBF", "USDRUBF"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.data_root, args.instrument, args.output)
