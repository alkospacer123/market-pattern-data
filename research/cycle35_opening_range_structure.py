from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp('2026-01-05')
DISC_END = pd.Timestamp('2026-03-01')
FORWARD_END = pd.Timestamp('2026-05-16')

STOP_POINTS = {
    'CNYRUBF': (6, 8, 10),
    'USDRUBF': (9, 12, 15),
}
TARGET_RS = (3.0, 4.0, 5.0)
EVENT_TYPES = ('REJECTION', 'SWEEP_RECLAIM', 'BREAK_RETEST')
ANCHOR_MODES = ('LEVEL', 'EVENT_EXTREME')
STRUCTURE = 'OPEN30'
SHORTLIST_CAP = 30
BUCKET_CAP = 3


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c27 = mod('research/cycle27_fixed_stop_structural_event.py', 'c27_for_c35')
c24 = c27.c24
v3 = c27.v3


def jsonable(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)):
        return str(v)
    return c27.jsonable(v)


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
    d = c['discovery']
    jan = d['january_stress']['expectancy_r']
    feb = d['february_stress']['expectancy_r']
    jan = -1e9 if jan is None else float(jan)
    feb = -1e9 if feb is None else float(feb)
    ds = d['discovery_stress']
    db = d['discovery_base']
    der = ds['expectancy_r']
    der = -1e9 if der is None else float(der)
    return (
        -min(jan, feb),
        -float(ds['pf']),
        -float(db['pf']),
        -der,
        -int(ds['days']),
        c['candidate_id'],
    )


def forward_trades(f, m1, cache, trade_cache, inst, sig, side, sp, tr, fw_mask):
    ix = np.flatnonzero(sig & fw_mask)
    gross = c27.execute_indices(f, m1, cache, trade_cache, inst, ix, side, sp, tr, 0)
    base = c27.execute_indices(f, m1, cache, trade_cache, inst, ix, side, sp, tr, 1)
    stress = c27.execute_indices(f, m1, cache, trade_cache, inst, ix, side, sp, tr, 2)
    return gross, base, stress


def neighbor_support(f, m1, cache, trade_cache, inst, event_mask, anchor, entries, side,
                     sp, tr, tick, fw_mask):
    rows = []

    for nsp in adjacent(STOP_POINTS[inst], sp):
        nsig = event_mask & c27.stop_valid(entries, anchor, tick, int(nsp), side)
        _, nb, ns = forward_trades(f, m1, cache, trade_cache, inst, nsig, side, int(nsp), float(tr), fw_mask)
        mb = c24.metrics(nb)
        ms = c24.metrics(ns)
        positive = bool(ms['n'] >= 10 and ms['expectancy_r'] is not None and ms['expectancy_r'] > 0)
        rows.append({
            'axis': 'stop', 'stop_points': int(nsp), 'target_r': float(tr),
            'base': mb, 'stress': ms, 'positive_stress_neighbor': positive,
        })

    for ntr in adjacent(TARGET_RS, tr):
        nsig = event_mask & c27.stop_valid(entries, anchor, tick, int(sp), side)
        _, nb, ns = forward_trades(f, m1, cache, trade_cache, inst, nsig, side, int(sp), float(ntr), fw_mask)
        mb = c24.metrics(nb)
        ms = c24.metrics(ns)
        positive = bool(ms['n'] >= 10 and ms['expectancy_r'] is not None and ms['expectancy_r'] > 0)
        rows.append({
            'axis': 'target', 'stop_points': int(sp), 'target_r': float(ntr),
            'base': mb, 'stress': ms, 'positive_stress_neighbor': positive,
        })

    return rows


