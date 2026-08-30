from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, HistGradientBoostingClassifier

DISC_END=pd.Timestamp("2026-05-16");EVAL_START=pd.Timestamp("2026-03-02");BLOCK_DAYS=7;TRAIN_DAYS=56;VALID_DAYS=14
MIN_STOP_TICKS=5.0
PROFILES={
 "XS1":(0.25,3.0,45),"XS2":(0.25,4.0,60),"XS3":(0.25,5.0,90),
 "XS4":(0.35,3.0,45),"XS5":(0.35,4.0,60),"XS6":(0.35,5.0,90),
 "XS7":(0.50,3.0,60),"XS8":(0.50,4.0,90),"XS9":(0.50,5.0,120),"XS10":(0.50,6.0,120),
}
PARAM_GRID=[{"max_leaf_nodes":a,"min_samples_leaf":b,"l2_regularization":c} for a in (7,15) for b in (30,60) for c in (1.0,10.0)]
MODEL_CONST={"learning_rate":0.05,"max_iter":120,"early_stopping":False,"random_state":20260401}
QUAL={"reg_quantile":0.95,"prob_quantile":0.75,"minimum_tail_rows":20,"minimum_dates":7,"base_pf":2.0,"stress_pf":1.35,"base_expectancy_r":0.35,"stress_expectancy_r":0.10,"hit_rate_margin":0.05,"largest_winner_share":0.35}

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3");c16=mod("research/cycle16_sparse_block.py","c16")

def block_bounds(i):
 s=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*i)
 if s>=DISC_END:raise ValueError("block out of range")
 return s,min(s+pd.Timedelta(days=BLOCK_DAYS),DISC_END)

def _m1_cache(m1):
 cache=getattr(_m1_cache,"cache",{});key=id(m1)
 if key not in cache:
  times=m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);cache[key]=(times,{int(t):j for j,t in enumerate(times)},m1.open.to_numpy(float),m1.high.to_numpy(float),m1.low.to_numpy(float),m1.close.to_numpy(float),m1.date.to_numpy())
  _m1_cache.cache=cache
 return cache[key]

def raw_trade(m5,m1,i,inst,side,profile):
 stop_atr,target_r,hold=profile;tick=float(v3.SPECS[inst]["tick"]);st=pd.Timestamp(m5.time.iloc[i]);et=st+pd.Timedelta(minutes=5)
 times,idxmap,op,hi,lo,cl,dates=_m1_cache(m1);ei=idxmap.get(int(et.value))
 if ei is None or dates[ei]!=m5.date.iloc[i]:return None
 atr=float(m5.atr14.iloc[i])
 if not np.isfinite(atr) or atr<=0:return None
 entry=float(op[ei]);atr_risk=stop_atr*atr;risk=max(atr_risk,MIN_STOP_TICKS*tick);floor_active=risk>atr_risk+1e-15
 stop=entry-side*risk;target=entry+side*target_r*risk;force=pd.Timestamp(et.date())+pd.Timedelta(hours=17);deadline=min(et+pd.Timedelta(minutes=hold),force)
 di=idxmap.get(int(deadline.value));exact=di is not None
 if di is None:di=int(np.searchsorted(times,int(deadline.value),side="right")-1)
 if di<ei or di>=len(m1) or dates[di]!=dates[ei]:return None
 xi=di;raw=float(op[di]) if exact else float(cl[di]);reason="TIME"
 for j in range(ei,di+1):
  o,h,l=float(op[j]),float(hi[j]),float(lo[j])
  if side==1:
   if o<=stop:xi,raw,reason=j,o,"STOP_GAP";break
   if o>=target:xi,raw,reason=j,target,"TARGET_GAP_CONSERVATIVE";break
   hs=l<=stop;ht=h>=target
   if hs:xi,raw,reason=j,stop,"STOP_FIRST_TIE" if ht else "STOP";break
   if ht:xi,raw,reason=j,target,"TARGET";break
  else:
   if o>=stop:xi,raw,reason=j,o,"STOP_GAP";break
   if o<=target:xi,raw,reason=j,target,"TARGET_GAP_CONSERVATIVE";break
   hs=h>=stop;ht=l<=target
   if hs:xi,raw,reason=j,stop,"STOP_FIRST_TIE" if ht else "STOP";break
   if ht:xi,raw,reason=j,target,"TARGET";break
 risk_bps=10000.0*risk/entry;gross_bps=10000.0*side*(raw-entry)/entry
 return {"entry_index":int(ei),"exit_index":int(xi),"entry_time":pd.Timestamp(m1.time.iloc[ei]),"exit_time":pd.Timestamp(m1.time.iloc[xi]),"entry":entry,"raw_exit":raw,"stop":stop,"target":target,"raw_risk":risk,"risk_bps":risk_bps,"raw_stop_ticks":risk/tick,"floor_active":bool(floor_active),"gross_bps":float(gross_bps),"reason":reason,"target_hit":str(reason).startswith("TARGET")}

