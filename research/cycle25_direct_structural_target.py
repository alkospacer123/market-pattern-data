from __future__ import annotations
import argparse, hashlib, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd

MIN_R=3.25; MAX_R=8.0

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);assert s.loader is not None;s.loader.exec_module(m);return m
c24=mod('research/cycle24_fixed_point_structural.py','c24');v3=c24.v3

def target_mask(entries,obj,tick,stop_points,side):
 target=obj-side*tick
 r=side*(target-entries)/(stop_points*tick)
 return np.isfinite(entries)&np.isfinite(obj)&np.isfinite(target)&(r>=MIN_R)&(r<=MAX_R),target,r

def structural_trade(f,m1,cache,i,inst,side,stop_points,target_price,friction_ticks):
 tick=float(v3.SPECS[inst]['tick']);decision=pd.Timestamp(f.time.iloc[i]);et=decision+pd.Timedelta(minutes=5);ei=cache['idxmap'].get(int(et.value))
 if ei is None or cache['date'][ei]!=f.date.iloc[i]: return None
 entry=float(cache['open'][ei]);risk=stop_points*tick;stop=entry-side*risk;target=float(target_price)
 rr=side*(target-entry)/risk
 if not np.isfinite(rr) or rr<MIN_R or rr>MAX_R:return None
 force=pd.Timestamp(et.date())+pd.Timedelta(hours=17);times=cache['times'];di=cache['idxmap'].get(int(force.value));exact=di is not None
 if di is None:di=int(np.searchsorted(times,int(force.value),side='right')-1)
 if di<ei or di>=len(m1) or cache['date'][di]!=cache['date'][ei]:return None
 raw_exit=float(cache['open'][di]) if exact else float(cache['close'][di]);xi=di;reason='TIME'
 for j in range(ei,di+1):
  o=float(cache['open'][j]);h=float(cache['high'][j]);l=float(cache['low'][j])
  if side==1:
   if o<=stop:xi,raw_exit,reason=j,o,'STOP_GAP';break
   if o>=target:xi,raw_exit,reason=j,target,'TARGET_GAP_CONSERVATIVE';break
   hs,ht=l<=stop,h>=target
   if hs:xi,raw_exit,reason=j,stop,'STOP_FIRST_TIE' if ht else 'STOP';break
   if ht:xi,raw_exit,reason=j,target,'TARGET';break
  else:
   if o>=stop:xi,raw_exit,reason=j,o,'STOP_GAP';break
   if o<=target:xi,raw_exit,reason=j,target,'TARGET_GAP_CONSERVATIVE';break
   hs,ht=h>=stop,l<=target
   if hs:xi,raw_exit,reason=j,stop,'STOP_FIRST_TIE' if ht else 'STOP';break
   if ht:xi,raw_exit,reason=j,target,'TARGET';break
 gross_bps=10000*side*(raw_exit-entry)/entry;risk_bps=10000*risk/entry;cost=10000*friction_ticks*tick/entry;bps=gross_bps-2*cost;rval=bps/risk_bps
 return {'signal_index':int(i),'signal_time':str(f.time.iloc[i]),'entry_time':str(m1.time.iloc[ei]),'exit_time':str(m1.time.iloc[xi]),'entry':entry,'stop':stop,'target':target,'target_r_initial':float(rr),'stop_points':int(stop_points),'reason':reason,'gross_bps':float(gross_bps),'bps':float(bps),'r':float(rval)}

def execute(f,m1,cache,inst,indices,targets,side,sp,friction):
 out=[];busy=None
 for i in indices:
  st=pd.Timestamp(f.time.iloc[int(i)])+pd.Timedelta(minutes=5)
  if busy is not None and st<=busy:continue
  tr=structural_trade(f,m1,cache,int(i),inst,side,sp,float(targets[int(i)]),friction)
  if tr is None:continue
  out.append(tr);busy=pd.Timestamp(tr['exit_time'])
 return out

