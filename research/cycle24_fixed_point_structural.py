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
STOP_POINTS = {
    'CNYRUBF': (4, 6, 8, 10),
    'USDRUBF': (6, 9, 12, 15),
}
TARGET_RS = (3.5, 4.0, 5.0, 6.0)
HOLD_MINUTES = {3.5: 90, 4.0: 120, 5.0: 240, 6.0: None}
STOP_ANCHORS = ('EXT5', 'EXT15', 'EXT30', 'FRACTAL', 'ROUND_RETEST')
TARGET_CONTEXTS = ('EXT30', 'EXT60', 'ROUND_NEXT', 'PREV_DAY')


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


v3 = mod('research/autonomous_search_v3.py', 'v3')


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
    return (mins >= 9 * 60) & (mins <= 16 * 60 + 50)


def load_context(root: Path, inst: str):
    m5raw, p5 = v3.load_prefix(root, inst, 'M5')
    m1, p1 = v3.load_prefix(root, inst, 'M1')
    f, _ = v3.build_features(m5raw, inst, 'M5')
    if f.time.max() >= FORWARD_END or m1.time.max() >= FORWARD_END:
        raise PermissionError('Cycle24 data fence violated')
    return f, m1, p5 + p1


def m1_cache(m1: pd.DataFrame):
    times = m1.time.to_numpy(dtype='datetime64[ns]').astype(np.int64)
    idxmap = {int(t): i for i, t in enumerate(times)}
    return {
        'times': times,
        'idxmap': idxmap,
        'open': m1.open.to_numpy(float),
        'high': m1.high.to_numpy(float),
        'low': m1.low.to_numpy(float),
        'close': m1.close.to_numpy(float),
        'date': m1.date.to_numpy(),
    }


def prev_day_levels(f: pd.DataFrame):
    daily = f.groupby('date', sort=False).agg(high=('high', 'max'), low=('low', 'min'))
    prev = daily.shift(1)
    pdh = f.date.map(prev.high).to_numpy(float)
    pdl = f.date.map(prev.low).to_numpy(float)
    return pdh, pdl


def confirmed_fractal(low: np.ndarray, high: np.ndarray, start: int, end_exclusive: int, side: int):
    lo = max(start + 2, 2)
    hi = min(end_exclusive - 2, len(low) - 2)
    if hi <= lo:
        return np.nan
    if side == 1:
        for j in range(hi - 1, lo - 1, -1):
            x = low[j]
            if x < low[j - 1] and x <= low[j - 2] and x < low[j + 1] and x <= low[j + 2]:
                return float(x)
    else:
        for j in range(hi - 1, lo - 1, -1):
            x = high[j]
            if x > high[j - 1] and x >= high[j - 2] and x > high[j + 1] and x >= high[j + 2]:
                return float(x)
    return np.nan


def nearest_round(entry: float, step: float, side: int, behind: bool):
    eps = 1e-12
    if behind:
        if side == 1:
            lvl = math.floor((entry - eps) / step) * step
        else:
            lvl = math.ceil((entry + eps) / step) * step
    else:
        if side == 1:
            lvl = math.ceil((entry + eps) / step) * step
        else:
            lvl = math.floor((entry - eps) / step) * step
    return float(lvl)


