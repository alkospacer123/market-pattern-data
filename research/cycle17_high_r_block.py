from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DISC_END=pd.Timestamp("2026-05-16");EVAL_START=pd.Timestamp("2026-03-02");BLOCK_DAYS=7;TRAIN_DAYS=56;VALID_DAYS=14
PROFILES={
 "HR1":(0.50,3.0,60),"HR2":(0.50,4.0,90),"HR3":(0.50,5.0,120),
 "HR4":(0.75,3.0,60),"HR5":(0.75,4.0,90),"HR6":(0.75,5.0,120),
 "HR7":(1.00,3.0,90),"HR8":(1.00,4.0,120),"HR9":(1.00,5.0,120),
 "HR10":(1.25,3.0,120),
}
TAIL_QS=(0.95,0.975)
PARAM_GRID=[{"max_leaf_nodes":a,"min_samples_leaf":b,"l2_regularization":c} for a in (7,15,31) for b in (20,50) for c in (1.0,10.0)]
MODEL_CONST={"learning_rate":0.05,"max_iter":120,"early_stopping":False,"random_state":20260401}
QUAL={"minimum_tail_rows":25,"minimum_dates":8,"base_pf":1.80,"stress_pf":1.25,"base_expectancy_r":0.25,"stress_expectancy_r":0.05,"largest_winner_share":0.35,"consensus_profiles":2,"consensus_target_levels":2}

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3");c11=mod("research/cycle11_nonlinear_pnl_block.py","c11");c16=mod("research/cycle16_sparse_block.py","c16")

def block_bounds(i):
 s=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*i)
 if s>=DISC_END:raise ValueError("block out of range")
 return s,min(s+pd.Timedelta(days=BLOCK_DAYS),DISC_END)

def add_high_r_labels(pool,contexts):
 n=len(pool);cols={}
 for pid in PROFILES:
  for sn in ("LONG","SHORT"):
   for stem in ("label","stress","base_r","stress_r"):cols[f"{stem}_{pid}_{sn}"]=np.full(n,np.nan,float)
   cols[f"exit_{pid}_{sn}"]=np.full(n,np.datetime64("NaT","ns"),dtype="datetime64[ns]")
   cols[f"target_hit_{pid}_{sn}"]=np.zeros(n,bool)
 for inst,(f,m1) in contexts.items():
  tick=float(v3.SPECS[inst]["tick"]);rows=pool.index[pool.instrument.eq(inst)].to_numpy()
  for ridx in rows:
   i=int(pool.at[ridx,"signal_index"]);atr=float(f.atr14.iloc[i])
   if not np.isfinite(atr) or atr<=0:continue
   for pid,p in PROFILES.items():
    stop_atr,_,_=p
    for sn,side in (("LONG",1),("SHORT",-1)):
     r=c11.isolated_trade(f,m1,i,inst,side,p,0)
     if r is None:continue
     entry=float(r["raw_entry"]);risk_bps=10000.0*stop_atr*atr/entry
     if not np.isfinite(risk_bps) or risk_bps<=0:continue
     gross=float(r["bps"]);base=gross-10000.0*(2.0*tick)/entry;stress=gross-10000.0*(4.0*tick)/entry
     cols[f"label_{pid}_{sn}"][ridx]=base;cols[f"stress_{pid}_{sn}"][ridx]=stress
     cols[f"base_r_{pid}_{sn}"][ridx]=base/risk_bps;cols[f"stress_r_{pid}_{sn}"][ridx]=stress/risk_bps
     cols[f"exit_{pid}_{sn}"][ridx]=np.datetime64(r["exit_time"],"ns");cols[f"target_hit_{pid}_{sn}"][ridx]=str(r["reason"]).startswith("TARGET")
 out=pool.copy()
 for k,v in cols.items():out[k]=v
 return out

