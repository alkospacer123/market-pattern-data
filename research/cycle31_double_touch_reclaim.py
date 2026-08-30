from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c29 = mod('research/cycle29_structure_aligned_passive.py', 'c29_for_c31')
v3 = c29.v3


def simulate_order(f: pd.DataFrame, m1: pd.DataFrame, cache: dict, i: int, inst: str, side: int,
                   anchor: float, stop_points: int, buffer_ticks: int, ttl_minutes: int,
                   target_r: float, mode_ticks: int):
    tick = float(v3.SPECS[inst]['tick'])
    if not np.isfinite(anchor):
        return None, None
    setup_close = float(f.close.iloc[i])
    limit = c29.derived_limit(float(anchor), tick, side, stop_points, buffer_ticks)
    if side == 1 and not setup_close > limit + 1e-12:
        return None, None
    if side == -1 and not setup_close < limit - 1e-12:
        return None, None

    order_start = pd.Timestamp(f.time.iloc[i]) + pd.Timedelta(minutes=5)
    force = pd.Timestamp(order_start.date()) + pd.Timedelta(hours=17)
    expiry = min(order_start + pd.Timedelta(minutes=ttl_minutes), force)
    if order_start >= force:
        return None, None

    times = cache['times']
    start_idx = int(np.searchsorted(times, int(order_start.value), side='left'))
    end_idx = int(np.searchsorted(times, int(expiry.value), side='left'))
    if start_idx >= len(m1) or start_idx >= end_idx or cache['date'][start_idx] != f.date.iloc[i]:
        return None, expiry

    # Stage 1: first touch is only a probe and can never fill.
    probe_idx = None
    for j in range(start_idx, min(end_idx, len(m1))):
        if cache['date'][j] != f.date.iloc[i]:
            break
        touched = float(cache['low'][j]) <= limit + 1e-12 if side == 1 else float(cache['high'][j]) >= limit - 1e-12
        if touched:
            probe_idx = j
            break
    if probe_idx is None:
        return None, expiry

    # Stage 2: require a completed later M1 reclaim at least one tick to the safe side.
    reclaim_idx = None
    for j in range(probe_idx + 1, min(end_idx, len(m1))):
        if cache['date'][j] != f.date.iloc[i]:
            break
        close = float(cache['close'][j])
        reclaimed = close >= limit + tick - 1e-12 if side == 1 else close <= limit - tick + 1e-12
        if reclaimed:
            reclaim_idx = j
            break
    if reclaim_idx is None:
        return None, expiry

    # Stage 3: only a strictly later second touch can fill. G/B/S preserve 0/1/2 tick execution uncertainty.
    fill_idx = None
    through = mode_ticks * tick
    for j in range(reclaim_idx + 1, min(end_idx, len(m1))):
        if cache['date'][j] != f.date.iloc[i]:
            break
        qualified = float(cache['low'][j]) <= limit - through + 1e-12 if side == 1 else float(cache['high'][j]) >= limit + through - 1e-12
        if qualified:
            fill_idx = j
            break
    if fill_idx is None:
        return None, expiry

    risk = stop_points * tick
    stop = limit - side * risk
    target = limit + side * target_r * risk
    hold = c29.HOLD_MINUTES[float(target_r)]
    deadline = force if hold is None else min(pd.Timestamp(cache['times'][fill_idx]) + pd.Timedelta(minutes=hold), force)
    di = cache['idxmap'].get(int(deadline.value))
    exact = di is not None
    if di is None:
        di = int(np.searchsorted(times, int(deadline.value), side='right') - 1)
    if di < fill_idx or di >= len(m1) or cache['date'][di] != cache['date'][fill_idx]:
        return None, expiry

    j = fill_idx
    o = float(cache['open'][j]); h = float(cache['high'][j]); l = float(cache['low'][j])
    raw_exit = None; xi = None; reason = None
    if side == 1:
        if o <= stop:
            xi, raw_exit, reason = j, o, 'FILL_BAR_STOP_GAP'
        elif l <= stop:
            xi, raw_exit, reason = j, stop, 'FILL_BAR_STOP'
    else:
        if o >= stop:
            xi, raw_exit, reason = j, o, 'FILL_BAR_STOP_GAP'
        elif h >= stop:
            xi, raw_exit, reason = j, stop, 'FILL_BAR_STOP'

    if raw_exit is None:
        raw_exit = float(cache['open'][di]) if exact else float(cache['close'][di])
        xi = di; reason = 'TIME'
        for j in range(fill_idx + 1, di + 1):
            o = float(cache['open'][j]); h = float(cache['high'][j]); l = float(cache['low'][j])
            if side == 1:
                if o <= stop:
                    xi, raw_exit, reason = j, o, 'STOP_GAP'; break
                if o >= target:
                    xi, raw_exit, reason = j, target, 'TARGET_GAP_CONSERVATIVE'; break
                hs, ht = l <= stop, h >= target
                if hs:
                    xi, raw_exit, reason = j, stop, 'STOP_FIRST_TIE' if ht else 'STOP'; break
                if ht:
                    xi, raw_exit, reason = j, target, 'TARGET'; break
            else:
                if o >= stop:
                    xi, raw_exit, reason = j, o, 'STOP_GAP'; break
                if o <= target:
                    xi, raw_exit, reason = j, target, 'TARGET_GAP_CONSERVATIVE'; break
                hs, ht = h >= stop, l <= target
                if hs:
                    xi, raw_exit, reason = j, stop, 'STOP_FIRST_TIE' if ht else 'STOP'; break
                if ht:
                    xi, raw_exit, reason = j, target, 'TARGET'; break

    gross_bps = 10000.0 * side * (float(raw_exit) - limit) / limit
    exit_cost_bps = 10000.0 * mode_ticks * tick / limit
    bps = gross_bps - exit_cost_bps
    risk_bps = 10000.0 * risk / limit
    tr = {
        'signal_index': int(i), 'signal_time': str(f.time.iloc[i]),
        'order_start': str(order_start), 'probe_time': str(m1.time.iloc[probe_idx]),
        'reclaim_time': str(m1.time.iloc[reclaim_idx]), 'entry_time': str(m1.time.iloc[fill_idx]),
        'exit_time': str(m1.time.iloc[int(xi)]), 'entry': limit,
        'anchor': float(anchor), 'anchor_buffer_ticks': int(buffer_ticks),
        'stop': stop, 'target': target, 'stop_points': int(stop_points),
        'target_r': float(target_r), 'ttl_minutes': int(ttl_minutes),
        'fill_through_ticks': int(mode_ticks), 'exit_friction_ticks': int(mode_ticks),
        'reason': reason, 'gross_bps': float(gross_bps), 'bps': float(bps),
        'risk_bps': float(risk_bps), 'r': float(bps / risk_bps),
    }
    return tr, pd.Timestamp(tr['exit_time'])


def run(root: Path, inst: str, outdir: Path):
    # Patch only the execution geometry. Candidate generation, Jan-Feb selection,
    # ranking, shortlist cap and Mar-May15 strict gates remain exactly Cycle 29.
    c29.simulate_order = simulate_order
    c29.run(root, inst, outdir)
    mp = outdir / 'run_manifest.json'
    manifest = json.loads(mp.read_text())
    manifest['engine'] = 'cycle31-probe-reclaim-second-touch-v1'
    manifest['cycle31_execution_change_only'] = True
    manifest['probe_reclaim_second_touch'] = True
    manifest['retired_internal_confirmation_accessed'] = False
    manifest['true_oos_2025_accessed'] = False
    mp.write_text(json.dumps(manifest, indent=2) + '\n')
    rp = outdir / 'report.md'
    body = rp.read_text()
    rp.write_text('# Cycle 31 — Probe → Reclaim → Second-Touch Passive Entry\n\n' + body + '\nResearch-only. Cycle-29 gates unchanged. Retired May16-Jul1 and TRUE OOS 2025 were not accessed.\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', type=Path, default=Path('.'))
    p.add_argument('--instrument', choices=('CNYRUBF','USDRUBF'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.data_root, a.instrument, a.output)
