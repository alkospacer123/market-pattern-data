from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DISC_END=pd.Timestamp("2026-05-16")
EVAL_START=pd.Timestamp("2026-03-02")
BLOCK_DAYS=7
TRAIN_DAYS=56
VALID_DAYS=14
PROFILES={"P1":(0.75,1.5,30),"P2":(1.00,2.0,60),"P3":(1.25,2.0,60),"P4":(1.50,3.0,120)}
PARAM_GRID=[{"max_leaf_nodes":a,"min_samples_leaf":b,"l2_regularization":c} for a in (7,15,31) for b in (20,50) for c in (1.0,10.0)]
MODEL_CONST={"learning_rate":0.05,"max_iter":120,"early_stopping":False,"random_state":2718}
BASE_FIELDS=("ret_5m_atr","ret_15m_atr","ret_30m_atr","ret_60m_atr","ret_120m_atr","body_atr","range_atr","close_pos_candle","pos_30m","pos_60m","pos_120m","dist_high_60m_atr","dist_low_60m_atr","eff_30m","eff_60m","vol_15m_60m","vol_30m_120m","relvol_60m","round_dist_atr","dist_pdh_atr","dist_pdl_atr","session_pos")


def mod(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3");c11=mod("research/cycle11_nonlinear_pnl_block.py","c11")


def block_bounds(i):
    s=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*i)
    if s>=DISC_END:raise ValueError("block index out of range")
    return s,min(s+pd.Timedelta(days=BLOCK_DAYS),DISC_END)


def load_labeled(root,inst):
    f,m1,_,prov=c11.load_context(root,inst);f=c11.add_labels(f,m1,inst);return f,m1,prov


def build_joint(cny,usd):
    c_map={t:i for i,t in enumerate(cny.time)};u_map={t:i for i,t in enumerate(usd.time)};times=sorted(set(c_map)&set(u_map));rows=[]
    for t in times:
        ci=c_map[t];ui=u_map[t]
        if cny.date.iloc[ci]!=usd.date.iloc[ui]:continue
        r={"time":t,"date":cny.date.iloc[ci],"cny_index":ci,"usd_index":ui}
        for prefix,f,i in (("cny",cny,ci),("usd",usd,ui)):
            for feat in BASE_FIELDS:r[f"{prefix}_{feat}"]=f[feat].iloc[i]
            for pid in PROFILES:
                for side in ("LONG","SHORT"):
                    r[f"{prefix}_label_{pid}_{side}"]=f[f"label_{pid}_{side}"].iloc[i]
                    r[f"{prefix}_exit_{pid}_{side}"]=f[f"exit_{pid}_{side}"].iloc[i]
        rows.append(r)
    j=pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    for h in (5,15,30,60):
        a=pd.to_numeric(j[f"cny_ret_{h}m_atr"],errors="coerce");b=pd.to_numeric(j[f"usd_ret_{h}m_atr"],errors="coerce")
        j[f"ret_diff_{h}m"]=a-b;j[f"sign_agree_{h}m"]=np.where(a.notna()&b.notna(),np.sign(a)*np.sign(b),np.nan)
    c=pd.to_numeric(j["cny_ret_5m_atr"],errors="coerce");u=pd.to_numeric(j["usd_ret_5m_atr"],errors="coerce");cs=c.shift(1);us=u.shift(1)
    j["corr_prior_12"]=cs.rolling(12,min_periods=8).corr(us);j["corr_prior_36"]=cs.rolling(36,min_periods=20).corr(us)
    cov=cs.rolling(36,min_periods=20).cov(us);var=us.rolling(36,min_periods=20).var();j["beta_prior_36"]=cov/var.replace(0,np.nan);j["residual_current"]=c-j["beta_prior_36"]*u
    mins=j.time.dt.hour*60+j.time.dt.minute;j["tod_sin"]=np.sin(2*np.pi*mins/1440.0);j["tod_cos"]=np.cos(2*np.pi*mins/1440.0)
    j["eligible_clock"]=j.time.map(c11.signal_clock)
    return j


def features():
    x=[f"{p}_{f}" for p in ("cny","usd") for f in BASE_FIELDS]
    x += [f"ret_diff_{h}m" for h in (5,15,30,60)]+[f"sign_agree_{h}m" for h in (5,15,30,60)]+["corr_prior_12","corr_prior_36","beta_prior_36","residual_current","tod_sin","tod_cos"]
    return x


def clean_X(df,cols):
    X=df[cols].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan;return X


def pf_exp(y):
    y=np.asarray(y,float);y=y[np.isfinite(y)]
    if len(y)==0:return 0.0,None
    gp=y[y>0].sum();gl=-y[y<0].sum();return (float(gp/gl) if gl else (float("inf") if gp else 0.0)),float(y.mean())


