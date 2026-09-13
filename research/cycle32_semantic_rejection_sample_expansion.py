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

PRIMARY_STRUCTURES = ('ROUND', 'ROLL30', 'ROLL60')
STRUCTURE_POOLS = (
    ('ROUND',),
    ('ROLL30',),
    ('ROLL60',),
    ('ROUND', 'ROLL30'),
    ('ROUND', 'ROLL60'),
    ('ROLL30', 'ROLL60'),
    ('ROUND', 'ROLL30', 'ROLL60'),
)
ANCHOR_MODES = ('LEVEL', 'EVENT_EXTREME')
BUFFERS = (1, 2, 3)
TTLS = (15, 30)
TARGET_RS = (4.0, 5.0, 6.0)
STOP_POINTS = {'CNYRUBF': (8, 10), 'USDRUBF': (9, 12)}
CONTEXTS = {
    'SHORT': ('eff_60m:HIGH25', 'pos_60m:HIGH25'),
    'LONG': ('eff_60m:HIGH25', 'pos_60m:LOW25'),
}


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c29 = mod('research/cycle29_structure_aligned_passive.py', 'c29_for_c32')
c27 = c29.c27
c24 = c29.c24
v3 = c29.v3


def jsonable(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)):
        return str(v)
    return c29.jsonable(v)


def pool_name(pool: tuple[str, ...]) -> str:
    return '_OR_'.join(pool)


def selected_contexts(f: pd.DataFrame, side_name: str):
    all_contexts, cuts = c29.allowed_contexts(f)
    mapping = {name: mask for name, mask in all_contexts}
    wanted = []
    for name in CONTEXTS[side_name]:
        if name in mapping:
            wanted.append((name, mapping[name]))
    return wanted, cuts


def pooled_event_and_anchor(f: pd.DataFrame, inst: str, structures: tuple[str, ...], side: int,
                            anchor_mode: str, levels: dict[str, dict[str, np.ndarray]]):
    close = f.close.to_numpy(float)
    masks = []
    anchors = []
    for structure in structures:
        m, a = c27.event_and_anchor(f, inst, structure, 'REJECTION', side, anchor_mode, levels)
        masks.append(np.asarray(m, bool))
        anchors.append(np.asarray(a, float))
    stack_m = np.vstack(masks)
    stack_a = np.vstack(anchors)
    merged = stack_m.any(axis=0)
    chosen = np.full(len(f), np.nan)
    # Deterministic, performance-independent tie-break: use the fired anchor closest to setup close.
    for i in np.flatnonzero(merged):
        js = np.flatnonzero(stack_m[:, i] & np.isfinite(stack_a[:, i]))
        if len(js):
            dist = np.abs(stack_a[js, i] - close[i])
            chosen[i] = stack_a[js[int(np.argmin(dist))], i]
    return merged, chosen, masks, anchors


def passive_signal(f: pd.DataFrame, base_event: np.ndarray, anchors: np.ndarray, side: int,
                   stop_points: int, buffer_ticks: int, tick: float, context_mask: np.ndarray):
    limits = anchors + side * (stop_points - buffer_ticks) * tick
    close = f.close.to_numpy(float)
    passive = np.isfinite(limits) & ((close > limits) if side == 1 else (close < limits))
    return base_event & passive & np.asarray(context_mask, bool)


def execute(f, m1, cache, inst, sig, anchors, side, sp, buf, ttl, tr, mode_ticks, window_mask):
    ix = np.flatnonzero(sig & window_mask)
    return c29.execute_candidate(f, m1, cache, inst, ix, anchors, side, sp, buf, ttl, tr, mode_ticks)


def component_support(f, m1, cache, inst, side, structures, anchor_mode, levels, context_mask,
                      sp, buf, ttl, tr, tick, fw_mask):
    rows = []
    for structure in structures:
        em, anchors = c27.event_and_anchor(f, inst, structure, 'REJECTION', side, anchor_mode, levels)
        sig = passive_signal(f, em, anchors, side, sp, buf, tick, context_mask)
        b = execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,1,fw_mask)
        s = execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,2,fw_mask)
        mb = c24.metrics(b); ms = c24.metrics(s)
        positive = bool(ms['n'] >= 5 and ms['expectancy_r'] is not None and ms['expectancy_r'] > 0)
        rows.append({'structure': structure, 'base': mb, 'stress': ms, 'positive_stress_component': positive})
    return rows


