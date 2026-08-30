from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp('2026-01-05')
JAN_END = pd.Timestamp('2026-02-01')
DISC_END = pd.Timestamp('2026-03-01')
FORWARD_END = pd.Timestamp('2026-05-16')
STOP_POINTS = {'CNYRUBF': (6, 8, 10), 'USDRUBF': (6, 9, 12, 15)}
BUFFERS = (1, 2, 3)
TTLS = (15, 30)
TARGET_RS = (3.0, 4.0, 5.0, 6.0)
HOLD_MINUTES = {3.0: 120, 4.0: 180, 5.0: 240, 6.0: None}


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c27 = mod('research/cycle27_fixed_stop_structural_event.py', 'c27')
c24 = c27.c24
v3 = c27.v3


def jsonable(v):
    if isinstance(v, np.generic): return v.item()
    if isinstance(v, np.ndarray): return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)): return str(v)
    raise TypeError(type(v).__name__)


def allowed_contexts(f: pd.DataFrame):
    all_contexts, cuts = c27.context_masks(f)
    keep = []
    for name, mask in all_contexts:
        if name == 'NONE' or name.startswith('clock_bucket:') or name.endswith(':LOW25') or name.endswith(':HIGH25'):
            keep.append((name, mask))
    return keep, cuts


def derived_limit(anchor: float, tick: float, side: int, stop_points: int, buffer_ticks: int) -> float:
    return float(anchor + side * (stop_points - buffer_ticks) * tick)


def simulate_order(f: pd.DataFrame, m1: pd.DataFrame, cache: dict, i: int, inst: str, side: int,
                   anchor: float, stop_points: int, buffer_ticks: int, ttl_minutes: int,
                   target_r: float, mode_ticks: int):
    tick = float(v3.SPECS[inst]['tick'])
    if not np.isfinite(anchor): return None, None
    setup_close = float(f.close.iloc[i])
    limit = derived_limit(float(anchor), tick, side, stop_points, buffer_ticks)
    if side == 1 and not setup_close > limit + 1e-12: return None, None
    if side == -1 and not setup_close < limit - 1e-12: return None, None

    order_start = pd.Timestamp(f.time.iloc[i]) + pd.Timedelta(minutes=5)
    force = pd.Timestamp(order_start.date()) + pd.Timedelta(hours=17)
    expiry = min(order_start + pd.Timedelta(minutes=ttl_minutes), force)
    if order_start >= force: return None, None

    times = cache['times']
    start_idx = int(np.searchsorted(times, int(order_start.value), side='left'))
    end_idx = int(np.searchsorted(times, int(expiry.value), side='left'))
    if start_idx >= len(m1) or start_idx >= end_idx or cache['date'][start_idx] != f.date.iloc[i]:
        return None, expiry

    fill_idx = None
    through = mode_ticks * tick
    for j in range(start_idx, min(end_idx, len(m1))):
        if cache['date'][j] != f.date.iloc[i]: break
        if side == 1:
            qualified = float(cache['low'][j]) <= limit - through + 1e-12
        else:
            qualified = float(cache['high'][j]) >= limit + through - 1e-12
        if qualified:
            fill_idx = j
            break
    if fill_idx is None:
        return None, expiry

    risk = stop_points * tick
    stop = limit - side * risk
    target = limit + side * target_r * risk
    hold = HOLD_MINUTES[float(target_r)]
    deadline = force if hold is None else min(pd.Timestamp(cache['times'][fill_idx]) + pd.Timedelta(minutes=hold), force)
    di = cache['idxmap'].get(int(deadline.value))
    exact = di is not None
    if di is None:
        di = int(np.searchsorted(times, int(deadline.value), side='right') - 1)
    if di < fill_idx or di >= len(m1) or cache['date'][di] != cache['date'][fill_idx]:
        return None, expiry

    # Fill bar: never credit target because pre/post-fill ordering is unknowable.
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
        'order_start': str(order_start), 'entry_time': str(m1.time.iloc[fill_idx]),
        'exit_time': str(m1.time.iloc[int(xi)]), 'entry': limit,
        'anchor': float(anchor), 'anchor_buffer_ticks': int(buffer_ticks),
        'stop': stop, 'target': target, 'stop_points': int(stop_points),
        'target_r': float(target_r), 'ttl_minutes': int(ttl_minutes),
        'fill_through_ticks': int(mode_ticks), 'exit_friction_ticks': int(mode_ticks),
        'reason': reason, 'gross_bps': float(gross_bps), 'bps': float(bps),
        'risk_bps': float(risk_bps), 'r': float(bps / risk_bps),
    }
    return tr, pd.Timestamp(tr['exit_time'])