def stats(bps,rvals,dates,hits):
 b=np.asarray(bps,float);r=np.asarray(rvals,float);d=np.asarray(dates,dtype=object);h=np.asarray(hits,bool);ok=np.isfinite(b)&np.isfinite(r);b,r,d,h=b[ok],r[ok],d[ok],h[ok]
 if not len(b):return {"n":0,"pf":0.0,"expectancy_bps":None,"expectancy_r":None,"dates":0,"largest_winner_share":None,"target_hit_rate":None}
 gp=b[b>0].sum();gl=-b[b<0].sum();pf=float(gp/gl) if gl else (float("inf") if gp else 0.0);w=b[b>0];share=float(w.max()/w.sum()) if len(w) else None
 return {"n":int(len(b)),"pf":pf,"expectancy_bps":float(b.mean()),"expectancy_r":float(r.mean()),"dates":int(len(set(d))),"largest_winner_share":share,"target_hit_rate":float(h.mean())}

def clean_X(df,cols):
 X=df[cols].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan;return X

def evaluate_tail(pred,val,pid,sn,hp,qv):
 q=float(np.quantile(pred,qv));mask=pred>=q
 b=stats(val.loc[mask,f"label_{pid}_{sn}"],val.loc[mask,f"base_r_{pid}_{sn}"],val.loc[mask,"date"],val.loc[mask,f"target_hit_{pid}_{sn}"])
 s=stats(val.loc[mask,f"stress_{pid}_{sn}"],val.loc[mask,f"stress_r_{pid}_{sn}"],val.loc[mask,"date"],val.loc[mask,f"target_hit_{pid}_{sn}"])
 good=(b["n"]>=QUAL["minimum_tail_rows"] and b["dates"]>=QUAL["minimum_dates"] and b["pf"]>=QUAL["base_pf"] and s["pf"]>=QUAL["stress_pf"] and b["expectancy_r"] is not None and b["expectancy_r"]>=QUAL["base_expectancy_r"] and s["expectancy_r"] is not None and s["expectancy_r"]>=QUAL["stress_expectancy_r"] and b["expectancy_bps"] is not None and b["expectancy_bps"]>0 and s["expectancy_bps"] is not None and s["expectancy_bps"]>0 and b["largest_winner_share"] is not None and b["largest_winner_share"]<=QUAL["largest_winner_share"])
 return {"qualified":bool(good),"quantile":float(qv),"threshold":max(0.0,q),"base":b,"stress":s,"hp":hp}

def fit_one(pool,features,pid,sn,start):
 ws=start-pd.Timedelta(days=TRAIN_DAYS);vs=start-pd.Timedelta(days=VALID_DAYS);yc=f"label_{pid}_{sn}";ec=f"exit_{pid}_{sn}"
 old=pool[(pool.time>=ws)&(pool.time<vs)&pool[yc].notna()&(pool[ec]<vs)].copy();val=pool[(pool.time>=vs)&(pool.time<start)&pool[yc].notna()&(pool[ec]<start)].copy();full=pool[(pool.time>=ws)&(pool.time<start)&pool[yc].notna()&(pool[ec]<start)].copy()
 if len(old)<300 or len(val)<300 or len(full)<650:return None
 Xo,yo=clean_X(old,features),old[yc].to_numpy(float);Xv=clean_X(val,features);Xf,yf=clean_X(full,features),full[yc].to_numpy(float);qualified=[];all_diag=[]
 for hp in PARAM_GRID:
  m=HistGradientBoostingRegressor(**MODEL_CONST,**hp);m.fit(Xo,yo);pred=m.predict(Xv)
  for qv in TAIL_QS:
   d=evaluate_tail(pred,val,pid,sn,hp,qv);all_diag.append(d)
   if d["qualified"]:qualified.append(d)
 def rank(d):return (min(d["base"]["pf"],d["stress"]["pf"]),min(d["base"]["expectancy_r"],d["stress"]["expectancy_r"]),d["base"]["dates"],d["base"]["target_hit_rate"])
 if not qualified:return {"enabled":False,"diagnostic":{"profile":pid,"side":sn,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"qualified_configs":0,"best_unqualified":max(all_diag,key=rank)}}
 best=max(qualified,key=rank);m=HistGradientBoostingRegressor(**MODEL_CONST,**best["hp"]);m.fit(Xf,yf)
 return {"enabled":True,"model":m,"threshold":best["threshold"],"diagnostic":{"profile":pid,"side":sn,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"qualified_configs":len(qualified),"selected":best}}

