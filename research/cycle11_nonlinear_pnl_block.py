from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DISC_START=pd.Timestamp("2026-01-05")
DISC_END=pd.Timestamp("2026-05-16")
EVAL_START=pd.Timestamp("2026-03-02")
BLOCK_DAYS=7
TRAIN_DAYS=56
VALID_DAYS=14
PROFILES={
    "P1":(0.75,1.5,30),
    "P2":(1.00,2.0,60),
    "P3":(1.25,2.0,60),
    "P4":(1.50,3.0,120),
}
PARAM_GRID=[
    {"max_leaf_nodes":leaves,"min_samples_leaf":leaf,"l2_regularization":l2}
    for leaves in (7,15,31) for leaf in (20,50) for l2 in (1.0,10.0)
]
MODEL_CONST={"learning_rate":0.05,"max_iter":120,"early_stopping":False,"random_state":1729}


def load_v3():
    spec=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py")
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v3=load_v3()


def signal_clock(ts:pd.Timestamp)->bool:
    mins=ts.hour*60+ts.minute
    return (600<=mins<=775) or (840<=mins<=1010)


def load_context(root:Path,inst:str):
    m5raw,p5=v3.load_prefix(root,inst,"M5");m1,p1=v3.load_prefix(root,inst,"M1")
    f,features=v3.build_features(m5raw,inst,"M5")
    numeric=[x for x in features if x!="clock_bucket"]
    mins=f.time.dt.hour*60+f.time.dt.minute
    f["tod_sin"]=np.sin(2*np.pi*mins/1440.0);f["tod_cos"]=np.cos(2*np.pi*mins/1440.0)
    f["inst_flag"]=0.0 if inst=="CNYRUBF" else 1.0
    numeric += ["tod_sin","tod_cos","inst_flag"]
    if f.time.max()>=DISC_END or m1.time.max()>=DISC_END:raise PermissionError("Cycle11 fence violation")
    return f,m1,numeric,p5+p1


def isolated_trade(m5,m1,i:int,inst:str,side:int,profile:tuple[float,float,int],friction_ticks:int=1):
    stop_atr,target_r,hold_min=profile;tick=float(v3.SPECS[inst]["tick"]);cost=friction_ticks*tick
    st=pd.Timestamp(m5.time.iloc[i]);et=st+pd.Timedelta(minutes=5)
    lookup=getattr(isolated_trade,"_lookup",{});key=id(m1)
    if key not in lookup:
        times=m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);lookup[key]=(times,{int(t):j for j,t in enumerate(times)},m1.open.to_numpy(float),m1.high.to_numpy(float),m1.low.to_numpy(float),m1.close.to_numpy(float),m1.date.to_numpy());isolated_trade._lookup=lookup
    times,idxmap,op,hi,lo,cl,dates=lookup[key];ei=idxmap.get(int(et.value))
    if ei is None or dates[ei]!=m5.date.iloc[i]:return None
    atr=float(m5.atr14.iloc[i])
    if not np.isfinite(atr) or atr<=0:return None
    entry=float(op[ei]);risk=stop_atr*atr;stop=entry-side*risk;target=entry+side*target_r*risk
    force=pd.Timestamp(et.date())+pd.Timedelta(hours=17);deadline=min(et+pd.Timedelta(minutes=hold_min),force)
    di=idxmap.get(int(deadline.value))
    if di is None:di=int(np.searchsorted(times,int(deadline.value),side="right")-1)
    if di<ei or di>=len(m1) or dates[di]!=dates[ei]:return None
    xi=di;raw=float(op[di]) if idxmap.get(int(deadline.value))==di else float(cl[di]);reason="TIME"
    for j in range(ei,di+1):
        o,h,l=float(op[j]),float(hi[j]),float(lo[j])
        if side==1:
            if o<=stop:xi,raw,reason=j,o,"STOP_GAP";break
            if o>=target:xi,raw,reason=j,target,"TARGET_GAP_CONSERVATIVE";break
            hit_s=l<=stop;hit_t=h>=target
            if hit_s:xi,raw,reason=j,stop,"STOP_FIRST_TIE" if hit_t else "STOP";break
            if hit_t:xi,raw,reason=j,target,"TARGET";break
        else:
            if o>=stop:xi,raw,reason=j,o,"STOP_GAP";break
            if o<=target:xi,raw,reason=j,target,"TARGET_GAP_CONSERVATIVE";break
            hit_s=h>=stop;hit_t=l<=target
            if hit_s:xi,raw,reason=j,stop,"STOP_FIRST_TIE" if hit_t else "STOP";break
            if hit_t:xi,raw,reason=j,target,"TARGET";break
    ae=entry+side*cost;ax=raw-side*cost;pnl=side*(ax-ae);bps=10000*pnl/entry
    return {"bps":float(bps),"exit_time":pd.Timestamp(m1.time.iloc[xi]),"entry_time":pd.Timestamp(m1.time.iloc[ei]),"raw_entry":entry,"raw_exit":raw,"reason":reason}