def execute_candidate(f, m1, cache, inst, indices, anchors, side, stop_points, buffer_ticks,
                      ttl_minutes, target_r, mode_ticks):
    trades = []
    busy_until = None
    for i in indices:
        i = int(i)
        order_start = pd.Timestamp(f.time.iloc[i]) + pd.Timedelta(minutes=5)
        if busy_until is not None and order_start <= busy_until:
            continue
        tr, occupied_until = simulate_order(
            f, m1, cache, i, inst, side, float(anchors[i]), stop_points,
            buffer_ticks, ttl_minutes, target_r, mode_ticks,
        )
        if occupied_until is not None:
            busy_until = occupied_until
        if tr is not None:
            trades.append(tr)
    return trades


def discovery_pass(gross, base, stress):
    jan_b = c24.metrics(c24.subset_trades(base, DISC_START, JAN_END))
    jan_s = c24.metrics(c24.subset_trades(stress, DISC_START, JAN_END))
    feb_b = c24.metrics(c24.subset_trades(base, JAN_END, DISC_END))
    feb_s = c24.metrics(c24.subset_trades(stress, JAN_END, DISC_END))
    db = c24.metrics(c24.subset_trades(base, DISC_START, DISC_END))
    ds = c24.metrics(c24.subset_trades(stress, DISC_START, DISC_END))
    dg = c24.metrics(c24.subset_trades(gross, DISC_START, DISC_END))

    def month_ok(b, s):
        stress_ok = s['n'] == 0 or (s['expectancy_r'] is not None and s['expectancy_r'] > 0)
        return (b['n'] >= 5 and b['days'] >= 4 and b['pf'] >= 1.20
                and b['expectancy_r'] is not None and b['expectancy_r'] > 0 and stress_ok)

    ratio = ds['n'] / db['n'] if db['n'] else 0.0
    ok = (month_ok(jan_b, jan_s) and month_ok(feb_b, feb_s)
          and db['n'] >= 14 and db['days'] >= 9 and ds['n'] >= 10 and ratio >= 0.50
          and db['pf'] >= 2.00 and ds['pf'] >= 1.40
          and db['expectancy_r'] is not None and db['expectancy_r'] >= 0.30
          and ds['expectancy_r'] is not None and ds['expectancy_r'] >= 0.10
          and db['expectancy_bps'] is not None and db['expectancy_bps'] > 0
          and ds['expectancy_bps'] is not None and ds['expectancy_bps'] > 0
          and db['largest_winner_share'] is not None and db['largest_winner_share'] <= 0.35)
    return bool(ok), {
        'january_base': jan_b, 'january_stress': jan_s,
        'february_base': feb_b, 'february_stress': feb_s,
        'discovery_gross': dg, 'discovery_base': db, 'discovery_stress': ds,
        'stress_base_trade_ratio': float(ratio),
    }


