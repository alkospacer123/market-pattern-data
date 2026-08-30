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
TARGET_PROFILES = (
    ('T3H60', 3.0, 60), ('T3H120', 3.0, 120),
    ('T4H120', 4.0, 120), ('T4H240', 4.0, 240),
    ('T5H240', 5.0, 240), ('T6EOD', 6.0, None),
)
LEVEL_TYPES = ('PREV_DAY', 'ROLL15', 'ROLL30', 'M1_FRACTAL', 'EQUAL_CLUSTER', 'ROUND', 'OPEN30')
EVENT_TYPES = ('SWEEP_CONFIRM', 'REJECT_FOLLOW', 'BREAK_RETEST_CONFIRM')
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
    if isinstance(v, np.generic): return v.item()
    if isinstance(v, np.ndarray): return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)): return str(v)
    raise TypeError(type(v).__name__)


def session_mask(m1: pd.DataFrame) -> np.ndarray:
    mins = (m1.time.dt.hour * 60 + m1.time.dt.minute).to_numpy()
    return (mins >= 9 * 60) & (mins <= 16 * 60 + 30)


def load_context(root: Path, inst: str):
    m5raw, p5 = v3.load_prefix(root, inst, 'M5')
    m1, p1 = v3.load_prefix(root, inst, 'M1')
    m5, _ = v3.build_features(m5raw, inst, 'M5')
    if m5.time.max() >= FORWARD_END or m1.time.max() >= FORWARD_END:
        raise PermissionError('Cycle28 data fence violated')
    return m5, m1, p5 + p1