def structural_arrays(f: pd.DataFrame, m1: pd.DataFrame, inst: str):
    n = len(f)
    cache = m1_cache(m1)
    step = float(v3.SPECS[inst]['round_step'])
    pdh, pdl = prev_day_levels(f)
    entries = np.full(n, np.nan)
    stop_anchor = {(sn, a): np.full(n, np.nan) for sn in ('LONG', 'SHORT') for a in STOP_ANCHORS}
    target_obj = {(sn, c): np.full(n, np.nan) for sn in ('LONG', 'SHORT') for c in TARGET_CONTEXTS}
    eligible = session_mask(f)
    op, hi, lo, dates = cache['open'], cache['high'], cache['low'], cache['date']
    idxmap = cache['idxmap']

    for i in np.flatnonzero(eligible):
        decision = pd.Timestamp(f.time.iloc[i])
        et = decision + pd.Timedelta(minutes=5)
        ei = idxmap.get(int(et.value))
        if ei is None or ei <= 0 or dates[ei] != f.date.iloc[i]:
            continue
        entry = float(op[ei])
        entries[i] = entry
        day = dates[ei]
        day_start = ei
        while day_start > 0 and dates[day_start - 1] == day:
            day_start -= 1

        for side_name, side in (('LONG', 1), ('SHORT', -1)):
            for w, name in ((5, 'EXT5'), (15, 'EXT15'), (30, 'EXT30')):
                s = max(day_start, ei - w)
                if ei - s < min(w, 3):
                    continue
                anchor = float(np.min(lo[s:ei])) if side == 1 else float(np.max(hi[s:ei]))
                stop_anchor[(side_name, name)][i] = anchor

            s30 = max(day_start, ei - 30)
            stop_anchor[(side_name, 'FRACTAL')][i] = confirmed_fractal(lo, hi, s30, ei, side)

            rbehind = nearest_round(entry, step, side, behind=True)
            s = max(day_start, ei - 30)
            if ei > s:
                touched = bool(np.any((lo[s:ei] <= rbehind + 1e-12) & (hi[s:ei] >= rbehind - 1e-12)))
                if touched:
                    stop_anchor[(side_name, 'ROUND_RETEST')][i] = rbehind

            for w, name in ((30, 'EXT30'), (60, 'EXT60')):
                s = max(day_start, ei - w)
                if ei - s < min(w, 5):
                    continue
                obj = float(np.max(hi[s:ei])) if side == 1 else float(np.min(lo[s:ei]))
                target_obj[(side_name, name)][i] = obj
            target_obj[(side_name, 'ROUND_NEXT')][i] = nearest_round(entry, step, side, behind=False)
            prev_level = pdh[i] if side == 1 else pdl[i]
            target_obj[(side_name, 'PREV_DAY')][i] = float(prev_level) if np.isfinite(prev_level) else np.nan

    return entries, stop_anchor, target_obj, cache


def stop_valid_mask(entries, anchor, tick: float, stop_points: int, side: int):
    dist = side * (entries - anchor) / tick
    buffer = stop_points - dist
    max_buffer = min(4, max(1, int(round(stop_points * 0.25))))
    return (np.isfinite(entries) & np.isfinite(anchor) & (dist > 0) & (dist < stop_points)
            & (buffer >= 1.0 - 1e-9) & (buffer <= max_buffer + 1e-9))


def target_valid_mask(entries, obj, tick: float, stop_points: int, target_r: float, side: int):
    risk = stop_points * tick
    dist_r = side * (obj - entries) / risk
    return (np.isfinite(entries) & np.isfinite(obj) & (dist_r >= target_r - 1e-12)
            & (dist_r <= target_r + 1.0 + 1e-12))


def onset(f: pd.DataFrame, raw: np.ndarray) -> np.ndarray:
    active = raw & session_mask(f)
    prev = np.r_[False, active[:-1]]
    same = np.r_[False, f.date.to_numpy()[1:] == f.date.to_numpy()[:-1]]
    return active & ~(prev & same)


def fixed_trade(f: pd.DataFrame, m1: pd.DataFrame, cache: dict, i: int, inst: str, side: int,
                stop_points: int, target_r: float, friction_ticks: int):
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
    cost_side_bps = 10000.0 * friction_ticks * tick / entry
    bps = gross_bps - 2.0 * cost_side_bps
    rval = bps / risk_bps
    return {
        'signal_index': int(i), 'signal_time': str(f.time.iloc[i]), 'entry_time': str(m1.time.iloc[ei]),
        'exit_time': str(m1.time.iloc[xi]), 'entry': entry, 'stop': stop, 'target': target,
        'stop_points': int(stop_points), 'target_r': float(target_r), 'reason': reason,
        'gross_bps': float(gross_bps), 'bps': float(bps), 'r': float(rval),
    }


def execute_indices(f, m1, cache, inst, indices, side, stop_points, target_r, friction_ticks):
    out = []
    busy_until = None
    for i in indices:
        st = pd.Timestamp(f.time.iloc[int(i)]) + pd.Timedelta(minutes=5)
        if busy_until is not None and st <= busy_until:
            continue
        tr = fixed_trade(f, m1, cache, int(i), inst, side, stop_points, target_r, friction_ticks)
        if tr is None:
            continue
        out.append(tr)
        busy_until = pd.Timestamp(tr['exit_time'])
    return out


def metrics(trades):
    if not trades:
        return {'n': 0, 'pf': 0.0, 'expectancy_bps': None, 'expectancy_r': None, 'days': 0,
                'largest_winner_share': None, 'total_bps': 0.0}
    b = np.array([x['bps'] for x in trades], float)
    r = np.array([x['r'] for x in trades], float)
    gp = b[b > 0].sum(); gl = -b[b < 0].sum()
    pf = float(gp / gl) if gl > 0 else (float('inf') if gp > 0 else 0.0)
    w = b[b > 0]
    share = float(w.max() / w.sum()) if len(w) else None
    days = len({str(x['signal_time'])[:10] for x in trades})
    return {'n': int(len(trades)), 'pf': pf, 'expectancy_bps': float(b.mean()), 'expectancy_r': float(r.mean()),
            'days': int(days), 'largest_winner_share': share, 'total_bps': float(b.sum())}


