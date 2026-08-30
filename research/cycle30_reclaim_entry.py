from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
import importlib.util

def mod(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); assert s.loader is not None; s.loader.exec_module(m); return m

c29=mod('research/cycle29_structure_aligned_passive.py','c29')
c27=c29.c27; c24=c29.c24; v3=c29.v3
DISC_START=c29.DISC_START; JAN_END=c29.JAN_END; DISC_END=c29.DISC_END; FORWARD_END=c29.FORWARD_END
STOP_POINTS=c29.STOP_POINTS; BUFFERS=c29.BUFFERS; TTLS=c29.TTLS; TARGET_RS=c29.TARGET_RS; HOLD_MINUTES=c29.HOLD_MINUTES

def jsonable(v):
    if isinstance(v,np.generic): return v.item()
    if isinstance(v,np.ndarray): return v.tolist()
    if isinstance(v,(pd.Timestamp,pd.Period)): return str(v)
    raise TypeError(type(v).__name__)

def confirmed_reclaim_trade(f,m1,cache,i,inst,side,anchor,stop_points,buffer_ticks,ttl_minutes,target_r,confirm_ticks):
    tick=float(v3.SPECS[inst]['tick'])
    if not np.isfinite(anchor): return None,None
    probe=c29.derived_limit(float(anchor),tick,side,stop_points,buffer_ticks)
    close=float(f.close.iloc[i])
    if side==1 and not close>probe+1e-12: return None,None
    if side==-1 and not close<probe-1e-12: return None,None
    start=pd.Timestamp(f.time.iloc[i])+pd.Timedelta(minutes=5)
    force=pd.Timestamp(start.date())+pd.Timedelta(hours=17)
    expiry=min(start+pd.Timedelta(minutes=ttl_minutes),force)
    if start>=force: return None,None
    times=cache['times']; si=int(np.searchsorted(times,int(start.value),'left')); ei=int(np.searchsorted(times,int(expiry.value),'left'))
    if si>=len(m1) or si>=ei or cache['date'][si]!=f.date.iloc[i]: return None,expiry
    touch=None
    for j in range(si,min(ei,len(m1))):
        if cache['date'][j]!=f.date.iloc[i]: break
        if side==1:
            ok=float(cache['low'][j])<=probe+1e-12 and float(cache['close'][j])>=probe+confirm_ticks*tick-1e-12
        else:
            ok=float(cache['high'][j])>=probe-1e-12 and float(cache['close'][j])<=probe-confirm_ticks*tick+1e-12
        if ok: touch=j; break
    if touch is None: return None,expiry
    entry_idx=touch+1
    if entry_idx>=len(m1) or cache['date'][entry_idx]!=cache['date'][touch]: return None,expiry
    entry_time=pd.Timestamp(m1.time.iloc[entry_idx])
    if entry_time>=force: return None,expiry
    entry=float(cache['open'][entry_idx]); risk=stop_points*tick
    stop=entry-side*risk
    required_anchor_stop=float(anchor)-side*buffer_ticks*tick
    if side==1 and stop>required_anchor_stop+1e-12: return None,entry_time
    if side==-1 and stop<required_anchor_stop-1e-12: return None,entry_time
    target=entry+side*float(target_r)*risk
    hold=HOLD_MINUTES[float(target_r)]
    deadline=force if hold is None else min(entry_time+pd.Timedelta(minutes=hold),force)
    di=int(np.searchsorted(times,int(deadline.value),'right')-1)
    if di<entry_idx or di>=len(m1) or cache['date'][di]!=cache['date'][entry_idx]: return None,entry_time
    raw_exit=float(cache['close'][di]); xi=di; reason='TIME'
    for j in range(entry_idx,di+1):
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
    raw_bps=10000.0*side*(raw_exit-entry)/entry
    friction_bps=10000.0*confirm_ticks*tick/entry
    bps=raw_bps-friction_bps
    risk_bps=10000.0*risk/entry
    tr={'signal_index':int(i),'signal_time':str(f.time.iloc[i]),'probe_price':probe,'probe_touch_time':str(m1.time.iloc[touch]),'entry_time':str(entry_time),'exit_time':str(m1.time.iloc[xi]),'entry':entry,'anchor':float(anchor),'anchor_buffer_ticks':int(buffer_ticks),'stop':stop,'target':target,'stop_points':int(stop_points),'target_r':float(target_r),'ttl_minutes':int(ttl_minutes),'confirmation_ticks':int(confirm_ticks),'exit_friction_ticks':int(confirm_ticks),'reason':reason,'gross_bps':float(raw_bps),'bps':float(bps),'risk_bps':float(risk_bps),'r':float(bps/risk_bps)}
    return tr,pd.Timestamp(tr['exit_time'])

def execute(f,m1,cache,inst,indices,anchors,side,sp,buf,ttl,tr,confirm_ticks):
    out=[]; busy=None
    for i in indices:
        i=int(i); st=pd.Timestamp(f.time.iloc[i])+pd.Timedelta(minutes=5)
        if busy is not None and st<=busy: continue
        trade,occ=confirmed_reclaim_trade(f,m1,cache,i,inst,side,float(anchors[i]),sp,buf,ttl,tr,confirm_ticks)
        if occ is not None: busy=occ
        if trade is not None: out.append(trade)
    return out