def rolling_prior(g: pd.Series, bars: int, kind: str) -> pd.Series:
    z = g.shift(1).rolling(bars, min_periods=max(3, bars // 2))
    return z.max() if kind == 'high' else z.min()


def confirmed_fractal_levels(m1: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    hi_out = np.full(len(m1), np.nan); lo_out = np.full(len(m1), np.nan)
    for _, idx in m1.groupby('date', sort=False).groups.items():
        ix = np.asarray(list(idx), dtype=int)
        h = m1.high.iloc[ix].to_numpy(float); l = m1.low.iloc[ix].to_numpy(float)
        ah = np.full(len(ix), np.nan); al = np.full(len(ix), np.nan)
        for j in range(2, len(ix) - 2):
            if h[j] > h[j-1] and h[j] >= h[j-2] and h[j] > h[j+1] and h[j] >= h[j+2]: ah[j+2] = h[j]
            if l[j] < l[j-1] and l[j] <= l[j-2] and l[j] < l[j+1] and l[j] <= l[j+2]: al[j+2] = l[j]
        hi_out[ix] = pd.Series(ah).ffill().to_numpy(float)
        lo_out[ix] = pd.Series(al).ffill().to_numpy(float)
    return hi_out, lo_out


def equal_cluster_levels(m1: pd.DataFrame, tick: float) -> tuple[np.ndarray, np.ndarray]:
    hi_out = np.full(len(m1), np.nan); lo_out = np.full(len(m1), np.nan)
    tol = 2.0 * tick + 1e-12
    for _, idx in m1.groupby('date', sort=False).groups.items():
        ix = np.asarray(list(idx), dtype=int)
        h = m1.high.iloc[ix].to_numpy(float); l = m1.low.iloc[ix].to_numpy(float)
        for k in range(len(ix)):
            s = max(0, k - 30); fh = np.nan; fl = np.nan
            for b in range(k - 1, s, -1):
                for a in range(b - 1, s - 1, -1):
                    if not np.isfinite(fh) and abs(h[b] - h[a]) <= tol: fh = 0.5 * (h[b] + h[a])
                    if not np.isfinite(fl) and abs(l[b] - l[a]) <= tol: fl = 0.5 * (l[b] + l[a])
                    if np.isfinite(fh) and np.isfinite(fl): break
                if np.isfinite(fh) and np.isfinite(fl): break
            hi_out[ix[k]] = fh; lo_out[ix[k]] = fl
    return hi_out, lo_out


def opening_range_levels(m1: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    hi_out = np.full(len(m1), np.nan); lo_out = np.full(len(m1), np.nan)
    mins_all = (m1.time.dt.hour * 60 + m1.time.dt.minute).to_numpy()
    for _, idx in m1.groupby('date', sort=False).groups.items():
        ix = np.asarray(list(idx), dtype=int); mins = mins_all[ix]
        om = (mins >= 9*60) & (mins <= 9*60 + 29)
        if om.sum() < 10: continue
        oh = float(m1.high.iloc[ix[om]].max()); ol = float(m1.low.iloc[ix[om]].min())
        av = mins >= 9*60 + 30
        hi_out[ix[av]] = oh; lo_out[ix[av]] = ol
    return hi_out, lo_out


def build_levels(m1: pd.DataFrame, inst: str) -> dict[str, dict[str, np.ndarray]]:
    tick = float(v3.SPECS[inst]['tick']); step = float(v3.SPECS[inst]['round_step'])
    daily = m1.groupby('date').agg(dh=('high','max'), dl=('low','min')); prev = daily.shift(1)
    levels = {'PREV_DAY': {'resistance': m1.date.map(prev.dh).to_numpy(float), 'support': m1.date.map(prev.dl).to_numpy(float)}}
    for bars, name in ((15, 'ROLL15'), (30, 'ROLL30')):
        rh = m1.groupby('date', sort=False).high.transform(lambda s,b=bars: rolling_prior(s,b,'high')).to_numpy(float)
        rl = m1.groupby('date', sort=False).low.transform(lambda s,b=bars: rolling_prior(s,b,'low')).to_numpy(float)
        levels[name] = {'resistance': rh, 'support': rl}
    fh, fl = confirmed_fractal_levels(m1); levels['M1_FRACTAL'] = {'resistance': fh, 'support': fl}
    eh, el = equal_cluster_levels(m1, tick); levels['EQUAL_CLUSTER'] = {'resistance': eh, 'support': el}
    close = m1.close.to_numpy(float); eps = tick * 1e-6
    levels['ROUND'] = {'resistance': np.ceil((close + eps) / step) * step, 'support': np.floor((close - eps) / step) * step}
    oh, ol = opening_range_levels(m1); levels['OPEN30'] = {'resistance': oh, 'support': ol}
    return levels


def basic_two_stage_event(m1: pd.DataFrame, inst: str, level: np.ndarray, event: str, side: int):
    tick = float(v3.SPECS[inst]['tick'])
    h = m1.high.to_numpy(float); l = m1.low.to_numpy(float); c = m1.close.to_numpy(float)
    ph = np.r_[np.nan, h[:-1]]; pl = np.r_[np.nan, l[:-1]]; pc = np.r_[np.nan, c[:-1]]; lp = np.r_[np.nan, level[:-1]]
    same = np.r_[False, m1.date.to_numpy()[1:] == m1.date.to_numpy()[:-1]]
    if side == 1:
        if event == 'SWEEP_CONFIRM':
            raw = same & np.isfinite(lp) & (pl <= lp-tick) & (pl >= lp-5*tick) & (pc > lp) & (l >= pl-1e-12) & (c > pc)
        else:
            raw = same & np.isfinite(lp) & (pl <= lp+tick) & (pl >= lp-4*tick) & (pc > lp) & (c > pc) & (c > lp)
        extreme = pl
    else:
        if event == 'SWEEP_CONFIRM':
            raw = same & np.isfinite(lp) & (ph >= lp+tick) & (ph <= lp+5*tick) & (pc < lp) & (h <= ph+1e-12) & (c < pc)
        else:
            raw = same & np.isfinite(lp) & (ph >= lp-tick) & (ph <= lp+4*tick) & (pc < lp) & (c < pc) & (c < lp)
        extreme = ph
    return raw & session_mask(m1), lp, extreme


def break_retest_event(m1: pd.DataFrame, inst: str, level: np.ndarray, side: int):
    tick = float(v3.SPECS[inst]['tick'])
    h = m1.high.to_numpy(float); l = m1.low.to_numpy(float); c = m1.close.to_numpy(float); dates = m1.date.to_numpy()
    raw = np.zeros(len(m1), dtype=bool); anchor_level = np.full(len(m1), np.nan); eligible = session_mask(m1)
    for i in range(2, len(m1)):
        if not eligible[i]: continue
        for j in range(i-1, max(0, i-6), -1):
            if j <= 0 or dates[j] != dates[i] or dates[j-1] != dates[i]: continue
            lv = float(level[j])
            if not np.isfinite(lv): continue
            if side == 1:
                broke = c[j] > lv+tick and c[j-1] <= lv+tick; held = np.all(c[j:i] >= lv-tick) if i > j else True
                retest = l[i] <= lv+2*tick and l[i] >= lv-3*tick and c[i] > lv
            else:
                broke = c[j] < lv-tick and c[j-1] >= lv-tick; held = np.all(c[j:i] <= lv+tick) if i > j else True
                retest = h[i] >= lv-2*tick and h[i] <= lv+3*tick and c[i] < lv
            if broke and held and retest:
                raw[i] = True; anchor_level[i] = lv; break
    return raw, anchor_level, l if side == 1 else h


def event_and_anchor(m1, inst, level_type, event, side, anchor_mode, levels):
    role = ('support' if side == 1 else 'resistance') if event != 'BREAK_RETEST_CONFIRM' else ('resistance' if side == 1 else 'support')
    level = levels[level_type][role]
    if event == 'BREAK_RETEST_CONFIRM': raw, frozen_level, extreme = break_retest_event(m1, inst, level, side)
    else: raw, frozen_level, extreme = basic_two_stage_event(m1, inst, level, event, side)
    return raw, np.asarray(frozen_level if anchor_mode == 'LEVEL' else extreme, float)


def next_entries(m1, cache):
    out = np.full(len(m1), np.nan)
    for i, t in enumerate(m1.time):
        et = pd.Timestamp(t) + pd.Timedelta(minutes=1); ei = cache['idxmap'].get(int(et.value))
        if ei is not None and cache['date'][ei] == m1.date.iloc[i]: out[i] = float(cache['open'][ei])
    return out


def stop_valid(entries, anchor, tick, stop_points, side):
    dist = side * (entries-anchor) / tick; buffer = stop_points-dist
    return np.isfinite(entries) & np.isfinite(anchor) & (dist > 0) & (dist < stop_points) & (buffer >= 1-1e-9) & (buffer <= 3+1e-9)


def m5_context_masks(m5, m1):
    feats = [x for x in CONTEXT_FEATURES if x in m5.columns]; train = ((m5.time >= DISC_START) & (m5.time < DISC_END)).to_numpy(); states, cuts = v3.fit_states(m5, feats, train)
    m5c = (m5.time + pd.Timedelta(minutes=5)).to_numpy(dtype='datetime64[ns]').astype(np.int64); m1c = (m1.time + pd.Timedelta(minutes=1)).to_numpy(dtype='datetime64[ns]').astype(np.int64)
    mapidx = np.searchsorted(m5c, m1c, side='right') - 1; valid = mapidx >= 0; same = np.zeros(len(m1), dtype=bool); vi = np.flatnonzero(valid)
    same[vi] = m5.date.iloc[mapidx[vi]].to_numpy() == m1.date.iloc[vi].to_numpy(); out = [('NONE', np.ones(len(m1), dtype=bool))]
    for feat in feats:
        if feat not in states: continue
        wanted = v3.TIME_STATES if feat == 'clock_bucket' else ('LOW25','HIGH25')
        for state in wanted:
            mm = v3.rule_mask(states, ((feat,state),), len(m5)); mapped = np.zeros(len(m1), dtype=bool); ok = valid & same; mapped[ok] = mm[mapidx[ok]]; out.append((f'{feat}:{state}', mapped))
    return out, cuts


def raw_trade(m1, cache, i, inst, side, stop_points, target_r, hold):
    tick=float(v3.SPECS[inst]['tick']); decision=pd.Timestamp(m1.time.iloc[i]); et=decision+pd.Timedelta(minutes=1); ei=cache['idxmap'].get(int(et.value))
    if ei is None or cache['date'][ei] != m1.date.iloc[i]: return None
    entry=float(cache['open'][ei]); risk=stop_points*tick; stop=entry-side*risk; target=entry+side*target_r*risk; force=pd.Timestamp(et.date())+pd.Timedelta(hours=17); deadline=force if hold is None else min(et+pd.Timedelta(minutes=hold),force)
    di=cache['idxmap'].get(int(deadline.value)); exact=di is not None
    if di is None: di=int(np.searchsorted(cache['times'],int(deadline.value),side='right')-1)
    if di<ei or di>=len(m1) or cache['date'][di]!=cache['date'][ei]: return None
    raw_exit=float(cache['open'][di]) if exact else float(cache['close'][di]); xi=di; reason='TIME'
    for j in range(ei,di+1):
        o=float(cache['open'][j]); h=float(cache['high'][j]); l=float(cache['low'][j])
        if side==1:
            if o<=stop: xi,raw_exit,reason=j,o,'STOP_GAP'; break
            if o>=target: xi,raw_exit,reason=j,target,'TARGET_GAP_CONSERVATIVE'; break
            hs,ht=l<=stop,h>=target
            if hs: xi,raw_exit,reason=j,stop,'STOP_FIRST_TIE' if ht else 'STOP'; break
            if ht: xi,raw_exit,reason=j,target,'TARGET'; break
        else:
            if o>=stop: xi,raw_exit,reason=j,o,'STOP_GAP'; break
            if o<=target: xi,raw_exit,reason=j,target,'TARGET_GAP_CONSERVATIVE'; break
            hs,ht=h>=stop,l<=target
            if hs: xi,raw_exit,reason=j,stop,'STOP_FIRST_TIE' if ht else 'STOP'; break
            if ht: xi,raw_exit,reason=j,target,'TARGET'; break
    gross_bps=10000*side*(raw_exit-entry)/entry; risk_bps=10000*risk/entry
    return {'signal_index':int(i),'signal_time':str(m1.time.iloc[i]),'entry_time':str(m1.time.iloc[ei]),'exit_time':str(m1.time.iloc[xi]),'entry':entry,'stop':stop,'target':target,'stop_points':int(stop_points),'target_r':float(target_r),'hold_minutes':hold,'reason':reason,'gross_bps':float(gross_bps),'risk_bps':float(risk_bps)}


def execute(m1, cache, trade_cache, inst, indices, side, sp, target_r, hold, friction):
    out=[]; busy=None; tick=float(v3.SPECS[inst]['tick'])
    for i in indices:
        i=int(i); st=pd.Timestamp(m1.time.iloc[i])+pd.Timedelta(minutes=1)
        if busy is not None and st<=busy: continue
        key=(i,side,int(sp),float(target_r),hold)
        if key not in trade_cache: trade_cache[key]=raw_trade(m1,cache,i,inst,side,sp,target_r,hold)
        raw=trade_cache[key]
        if raw is None: continue
        tr=dict(raw); cost=10000*friction*tick/float(tr['entry']); tr['bps']=float(tr['gross_bps']-2*cost); tr['r']=float(tr['bps']/tr['risk_bps']); out.append(tr); busy=pd.Timestamp(tr['exit_time'])
    return out


def forward_eval(gross, base, stress):
    mg=c24.metrics(gross); mb=c24.metrics(base); ms=c24.metrics(stress); q10=c24.bootstrap_q10(base)
    periods=(('2026-03',pd.Timestamp('2026-03-01'),pd.Timestamp('2026-04-01')),('2026-04',pd.Timestamp('2026-04-01'),pd.Timestamp('2026-05-01')),('2026-05a',pd.Timestamp('2026-05-01'),pd.Timestamp('2026-05-16')))
    bb={}; ss={}
    for name,s,e in periods: bb[name]=c24.metrics(c24.subset_trades(base,s,e)); ss[name]=c24.metrics(c24.subset_trades(stress,s,e))
    bp=all(v['total_bps']>0 for v in bb.values()); sp=all(v['total_bps']>0 for v in ss.values())
    ok=(mb['pf']>=2 and ms['pf']>=1.5 and mb['expectancy_r'] is not None and mb['expectancy_r']>=.30 and ms['expectancy_r'] is not None and ms['expectancy_r']>=.10 and q10 is not None and q10>0 and mb['n']>=30 and mb['days']>=15 and bp and sp and mb['largest_winner_share'] is not None and mb['largest_winner_share']<=.25 and mg['total_bps']>=mb['total_bps']>=ms['total_bps'])
    return bool(ok),{'gross':mg,'base':mb,'stress':ms,'bootstrap_p10_base_r':q10,'base_blocks':bb,'stress_blocks':ss,'all_base_blocks_positive':bp,'all_stress_blocks_positive':sp}


def run(root:Path,inst:str,outdir:Path):
    m5,m1,prov=load_context(root,inst); levels=build_levels(m1,inst); cache=c24.m1_cache(m1); entries=next_entries(m1,cache); contexts,cuts=m5_context_masks(m5,m1); tick=float(v3.SPECS[inst]['tick'])
    dm=((m1.time>=DISC_START)&(m1.time<DISC_END)).to_numpy(); fm=((m1.time>=DISC_END)&(m1.time<FORWARD_END)).to_numpy(); trade_cache={}; seen={}; passes=[]; generated=0
    for side_name,side in (('LONG',1),('SHORT',-1)):
        for event in EVENT_TYPES:
            for lt in LEVEL_TYPES:
                for am in ANCHOR_MODES:
                    em,anchor=event_and_anchor(m1,inst,lt,event,side,am,levels)
                    if not em.any(): continue
                    for stop in STOP_POINTS[inst]:
                        valid=em&stop_valid(entries,anchor,tick,stop,side)
                        if valid[dm].sum()<5: continue
                        for profile,target_r,hold in TARGET_PROFILES:
                            for ctx,cm in contexts:
                                sig=valid&cm
                                if sig[dm].sum()<5: continue
                                generated+=1; digest=hashlib.sha256(np.packbits(sig[dm].astype(np.uint8)).tobytes()).hexdigest(); key=(side_name,digest,stop,profile); cid=f'{inst}|{side_name}|{event}|{lt}|{am}|SL{stop}|{profile}|{ctx}'
                                if key in seen: continue
                                seen[key]=cid; ix=np.flatnonzero(sig&dm)
                                g=execute(m1,cache,trade_cache,inst,ix,side,stop,target_r,hold,0); b=execute(m1,cache,trade_cache,inst,ix,side,stop,target_r,hold,1); s=execute(m1,cache,trade_cache,inst,ix,side,stop,target_r,hold,2); ok,diag=c24.discovery_pass(g,b,s)
                                if ok: passes.append({'candidate_id':cid,'direction':side_name,'side':side,'event':event,'structure':lt,'anchor_mode':am,'stop_points':int(stop),'profile':profile,'target_r':float(target_r),'hold_minutes':hold,'context':ctx,'discovery_mask_digest':digest,'discovery':diag,'signal_mask':sig})
    def rank(c):
        d=c['discovery']; j=d['january_stress']['expectancy_r']; fe=d['february_stress']['expectancy_r']; ds=d['discovery_stress']; db=d['discovery_base']; return(-min(j,fe),-ds['pf'],-db['pf'],-ds['expectancy_r'],-ds['days'],c['candidate_id'])
    passes.sort(key=rank); short=[]; buckets={}
    for c in passes:
        bucket=(c['direction'],c['event'],c['structure'],c['anchor_mode'],c['context'])
        if buckets.get(bucket,0)>=3: continue
        buckets[bucket]=buckets.get(bucket,0)+1; short.append(c)
        if len(short)>=60: break
    results=[]; surv=[]
    for c in short:
        sig=c.pop('signal_mask'); ix=np.flatnonzero(sig&fm); side=int(c['side']); stop=int(c['stop_points']); target=float(c['target_r']); hold=c['hold_minutes']
        g=execute(m1,cache,trade_cache,inst,ix,side,stop,target,hold,0); b=execute(m1,cache,trade_cache,inst,ix,side,stop,target,hold,1); s=execute(m1,cache,trade_cache,inst,ix,side,stop,target,hold,2); ok,fw=forward_eval(g,b,s); row=dict(c); row['forward']=fw; row['survivor']=bool(ok); results.append(row)
        if ok: surv.append(row)
    outdir.mkdir(parents=True,exist_ok=True); manifest={'engine':'cycle28-m1-fixed-stop-micro-v1','instrument':inst,'point_size':tick,'stop_points':STOP_POINTS[inst],'target_profiles':TARGET_PROFILES,'level_types':LEVEL_TYPES,'event_types':EVENT_TYPES,'anchor_modes':ANCHOR_MODES,'contexts_searched':len(contexts),'generated_candidate_evaluations':generated,'deduped_discovery_masks':len(seen),'discovery_passes':len(passes),'shortlisted':len(short),'survivors':len(surv),'m5_quantile_cutpoints':cuts,'retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,'commission_excluded':True,'provenance':prov}
    (outdir/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=jsonable)+'\n'); (outdir/'shortlist.json').write_text(json.dumps(results,indent=2,default=jsonable)+'\n'); (outdir/'survivors.json').write_text(json.dumps(surv,indent=2,default=jsonable)+'\n')
    report=[f'# Cycle 28 — {inst}','',f'- Generated candidate evaluations: **{generated}**',f'- Deduped discovery masks: **{len(seen)}**',f'- Discovery passes: **{len(passes)}**',f'- Frozen shortlist: **{len(short)}**',f'- Strict survivors: **{len(surv)}**','','## Top forward candidates']
    for r in results[:15]:
        b=r['forward']['base']; s=r['forward']['stress']; report.append(f"- `{r['candidate_id']}` — survivor={r['survivor']}; BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}; STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}; N={b['n']}, days={b['days']}; P10={r['forward']['bootstrap_p10_base_r']}")
    (outdir/'report.md').write_text('\n'.join(report)+'\n'); print(json.dumps(manifest,indent=2,default=jsonable))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--data-root',type=Path,default=Path('.')); p.add_argument('--instrument',choices=('CNYRUBF','USDRUBF'),required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); run(a.data_root,a.instrument,a.output)