def fit_model(j,cols,target,pid,side,start):
    ws=start-pd.Timedelta(days=TRAIN_DAYS);vs=start-pd.Timedelta(days=VALID_DAYS);pre="cny" if target=="CNYRUBF" else "usd";ycol=f"{pre}_label_{pid}_{side}";ecol=f"{pre}_exit_{pid}_{side}"
    old=j[(j.time>=ws)&(j.time<vs)&j.eligible_clock&j[ycol].notna()&(j[ecol]<vs)].copy();val=j[(j.time>=vs)&(j.time<start)&j.eligible_clock&j[ycol].notna()&(j[ecol]<start)].copy();full=j[(j.time>=ws)&(j.time<start)&j.eligible_clock&j[ycol].notna()&(j[ecol]<start)].copy()
    if len(old)<250 or len(val)<70 or len(full)<450:return None
    Xo=clean_X(old,cols);yo=old[ycol].to_numpy(float);Xv=clean_X(val,cols);yv=val[ycol].to_numpy(float);Xf=clean_X(full,cols);yf=full[ycol].to_numpy(float);cand=[]
    for hp in PARAM_GRID:
        m=HistGradientBoostingRegressor(**MODEL_CONST,**hp);m.fit(Xo,yo);p=m.predict(Xv);mse=float(np.mean((p-yv)**2));q=float(np.quantile(p,.90));tail=yv[p>=q]
        if len(tail)>=10:pf,ex=pf_exp(tail);rank=(1,min(pf,20.0),ex if ex is not None else -1e9,-mse)
        else:pf,ex=0.0,None;rank=(0,0.0,-1e9,-mse)
        cand.append({"hp":hp,"mse":mse,"p90":q,"tail_n":len(tail),"tail_pf":pf,"tail_exp":ex,"rank":rank})
    best=max(cand,key=lambda z:z["rank"]);thr=max(0.0,float(best["p90"]));model=HistGradientBoostingRegressor(**MODEL_CONST,**best["hp"]);model.fit(Xf,yf)
    return {"model":model,"threshold":thr,"diag":{"target":target,"profile":pid,"side":side,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"hp":best["hp"],"threshold":thr,"tail_n":best["tail_n"],"tail_pf":best["tail_pf"],"tail_exp":best["tail_exp"],"mse":best["mse"]}}


def choose_signals(j,cols,models,start,end):
    out={"CNYRUBF":[],"USDRUBF":[]};summary={}
    q=j[(j.time>=start)&(j.time<end)&j.eligible_clock]
    for target in out:
        last=None;counts={}
        for _,row in q.iterrows():
            X=clean_X(pd.DataFrame([row]),cols);choices=[]
            for pid in PROFILES:
                for side_name,side in (("LONG",1),("SHORT",-1)):
                    fit=models.get((target,pid,side_name))
                    if not fit:continue
                    p=float(fit["model"].predict(X)[0]);thr=fit["threshold"]
                    if p>=thr:choices.append((p,pid,side_name,side,thr))
            if not choices:last=None;continue
            p,pid,side_name,side,thr=max(choices,key=lambda z:z[0]);key=(pid,side)
            if key!=last:
                idx=int(row.cny_index if target=="CNYRUBF" else row.usd_index);out[target].append({"signal_index":idx,"signal_time":str(row.time),"side":side,"profile":pid,"predicted_base_bps":p,"threshold":thr});counts[pid]=counts.get(pid,0)+1
            last=key
        summary[target]={"state_onsets":len(out[target]),"profiles":counts}
    return out,summary


def run(root:Path,out:Path,index:int):
    start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);cny,cny_m1,p1=load_labeled(root,"CNYRUBF");usd,usd_m1,p2=load_labeled(root,"USDRUBF");j=build_joint(cny,usd);cols=features();models={};diags=[]
    for target in ("CNYRUBF","USDRUBF"):
        for pid in PROFILES:
            for side in ("LONG","SHORT"):
                fit=fit_model(j,cols,target,pid,side,start);models[(target,pid,side)]=fit
                if fit:diags.append(fit["diag"])
    sigs,summary=choose_signals(j,cols,models,start,end);inst=[]
    for target,f,m1 in (("CNYRUBF",cny,cny_m1),("USDRUBF",usd,usd_m1)):
        g=c11.execute_mixed(f,m1,sigs[target],target,0);b=c11.execute_mixed(f,m1,sigs[target],target,1);s=c11.execute_mixed(f,m1,sigs[target],target,2);inst.append({"instrument":target,"signals":sigs[target],"gross_trades":g,"base_trades":b,"stress_trades":s,"gross":v3.metrics(g),"base":v3.metrics(b),"stress":v3.metrics(s)})
    result={"engine":"cycle13-cross-leadlag-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"joint_rows":len(j),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"model_diagnostics":diags,"prediction_summary":summary,"instruments":inst,"provenance":p1+p2}
    (out/"block_result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"models":len(diags),"summary":summary},indent=2))

if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--data-root",type=Path,default=Path("."));a.add_argument("--output",type=Path,required=True);a.add_argument("--block-index",type=int,required=True);z=a.parse_args();run(z.data_root,z.output,z.block_index)