def choose(pool,features,models,start,end):
 out={"CNYRUBF":[],"USDRUBF":[]};summary={}
 for inst in out:
  q=pool[(pool.instrument==inst)&(pool.time>=start)&(pool.time<end)].sort_values("time");last_direction=None;counts={}
  for _,r in q.iterrows():
   X=clean_X(pd.DataFrame([r]),features);by={1:[],-1:[]}
   for pid,p in PROFILES.items():
    for sn,side in (("LONG",1),("SHORT",-1)):
     fit=models.get((pid,sn))
     if not fit or not fit.get("enabled"):continue
     pred=float(fit["model"].predict(X)[0]);thr=float(fit["threshold"])
     if pred>=thr:by[side].append((pred,pid,thr,float(p[1])))
   def ok(side):return len(by[side])>=QUAL["consensus_profiles"] and len({x[3] for x in by[side]})>=QUAL["consensus_target_levels"]
   lo,sh=ok(1),ok(-1)
   if lo and sh:last_direction=None;continue
   if not lo and not sh:last_direction=None;continue
   side=1 if lo else -1
   if last_direction==side:continue
   pred,pid,thr,_=max(by[side],key=lambda z:(z[0],z[3]));out[inst].append({"signal_index":int(r.signal_index),"signal_time":str(r.time),"side":side,"profile":pid,"predicted_base_bps":pred,"threshold":thr,"consensus_count":len(by[side]),"consensus_target_levels":sorted({x[3] for x in by[side]})});counts[pid]=counts.get(pid,0)+1;last_direction=side
  summary[inst]={"state_onsets":len(out[inst]),"profiles":counts}
 return out,summary

def decorate(trades):
 for t in trades:
  sa,tr,_=PROFILES[t["profile"]];risk_bps=10000.0*abs(float(t["entry"])-float(t["stop"]))/float(t["entry"]);t["stop_atr"]=sa;t["target_r"]=tr;t["realized_r"]=float(t["bps"])/risk_bps if risk_bps>0 else None;t["target_hit"]=str(t["reason"]).startswith("TARGET")
 return trades

def run(root,out,index):
 start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts,pool,features,prov=c16.combine_features(root);pool=add_high_r_labels(pool,contexts);models={};diag=[]
 for pid in PROFILES:
  for sn in ("LONG","SHORT"):
   fit=fit_one(pool,features,pid,sn,start);models[(pid,sn)]=fit
   if fit:diag.append(fit["diagnostic"])
 sigs,summary=choose(pool,features,models,start,end);c11.PROFILES=PROFILES;inst_rows=[]
 for inst,(f,m1) in contexts.items():
  g=decorate(c11.execute_mixed(f,m1,sigs[inst],inst,0));b=decorate(c11.execute_mixed(f,m1,sigs[inst],inst,1));s=decorate(c11.execute_mixed(f,m1,sigs[inst],inst,2));inst_rows.append({"instrument":inst,"signals":sigs[inst],"gross_trades":g,"base_trades":b,"stress_trades":s,"gross":v3.metrics(g),"base":v3.metrics(b),"stress":v3.metrics(s)})
 res={"engine":"cycle17-high-r-expectancy-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"feature_count":len(features),"profiles":PROFILES,"tail_quantiles":TAIL_QS,"qualification":QUAL,"model_diagnostics":diag,"prediction_summary":summary,"instruments":inst_rows,"provenance":prov}
 (out/"block_result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"features":len(features),"enabled_models":sum(1 for x in models.values() if x and x.get("enabled")),"summary":summary},indent=2))

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--data-root",type=Path,default=Path("."));p.add_argument("--output",type=Path,required=True);p.add_argument("--block-index",type=int,required=True);a=p.parse_args();run(a.data_root,a.output,a.block_index)
