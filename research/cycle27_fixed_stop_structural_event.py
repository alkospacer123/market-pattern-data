from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp('2026-01-05')
JAN_END = pd.Timestamp('2026-02-01')
DISC_END = pd.Timestamp('2026-03-01')
FORWARD_END = pd.Timestamp('2026-05-16')
BOOTSTRAP_SEED = 20260401
BOOTSTRAP_REPS = 1000
STOP_POINTS = {'CNYRUBF': (6, 8, 10), 'USDRUBF': (6, 9, 12, 15)}
TARGET_RS = (3.0, 4.0, 5.0, 6.0)
HOLD_MINUTES = {3.0: 120, 4.0: 180, 5.0: 240, 6.0: None}
LEVEL_TYPES = ('PREV_DAY', 'ROLL30', 'ROLL60', 'M5_FRACTAL', 'EQUAL_CLUSTER', 'ROUND', 'OPEN30')
EVENT_TYPES = ('REJECTION', 'SWEEP_RECLAIM', 'BREAK_RETEST')
ANCHOR_MODES = ('LEVEL', 'EVENT_EXTREME')
CONTEXT_FEATURES = (
    'ret_15m_atr', 'ret_30m_atr', 'pos_30m', 'pos_60m', 'pos_120m',
    'eff_30m', 'eff_60m', 'vol_15m_60m', 'vol_30m_120m', 'relvol_60m',
    'dist_pdh_atr', 'dist_pdl_atr', 'session_pos', 'clock_bucket',
)


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c24 = mod('research/cycle24_fixed_point_structural.py', 'c24')
v3 = c24.v3


def jsonable(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)):
        return str(v)
    raise TypeError(type(v).__name__)


def session_mask(f: pd.DataFrame) -> np.ndarray:
    mins = (f.time.dt.hour * 60 + f.time.dt.minute).to_numpy()
    return (mins >= 9 * 60) & (mins <= 16 * 60 + 30)


