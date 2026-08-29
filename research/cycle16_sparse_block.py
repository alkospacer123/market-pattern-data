from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DISC_END=pd.Timestamp("2026-05-16");EVAL_START=pd.Timestamp("2026-03-02");BLOCK_DAYS=7;TRAIN_DAYS=56;VALID_DAYS=14
PROFILES={"P1":(0.75,1.5,30),"P2":(1.00,2.0,60),"P3":(1.25,2.0,60),"P4":(1.50,3.0,120)}
PARAM_GRID=[{"max_leaf_nodes":a,"min_samples_leaf":b,"l2_regularization":c} for a in (7,15,31) for b in (20,50) for c in (1.0,10.0)]
MODEL_CONST={"learning_rate":0.05,"max_iter":120,"early_stopping":False,"random_state":1618}
QUAL={"tail_quantile":0.95,"minimum_tail_rows":12,"base_pf":2.0,"stress_pf":1.3,"minimum_dates":4,"largest_winner_share":0.35,"consensus_profiles":2}


def mod(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3");c11=mod("research/cycle11_nonlinear_pnl_block.py","c11");c14f=mod("research/cycle14_m1_micro_fast_runner.py","c14f");c13=mod("research/cycle13_cross_leadlag_block.py","c13")


def block_bounds(i):
    s=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*i)
    if s>=DISC_END:raise ValueError("block out of range")
    return s,min(s+pd.Timedelta(days=BLOCK_DAYS),DISC_END)


def pf_stats(vals,dates):
    y=np.asarray(vals,float);ok=np.isfinite(y);y=y[ok];d=np.asarray(dates,dtype=object)[ok]
    if not len(y):return {"n":0,"pf":0.0,"expectancy":None,"dates":0,"largest_winner_share":None}
    gp=y[y>0].sum();gl=-y[y<0].sum();pf=float(gp/gl) if gl else (float("inf") if gp else 0.0);wins=y[y>0];share=float(wins.max()/wins.sum()) if len(wins) else None
    return {"n":int(len(y)),"pf":pf,"expectancy":float(y.mean()),"dates":int(len(set(d))),"largest_winner_share":share}


def augment_dataset(root:Path,inst:str):
    # Uses the semantically identical fast implementation of preregistered Cycle-14 micro features.
    f,m1,ds,prov=c14f.build_dataset_fast(root,inst)
    # Merge the complete numeric causal M5 fields that Cycle 11 exposed.
    _,_,numeric,_=c11.load_context(root,inst)
    for feat in numeric:
        if feat.startswith("fwd_"):continue
        ds["m5_"+feat]=[f[feat].iloc[int(i)] for i in ds.signal_index]
    # Calculate isolated STRESS labels for exactly the same signal bar/profile/direction.
    for pid,p in PROFILES.items():
        for side_name,side in (("LONG",1),("SHORT",-1)):
            vals=[]
            for i in ds.signal_index.astype(int):
                r=c11.isolated_trade(f,m1,int(i),inst,side,p,2);vals.append(np.nan if r is None else float(r["bps"]))
            ds[f"stress_{pid}_{side_name}"]=vals
    return f,m1,ds,prov


def build_cross(cny_f,usd_f):
    j=c13.build_joint(cny_f,usd_f)
    cols=["time","ret_diff_5m","ret_diff_15m","ret_diff_30m","ret_diff_60m","sign_agree_5m","sign_agree_15m","sign_agree_30m","sign_agree_60m","corr_prior_12","corr_prior_36","beta_prior_36","residual_current"]
    return j[cols].copy()


def combine_features(root:Path):
    contexts={};frames=[];prov=[]
    for inst in ("CNYRUBF","USDRUBF"):
        f,m1,ds,p=augment_dataset(root,inst);contexts[inst]=(f,m1);frames.append((inst,ds));prov+=p
    cross=build_cross(contexts["CNYRUBF"][0],contexts["USDRUBF"][0]);combined=[]
    for inst,ds in frames:
        q=ds.merge(cross,on="time",how="left",validate="many_to_one");combined.append(q)
    pool=pd.concat(combined,ignore_index=True,sort=False)
    feature_cols=[]
    for c in pool.columns:
        if c.startswith("m5_") or c.startswith("ctx_") or (c.startswith("m") and "_" in c and c[1:3].rstrip('_').isdigit()):feature_cols.append(c)
    for c in ("tod_sin","tod_cos","inst_flag","ret_diff_5m","ret_diff_15m","ret_diff_30m","ret_diff_60m","sign_agree_5m","sign_agree_15m","sign_agree_30m","sign_agree_60m","corr_prior_12","corr_prior_36","beta_prior_36","residual_current"):
        if c in pool.columns and c not in feature_cols:feature_cols.append(c)
    feature_cols=sorted(set(feature_cols))
    return contexts,pool,feature_cols,prov


def clean_X(df,cols):
    X=df[cols].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan;return X


def qualify_config(model,Xv,val,pid,side_name,hp):
    pred=model.predict(Xv);q=float(np.quantile(pred,QUAL["tail_quantile"]));mask=pred>=q
    b=pf_stats(val.loc[mask,f"label_{pid}_{side_name}"].to_numpy(float),val.loc[mask,"date"].to_numpy())
    s=pf_stats(val.loc[mask,f"stress_{pid}_{side_name}"].to_numpy(float),val.loc[mask,"date"].to_numpy())
    good=(b["n"]>=QUAL["minimum_tail_rows"] and b["pf"]>=QUAL["base_pf"] and s["pf"]>=QUAL["stress_pf"] and b["expectancy"] is not None and b["expectancy"]>0 and s["expectancy"] is not None and s["expectancy"]>0 and b["dates"]>=QUAL["minimum_dates"] and b["largest_winner_share"] is not None and b["largest_winner_share"]<=QUAL["largest_winner_share"])
    return {"qualified":bool(good),"threshold":max(0.0,q),"base":b,"stress":s,"hp":hp}