def forward_eval(gross, base, stress):
    mg = c24.metrics(gross); mb = c24.metrics(base); ms = c24.metrics(stress)
    q10 = c24.bootstrap_q10(base)
    periods = (
        ('2026-03', pd.Timestamp('2026-03-01'), pd.Timestamp('2026-04-01')),
        ('2026-04', pd.Timestamp('2026-04-01'), pd.Timestamp('2026-05-01')),
        ('2026-05a', pd.Timestamp('2026-05-01'), pd.Timestamp('2026-05-16')),
    )
    bb = {}; ss = {}
    for name, start, end in periods:
        bb[name] = c24.metrics(c24.subset_trades(base, start, end))
        ss[name] = c24.metrics(c24.subset_trades(stress, start, end))
    base_blocks = all(x['total_bps'] > 0 for x in bb.values())
    stress_blocks = all(x['total_bps'] > 0 for x in ss.values())
    ratio = ms['n'] / mb['n'] if mb['n'] else 0.0
    ok = (mb['pf'] >= 2.00 and ms['pf'] >= 1.50
          and mb['expectancy_r'] is not None and mb['expectancy_r'] >= 0.30
          and ms['expectancy_r'] is not None and ms['expectancy_r'] >= 0.10
          and q10 is not None and q10 > 0
          and mb['n'] >= 30 and mb['days'] >= 15 and ms['n'] >= 20 and ratio >= 0.50
          and base_blocks and stress_blocks
          and mb['largest_winner_share'] is not None and mb['largest_winner_share'] <= 0.25)
    return bool(ok), {
        'gross': mg, 'base': mb, 'stress': ms,
        'bootstrap_p10_base_r': q10, 'stress_base_trade_ratio': float(ratio),
        'base_blocks': bb, 'stress_blocks': ss,
        'all_base_blocks_positive': base_blocks, 'all_stress_blocks_positive': stress_blocks,
    }