def one_axis_neighbors(inst, sp, buf, ttl, tr):
    out = set()

    def adjacent(values, current):
        values = list(values)
        i = values.index(current)
        r = []
        if i > 0: r.append(values[i - 1])
        if i + 1 < len(values): r.append(values[i + 1])
        return r

    for x in adjacent(STOP_POINTS[inst], sp):
        if buf < x:
            out.add((x,buf,ttl,tr,'stop'))
    for x in adjacent(BUFFERS, buf):
        if x < sp:
            out.add((sp,x,ttl,tr,'buffer'))
    for x in adjacent(TTLS, ttl):
        out.add((sp,buf,x,tr,'ttl'))
    for x in adjacent(TARGET_RS, tr):
        out.add((sp,buf,ttl,x,'target'))
    return sorted(out)


def neighbor_support(f,m1,cache,inst,base_event,anchors,side,context_mask,sp,buf,ttl,tr,tick,fw_mask):
    rows=[]
    for nsp,nbuf,nttl,ntr,axis in one_axis_neighbors(inst,sp,buf,ttl,tr):
        sig=passive_signal(f,base_event,anchors,side,nsp,nbuf,tick,context_mask)
        b=execute(f,m1,cache,inst,sig,anchors,side,nsp,nbuf,nttl,ntr,1,fw_mask)
        s=execute(f,m1,cache,inst,sig,anchors,side,nsp,nbuf,nttl,ntr,2,fw_mask)
        mb=c24.metrics(b); ms=c24.metrics(s)
        positive=bool(ms['n'] >= 5 and ms['expectancy_r'] is not None and ms['expectancy_r'] > 0)
        rows.append({'axis':axis,'stop_points':nsp,'buffer':nbuf,'ttl':nttl,'target_r':ntr,
                     'base':mb,'stress':ms,'positive_stress_neighbor':positive})
    return rows


def rank_key(c):
    d=c['discovery']
    js=d['january_stress']['expectancy_r']; fs=d['february_stress']['expectancy_r']
    js=-1e9 if js is None else js; fs=-1e9 if fs is None else fs
    ds=d['discovery_stress']; db=d['discovery_base']
    # Prefer pooled hypotheses at equal discovery quality, then sample size.
    return (-min(js,fs), -ds['pf'], -db['pf'], -(ds['expectancy_r'] or -1e9), -db['days'], -len(c['structures']), c['candidate_id'])