def add_labels(f,m1,inst):
    eligible=np.array([signal_clock(t) for t in f.time],dtype=bool)
    for pid,p in PROFILES.items():
        for side,name in ((1,"LONG"),(-1,"SHORT")):
            y=np.full(len(f),np.nan);ex=np.full(len(f),np.datetime64("NaT","ns"),dtype="datetime64[ns]")
            for i in np.flatnonzero(eligible):
                r=isolated_trade(f,m1,int(i),inst,side,p,1)
                if r is not None:y[i]=r["bps"];ex[i]=np.datetime64(r["exit_time"],"ns")
            f[f"label_{pid}_{name}"]=y;f[f"exit_{pid}_{name}"]=ex
    f["eligible_clock"]=eligible
    return f


def pf_exp(y):
    y=np.asarray(y,float);y=y[np.isfinite(y)]
    if len(y)==0:return 0.0,None
    gp=y[y>0].sum();gl=-y[y<0].sum();pf=gp/gl if gl>0 else (float("inf") if gp>0 else 0.0)
    return float(pf),float(y.mean())


def clean_X(df,features):
    X=df[features].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=float,copy=True);X[~np.isfinite(X)]=np.nan;return X


def fit_side_profile(pool,features,side_name,pid,block_start):
    ws=block_start-pd.Timedelta(days=TRAIN_DAYS);vs=block_start-pd.Timedelta(days=VALID_DAYS)
    ycol=f"label_{pid}_{side_name}";ecol=f"exit_{pid}_{side_name}"
    old=pool[(pool.time>=ws)&(pool.time<vs)&pool.eligible_clock&pool[ycol].notna()&(pool[ecol]<vs)].copy()
    val=pool[(pool.time>=vs)&(pool.time<block_start)&pool.eligible_clock&pool[ycol].notna()&(pool[ecol]<block_start)].copy()
    full=pool[(pool.time>=ws)&(pool.time<block_start)&pool.eligible_clock&pool[ycol].notna()&(pool[ecol]<block_start)].copy()
    if len(old)<300 or len(val)<80 or len(full)<500:return None
    Xo=clean_X(old,features);yo=old[ycol].to_numpy(float);Xv=clean_X(val,features);yv=val[ycol].to_numpy(float);Xf=clean_X(full,features);yf=full[ycol].to_numpy(float)
    candidates=[]
    for hp in PARAM_GRID:
        model=HistGradientBoostingRegressor(**MODEL_CONST,**hp);model.fit(Xo,yo);pv=model.predict(Xv);mse=float(np.mean((pv-yv)**2));q=float(np.quantile(pv,0.90));tail=yv[pv>=q]
        if len(tail)>=10:
            pfe,ex=pf_exp(tail);rank=(1,float(min(pfe,20.0)),float(ex if ex is not None else -1e9),-mse)
        else:
            pfe,ex=0.0,None;rank=(0,0.0,-1e9,-mse)
        candidates.append({"hp":hp,"mse":mse,"val_pred_p90":q,"tail_n":int(len(tail)),"tail_pf":pfe,"tail_expectancy_bps":ex,"rank":rank})
    best=max(candidates,key=lambda z:z["rank"]);hp=best["hp"]
    threshold=max(0.0,float(best["val_pred_p90"]))
    model=HistGradientBoostingRegressor(**MODEL_CONST,**hp);model.fit(Xf,yf)
    return {"model":model,"threshold":threshold,"diagnostic":{"profile":pid,"side":side_name,"window_start":str(ws),"validation_start":str(vs),"old_rows":len(old),"validation_rows":len(val),"full_rows":len(full),"selected_hp":hp,"threshold":threshold,"selection":{k:v for k,v in best.items() if k not in ("hp","rank")}}}


def block_bounds(index:int):
    start=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*index)
    if start>=DISC_END:raise ValueError("block index out of range")
    return start,min(start+pd.Timedelta(days=BLOCK_DAYS),DISC_END)


def choose_signals(contexts,features,models,start,end):
    signals={inst:[] for inst in contexts};pred_summary={}
    for inst,(f,m1,_) in contexts.items():
        mask=(f.time>=start)&(f.time<end)&f.eligible_clock;idx=np.flatnonzero(mask.to_numpy());last_key=None;chosen_count={}
        for i in idx:
            row=f.iloc[[i]];X=clean_X(row,features);choices=[]
            for pid in PROFILES:
                for side_name,side in (("LONG",1),("SHORT",-1)):
                    fit=models.get((pid,side_name))
                    if fit is None:continue
                    p=float(fit["model"].predict(X)[0]);thr=float(fit["threshold"])
                    if p>=thr:choices.append((p,pid,side_name,side,thr))
            if not choices:last_key=None;continue
            p,pid,side_name,side,thr=max(choices,key=lambda z:z[0]);key=(pid,side)
            if key!=last_key:
                signals[inst].append({"signal_index":int(i),"signal_time":str(f.time.iloc[i]),"side":side,"profile":pid,"predicted_base_bps":p,"threshold":thr});chosen_count[pid]=chosen_count.get(pid,0)+1
            last_key=key
        pred_summary[inst]={"state_onsets":len(signals[inst]),"profiles":chosen_count}
    return signals,pred_summary


