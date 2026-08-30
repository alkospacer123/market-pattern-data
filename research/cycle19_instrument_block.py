from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
c18=mod("research/cycle18_barrier_block.py","c18");c16=c18.c16;v3=c18.v3
PARAM_GRID=[{"max_leaf_nodes":a,"min_samples_leaf":b,"l2_regularization":c} for a in (7,15) for b in (20,40) for c in (1.0,10.0)]
QUAL={"reg_quantile":0.95,"prob_quantile":0.75,"minimum_tail_rows":12,"minimum_dates":5,"base_pf":2.0,"stress_pf":1.35,"base_expectancy_r":0.35,"stress_expectancy_r":0.10,"hit_rate_margin":0.05,"largest_winner_share":0.40}
MODEL_CONST=c18.MODEL_CONST

def fit_one(inst_pool,features,pid,sn,start):
 ws=start-pd.Timedelta(days=c18.TRAIN_DAYS);vs=start-pd.Timedelta(days=c18.VALID_DAYS);yc=f"base_r_{pid}_{sn}";ec=f"exit_{pid}_{sn}";hc=f"target_hit_{pid}_{sn}"
 old=inst_pool[(inst_pool.time>=ws)&(inst_pool.time<vs)&inst_pool[yc].notna()&(inst_pool[ec]<vs)].copy();val=inst_pool[(inst_pool.time>=vs)&(inst_pool.time<start)&inst_pool[yc].notna()&(inst_pool[ec]<start)].copy();full=inst_pool[(inst_pool.time>=ws)&(inst_pool.time<start)&inst_pool[yc].notna()&(inst_pool[ec]<start)].copy()
 if len(old)<150 or len(val)<120 or len(full)<300 or old[hc].nunique()<2 or full[hc].nunique()<2:return None
 Xo,yo=c18.clean_X(old,features),old[yc].to_numpy(float);co=old[hc].astype(int).to_numpy();Xv=c18.clean_X(val,features);Xf,yf=c18.clean_X(full,features),full[yc].to_numpy(float);cf=full[hc].astype(int).to_numpy();qualified=[];all_diag=[]
 for hp in PARAM_GRID:
  reg=HistGradientBoostingRegressor(**MODEL_CONST,**hp);clf=HistGradientBoostingClassifier(**MODEL_CONST,**hp);reg.fit(Xo,yo);clf.fit(Xo,co)
  rp=reg.predict(Xv);cp=clf.predict_proba(Xv)[:,1];rt=float(np.quantile(rp,QUAL["reg_quantile"]));pt=float(np.quantile(cp,QUAL["prob_quantile"]));mask=(rp>=rt)&(cp>=pt)
  b=c18.stats(val.loc[mask,f"base_bps_{pid}_{sn}"],val.loc[mask,f"base_r_{pid}_{sn}"],val.loc[mask,"date"],val.loc[mask,f"target_hit_{pid}_{sn}"],val.loc[mask,f"raw_stop_ticks_{pid}_{sn}"],val.loc[mask,f"floor_active_{pid}_{sn}"])
  s=c18.stats(val.loc[mask,f"stress_bps_{pid}_{sn}"],val.loc[mask,f"stress_r_{pid}_{sn}"],val.loc[mask,"date"],val.loc[mask,f"target_hit_{pid}_{sn}"],val.loc[mask,f"raw_stop_ticks_{pid}_{sn}"],val.loc[mask,f"floor_active_{pid}_{sn}"])
  min_hit=1.0/(float(c18.PROFILES[pid][1])+1.0)+QUAL["hit_rate_margin"]
  good=(b["n"]>=QUAL["minimum_tail_rows"] and b["dates"]>=QUAL["minimum_dates"] and b["pf"]>=QUAL["base_pf"] and s["pf"]>=QUAL["stress_pf"] and b["expectancy_r"] is not None and b["expectancy_r"]>=QUAL["base_expectancy_r"] and s["expectancy_r"] is not None and s["expectancy_r"]>=QUAL["stress_expectancy_r"] and b["expectancy_bps"] is not None and b["expectancy_bps"]>0 and s["expectancy_bps"] is not None and s["expectancy_bps"]>0 and b["target_hit_rate"] is not None and b["target_hit_rate"]>=min_hit and b["largest_winner_share"] is not None and b["largest_winner_share"]<=QUAL["largest_winner_share"])
  d={"qualified":bool(good),"reg_threshold":max(0.0,rt),"prob_threshold":pt,"base":b,"stress":s,"minimum_hit_rate":min_hit,"hp":hp};all_diag.append(d)
  if good:qualified.append(d)
 def rank(d):
  er=d["stress"]["expectancy_r"] if d["stress"]["expectancy_r"] is not None else -1e9;return (min(d["base"]["pf"],d["stress"]["pf"]),min(d["base"]["expectancy_r"] or -1e9,er),d["base"]["target_hit_rate"] or 0,d["base"]["dates"])
 if not qualified:return {"enabled":False,"diagnostic":{"profile":pid,"side":sn,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"qualified_configs":0,"best_unqualified":max(all_diag,key=rank)}}
 best=max(qualified,key=rank);reg=HistGradientBoostingRegressor(**MODEL_CONST,**best["hp"]);clf=HistGradientBoostingClassifier(**MODEL_CONST,**best["hp"]);reg.fit(Xf,yf);clf.fit(Xf,cf)
 return {"enabled":True,"reg":reg,"clf":clf,"reg_threshold":best["reg_threshold"],"prob_threshold":best["prob_threshold"],"diagnostic":{"profile":pid,"side":sn,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"qualified_configs":len(qualified),"selected":best}}