def run(root:Path,inst:str,outdir:Path):
    f,m1,provenance=c24.load_context(root,inst)
    _,_,_,cache=c24.structural_arrays(f,m1,inst)
    levels=c27.build_levels(f,inst); contexts,cuts=c29.allowed_contexts(f)
    tick=float(v3.SPECS[inst]['tick'])
    disc=((f.time>=DISC_START)&(f.time<DISC_END)).to_numpy(); fw=((f.time>=DISC_END)&(f.time<FORWARD_END)).to_numpy()
    generated=0; seen={}; candidates=[]
    for side_name,side in (('LONG',1),('SHORT',-1)):
      for event in c27.EVENT_TYPES:
       for structure in c27.LEVEL_TYPES:
        for anchor_mode in c27.ANCHOR_MODES:
         em,anchors=c27.event_and_anchor(f,inst,structure,event,side,anchor_mode,levels)
         if not em.any(): continue
         for sp in STOP_POINTS[inst]:
          for buf in BUFFERS:
           if buf>=sp: continue
           probes=anchors+side*(sp-buf)*tick
           passive=np.isfinite(probes)&((f.close.to_numpy(float)>probes) if side==1 else (f.close.to_numpy(float)<probes))
           base_signal=em&passive
           if base_signal[disc].sum()<5: continue
           for ttl in TTLS:
            for target_r in TARGET_RS:
             for ctx_name,ctx_mask in contexts:
              sig=base_signal&ctx_mask
              if sig[disc].sum()<5: continue
              generated+=1
              digest=hashlib.sha256(np.packbits(sig[disc].astype(np.uint8)).tobytes()).hexdigest()
              key=(side_name,digest,sp,buf,ttl,target_r)
              cid=f'{inst}|{side_name}|{event}|{structure}|{anchor_mode}|SL{sp}|B{buf}|TTL{ttl}|TP{target_r:g}R|RECLAIM|{ctx_name}'
              if key in seen: continue
              seen[key]=cid; ix=np.flatnonzero(sig&disc)
              gross=execute(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,target_r,0)
              base=execute(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,target_r,1)
              stress=execute(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,target_r,2)
              passed,diag=c29.discovery_pass(gross,base,stress)
              if passed:
               candidates.append({'candidate_id':cid,'direction':side_name,'side':side,'event':event,'structure':structure,'anchor_mode':anchor_mode,'stop_points':sp,'anchor_buffer_ticks':buf,'ttl_minutes':ttl,'target_r':target_r,'context':ctx_name,'discovery_mask_digest':digest,'discovery':diag,'signal_mask':sig,'anchors':anchors})
    def rank(c):
      d=c['discovery']; js=d['january_stress']['expectancy_r']; fs=d['february_stress']['expectancy_r']; js=-1e9 if js is None else js; fs=-1e9 if fs is None else fs
      return (-min(js,fs),-d['discovery_stress']['pf'],-d['discovery_base']['pf'],-(d['discovery_stress']['expectancy_r'] or -1e9),-d['discovery_base']['days'],c['candidate_id'])
    candidates.sort(key=rank); shortlist=[]; buckets={}
    for c in candidates:
      bucket=(c['direction'],c['event'],c['structure'],c['anchor_mode'],c['context'])
      if buckets.get(bucket,0)>=3: continue
      buckets[bucket]=buckets.get(bucket,0)+1; shortlist.append(c)
      if len(shortlist)>=60: break
    results=[]; survivors=[]
    for c in shortlist:
      sig=c.pop('signal_mask'); anchors=c.pop('anchors'); ix=np.flatnonzero(sig&fw)
      side=int(c['side']); sp=int(c['stop_points']); buf=int(c['anchor_buffer_ticks']); ttl=int(c['ttl_minutes']); tr=float(c['target_r'])
      gross=execute(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,0); base=execute(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,1); stress=execute(f,m1,cache,inst,ix,anchors,side,sp,buf,ttl,tr,2)
      ok,diag=c29.forward_eval(gross,base,stress); row=dict(c); row['forward']=diag; row['survivor']=bool(ok); results.append(row)
      if ok: survivors.append(row)
    outdir.mkdir(parents=True,exist_ok=True)
    manifest={'engine':'cycle30-passive-probe-reclaim-v1','instrument':inst,'point_size':tick,'stop_points':STOP_POINTS[inst],'anchor_buffers':BUFFERS,'ttls':TTLS,'target_rs':TARGET_RS,'generated_candidate_evaluations':generated,'deduped_discovery_candidates':len(seen),'discovery_passes':len(candidates),'shortlisted':len(shortlist),'survivors':len(survivors),'quantile_cutpoints':cuts,'layers':{'GROSS':'touch+0tick reclaim','BASE':'touch+1tick reclaim','STRESS':'touch+2tick reclaim'},'retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,'commission_excluded':True,'provenance':provenance}
    (outdir/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=jsonable)+'\n')
    (outdir/'shortlist.json').write_text(json.dumps(results,indent=2,default=jsonable)+'\n')
    (outdir/'survivors.json').write_text(json.dumps(survivors,indent=2,default=jsonable)+'\n')
    lines=[f'# Cycle 30 — {inst}','',f'- Generated: **{generated}**',f'- Discovery passes: **{len(candidates)}**',f'- Frozen shortlist: **{len(shortlist)}**',f'- Strict survivors: **{len(survivors)}**','','## Top forward candidates']
    for r in results[:20]:
      b=r['forward']['base']; s=r['forward']['stress']; lines.append(f"- `{r['candidate_id']}` — survivor={r['survivor']}; BASE PF {b['pf']:.3f}, E[R] {b['expectancy_r']}, N={b['n']}; STRESS PF {s['pf']:.3f}, E[R] {s['expectancy_r']}, N={s['n']}; ratio={r['forward']['stress_base_trade_ratio']:.3f}; P10={r['forward']['bootstrap_p10_base_r']}")
    (outdir/'report.md').write_text('\n'.join(lines)+'\n'); print(json.dumps(manifest,indent=2,default=jsonable))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--data-root',type=Path,default=Path('.')); p.add_argument('--instrument',choices=('CNYRUBF','USDRUBF'),required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); run(a.data_root,a.instrument,a.output)