def frictionize(raw,inst,friction_ticks):
 tick=float(v3.SPECS[inst]["tick"]);entry=float(raw["entry"]);side_cost_bps=10000.0*friction_ticks*tick/entry;bps=float(raw["gross_bps"]-2.0*side_cost_bps);r=bps/float(raw["risk_bps"])
 return bps,float(r)

def add_labels(pool,contexts):
 n=len(pool);cols={}
 for pid in PROFILES:
  for sn in ("LONG","SHORT"):
   for stem in ("base_bps","stress_bps","base_r","stress_r","raw_stop_ticks"):cols[f"{stem}_{pid}_{sn}"]=np.full(n,np.nan,float)
   cols[f"exit_{pid}_{sn}"]=np.full(n,np.datetime64("NaT","ns"),dtype="datetime64[ns]");cols[f"target_hit_{pid}_{sn}"]=np.zeros(n,bool);cols[f"floor_active_{pid}_{sn}"]=np.zeros(n,bool)
 for inst,(f,m1) in contexts.items():
  rows=pool.index[pool.instrument.eq(inst)].to_numpy()
  for ridx in rows:
   i=int(pool.at[ridx,"signal_index"])
   for pid,p in PROFILES.items():
    for sn,side in (("LONG",1),("SHORT",-1)):
     raw=raw_trade(f,m1,i,inst,side,p)
     if raw is None:continue
     bb,br=frictionize(raw,inst,1);sb,sr=frictionize(raw,inst,2)
     cols[f"base_bps_{pid}_{sn}"][ridx]=bb;cols[f"stress_bps_{pid}_{sn}"][ridx]=sb;cols[f"base_r_{pid}_{sn}"][ridx]=br;cols[f"stress_r_{pid}_{sn}"][ridx]=sr;cols[f"raw_stop_ticks_{pid}_{sn}"][ridx]=raw["raw_stop_ticks"];cols[f"exit_{pid}_{sn}"][ridx]=np.datetime64(raw["exit_time"],"ns");cols[f"target_hit_{pid}_{sn}"][ridx]=raw["target_hit"];cols[f"floor_active_{pid}_{sn}"][ridx]=raw["floor_active"]
 out=pool.copy()
 for k,v in cols.items():out[k]=v
 return out

def stats(bps,rvals,dates,hits,stops,floors):
 b=np.asarray(bps,float);r=np.asarray(rvals,float);d=np.asarray(dates,dtype=object);h=np.asarray(hits,bool);s=np.asarray(stops,float);fl=np.asarray(floors,bool);ok=np.isfinite(b)&np.isfinite(r)&np.isfinite(s);b,r,d,h,s,fl=b[ok],r[ok],d[ok],h[ok],s[ok],fl[ok]
 if not len(b):return {"n":0,"pf":0.0,"expectancy_bps":None,"expectancy_r":None,"dates":0,"largest_winner_share":None,"target_hit_rate":None,"median_stop_ticks":None,"floor_rate":None}
 gp=b[b>0].sum();gl=-b[b<0].sum();pf=float(gp/gl) if gl else (float("inf") if gp else 0.0);w=b[b>0];share=float(w.max()/w.sum()) if len(w) else None
 return {"n":int(len(b)),"pf":pf,"expectancy_bps":float(b.mean()),"expectancy_r":float(r.mean()),"dates":int(len(set(d))),"largest_winner_share":share,"target_hit_rate":float(h.mean()),"median_stop_ticks":float(np.median(s)),"floor_rate":float(fl.mean())}