def subset_trades(trades, start: pd.Timestamp, end: pd.Timestamp):
    return [x for x in trades if start <= pd.Timestamp(x['signal_time']) < end]


def month_positive_count(trades):
    by = {}
    for x in trades:
        k = pd.Timestamp(x['signal_time']).strftime('%Y-%m')
        by.setdefault(k, 0.0)
        by[k] += float(x['bps'])
    return sum(v > 0 for v in by.values()), by


def bootstrap_q10(trades):
    if not trades:
        return None
    by = {}
    for x in trades:
        d = str(x['signal_time'])[:10]
        by.setdefault(d, []).append(float(x['r']))
    dates = np.array(sorted(by), dtype=object)
    if len(dates) < 2:
        return None
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_REPS)
    for k in range(BOOTSTRAP_REPS):
        sample = rng.choice(dates, size=len(dates), replace=True)
        vals = np.concatenate([np.asarray(by[d], float) for d in sample])
        means[k] = vals.mean()
    return float(np.quantile(means, 0.10))


def discovery_pass(gross, base, stress):
    jan_b = metrics(subset_trades(base, DISC_START, JAN_END)); jan_s = metrics(subset_trades(stress, DISC_START, JAN_END))
    feb_b = metrics(subset_trades(base, JAN_END, DISC_END)); feb_s = metrics(subset_trades(stress, JAN_END, DISC_END))
    db = metrics(subset_trades(base, DISC_START, DISC_END)); ds = metrics(subset_trades(stress, DISC_START, DISC_END)); dg = metrics(subset_trades(gross, DISC_START, DISC_END))
    def mo_ok(b, s):
        return (b['n'] >= 5 and b['days'] >= 4 and b['pf'] >= 1.20 and b['expectancy_r'] is not None
                and b['expectancy_r'] > 0 and s['expectancy_r'] is not None and s['expectancy_r'] > 0)
    ok = (mo_ok(jan_b, jan_s) and mo_ok(feb_b, feb_s) and db['n'] >= 14 and db['days'] >= 9
          and db['pf'] >= 2.0 and ds['pf'] >= 1.40 and db['expectancy_r'] is not None and db['expectancy_r'] >= 0.30
          and ds['expectancy_r'] is not None and ds['expectancy_r'] >= 0.10 and db['expectancy_bps'] is not None
          and db['expectancy_bps'] > 0 and ds['expectancy_bps'] is not None and ds['expectancy_bps'] > 0
          and db['largest_winner_share'] is not None and db['largest_winner_share'] <= 0.35
          and dg['total_bps'] >= db['total_bps'] >= ds['total_bps'])
    return bool(ok), {'january_base': jan_b, 'january_stress': jan_s, 'february_base': feb_b,
                      'february_stress': feb_s, 'discovery_gross': dg, 'discovery_base': db, 'discovery_stress': ds}


def forward_eval(gross, base, stress):
    fg = subset_trades(gross, DISC_END, FORWARD_END); fb = subset_trades(base, DISC_END, FORWARD_END); fs = subset_trades(stress, DISC_END, FORWARD_END)
    mg, mb, ms = metrics(fg), metrics(fb), metrics(fs)
    bp, bmonths = month_positive_count(fb); sp, smonths = month_positive_count(fs); q10 = bootstrap_q10(fb)
    ok = (mb['pf'] >= 2.0 and ms['pf'] >= 1.5 and mb['expectancy_r'] is not None and mb['expectancy_r'] >= 0.30
          and ms['expectancy_r'] is not None and ms['expectancy_r'] >= 0.10 and q10 is not None and q10 > 0
          and mb['n'] >= 20 and mb['days'] >= 12 and bp >= 2 and sp >= 2 and mb['largest_winner_share'] is not None
          and mb['largest_winner_share'] <= 0.30 and mg['total_bps'] >= mb['total_bps'] >= ms['total_bps'])
    return bool(ok), {'gross': mg, 'base': mb, 'stress': ms, 'bootstrap_p10_base_r': q10,
                      'positive_base_months': bp, 'positive_stress_months': sp,
                      'base_months': bmonths, 'stress_months': smonths}