def run(root: Path, inst: str, outdir: Path):
    f, m1, provenance = c24.load_context(root, inst)
    _, _, _, cache = c24.structural_arrays(f, m1, inst)
    levels = c27.build_levels(f, inst)
    contexts, cuts = allowed_contexts(f)
    tick = float(v3.SPECS[inst]['tick'])
    disc_mask = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    fw_mask = ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy()
    generated = 0; seen = {}; candidates = []

    for side_name, side in (('LONG', 1), ('SHORT', -1)):
        for event in c27.EVENT_TYPES:
            for structure in c27.LEVEL_TYPES:
                for anchor_mode in c27.ANCHOR_MODES:
                    event_mask, anchors = c27.event_and_anchor(f, inst, structure, event, side, anchor_mode, levels)
                    if not event_mask.any(): continue
                    for sp in STOP_POINTS[inst]:
                        for buf in BUFFERS:
                            if buf >= sp: continue
                            limits = anchors + side * (sp - buf) * tick
                            passive = np.isfinite(limits) & ((f.close.to_numpy(float) > limits) if side == 1 else (f.close.to_numpy(float) < limits))
                            base_signal = event_mask & passive
                            if base_signal[disc_mask].sum() < 5: continue
                            for ttl in TTLS:
                                for tr in TARGET_RS:
                                    for ctx_name, ctx_mask in contexts:
                                        sig = base_signal & ctx_mask
                                        if sig[disc_mask].sum() < 5: continue
                                        generated += 1
                                        digest = hashlib.sha256(np.packbits(sig[disc_mask].astype(np.uint8)).tobytes()).hexdigest()
                                        key = (side_name, digest, sp, buf, ttl, tr)
                                        cid = f'{inst}|{side_name}|{event}|{structure}|{anchor_mode}|SL{sp}|B{buf}|TTL{ttl}|TP{tr:g}R|{ctx_name}'
                                        if key in seen: continue
                                        seen[key] = cid
                                        ix = np.flatnonzero(sig & disc_mask)
                                        gross = execute_candidate(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,0)
                                        base = execute_candidate(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,1)
                                        stress = execute_candidate(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,2)
                                        passed, diag = discovery_pass(gross, base, stress)
                                        if passed:
                                            candidates.append({
                                                'candidate_id': cid, 'direction': side_name, 'side': side,
                                                'event': event, 'structure': structure, 'anchor_mode': anchor_mode,
                                                'stop_points': sp, 'anchor_buffer_ticks': buf,
                                                'ttl_minutes': ttl, 'target_r': tr, 'context': ctx_name,
                                                'discovery_mask_digest': digest, 'discovery': diag,
                                                'signal_mask': sig, 'anchors': anchors,
                                            })

    def rank(c):
        d = c['discovery']; js = d['january_stress']['expectancy_r']; fs = d['february_stress']['expectancy_r']
        js = -1e9 if js is None else js; fs = -1e9 if fs is None else fs
        ds = d['discovery_stress']; db = d['discovery_base']
        return (-min(js, fs), -ds['pf'], -db['pf'], -(ds['expectancy_r'] or -1e9), -db['days'], c['candidate_id'])

    candidates.sort(key=rank)
    shortlisted = []; bucket_count = {}
    for c in candidates:
        bucket = (c['direction'],c['event'],c['structure'],c['anchor_mode'],c['context'])
        if bucket_count.get(bucket,0) >= 3: continue
        bucket_count[bucket] = bucket_count.get(bucket,0) + 1
        shortlisted.append(c)
        if len(shortlisted) >= 60: break

    results = []; survivors = []
    for c in shortlisted:
        sig = c.pop('signal_mask'); anchors = c.pop('anchors')
        ix = np.flatnonzero(sig & fw_mask)
        side=int(c['side']); sp=int(c['stop_points']); buf=int(c['anchor_buffer_ticks']); ttl=int(c['ttl_minutes']); tr=float(c['target_r'])
        gross=execute_candidate(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,0)
        base=execute_candidate(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,1)
        stress=execute_candidate(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,2)
        ok, fw = forward_eval(gross,base,stress)
        row=dict(c); row['forward']=fw; row['survivor']=bool(ok); results.append(row)
        if ok: survivors.append(row)

    outdir.mkdir(parents=True, exist_ok=True)
    manifest = {
        'engine':'cycle29-structure-aligned-passive-v1','instrument':inst,'point_size':tick,
        'stop_points':STOP_POINTS[inst],'anchor_buffers':BUFFERS,'ttls':TTLS,'target_rs':TARGET_RS,
        'context_count':len(contexts),'generated_candidate_evaluations':generated,
        'deduped_discovery_candidates':len(seen),'discovery_passes':len(candidates),
        'shortlisted':len(shortlisted),'survivors':len(survivors),
        'quantile_cutpoints':cuts,'fill_models':{'GROSS':0,'BASE':1,'STRESS':2},
        'retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,
        'commission_excluded':True,'provenance':provenance,
    }
    (outdir/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=jsonable)+'\n')
    (outdir/'shortlist.json').write_text(json.dumps(results,indent=2,default=jsonable)+'\n')
    (outdir/'survivors.json').write_text(json.dumps(survivors,indent=2,default=jsonable)+'\n')
    report=[f'# Cycle 29 — {inst}','',f'- Generated candidate evaluations: **{generated}**',f'- Discovery passes: **{len(candidates)}**',f'- Frozen shortlist: **{len(shortlisted)}**',f'- Strict survivors: **{len(survivors)}**','','## Top forward candidates']
    for r in results[:20]:
        b=r['forward']['base']; s=r['forward']['stress']
        report.append(f"- `{r['candidate_id']}` — survivor={r['survivor']}; BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}, N={b['n']}; STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}, N={s['n']}; fill ratio={r['forward']['stress_base_trade_ratio']:.3f}; P10={r['forward']['bootstrap_p10_base_r']}")
    (outdir/'report.md').write_text('\n'.join(report)+'\n')
    print(json.dumps(manifest,indent=2,default=jsonable))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--data-root',type=Path,default=Path('.')); p.add_argument('--instrument',choices=('CNYRUBF','USDRUBF'),required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); run(a.data_root,a.instrument,a.output)