def clean_X(df,features):
 X=df[features].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan;return X

def eval_config(reg,clf,Xv,val,pid,sn,hp):
 rp=reg.predict(Xv);cp=clf.predict_proba(Xv)[:,1];rt=float(np.quantile(rp,QUAL["reg_quantile"]));pt=float(np.quantile(cp,QUAL["prob_quantile"]));mask=(rp>=rt)&(cp>=pt)
 args=(val.loc[mask,f"base_bps_{pid}_{sn}"],val.loc[mask,f"base_r_{pid}_{sn}"],val.loc[mask,"date"],val.loc[mask,f"target_hit_{pid}_{sn}"],val.loc[mask,f"raw_stop_ticks_{pid}_{sn}"],val.loc[mask,f"floor_active_{pid}_{sn}"])
 b=stats(*args);args2=(val.loc[mask,f"stress_bps_{pid}_{sn}"],val.loc[mask,f"stress_r_{pid}_{sn}"],val.loc[mask,"date"],val.loc[mask,f"target_hit_{pid}_{sn}"],val.loc[mask,f"raw_stop_ticks_{pid}_{sn}"],val.loc[mask,f"floor_active_{pid}_{sn}"]);s=stats(*args2);target_r=float(PROFILES[pid][1]);min_hit=1.0/(target_r+1.0)+QUAL["hit_rate_margin"]
 good=(b["n"]>=QUAL["minimum_tail_rows"] and b["dates"]>=QUAL["minimum_dates"] and b["pf"]>=QUAL["base_pf"] and s["pf"]>=QUAL["stress_pf"] and b["expectancy_r"] is not None and b["expectancy_r"]>=QUAL["base_expectancy_r"] and s["expectancy_r"] is not None and s["expectancy_r"]>=QUAL["stress_expectancy_r"] and b["expectancy_bps"] is not None and b["expectancy_bps"]>0 and s["expectancy_bps"] is not None and s["expectancy_bps"]>0 and b["target_hit_rate"] is not None and b["target_hit_rate"]>=min_hit and b["largest_winner_share"] is not None and b["largest_winner_share"]<=QUAL["largest_winner_share"])
 return {"qualified":bool(good),"reg_threshold":max(0.0,rt),"prob_threshold":pt,"base":b,"stress":s,"minimum_hit_rate":min_hit,"hp":hp}

def fit_one(pool,features,pid,sn,start):
 ws=start-pd.Timedelta(days=TRAIN_DAYS);vs=start-pd.Timedelta(days=VALID_DAYS);yc=f"base_r_{pid}_{sn}";ec=f"exit_{pid}_{sn}";hc=f"target_hit_{pid}_{sn}"
 old=pool[(pool.time>=ws)&(pool.time<vs)&pool[yc].notna()&(pool[ec]<vs)].copy();val=pool[(pool.time>=vs)&(pool.time<start)&pool[yc].notna()&(pool[ec]<start)].copy();full=pool[(pool.time>=ws)&(pool.time<start)&pool[yc].notna()&(pool[ec]<start)].copy()
 if len(old)<300 or len(val)<250 or len(full)<600 or old[hc].nunique()<2 or full[hc].nunique()<2:return None
 Xo,yo=clean_X(old,features),old[yc].to_numpy(float);co=old[hc].astype(int).to_numpy();Xv=clean_X(val,features);Xf,yf=clean_X(full,features),full[yc].to_numpy(float);cf=full[hc].astype(int).to_numpy();qualified=[];all_diag=[]
 for hp in PARAM_GRID:
  reg=HistGradientBoostingRegressor(**MODEL_CONST,**hp);clf=HistGradientBoostingClassifier(**MODEL_CONST,**hp);reg.fit(Xo,yo);clf.fit(Xo,co);d=eval_config(reg,clf,Xv,val,pid,sn,hp);all_diag.append(d)
  if d["qualified"]:qualified.append(d)
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
   X=clean_X(pd.DataFrame([r]),features);by={1:[],-1:[]}
   for pid,p in PROFILES.items():
    for sn,side in (("LONG",1),("SHORT",-1)):
     fit=models.get((pid,sn))
     if not fit or not fit.get("enabled"):continue
     rp=float(fit["reg"].predict(X)[0]);cp=float(fit["clf"].predict_proba(X)[0,1])
     if rp>=fit["reg_threshold"] and cp>=fit["prob_threshold"]:by[side].append((rp,cp,pid,float(p[1])))
   lo=bool(by[1]);sh=bool(by[-1])
   if lo and sh:last=None;continue
   if not lo and not sh:last=None;continue
   side=1 if lo else -1
   if last==side:continue
   rp,cp,pid,tr=max(by[side],key=lambda z:(z[0],z[1],z[3]));out[inst].append({"signal_index":int(r.signal_index),"signal_time":str(r.time),"side":side,"profile":pid,"predicted_base_r":rp,"predicted_hit_probability":cp,"reg_threshold":models[(pid,"LONG" if side==1 else "SHORT")]["reg_threshold"],"prob_threshold":models[(pid,"LONG" if side==1 else "SHORT")]["prob_threshold"]});counts[pid]=counts.get(pid,0)+1;last=side
  summary[inst]={"state_onsets":len(out[inst]),"profiles":counts}
 return out,summary

