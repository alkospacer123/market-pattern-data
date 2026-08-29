from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.neighbors import NearestNeighbors

DISC_END=pd.Timestamp("2026-05-16")
EVAL_START=pd.Timestamp("2026-03-02")
BLOCK_DAYS=7
TRAIN_DAYS=56
KS=(25,50,100)
SEQ_LEN=6
SEQ_FEATURES=("ret_5m_atr","body_atr","range_atr","close_pos_candle","relvol_60m","pos_60m","dist_high_60m_atr","dist_low_60m_atr","dist_pdh_atr","dist_pdl_atr")


def load_module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v3=load_module("research/autonomous_search_v3.py","v3")
c11=load_module("research/cycle11_nonlinear_pnl_block.py","c11")
PROFILES=c11.PROFILES


def block_bounds(index:int):
    start=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*index)
    if start>=DISC_END:raise ValueError("block index out of range")
    return start,min(start+pd.Timedelta(days=BLOCK_DAYS),DISC_END)


def build_sequences(f:pd.DataFrame,inst:str)->pd.DataFrame:
    rows=[];times=f.time.tolist();dates=f.date.to_numpy()
    label_cols=[f"label_{pid}_{side}" for pid in PROFILES for side in ("LONG","SHORT")]
    exit_cols=[f"exit_{pid}_{side}" for pid in PROFILES for side in ("LONG","SHORT")]
    for i in range(SEQ_LEN-1,len(f)):
        if not c11.signal_clock(times[i]):continue
        j0=i-(SEQ_LEN-1)
        if any(dates[j]!=dates[i] for j in range(j0,i+1)):continue
        if any((times[j]-times[j-1])!=pd.Timedelta(minutes=5) for j in range(j0+1,i+1)):continue
        row={"time":times[i],"date":dates[i],"instrument":inst,"signal_index":int(i),"tod_sin":float(np.sin(2*np.pi*(times[i].hour*60+times[i].minute)/1440.0)),"tod_cos":float(np.cos(2*np.pi*(times[i].hour*60+times[i].minute)/1440.0)),"inst_flag":0.0 if inst=="CNYRUBF" else 1.0}
        for lag,j in enumerate(range(j0,i+1)):
            # lag0 is oldest and lag5 is current; order is frozen and deterministic.
            for feat in SEQ_FEATURES:row[f"l{lag}_{feat}"]=float(f[feat].iloc[j]) if pd.notna(f[feat].iloc[j]) else np.nan
        for col in label_cols+exit_cols:row[col]=f[col].iloc[i]
        rows.append(row)
    return pd.DataFrame(rows)


def vector_columns():
    return [f"l{lag}_{feat}" for lag in range(SEQ_LEN) for feat in SEQ_FEATURES]+["tod_sin","tod_cos","inst_flag"]


def pf_exp_win(y):
    y=np.asarray(y,float);y=y[np.isfinite(y)]
    if len(y)==0:return {"n":0,"pf":0.0,"expectancy":None,"win_rate":0.0}
    gp=y[y>0].sum();gl=-y[y<0].sum();pf=gp/gl if gl>0 else (float("inf") if gp>0 else 0.0)
    return {"n":int(len(y)),"pf":float(pf),"expectancy":float(y.mean()),"win_rate":float((y>0).mean())}


def fit_space(hist:pd.DataFrame,features:list[str]):
    X=hist[features].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True)
    X[~np.isfinite(X)]=np.nan
    imp=SimpleImputer(strategy="median");Xi=imp.fit_transform(X)
    scaler=StandardScaler();Xs=scaler.fit_transform(Xi)
    ncomp=min(12,Xs.shape[1],max(1,Xs.shape[0]-1));pca=PCA(n_components=ncomp,random_state=1729);Xp=pca.fit_transform(Xs)
    nn=NearestNeighbors(n_neighbors=min(100,len(hist)),metric="euclidean");nn.fit(Xp)
    return imp,scaler,pca,nn,Xp


def transform_query(q,features,imp,scaler,pca):
    X=q[features].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan
    return pca.transform(scaler.transform(imp.transform(X)))