def choose(pool,features,models,start,end):
 out={"CNYRUBF":[],"USDRUBF":[]};summary={}
 for inst in out:
  q=pool[(pool.instrument==inst)&(pool.time>=start)&(pool.time<end)].sort_values("time");last=None;counts={}
  for _,r in q.iterrows():
   X=c18.clean_X(pd.DataFrame([r]),features);by={1:[],-1:[]}
   for pid,p in c18.PROFILES.items():
    for sn,side in (("LONG",1),("SHORT",-1)):
     fit=models.get((inst,pid,sn))
     if not fit or not fit.get("enabled"):continue
     rp=float(fit["reg"].predict(X)[0]);cp=float(fit["clf"].predict_proba(X)[0,1])
     if rp>=fit["reg_threshold"] and cp>=fit["prob_threshold"]:by[side].append((rp,cp,pid,float(p[1])))
   lo=bool(by[1]);sh=bool(by[-1])
   if lo and sh:last=None;continue
   if not lo and not sh:last=None;continue
   side=1 if lo else -1
   if last==side:continue
   rp,cp,pid,tr=max(by[side],key=lambda z:(z[0],z[1],z[3]));fit=models[(inst,pid,"LONG" if side==1 else "SHORT")]
   out[inst].append({"signal_index":int(r.signal_index),"signal_time":str(r.time),"side":side,"profile":pid,"predicted_base_r":rp,"predicted_hit_probability":cp,"reg_threshold":fit["reg_threshold"],"prob_threshold":fit["prob_threshold"]});counts[pid]=counts.get(pid,0)+1;last=side
  summary[inst]={"state_onsets":len(out[inst]),"profiles":counts}
 return out,summary

def run(root:Path,out:Path,index:int):
 start,end=c18.block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts,pool,features,prov=c16.combine_features(root);pool=c18.add_labels(pool,contexts);models={};diag=[]
 for inst in ("CNYRUBF","USDRUBF"):
  ip=pool[pool.instrument.eq(inst)].copy()
  for pid in c18.PROFILES:
   for sn in ("LONG","SHORT"):
    fit=fit_one(ip,features,pid,sn,start);models[(inst,pid,sn)]=fit
    if fit:
     d=dict(fit["diagnostic"]);d["instrument"]=inst;diag.append(d)
 sigs,summary=choose(pool,features,models,start,end);inst_rows=[]
 for inst,(f,m1) in contexts.items():
  g=c18.execute(f,m1,sigs[inst],inst,0);b=c18.execute(f,m1,sigs[inst],inst,1);s=c18.execute(f,m1,sigs[inst],inst,2);inst_rows.append({"instrument":inst,"signals":sigs[inst],"gross_trades":g,"base_trades":b,"stress_trades":s,"gross":v3.metrics(g),"base":v3.metrics(b),"stress":v3.metrics(s)})
 res={"engine":"cycle19-instrument-specific-high-r-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"minimum_stop_ticks":c18.MIN_STOP_TICKS,"feature_count":len(features),"profiles":c18.PROFILES,"qualification":QUAL,"model_diagnostics":diag,"prediction_summary":summary,"instruments":inst_rows,"provenance":prov}
 (out/"block_result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"features":len(features),"enabled_models":sum(1 for x in models.values() if x and x.get("enabled")),"summary":summary},indent=2))

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--data-root",type=Path,default=Path("."));p.add_argument("--output",type=Path,required=True);p.add_argument("--block-index",type=int,required=True);a=p.parse_args();run(a.data_root,a.output,a.block_index)