def execute_mixed(f,m1,signals,inst,friction_ticks):
    tick=float(v3.SPECS[inst]["tick"]);cost=friction_ticks*tick
    times=m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);lookup={int(t):i for i,t in enumerate(times)};op=m1.open.to_numpy(float);hi=m1.high.to_numpy(float);lo=m1.low.to_numpy(float);cl=m1.close.to_numpy(float);dates=m1.date.to_numpy();out=[];busy=-1
    for sig in signals:
        st=pd.Timestamp(sig["signal_time"]);et=st+pd.Timedelta(minutes=5);ei=lookup.get(int(et.value))
        if ei is None or ei<=busy or dates[ei]!=f.date.iloc[int(sig["signal_index"])]:continue
        side=int(sig["side"]);stop_atr,target_r,hold=PROFILES[sig["profile"]];atr=float(f.atr14.iloc[int(sig["signal_index"])]);entry=float(op[ei])
        if not np.isfinite(atr) or atr<=0:continue
        risk=stop_atr*atr;stop=entry-side*risk;target=entry+side*target_r*risk;force=pd.Timestamp(et.date())+pd.Timedelta(hours=17);deadline=min(et+pd.Timedelta(minutes=hold),force)
        di=lookup.get(int(deadline.value));exact=di is not None
        if di is None:di=int(np.searchsorted(times,int(deadline.value),side="right")-1)
        if di<ei or di>=len(m1) or dates[di]!=dates[ei]:continue
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
        busy=xi;ae=entry+side*cost;ax=raw-side*cost;pnl=side*(ax-ae)
        out.append({"instrument":inst,"date":str(dates[ei]),"month":str(pd.Timestamp(dates[ei]).to_period("M")),"side":side,"profile":sig["profile"],"predicted_base_bps":sig["predicted_base_bps"],"threshold":sig["threshold"],"signal_time":str(st),"entry_time":str(m1.time.iloc[ei]),"exit_time":str(m1.time.iloc[xi]),"entry":entry,"stop":stop,"target":target,"raw_exit":raw,"friction_ticks_per_side":friction_ticks,"bps":float(10000*pnl/entry),"reason":reason})
    return out


def run(root:Path,out:Path,index:int):
    start,end=block_bounds(index);out.mkdir(parents=True,exist_ok=True);contexts={};features=None;provenance=[];frames=[]
    for inst in ("CNYRUBF","USDRUBF"):
        f,m1,feat,prov=load_context(root,inst);f=add_labels(f,m1,inst);contexts[inst]=(f,m1,prov);provenance+=prov
        if features is None:features=feat
        q=f.copy();q["instrument_key"]=inst;frames.append(q)
    pool=pd.concat(frames,ignore_index=True,sort=False);models={};diagnostics=[]
    for pid in PROFILES:
        for side_name in ("LONG","SHORT"):
            fit=fit_side_profile(pool,features,side_name,pid,start);models[(pid,side_name)]=fit
            if fit is not None:diagnostics.append(fit["diagnostic"])
    signals,pred_summary=choose_signals(contexts,features,models,start,end);inst_results=[]
    for inst,(f,m1,_) in contexts.items():
        gross=execute_mixed(f,m1,signals[inst],inst,0);base=execute_mixed(f,m1,signals[inst],inst,1);stress=execute_mixed(f,m1,signals[inst],inst,2)
        inst_results.append({"instrument":inst,"signals":signals[inst],"gross_trades":gross,"base_trades":base,"stress_trades":stress,"gross":v3.metrics(gross),"base":v3.metrics(base),"stress":v3.metrics(stress)})
    result={"engine":"cycle11-nonlinear-pnl-v1","block_index":index,"block_start":str(start),"block_end_exclusive":str(end),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"profiles":PROFILES,"model_diagnostics":diagnostics,"prediction_summary":pred_summary,"instruments":inst_results,"provenance":provenance}
    (out/"block_result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");print(json.dumps({"block":index,"start":str(start),"end":str(end),"models":len(diagnostics),"summary":pred_summary},indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);ap.add_argument("--block-index",type=int,required=True);a=ap.parse_args();run(a.data_root,a.output,a.block_index)