def choose_for_query(hist:pd.DataFrame,neighbor_idx:np.ndarray):
    choices=[]
    for pid in PROFILES:
        for side_name,side in (("LONG",1),("SHORT",-1)):
            col=f"label_{pid}_{side_name}";eligible=[]
            for k in KS:
                if len(neighbor_idx)<k:continue
                vals=hist.iloc[neighbor_idx[:k]][col].to_numpy(float);m=pf_exp_win(vals)
                ok=m["pf"]>=1.50 and m["expectancy"] is not None and m["expectancy"]>0 and m["win_rate"]>0.50
                if ok:eligible.append((k,m))
            if len(eligible)>=2:
                min_exp=min(m["expectancy"] for _,m in eligible);score=float(min_exp*math.sqrt(len(eligible)))
                choices.append({"score":score,"profile":pid,"side":side,"side_name":side_name,"eligible_depths":[{"k":k,**m} for k,m in eligible]})
    if not choices:return None
    return max(choices,key=lambda z:z["score"])


def run(root:Path,out:Path,index:int):
    start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts={};seqs=[];provenance=[]
    for inst in ("CNYRUBF","USDRUBF"):
        f,m1,_,prov=c11.load_context(root,inst);f=c11.add_labels(f,m1,inst);contexts[inst]=(f,m1);provenance+=prov;seqs.append(build_sequences(f,inst))
    pool=pd.concat(seqs,ignore_index=True,sort=False);features=vector_columns();ws=start-pd.Timedelta(days=TRAIN_DAYS)
    exit_cols=[f"exit_{pid}_{side}" for pid in PROFILES for side in ("LONG","SHORT")]
    hist_mask=(pool.time>=ws)&(pool.time<start)
    for col in exit_cols:hist_mask &= pool[col].notna() & (pool[col]<start)
    hist=pool.loc[hist_mask].reset_index(drop=True)
    if len(hist)<100:raise RuntimeError(f"insufficient causal analog pool: {len(hist)}")
    imp,scaler,pca,nn,_=fit_space(hist,features);signals={i:[] for i in contexts};diag={"historical_rows":len(hist),"pca_components":int(pca.n_components_),"pca_variance_sum":float(pca.explained_variance_ratio_.sum())}
    for inst,(f,m1) in contexts.items():
        q=pool[(pool.instrument==inst)&(pool.time>=start)&(pool.time<end)].copy().reset_index(drop=True)
        if q.empty:continue
        Xq=transform_query(q,features,imp,scaler,pca);_,inds=nn.kneighbors(Xq,n_neighbors=min(100,len(hist)),return_distance=True);last_key=None
        for qi in range(len(q)):
            choice=choose_for_query(hist,inds[qi])
            if choice is None:last_key=None;continue
            key=(choice["profile"],choice["side"])
            if key!=last_key:
                signals[inst].append({"signal_index":int(q.signal_index.iloc[qi]),"signal_time":str(q.time.iloc[qi]),"side":int(choice["side"]),"profile":choice["profile"],"analog_score":choice["score"],"analog_depths":choice["eligible_depths"]})
            last_key=key
    inst_results=[]
    for inst,(f,m1) in contexts.items():
        # Reuse Cycle 11 execution semantics; predicted_base_bps/threshold are audit-only fields expected by that function.
        adapted=[]
        for s in signals[inst]:adapted.append({**s,"predicted_base_bps":float(s["analog_score"]),"threshold":0.0})
        gross=c11.execute_mixed(f,m1,adapted,inst,0);base=c11.execute_mixed(f,m1,adapted,inst,1);stress=c11.execute_mixed(f,m1,adapted,inst,2)
        inst_results.append({"instrument":inst,"signals":signals[inst],"gross_trades":gross,"base_trades":base,"stress_trades":stress,"gross":v3.metrics(gross),"base":v3.metrics(base),"stress":v3.metrics(stress)})
    result={"engine":"cycle12-historical-analog-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"diagnostics":diag,"instruments":inst_results,"provenance":provenance}
    (out/"block_result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"start":str(start),"end":str(end),"hist":len(hist),"signals":{r['instrument']:len(r['signals']) for r in inst_results}},indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);ap.add_argument("--block-index",type=int,required=True);a=ap.parse_args();run(a.data_root,a.output,a.block_index)
