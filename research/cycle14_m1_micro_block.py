from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DISC_END=pd.Timestamp("2026-05-16");EVAL_START=pd.Timestamp("2026-03-02");BLOCK_DAYS=7;TRAIN_DAYS=56;VALID_DAYS=14
PROFILES={"P1":(0.75,1.5,30),"P2":(1.00,2.0,60),"P3":(1.25,2.0,60),"P4":(1.50,3.0,120)}
PARAM_GRID=[{"max_leaf_nodes":a,"min_samples_leaf":b,"l2_regularization":c} for a in (7,15,31) for b in (20,50) for c in (1.0,10.0)]
MODEL_CONST={"learning_rate":.05,"max_iter":120,"early_stopping":False,"random_state":31415}
WINDOWS=(5,15,30)

def mod(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3");c11=mod("research/cycle11_nonlinear_pnl_block.py","c11")

def block_bounds(i):
    s=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*i)
    if s>=DISC_END:raise ValueError("block out of range")
    return s,min(s+pd.Timedelta(days=BLOCK_DAYS),DISC_END)

def longest_run(signs,val):
    best=cur=0
    for x in signs:
        if x==val:cur+=1;best=max(best,cur)
        else:cur=0
    return best

def micro_for_bar(m1:pd.DataFrame,end_time:pd.Timestamp,atr:float):
    # M5 bar stamped t is fully known at t+5; last known M1 bar starts at t+4.
    last=end_time+pd.Timedelta(minutes=4);out={}
    if not np.isfinite(atr) or atr<=0:return None
    for n in WINDOWS:
        first=last-pd.Timedelta(minutes=n-1);w=m1[(m1.time>=first)&(m1.time<=last)].copy()
        if len(w)!=n or w.date.nunique()!=1:return None
        tt=w.time.tolist()
        if any(tt[k]-tt[k-1]!=pd.Timedelta(minutes=1) for k in range(1,len(tt))):return None
        close=w.close.to_numpy(float);op=w.open.to_numpy(float);high=w.high.to_numpy(float);low=w.low.to_numpy(float);vol=w.volume.to_numpy(float)
        d=np.diff(close);sg=np.sign(d);absd=np.abs(d);net=close[-1]-op[0];path=absd.sum();rms=float(np.sqrt(np.mean(d*d))) if len(d) else 0.0;hr=float(high.max()-low.min())
        denom=max(hr,1e-12);half=max(1,n//2);first_ret=close[half-1]-op[0];second_ret=close[-1]-op[half] if half<n else 0.0
        vm=float(np.median(vol));vmean=float(np.mean(vol));vstd=float(np.std(vol));pv=d*vol[1:] if len(d) else np.array([]);pvden=float(np.abs(pv).sum())
        p=f"m{n}_";out[p+"net_atr"]=net/atr;out[p+"abs_path_atr"]=path/atr;out[p+"rms_atr"]=rms/atr;out[p+"eff"]=abs(net)/path if path>1e-12 else 0.0;out[p+"frac_pos"]=float(np.mean(sg>0)) if len(sg) else 0.0;out[p+"frac_neg"]=float(np.mean(sg<0)) if len(sg) else 0.0;out[p+"sign_change"]=float(np.mean(sg[1:]!=sg[:-1])) if len(sg)>1 else 0.0;out[p+"run_pos"]=longest_run(sg,1);out[p+"run_neg"]=longest_run(sg,-1);out[p+"close_pos"]=(close[-1]-low.min())/denom;out[p+"range_atr"]=hr/atr;out[p+"max_abs_atr"]=(absd.max()/atr) if len(absd) else 0.0;out[p+"last_ret_atr"]=(d[-1]/atr) if len(d) else 0.0;out[p+"half_diff_atr"]=(first_ret-second_ret)/atr;out[p+"last_vol_med"]=vol[-1]/vm if vm>0 else np.nan;out[p+"vol_cv"]=vstd/vmean if vmean>0 else np.nan;out[p+"max_vol_share"]=float(vol.max()/vol.sum()) if vol.sum()>0 else np.nan;out[p+"pv_imbalance"]=float(pv.sum()/pvden) if pvden>0 else 0.0
    return out

def build_dataset(root:Path,inst:str):
    f,m1,_,prov=c11.load_context(root,inst);f=c11.add_labels(f,m1,inst);rows=[]
    for i,r in f.iterrows():
        if not c11.signal_clock(r.time):continue
        micro=micro_for_bar(m1,pd.Timestamp(r.time),float(r.atr14))
        if micro is None:continue
        row={"time":r.time,"date":r.date,"instrument":inst,"signal_index":int(i),"inst_flag":0.0 if inst=="CNYRUBF" else 1.0}
        row.update(micro);mins=r.time.hour*60+r.time.minute;row["tod_sin"]=float(np.sin(2*np.pi*mins/1440));row["tod_cos"]=float(np.cos(2*np.pi*mins/1440))
        for feat in ("ret_5m_atr","body_atr","range_atr","close_pos_candle","dist_pdh_atr","dist_pdl_atr","round_dist_atr","session_pos"):row["ctx_"+feat]=r[feat]
        for pid in PROFILES:
            for side in ("LONG","SHORT"):
                row[f"label_{pid}_{side}"]=f[f"label_{pid}_{side}"].iloc[i];row[f"exit_{pid}_{side}"]=f[f"exit_{pid}_{side}"].iloc[i]
        rows.append(row)
    return f,m1,pd.DataFrame(rows),prov

def feat_cols(df):return [c for c in df.columns if c.startswith("m") or c.startswith("ctx_")]+["tod_sin","tod_cos","inst_flag"]
def clean_X(df,cols):
    X=df[cols].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan;return X
def pf_exp(y):
    y=np.asarray(y,float);y=y[np.isfinite(y)]
    if not len(y):return 0.0,None
    gp=y[y>0].sum();gl=-y[y<0].sum();return (float(gp/gl) if gl else (float("inf") if gp else 0.0)),float(y.mean())
def fit_model(pool,cols,pid,side,start):
    ws=start-pd.Timedelta(days=TRAIN_DAYS);vs=start-pd.Timedelta(days=VALID_DAYS);yc=f"label_{pid}_{side}";ec=f"exit_{pid}_{side}"
    old=pool[(pool.time>=ws)&(pool.time<vs)&pool[yc].notna()&(pool[ec]<vs)];val=pool[(pool.time>=vs)&(pool.time<start)&pool[yc].notna()&(pool[ec]<start)];full=pool[(pool.time>=ws)&(pool.time<start)&pool[yc].notna()&(pool[ec]<start)]
    if len(old)<300 or len(val)<80 or len(full)<500:return None
    Xo,yo=clean_X(old,cols),old[yc].to_numpy(float);Xv,yv=clean_X(val,cols),val[yc].to_numpy(float);Xf,yf=clean_X(full,cols),full[yc].to_numpy(float);cand=[]
    for hp in PARAM_GRID:
        m=HistGradientBoostingRegressor(**MODEL_CONST,**hp);m.fit(Xo,yo);p=m.predict(Xv);mse=float(np.mean((p-yv)**2));q=float(np.quantile(p,.9));tail=yv[p>=q]
        if len(tail)>=10:pf,ex=pf_exp(tail);rank=(1,min(pf,20),ex if ex is not None else -1e9,-mse)
        else:pf,ex=0,None;rank=(0,0,-1e9,-mse)
        cand.append({"hp":hp,"mse":mse,"p90":q,"tail_n":len(tail),"tail_pf":pf,"tail_exp":ex,"rank":rank})
    best=max(cand,key=lambda z:z["rank"]);thr=max(0,float(best["p90"]));m=HistGradientBoostingRegressor(**MODEL_CONST,**best["hp"]);m.fit(Xf,yf)
    return {"model":m,"threshold":thr,"diag":{"profile":pid,"side":side,"old_rows":len(old),"val_rows":len(val),"full_rows":len(full),"hp":best["hp"],"threshold":thr,"tail_n":best["tail_n"],"tail_pf":best["tail_pf"],"tail_exp":best["tail_exp"]}}
def choose(ds,cols,models,start,end):
    out={"CNYRUBF":[],"USDRUBF":[]};summary={}
    for inst in out:
        q=ds[(ds.instrument==inst)&(ds.time>=start)&(ds.time<end)];last=None;counts={}
        for _,r in q.iterrows():
            X=clean_X(pd.DataFrame([r]),cols);choices=[]
            for pid in PROFILES:
                for sn,side in (("LONG",1),("SHORT",-1)):
                    fit=models.get((pid,sn));
                    if not fit:continue
                    p=float(fit["model"].predict(X)[0]);thr=fit["threshold"]
                    if p>=thr:choices.append((p,pid,side,thr))
            if not choices:last=None;continue
            p,pid,side,thr=max(choices,key=lambda z:z[0]);key=(pid,side)
            if key!=last:out[inst].append({"signal_index":int(r.signal_index),"signal_time":str(r.time),"side":side,"profile":pid,"predicted_base_bps":p,"threshold":thr});counts[pid]=counts.get(pid,0)+1
            last=key
        summary[inst]={"state_onsets":len(out[inst]),"profiles":counts}
    return out,summary
def run(root:Path,out:Path,index:int):
    start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts={};frames=[];prov=[]
    for inst in ("CNYRUBF","USDRUBF"):
        f,m1,ds,p=build_dataset(root,inst);contexts[inst]=(f,m1);frames.append(ds);prov+=p
    pool=pd.concat(frames,ignore_index=True,sort=False);cols=feat_cols(pool);models={};diag=[]
    for pid in PROFILES:
        for side in ("LONG","SHORT"):
            fit=fit_model(pool,cols,pid,side,start);models[(pid,side)]=fit
            if fit:diag.append(fit["diag"])
    sigs,summary=choose(pool,cols,models,start,end);inst_rows=[]
    for inst,(f,m1) in contexts.items():
        g=c11.execute_mixed(f,m1,sigs[inst],inst,0);b=c11.execute_mixed(f,m1,sigs[inst],inst,1);s=c11.execute_mixed(f,m1,sigs[inst],inst,2);inst_rows.append({"instrument":inst,"signals":sigs[inst],"gross_trades":g,"base_trades":b,"stress_trades":s,"gross":v3.metrics(g),"base":v3.metrics(b),"stress":v3.metrics(s)})
    result={"engine":"cycle14-m1-micro-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"feature_count":len(cols),"model_diagnostics":diag,"prediction_summary":summary,"instruments":inst_rows,"provenance":prov}
    (out/"block_result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"features":len(cols),"models":len(diag),"summary":summary},indent=2))
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("--data-root",type=Path,default=Path("."));a.add_argument("--output",type=Path,required=True);a.add_argument("--block-index",type=int,required=True);z=a.parse_args();run(z.data_root,z.output,z.block_index)