def rolling_prior(g: pd.Series, bars: int, kind: str) -> pd.Series:
    z = g.shift(1).rolling(bars, min_periods=max(3, bars // 2))
    return z.max() if kind == 'high' else z.min()


def confirmed_fractal_levels(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    hi_out = np.full(len(f), np.nan)
    lo_out = np.full(len(f), np.nan)
    for _, idx in f.groupby('date', sort=False).groups.items():
        ix = np.asarray(list(idx), dtype=int)
        h = f.high.iloc[ix].to_numpy(float)
        l = f.low.iloc[ix].to_numpy(float)
        ah = np.full(len(ix), np.nan)
        al = np.full(len(ix), np.nan)
        for j in range(2, len(ix) - 2):
            if h[j] > h[j - 1] and h[j] >= h[j - 2] and h[j] > h[j + 1] and h[j] >= h[j + 2]:
                ah[j + 2] = h[j]
            if l[j] < l[j - 1] and l[j] <= l[j - 2] and l[j] < l[j + 1] and l[j] <= l[j + 2]:
                al[j + 2] = l[j]
        ah = pd.Series(ah).ffill().to_numpy(float)
        al = pd.Series(al).ffill().to_numpy(float)
        hi_out[ix] = ah
        lo_out[ix] = al
    return hi_out, lo_out


def equal_cluster_levels(f: pd.DataFrame, tick: float) -> tuple[np.ndarray, np.ndarray]:
    hi_out = np.full(len(f), np.nan)
    lo_out = np.full(len(f), np.nan)
    tol = 2.0 * tick + 1e-12
    for _, idx in f.groupby('date', sort=False).groups.items():
        ix = np.asarray(list(idx), dtype=int)
        h = f.high.iloc[ix].to_numpy(float)
        l = f.low.iloc[ix].to_numpy(float)
        for k in range(len(ix)):
            s = max(0, k - 12)
            found_h = np.nan
            found_l = np.nan
            for b in range(k - 1, s, -1):
                for a in range(b - 1, s - 1, -1):
                    if not np.isfinite(found_h) and abs(h[b] - h[a]) <= tol:
                        found_h = 0.5 * (h[b] + h[a])
                    if not np.isfinite(found_l) and abs(l[b] - l[a]) <= tol:
                        found_l = 0.5 * (l[b] + l[a])
                    if np.isfinite(found_h) and np.isfinite(found_l):
                        break
                if np.isfinite(found_h) and np.isfinite(found_l):
                    break
            hi_out[ix[k]] = found_h
            lo_out[ix[k]] = found_l
    return hi_out, lo_out


def opening_range_levels(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    hi_out = np.full(len(f), np.nan)
    lo_out = np.full(len(f), np.nan)
    mins_all = (f.time.dt.hour * 60 + f.time.dt.minute).to_numpy()
    for _, idx in f.groupby('date', sort=False).groups.items():
        ix = np.asarray(list(idx), dtype=int)
        mins = mins_all[ix]
        open_mask = (mins >= 9 * 60) & (mins <= 9 * 60 + 25)
        if open_mask.sum() < 3:
            continue
        oh = float(f.high.iloc[ix[open_mask]].max())
        ol = float(f.low.iloc[ix[open_mask]].min())
        avail = mins >= 9 * 60 + 30
        hi_out[ix[avail]] = oh
        lo_out[ix[avail]] = ol
    return hi_out, lo_out


def build_levels(f: pd.DataFrame, inst: str) -> dict[str, dict[str, np.ndarray]]:
    tick = float(v3.SPECS[inst]['tick'])
    step = float(v3.SPECS[inst]['round_step'])
    levels: dict[str, dict[str, np.ndarray]] = {}
    levels['PREV_DAY'] = {
        'resistance': pd.to_numeric(f.prev_day_high, errors='coerce').to_numpy(float),
        'support': pd.to_numeric(f.prev_day_low, errors='coerce').to_numpy(float),
    }
    for bars, name in ((6, 'ROLL30'), (12, 'ROLL60')):
        rh = f.groupby('date', sort=False).high.transform(lambda s, b=bars: rolling_prior(s, b, 'high')).to_numpy(float)
        rl = f.groupby('date', sort=False).low.transform(lambda s, b=bars: rolling_prior(s, b, 'low')).to_numpy(float)
        levels[name] = {'resistance': rh, 'support': rl}
    fh, fl = confirmed_fractal_levels(f)
    levels['M5_FRACTAL'] = {'resistance': fh, 'support': fl}
    eh, el = equal_cluster_levels(f, tick)
    levels['EQUAL_CLUSTER'] = {'resistance': eh, 'support': el}
    close = f.close.to_numpy(float)
    eps = tick * 1e-6
    levels['ROUND'] = {
        'resistance': np.ceil((close + eps) / step) * step,
        'support': np.floor((close - eps) / step) * step,
    }
    oh, ol = opening_range_levels(f)
    levels['OPEN30'] = {'resistance': oh, 'support': ol}
    return levels


def event_and_anchor(f: pd.DataFrame, inst: str, level_type: str, event: str, side: int,
                     anchor_mode: str, levels: dict[str, dict[str, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    tick = float(v3.SPECS[inst]['tick'])
    h = f.high.to_numpy(float)
    l = f.low.to_numpy(float)
    c = f.close.to_numpy(float)
    prev_c = np.r_[np.nan, c[:-1]]
    prev2_c = np.r_[np.nan, np.nan, c[:-2]]
    same_prev = np.r_[False, f.date.to_numpy()[1:] == f.date.to_numpy()[:-1]]
    same_prev2 = np.r_[False, False, (f.date.to_numpy()[2:] == f.date.to_numpy()[1:-1]) & (f.date.to_numpy()[1:-1] == f.date.to_numpy()[:-2])]

    if event in ('REJECTION', 'SWEEP_RECLAIM'):
        role = 'support' if side == 1 else 'resistance'
        level = levels[level_type][role].copy()
        if side == 1:
            if event == 'REJECTION':
                raw = np.isfinite(level) & (l <= level + tick) & (l >= level - 4 * tick) & (c > level)
            else:
                raw = np.isfinite(level) & (l <= level - tick) & (l >= level - 6 * tick) & (c > level)
            extreme = l
        else:
            if event == 'REJECTION':
                raw = np.isfinite(level) & (h >= level - tick) & (h <= level + 4 * tick) & (c < level)
            else:
                raw = np.isfinite(level) & (h >= level + tick) & (h <= level + 6 * tick) & (c < level)
            extreme = h
        anchor = level if anchor_mode == 'LEVEL' else extreme
    else:
        role = 'resistance' if side == 1 else 'support'
        base = levels[level_type][role]
        level = np.r_[np.nan, base[:-1]]
        if side == 1:
            raw = (same_prev & same_prev2 & np.isfinite(level) & (prev_c > level + tick)
                   & (prev2_c <= level + tick) & (l <= level + 3 * tick)
                   & (l >= level - 3 * tick) & (c > level))
            extreme = l
        else:
            raw = (same_prev & same_prev2 & np.isfinite(level) & (prev_c < level - tick)
                   & (prev2_c >= level - tick) & (h >= level - 3 * tick)
                   & (h <= level + 3 * tick) & (c < level))
            extreme = h
        anchor = level if anchor_mode == 'LEVEL' else extreme

    raw &= session_mask(f)
    return raw, np.asarray(anchor, float)


def stop_valid(entries: np.ndarray, anchor: np.ndarray, tick: float, stop_points: int, side: int) -> np.ndarray:
    dist = side * (entries - anchor) / tick
    buffer = stop_points - dist
    return (np.isfinite(entries) & np.isfinite(anchor) & (dist > 0) & (dist < stop_points)
            & (buffer >= 1.0 - 1e-9) & (buffer <= 3.0 + 1e-9))


def raw_trade(f: pd.DataFrame, m1: pd.DataFrame, cache: dict, i: int, inst: str, side: int,
              stop_points: int, target_r: float):
    tick = float(v3.SPECS[inst]['tick'])
    decision = pd.Timestamp(f.time.iloc[i])
    et = decision + pd.Timedelta(minutes=5)
    ei = cache['idxmap'].get(int(et.value))
    if ei is None or cache['date'][ei] != f.date.iloc[i]:
        return None
    entry = float(cache['open'][ei])
    risk = stop_points * tick
    stop = entry - side * risk
    target = entry + side * target_r * risk
    hold = HOLD_MINUTES[float(target_r)]
    force = pd.Timestamp(et.date()) + pd.Timedelta(hours=17)
    deadline = force if hold is None else min(et + pd.Timedelta(minutes=hold), force)
    times = cache['times']
    di = cache['idxmap'].get(int(deadline.value))
    exact = di is not None
    if di is None:
        di = int(np.searchsorted(times, int(deadline.value), side='right') - 1)
    if di < ei or di >= len(m1) or cache['date'][di] != cache['date'][ei]:
        return None

    raw_exit = float(cache['open'][di]) if exact else float(cache['close'][di])
    xi = di
    reason = 'TIME'
    for j in range(ei, di + 1):
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
    gross_bps = 10000.0 * side * (raw_exit - entry) / entry
    risk_bps = 10000.0 * risk / entry
    return {
        'signal_index': int(i), 'signal_time': str(f.time.iloc[i]), 'entry_time': str(m1.time.iloc[ei]),
        'exit_time': str(m1.time.iloc[xi]), 'entry': entry, 'stop': stop, 'target': target,
        'stop_points': int(stop_points), 'target_r': float(target_r), 'reason': reason,
        'gross_bps': float(gross_bps), 'risk_bps': float(risk_bps),
    }


def execute_indices(f, m1, cache, trade_cache, inst, indices, side, stop_points, target_r, friction_ticks):
    out = []
    busy_until = None
    tick = float(v3.SPECS[inst]['tick'])
    for i in indices:
        i = int(i)
        st = pd.Timestamp(f.time.iloc[i]) + pd.Timedelta(minutes=5)
        if busy_until is not None and st <= busy_until:
            continue
        key = (i, side, int(stop_points), float(target_r))
        if key not in trade_cache:
            trade_cache[key] = raw_trade(f, m1, cache, i, inst, side, stop_points, target_r)
        raw = trade_cache[key]
        if raw is None:
            continue
        tr = dict(raw)
        side_cost_bps = 10000.0 * friction_ticks * tick / float(tr['entry'])
        tr['bps'] = float(tr['gross_bps'] - 2.0 * side_cost_bps)
        tr['r'] = float(tr['bps'] / tr['risk_bps'])
        out.append(tr)
        busy_until = pd.Timestamp(tr['exit_time'])
    return out


def discovery_pass(gross, base, stress):
    return c24.discovery_pass(gross, base, stress)


def forward_eval(gross, base, stress):
    mg = c24.metrics(gross); mb = c24.metrics(base); ms = c24.metrics(stress)
    q10 = c24.bootstrap_q10(base)
    periods = (
        ('2026-03', pd.Timestamp('2026-03-01'), pd.Timestamp('2026-04-01')),
        ('2026-04', pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-01')),
        ('2026-05a', pd.Timestamp('2026-05-01'), pd.Timestamp('2026-05-16')),
    )
    block_base = {}
    block_stress = {}
    for name, start, end in periods:
        block_base[name] = c24.metrics(c24.subset_trades(base, start, end))
        block_stress[name] = c24.metrics(c24.subset_trades(stress, start, end))
    all_base_positive = all(v['total_bps'] > 0 for v in block_base.values())
    all_stress_positive = all(v['total_bps'] > 0 for v in block_stress.values())
    ok = (mb['pf'] >= 2.0 and ms['pf'] >= 1.5 and mb['expectancy_r'] is not None and mb['expectancy_r'] >= 0.30
          and ms['expectancy_r'] is not None and ms['expectancy_r'] >= 0.10 and q10 is not None and q10 > 0
          and mb['n'] >= 30 and mb['days'] >= 15 and all_base_positive and all_stress_positive
          and mb['largest_winner_share'] is not None and mb['largest_winner_share'] <= 0.25
          and mg['total_bps'] >= mb['total_bps'] >= ms['total_bps'])
    return bool(ok), {
        'gross': mg, 'base': mb, 'stress': ms, 'bootstrap_p10_base_r': q10,
        'base_blocks': block_base, 'stress_blocks': block_stress,
        'all_base_blocks_positive': all_base_positive, 'all_stress_blocks_positive': all_stress_positive,
    }


def context_masks(f: pd.DataFrame):
    feats = [x for x in CONTEXT_FEATURES if x in f.columns]
    train = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    states, cuts = v3.fit_states(f, feats, train)
    out = [('NONE', np.ones(len(f), dtype=bool))]
    for feat in feats:
        if feat not in states:
            continue
        for state in v3.feature_search_states(feat):
            mask = v3.rule_mask(states, ((feat, state),), len(f))
            out.append((f'{feat}:{state}', mask))
    return out, cuts


def run(root: Path, inst: str, outdir: Path):
    f, m1, provenance = c24.load_context(root, inst)
    entries, _, _, cache = c24.structural_arrays(f, m1, inst)
    levels = build_levels(f, inst)
    contexts, cuts = context_masks(f)
    tick = float(v3.SPECS[inst]['tick'])
    disc_mask = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    fw_mask = ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy()
    trade_cache = {}
    seen = {}
    candidates = []
    generated = 0

    for side_name, side in (('LONG', 1), ('SHORT', -1)):
        for event in EVENT_TYPES:
            for level_type in LEVEL_TYPES:
                for anchor_mode in ANCHOR_MODES:
                    event_mask, anchor = event_and_anchor(f, inst, level_type, event, side, anchor_mode, levels)
                    if not event_mask.any():
                        continue
                    for sp in STOP_POINTS[inst]:
                        valid = event_mask & stop_valid(entries, anchor, tick, sp, side)
                        if valid[disc_mask].sum() < 5:
                            continue
                        for tr in TARGET_RS:
                            for context_name, cmask in contexts:
                                sig = valid & cmask
                                if sig[disc_mask].sum() < 5:
                                    continue
                                generated += 1
                                digest = hashlib.sha256(np.packbits(sig[disc_mask].astype(np.uint8)).tobytes()).hexdigest()
                                dedupe_key = (side_name, digest, sp, tr)
                                cid = f'{inst}|{side_name}|{event}|{level_type}|{anchor_mode}|SL{sp}|TP{tr:g}R|{context_name}'
                                if dedupe_key in seen:
                                    continue
                                seen[dedupe_key] = cid
                                dix = np.flatnonzero(sig & disc_mask)
                                gross = execute_indices(f, m1, cache, trade_cache, inst, dix, side, sp, tr, 0)
                                base = execute_indices(f, m1, cache, trade_cache, inst, dix, side, sp, tr, 1)
                                stress = execute_indices(f, m1, cache, trade_cache, inst, dix, side, sp, tr, 2)
                                passed, diag = discovery_pass(gross, base, stress)
                                if passed:
                                    candidates.append({
                                        'candidate_id': cid, 'direction': side_name, 'side': side,
                                        'event': event, 'structure': level_type, 'anchor_mode': anchor_mode,
                                        'stop_points': int(sp), 'target_r': float(tr), 'context': context_name,
                                        'discovery_mask_digest': digest, 'discovery': diag,
                                        'signal_mask': sig,
                                    })

    def rank(c):
        d = c['discovery']
        j = d['january_stress']['expectancy_r']; fe = d['february_stress']['expectancy_r']
        ds = d['discovery_stress']; db = d['discovery_base']
        return (-min(j, fe), -ds['pf'], -db['pf'], -ds['expectancy_r'], -ds['days'], c['candidate_id'])

    candidates.sort(key=rank)
    shortlisted = []
    bucket_count = {}
    for c in candidates:
        bucket = (c['direction'], c['event'], c['structure'], c['anchor_mode'], c['context'])
        if bucket_count.get(bucket, 0) >= 3:
            continue
        bucket_count[bucket] = bucket_count.get(bucket, 0) + 1
        shortlisted.append(c)
        if len(shortlisted) >= 60:
            break

    results = []
    survivors = []
    for c in shortlisted:
        sig = c.pop('signal_mask')
        fix = np.flatnonzero(sig & fw_mask)
        side = int(c['side']); sp = int(c['stop_points']); tr = float(c['target_r'])
        gross = execute_indices(f, m1, cache, trade_cache, inst, fix, side, sp, tr, 0)
        base = execute_indices(f, m1, cache, trade_cache, inst, fix, side, sp, tr, 1)
        stress = execute_indices(f, m1, cache, trade_cache, inst, fix, side, sp, tr, 2)
        ok, fw = forward_eval(gross, base, stress)
        row = dict(c)
        row['forward'] = fw
        row['survivor'] = bool(ok)
        results.append(row)
        if ok:
            survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'engine': 'cycle27-fixed-stop-structural-event-v1', 'instrument': inst,
        'point_size': tick, 'stop_points': STOP_POINTS[inst], 'target_rs': TARGET_RS,
        'level_types': LEVEL_TYPES, 'event_types': EVENT_TYPES, 'anchor_modes': ANCHOR_MODES,
        'context_features': CONTEXT_FEATURES, 'generated_candidate_evaluations': generated,
        'deduped_discovery_masks': len(seen), 'discovery_passes': len(candidates),
        'shortlisted': len(shortlisted), 'survivors': len(survivors),
        'quantile_cutpoints': cuts,
        'retired_internal_confirmation_accessed': False, 'true_oos_2025_accessed': False,
        'commission_excluded': True, 'provenance': provenance,
    }
    (outdir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=jsonable) + '\n')
    (outdir / 'shortlist.json').write_text(json.dumps(results, indent=2, default=jsonable) + '\n')
    (outdir / 'survivors.json').write_text(json.dumps(survivors, indent=2, default=jsonable) + '\n')
    report = [
        f'# Cycle 27 — {inst}', '',
        f'- Generated candidate evaluations: **{generated}**',
        f'- Deduped discovery masks: **{len(seen)}**',
        f'- Discovery passes: **{len(candidates)}**',
        f'- Frozen shortlist: **{len(shortlisted)}**',
        f'- Strict survivors: **{len(survivors)}**', '',
        '## Top forward candidates',
    ]
    for r in results[:15]:
        b = r['forward']['base']; s = r['forward']['stress']
        report.append(
            f"- `{r['candidate_id']}` — survivor={r['survivor']}; "
            f"BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}; "
            f"STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}; N={b['n']}, days={b['days']}; "
            f"P10={r['forward']['bootstrap_p10_base_r']}"
        )
    (outdir / 'report.md').write_text('\n'.join(report) + '\n')
    print(json.dumps(manifest, indent=2, default=jsonable))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', type=Path, default=Path('.'))
    p.add_argument('--instrument', choices=('CNYRUBF', 'USDRUBF'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.data_root, a.instrument, a.output)