def execute(f,m1,signals,inst,friction_ticks):
 out=[];busy_exit=None
 for sig in signals:
  raw=raw_trade(f,m1,int(sig["signal_index"]),inst,int(sig["side"]),PROFILES[sig["profile"]])
  if raw is None:continue
  if busy_exit is not None and raw["entry_time"]<=busy_exit:continue
  bps,rr=frictionize(raw,inst,friction_ticks);busy_exit=raw["exit_time"]
  out.append({"instrument":inst,"date":str(raw["entry_time"].date()),"month":str(raw["entry_time"].to_period("M")),"side":int(sig["side"]),"profile":sig["profile"],"stop_atr":PROFILES[sig["profile"]][0],"target_r":PROFILES[sig["profile"]][1],"predicted_base_r":sig["predicted_base_r"],"predicted_hit_probability":sig["predicted_hit_probability"],"signal_time":sig["signal_time"],"entry_time":str(raw["entry_time"]),"exit_time":str(raw["exit_time"]),"entry":raw["entry"],"stop":raw["stop"],"target":raw["target"],"raw_exit":raw["raw_exit"],"raw_stop_ticks":raw["raw_stop_ticks"],"floor_active":raw["floor_active"],"friction_ticks_per_side":friction_ticks,"bps":bps,"realized_r":rr,"target_hit":raw["target_hit"],"reason":raw["reason"]})
 return out

def run(root,out,index):
 start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts,pool,features,prov=c16.combine_features(root);pool=add_labels(pool,contexts);models={};diag=[]
 for pid in PROFILES:
  for sn in ("LONG","SHORT"):
   fit=fit_one(pool,features,pid,sn,start);models[(pid,sn)]=fit
   if fit:diag.append(fit["diagnostic"])
 sigs,summary=choose(pool,features,models,start,end);inst_rows=[]
 for inst,(f,m1) in contexts.items():
  g=execute(f,m1,sigs[inst],inst,0);b=execute(f,m1,sigs[inst],inst,1);s=execute(f,m1,sigs[inst],inst,2);inst_rows.append({"instrument":inst,"signals":sigs[inst],"gross_trades":g,"base_trades":b,"stress_trades":s,"gross":v3.metrics(g),"base":v3.metrics(b),"stress":v3.metrics(s)})
 res={"engine":"cycle18-ultrashort-barrier-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"minimum_stop_ticks":MIN_STOP_TICKS,"feature_count":len(features),"profiles":PROFILES,"qualification":QUAL,"model_diagnostics":diag,"prediction_summary":summary,"instruments":inst_rows,"provenance":prov}
 (out/"block_result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"features":len(features),"enabled_models":sum(1 for x in models.values() if x and x.get("enabled")),"summary":summary},indent=2))

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--data-root",type=Path,default=Path("."));p.add_argument("--output",type=Path,required=True);p.add_argument("--block-index",type=int,required=True);a=p.parse_args();run(a.data_root,a.output,a.block_index)