def run(root: Path, inst: str, outdir: Path):
    f, m1, provenance = load_context(root, inst)
    entries, stop_anchors, target_objs, cache = structural_arrays(f, m1, inst)
    tick = float(v3.SPECS[inst]['tick'])
    candidates = []
    seen_masks = {}

    for side_name, side in (('LONG', 1), ('SHORT', -1)):
        for anchor_type in STOP_ANCHORS:
            anchor = stop_anchors[(side_name, anchor_type)]
            for sp in STOP_POINTS[inst]:
                sm = stop_valid_mask(entries, anchor, tick, sp, side)
                if not sm.any():
                    continue
                for ctx in TARGET_CONTEXTS:
                    obj = target_objs[(side_name, ctx)]
                    for tr in TARGET_RS:
                        tm = target_valid_mask(entries, obj, tick, sp, tr, side)
                        sig = onset(f, sm & tm & session_mask(f))
                        digest = hashlib.sha256(np.packbits(sig.astype(np.uint8)).tobytes()).hexdigest()
                        cid = f'{inst}|{side_name}|{anchor_type}|SL{sp}|{ctx}|TP{tr:g}R'
                        if digest in seen_masks:
                            continue
                        seen_masks[digest] = cid
                        ix = np.flatnonzero(sig)
                        if len(ix) < 5:
                            continue
                        gross = execute_indices(f, m1, cache, inst, ix, side, sp, tr, 0)
                        base = execute_indices(f, m1, cache, inst, ix, side, sp, tr, 1)
                        stress = execute_indices(f, m1, cache, inst, ix, side, sp, tr, 2)
                        passed, diag = discovery_pass(gross, base, stress)
                        if passed:
                            candidates.append({'candidate_id': cid, 'direction': side_name, 'side': side,
                                               'stop_anchor': anchor_type, 'stop_points': sp,
                                               'target_context': ctx, 'target_r': tr, 'mask_digest': digest,
                                               'discovery': diag, 'gross_trades': gross,
                                               'base_trades': base, 'stress_trades': stress})

    def rank(c):
        d = c['discovery']; j = d['january_stress']['expectancy_r']; fe = d['february_stress']['expectancy_r']
        ds = d['discovery_stress']; db = d['discovery_base']
        return (-min(j, fe), -ds['pf'], -db['pf'], -ds['expectancy_r'], -ds['days'], c['candidate_id'])
    candidates.sort(key=rank)

    shortlisted = []
    mask_dir_count = {}
    for c in candidates:
        key = (c['mask_digest'], c['direction'])
        count = mask_dir_count.get(key, 0)
        if count >= 2:
            continue
        mask_dir_count[key] = count + 1
        shortlisted.append(c)
        if len(shortlisted) >= 40:
            break

    results = []
    survivors = []
    for c in shortlisted:
        ok, fw = forward_eval(c['gross_trades'], c['base_trades'], c['stress_trades'])
        row = {k: v for k, v in c.items() if not k.endswith('_trades')}
        row['forward'] = fw; row['survivor'] = bool(ok)
        results.append(row)
        if ok:
            survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'engine': 'cycle24-fixed-point-structural-v1', 'instrument': inst, 'point_size': tick,
        'stop_points': STOP_POINTS[inst], 'target_rs': TARGET_RS, 'stop_anchors': STOP_ANCHORS,
        'target_contexts': TARGET_CONTEXTS, 'candidate_masks': len(seen_masks),
        'discovery_passes': len(candidates), 'shortlisted': len(shortlisted), 'survivors': len(survivors),
        'retired_internal_confirmation_accessed': False, 'true_oos_2025_accessed': False,
        'commission_excluded': True, 'provenance': provenance,
    }
    (outdir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=jsonable) + '\n')
    (outdir / 'shortlist.json').write_text(json.dumps(results, indent=2, default=jsonable) + '\n')
    (outdir / 'survivors.json').write_text(json.dumps(survivors, indent=2, default=jsonable) + '\n')
    report = [f'# Cycle 24 — {inst}', '', f'- Candidate masks: **{len(seen_masks)}**',
              f'- Discovery passes: **{len(candidates)}**', f'- Frozen shortlist: **{len(shortlisted)}**',
              f'- Strict survivors: **{len(survivors)}**', '', '## Top forward candidates']
    for r in results[:10]:
        b = r['forward']['base']; s = r['forward']['stress']
        report.append(f"- `{r['candidate_id']}` — survivor={r['survivor']}; BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}; STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}; N={b['n']}, days={b['days']}")
    (outdir / 'report.md').write_text('\n'.join(report) + '\n')
    print(json.dumps(manifest, indent=2, default=jsonable))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data-root', type=Path, default=Path('.'))
    p.add_argument('--instrument', choices=('CNYRUBF', 'USDRUBF'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.data_root, a.instrument, a.output)