def run(root: Path, inst: str, outdir: Path):
    f, m1, provenance = c24.load_context(root, inst)
    entries, _, _, cache = c24.structural_arrays(f, m1, inst)
    levels = c27.build_levels(f, inst)
    tick = float(v3.SPECS[inst]['tick'])
    disc_mask = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    fw_mask = ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy()

    generated = 0
    seen = {}
    candidates = []
    trade_cache = {}

    for side_name, side in (('LONG', 1), ('SHORT', -1)):
        for event in EVENT_TYPES:
            for anchor_mode in ANCHOR_MODES:
                event_mask, anchor = c27.event_and_anchor(
                    f, inst, STRUCTURE, event, side, anchor_mode, levels
                )
                if not event_mask.any():
                    continue

                for sp in STOP_POINTS[inst]:
                    sig = event_mask & c27.stop_valid(entries, anchor, tick, int(sp), side)
                    if sig[disc_mask].sum() < 5:
                        continue

                    for tr in TARGET_RS:
                        generated += 1
                        digest = hashlib.sha256(
                            np.packbits(sig[disc_mask].astype(np.uint8)).tobytes()
                        ).hexdigest()
                        key = (side_name, event, anchor_mode, digest, int(sp), float(tr))
                        cid = (
                            f'{inst}|{side_name}|{event}|OPEN30|{anchor_mode}|'
                            f'SL{sp}|TP{tr:g}R|NONE'
                        )
                        if key in seen:
                            continue
                        seen[key] = cid

                        dix = np.flatnonzero(sig & disc_mask)
                        gross = c27.execute_indices(
                            f, m1, cache, trade_cache, inst, dix, side, int(sp), float(tr), 0
                        )
                        base = c27.execute_indices(
                            f, m1, cache, trade_cache, inst, dix, side, int(sp), float(tr), 1
                        )
                        stress = c27.execute_indices(
                            f, m1, cache, trade_cache, inst, dix, side, int(sp), float(tr), 2
                        )
                        passed, diag = c27.discovery_pass(gross, base, stress)
                        if passed:
                            candidates.append({
                                'candidate_id': cid,
                                'direction': side_name,
                                'side': int(side),
                                'event': event,
                                'structure': STRUCTURE,
                                'anchor_mode': anchor_mode,
                                'stop_points': int(sp),
                                'target_r': float(tr),
                                'context': 'NONE',
                                'discovery_mask_digest': digest,
                                'discovery': diag,
                                'signal_mask': sig,
                                'event_mask': event_mask,
                                'anchor': anchor,
                            })

    candidates.sort(key=rank_key)

    shortlisted = []
    bucket_count = {}
    for c in candidates:
        bucket = (c['direction'], c['event'], c['anchor_mode'])
        if bucket_count.get(bucket, 0) >= BUCKET_CAP:
            continue
        bucket_count[bucket] = bucket_count.get(bucket, 0) + 1
        shortlisted.append(c)
        if len(shortlisted) >= SHORTLIST_CAP:
            break

    results = []
    survivors = []
    for c in shortlisted:
        sig = c.pop('signal_mask')
        event_mask = c.pop('event_mask')
        anchor = c.pop('anchor')
        side = int(c['side'])
        sp = int(c['stop_points'])
        tr = float(c['target_r'])

        gross, base, stress = forward_trades(
            f, m1, cache, trade_cache, inst, sig, side, sp, tr, fw_mask
        )
        strict_ok, fw = c27.forward_eval(gross, base, stress)

        neighbors = neighbor_support(
            f, m1, cache, trade_cache, inst, event_mask, anchor, entries, side,
            sp, tr, tick, fw_mask
        )
        positive_neighbors = sum(1 for x in neighbors if x['positive_stress_neighbor'])
        robust_ok = bool(positive_neighbors >= 1)
        final_ok = bool(strict_ok and robust_ok)

        row = dict(c)
        row['forward'] = fw
        row['neighbor_support'] = neighbors
        row['positive_stress_neighbors'] = int(positive_neighbors)
        row['cycle27_forward_gate_pass'] = bool(strict_ok)
        row['execution_neighbor_robustness_pass'] = bool(robust_ok)
        row['survivor'] = bool(final_ok)
        results.append(row)
        if final_ok:
            survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    status = (
        'OPENING_RANGE_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION'
        if survivors else 'NO_OPENING_RANGE_RESEARCH_SURVIVOR'
    )
    manifest = {
        'engine': 'cycle35-opening-range-structure-v1',
        'instrument': inst,
        'status': status,
        'structure': STRUCTURE,
        'opening_range_window': '09:00-09:25 M5; available from 09:30',
        'event_types': EVENT_TYPES,
        'anchor_modes': ANCHOR_MODES,
        'context': 'NONE',
        'stop_points': STOP_POINTS[inst],
        'target_rs': TARGET_RS,
        'hold_minutes': {str(k): int(c27.HOLD_MINUTES[k]) for k in TARGET_RS},
        'generated_candidate_evaluations': generated,
        'deduped_discovery_candidates': len(seen),
        'discovery_passes': len(candidates),
        'shortlisted': len(shortlisted),
        'survivors': len(survivors),
        'research_forward_is_not_untouched_confirmation': True,
        'retired_internal_confirmation_accessed': False,
        'true_oos_2025_accessed': False,
        'commission_excluded': True,
        'provenance': provenance,
    }

    (outdir / 'run_manifest.json').write_text(
        json.dumps(manifest, indent=2, default=jsonable) + '\n', encoding='utf-8'
    )
    (outdir / 'shortlist.json').write_text(
        json.dumps(results, indent=2, default=jsonable) + '\n', encoding='utf-8'
    )
    (outdir / 'survivors.json').write_text(
        json.dumps(survivors, indent=2, default=jsonable) + '\n', encoding='utf-8'
    )

    report = [
        f'# Cycle 35 — {inst} Opening-Range Structural Behavior',
        '',
        f'Status: **{status}**',
        f'Generated={generated}; deduped={len(seen)}; discovery passes={len(candidates)}; '
        f'shortlist={len(shortlisted)}; survivors={len(survivors)}',
        '',
        'OPEN30 is constructed only from completed 09:00-09:25 M5 bars and is available from 09:30.',
        'No context filters are used. Mar-May15 is research-only; May16-Jul1 and TRUE OOS 2025 were not accessed.',
        '',
        '## Top forward candidates',
    ]
    for r in results[:15]:
        b = r['forward']['base']
        s = r['forward']['stress']
        report.append(
            f"- `{r['candidate_id']}` — survivor={r['survivor']}; "
            f"BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}, N={b['n']}; "
            f"STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}, N={s['n']}; "
            f"P10={r['forward']['bootstrap_p10_base_r']}; "
            f"positive neighbors={r['positive_stress_neighbors']}"
        )
    (outdir / 'report.md').write_text('\n'.join(report) + '\n', encoding='utf-8')

    print(json.dumps({
        'instrument': inst,
        'status': status,
        'generated': generated,
        'passes': len(candidates),
        'shortlist': len(shortlisted),
        'survivors': len(survivors),
    }, indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', type=Path, default=Path('.'))
    p.add_argument('--instrument', choices=('CNYRUBF', 'USDRUBF'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.data_root, a.instrument, a.output)