def run(root:Path,inst:str,outdir:Path):
 f,m1,prov=c24.load_context(root,inst);entries,anchors,objs,cache=c24.structural_arrays(f,m1,inst);tick=float(v3.SPECS[inst]['tick']);seen={};passes=[]
 for side_name,side in (('LONG',1),('SHORT',-1)):
  for anchor_name in c24.STOP_ANCHORS:
   anchor=anchors[(side_name,anchor_name)]
   for sp in c24.STOP_POINTS[inst]:
    sm=c24.stop_valid_mask(entries,anchor,tick,sp,side)
    if not sm.any():continue
    for ctx in c24.TARGET_CONTEXTS:
     tm,target,rr=target_mask(entries,objs[(side_name,ctx)],tick,sp,side);sig=c24.onset(f,sm&tm&c24.session_mask(f));digest=hashlib.sha256(np.packbits(sig.astype(np.uint8)).tobytes()).hexdigest();cid=f'{inst}|{side_name}|{anchor_name}|SL{sp}|{ctx}|DIRECT'
     if digest in seen:continue
     seen[digest]=cid;ix=np.flatnonzero(sig)
     if len(ix)<5:continue
     g=execute(f,m1,cache,inst,ix,target,side,sp,0);b=execute(f,m1,cache,inst,ix,target,side,sp,1);s=execute(f,m1,cache,inst,ix,target,side,sp,2);ok,diag=c24.discovery_pass(g,b,s)
     if ok:
      rrvals=[x['target_r_initial'] for x in b];passes.append({'candidate_id':cid,'direction':side_name,'side':side,'stop_anchor':anchor_name,'stop_points':sp,'target_context':ctx,'mask_digest':digest,'discovery':diag,'discovery_target_r_median':float(np.median(rrvals)) if rrvals else None,'gross_trades':g,'base_trades':b,'stress_trades':s})
 def rank(c):
  d=c['discovery'];j=d['january_stress']['expectancy_r'];fe=d['february_stress']['expectancy_r'];ds=d['discovery_stress'];db=d['discovery_base'];return(-min(j,fe),-ds['pf'],-db['pf'],-ds['expectancy_r'],-ds['days'],c['candidate_id'])
 passes.sort(key=rank);short=passes[:40];results=[];surv=[]
 for c in short:
  ok,fw=c24.forward_eval(c['gross_trades'],c['base_trades'],c['stress_trades']);row={k:v for k,v in c.items() if not k.endswith('_trades')};row['forward']=fw;row['survivor']=bool(ok);results.append(row)
  if ok:surv.append(row)
 outdir.mkdir(parents=True,exist_ok=True);manifest={'engine':'cycle25-direct-structural-target-v1','instrument':inst,'point_size':tick,'stop_points':c24.STOP_POINTS[inst],'stop_anchors':c24.STOP_ANCHORS,'target_contexts':c24.TARGET_CONTEXTS,'target_r_range':[MIN_R,MAX_R],'candidate_masks':len(seen),'discovery_passes':len(passes),'shortlisted':len(short),'survivors':len(surv),'retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,'commission_excluded':True,'provenance':prov}
 (outdir/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=c24.jsonable)+'\n');(outdir/'shortlist.json').write_text(json.dumps(results,indent=2,default=c24.jsonable)+'\n');(outdir/'survivors.json').write_text(json.dumps(surv,indent=2,default=c24.jsonable)+'\n')
 report=[f'# Cycle 25 — {inst}','',f'- Candidate masks: **{len(seen)}**',f'- Discovery passes: **{len(passes)}**',f'- Shortlist: **{len(short)}**',f'- Strict survivors: **{len(surv)}**','','## Top forward']
 for r in results[:10]:
  b=r['forward']['base'];s=r['forward']['stress'];report.append(f"- `{r['candidate_id']}` median discovery target {r['discovery_target_r_median']:.2f}R — survivor={r['survivor']}; BASE PF={b['pf']:.3f}, E[R]={b['expectancy_r']}; STRESS PF={s['pf']:.3f}, E[R]={s['expectancy_r']}; N={b['n']}")
 (outdir/'report.md').write_text('\n'.join(report)+'\n');print(json.dumps(manifest,indent=2,default=c24.jsonable))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data-root',type=Path,default=Path('.'));p.add_argument('--instrument',choices=('CNYRUBF','USDRUBF'),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.data_root,a.instrument,a.output)