def fit_one(pool,features,pid,side_name,start):
    ws=start-pd.Timedelta(days=TRAIN_DAYS);vs=start-pd.Timedelta(days=VALID_DAYS);yc=f"label_{pid}_{side_name}";sc=f"stress_{pid}_{side_name}";ec=f"exit_{pid}_{side_name}"
    old=pool[(pool.time>=ws)&(pool.time<vs)&pool[yc].notna()&pool[sc].notna()&(pool[ec]<vs)].copy();val=pool[(pool.time>=vs)&(pool.time<start)&pool[yc].notna()&pool[sc].notna()&(pool[ec]<start)].copy();full=pool[(pool.time>=ws)&(pool.time<start)&pool[yc].notna()&pool[sc].notna()&(pool[ec]<start)].copy()
    if len(old)<300 or len(val)<200 or len(full)<600:return None
    Xo,yo=clean_X(old,features),old[yc].to_numpy(float);Xv=clean_X(val,features);Xf,yf=clean_X(full,features),full[yc].to_numpy(float);qualified=[];all_diag=[]
    for hp in PARAM_GRID:
        m=HistGradientBoostingRegressor(**MODEL_CONST,**hp);m.fit(Xo,yo);d=qualify_config(m,Xv,val,pid,side_name,hp);all_diag.append(d)
        if d["qualified"]:qualified.append(d)
    if not qualified:return {"enabled":False,"diagnostic":{"profile":pid,"side":side_name,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"qualified_configs":0,"best_unqualified":max(all_diag,key=lambda d:(min(d['base']['pf'],d['stress']['pf']),d['stress']['expectancy'] if d['stress']['expectancy'] is not None else -1e9))}}
    best=max(qualified,key=lambda d:(min(d["base"]["pf"],d["stress"]["pf"]),d["stress"]["expectancy"],d["base"]["dates"]));m=HistGradientBoostingRegressor(**MODEL_CONST,**best["hp"]);m.fit(Xf,yf)
    return {"enabled":True,"model":m,"threshold":best["threshold"],"diagnostic":{"profile":pid,"side":side_name,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"qualified_configs":len(qualified),"selected":best}}


def choose_signals(pool,features,models,start,end):
    out={"CNYRUBF":[],"USDRUBF":[]};summary={}
    for inst in out:
        q=pool[(pool.instrument==inst)&(pool.time>=start)&(pool.time<end)].sort_values("time");last=None;counts={}
        for _,r in q.iterrows():
            X=clean_X(pd.DataFrame([r]),features);by_side={1:[], -1:[]}
            for pid in PROFILES:
                for side_name,side in (("LONG",1),("SHORT",-1)):
                    fit=models.get((pid,side_name));
                    if not fit or not fit.get("enabled"):continue
                    p=float(fit["model"].predict(X)[0]);thr=float(fit["threshold"])
                    if p>=thr:by_side[side].append((p,pid,thr))
            long_ok=len(by_side[1])>=QUAL["consensus_profiles"];short_ok=len(by_side[-1])>=QUAL["consensus_profiles"]
            if long_ok and short_ok:last=None;continue
            if not long_ok and not short_ok:last=None;continue
            side=1 if long_ok else -1;p,pid,thr=max(by_side[side],key=lambda z:z[0]);key=(side,pid)
            if key!=last:
                out[inst].append({"signal_index":int(r.signal_index),"signal_time":str(r.time),"side":side,"profile":pid,"predicted_base_bps":p,"threshold":thr,"consensus_count":len(by_side[side])});counts[pid]=counts.get(pid,0)+1
            last=key
        summary[inst]={"state_onsets":len(out[inst]),"profiles":counts}
    return out,summary


def run(root:Path,out:Path,index:int):
    start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts,pool,features,prov=combine_features(root);models={};diag=[]
    for pid in PROFILES:
        for side_name in ("LONG","SHORT"):
            fit=fit_one(pool,features,pid,side_name,start);models[(pid,side_name)]=fit
            if fit:diag.append(fit["diagnostic"])
    sigs,summary=choose_signals(pool,features,models,start,end);inst_rows=[]
    for inst,(f,m1) in contexts.items():
        g=c11.execute_mixed(f,m1,sigs[inst],inst,0);b=c11.execute_mixed(f,m1,sigs[inst],inst,1);s=c11.execute_mixed(f,m1,sigs[inst],inst,2);inst_rows.append({"instrument":inst,"signals":sigs[inst],"gross_trades":g,"base_trades":b,"stress_trades":s,"gross":v3.metrics(g),"base":v3.metrics(b),"stress":v3.metrics(s)})
    result={"engine":"cycle16-sparse-consensus-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"feature_count":len(features),"qualification":QUAL,"model_diagnostics":diag,"prediction_summary":summary,"instruments":inst_rows,"provenance":prov}
    (out/"block_result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"features":len(features),"enabled_models":sum(1 for x in models.values() if x and x.get('enabled')),"summary":summary},indent=2))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--data-root",type=Path,default=Path("."));p.add_argument("--output",type=Path,required=True);p.add_argument("--block-index",type=int,required=True);a=p.parse_args();run(a.data_root,a.output,a.block_index)