def run(root: Path, inst: str, outdir: Path):
    f,m1,provenance=c24.load_context(root,inst)
    _,_,_,cache=c24.structural_arrays(f,m1,inst)
    levels=c27.build_levels(f,inst)
    tick=float(v3.SPECS[inst]['tick'])
    disc_mask=((f.time>=DISC_START)&(f.time<DISC_END)).to_numpy()
    fw_mask=((f.time>=DISC_END)&(f.time<FORWARD_END)).to_numpy()
    generated=0; seen={}; candidates=[]; cuts_out={}

    for side_name,side in (('SHORT',-1),('LONG',1)):
        contexts,cuts=selected_contexts(f,side_name)
        cuts_out.update(cuts)
        for structures in STRUCTURE_POOLS:
            for anchor_mode in ANCHOR_MODES:
                base_event,anchors,_,_=pooled_event_and_anchor(f,inst,structures,side,anchor_mode,levels)
                if not base_event.any():
                    continue
                for sp in STOP_POINTS[inst]:
                    for buf in BUFFERS:
                        if buf>=sp: continue
                        for ttl in TTLS:
                            for tr in TARGET_RS:
                                for ctx_name,ctx_mask in contexts:
                                    sig=passive_signal(f,base_event,anchors,side,sp,buf,tick,ctx_mask)
                                    if sig[disc_mask].sum()<5: continue
                                    generated+=1
                                    digest=hashlib.sha256(np.packbits(sig[disc_mask].astype(np.uint8)).tobytes()).hexdigest()
                                    key=(side_name,digest,sp,buf,ttl,tr)
                                    cid=f'{inst}|{side_name}|REJECTION|{pool_name(structures)}|{anchor_mode}|SL{sp}|B{buf}|TTL{ttl}|TP{tr:g}R|{ctx_name}'
                                    if key in seen: continue
                                    seen[key]=cid
                                    g=execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,0,disc_mask)
                                    b=execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,1,disc_mask)
                                    s=execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,2,disc_mask)
                                    passed,diag=c29.discovery_pass(g,b,s)
                                    if passed:
                                        candidates.append({'candidate_id':cid,'direction':side_name,'side':side,
                                            'structures':list(structures),'anchor_mode':anchor_mode,'stop_points':sp,
                                            'anchor_buffer_ticks':buf,'ttl_minutes':ttl,'target_r':tr,'context':ctx_name,
                                            'discovery_mask_digest':digest,'discovery':diag,'signal_mask':sig,
                                            'anchors':anchors,'base_event':base_event,'context_mask':ctx_mask})

    candidates.sort(key=rank_key)
    shortlisted=[]; bucket_count={}
    for c in candidates:
        bucket=(c['direction'],tuple(c['structures']),c['anchor_mode'],c['context'])
        if bucket_count.get(bucket,0)>=3: continue
        bucket_count[bucket]=bucket_count.get(bucket,0)+1
        shortlisted.append(c)
        if len(shortlisted)>=60: break

    results=[]; survivors=[]
    for c in shortlisted:
        sig=c.pop('signal_mask'); anchors=c.pop('anchors'); base_event=c.pop('base_event'); ctx_mask=c.pop('context_mask')
        side=int(c['side']); sp=int(c['stop_points']); buf=int(c['anchor_buffer_ticks']); ttl=int(c['ttl_minutes']); tr=float(c['target_r'])
        g=execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,0,fw_mask)
        b=execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,1,fw_mask)
        s=execute(f,m1,cache,inst,sig,anchors,side,sp,buf,ttl,tr,2,fw_mask)
        strict_ok,fw=c29.forward_eval(g,b,s)
        components=component_support(f,m1,cache,inst,side,tuple(c['structures']),c['anchor_mode'],levels,ctx_mask,sp,buf,ttl,tr,tick,fw_mask)
        semantic_positive=sum(1 for x in components if x['positive_stress_component'])
        neighbors=neighbor_support(f,m1,cache,inst,base_event,anchors,side,ctx_mask,sp,buf,ttl,tr,tick,fw_mask)
        neighbor_positive=sum(1 for x in neighbors if x['positive_stress_neighbor'])
        pooled_eligible=len(c['structures'])>=2
        robust_ok=bool(pooled_eligible and semantic_positive>=2 and neighbor_positive>=2)
        final_ok=bool(strict_ok and robust_ok)
        row=dict(c)
        row['forward']=fw
        row['component_support']=components
        row['positive_stress_components']=semantic_positive
        row['neighbor_support']=neighbors
        row['positive_stress_neighbors']=neighbor_positive
        row['cycle29_gate_pass']=bool(strict_ok)
        row['cluster_robustness_pass']=robust_ok
        row['survivor']=final_ok
        results.append(row)
        if final_ok: survivors.append(row)

    outdir.mkdir(parents=True,exist_ok=True)
    status='SEMANTIC_SAMPLE_EXPANSION_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION' if survivors else 'NO_SEMANTIC_SAMPLE_EXPANSION_RESEARCH_SURVIVOR'
    manifest={'engine':'cycle32-semantic-rejection-sample-expansion-v1','instrument':inst,'status':status,
        'primary_hypothesis_instrument':'CNYRUBF','replication_control_instrument':'USDRUBF',
        'structures':PRIMARY_STRUCTURES,'structure_pools':[list(x) for x in STRUCTURE_POOLS],
        'event':'REJECTION','anchor_modes':ANCHOR_MODES,'stop_points':STOP_POINTS[inst],
        'buffers':BUFFERS,'ttls':TTLS,'target_rs':TARGET_RS,'contexts':CONTEXTS,
        'generated_candidate_evaluations':generated,'deduped_discovery_candidates':len(seen),
        'discovery_passes':len(candidates),'shortlisted':len(shortlisted),'survivors':len(survivors),
        'research_forward_is_not_untouched_confirmation':True,
        'retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,
        'commission_excluded':True,'quantile_cutpoints':cuts_out,'provenance':provenance}
    (outdir/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=jsonable)+'\n',encoding='utf-8')
    (outdir/'shortlist.json').write_text(json.dumps(results,indent=2,default=jsonable)+'\n',encoding='utf-8')
    (outdir/'survivors.json').write_text(json.dumps(survivors,indent=2,default=jsonable)+'\n',encoding='utf-8')
    report=[f'# Cycle 32 — {inst} Semantic Rejection Sample Expansion','',f'Status: **{status}**',
        f'Generated={generated}; deduped={len(seen)}; discovery passes={len(candidates)}; shortlist={len(shortlisted)}; survivors={len(survivors)}','',
        'Mar-May15 is research-only and is not untouched confirmation. Retired May16-Jul1 and TRUE OOS 2025 were not accessed.']
    (outdir/'report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    print(json.dumps({'instrument':inst,'status':status,'generated':generated,'passes':len(candidates),'shortlist':len(shortlisted),'survivors':len(survivors)},indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data-root',type=Path,default=Path('.'))
    p.add_argument('--instrument',choices=('CNYRUBF','USDRUBF'),required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); run(a.data_root,a.instrument,a.output)
