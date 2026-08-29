from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
import numpy as np
import pandas as pd

DISC_END=pd.Timestamp("2026-05-16")
EVAL_START=pd.Timestamp("2026-03-02")
TRAIN_DAYS=56
VALID_DAYS=14
ALPHAS=(1.0,10.0,100.0)
FORECAST_HORIZON_MIN=30
STOP_ATR=1.5
TIME_EXIT_MIN=30
RESEARCH_GATES={"base_pf":1.30,"stress_pf":1.10,"minimum_trades":30,"minimum_unique_days":15,"minimum_positive_months":2,"largest_winner_share":0.25}

def load_engine():
    spec=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v3=load_engine()

FEATURES=[
 "range_atr","body_atr","body_frac","close_pos_candle","upper_wick_frac","lower_wick_frac",
 "ret_5m_atr","ret_15m_atr","ret_30m_atr","ret_60m_atr","ret_120m_atr",
 "pos_15m","pos_30m","pos_60m","pos_120m","pos_240m",
 "dist_high_15m_atr","dist_low_15m_atr","dist_high_30m_atr","dist_low_30m_atr",
 "dist_high_60m_atr","dist_low_60m_atr","dist_high_120m_atr","dist_low_120m_atr",
 "dist_high_240m_atr","dist_low_240m_atr",
 "eff_15m","eff_30m","eff_60m","eff_120m","vol_15m_60m","vol_30m_120m",
 "relvol_60m","vol_z_60m","round_dist_atr","round_pos","dist_pdh_atr","dist_pdl_atr",
 "gap_prevclose_atr","session_pos","tod_sin","tod_cos"
]

def context(root:Path,inst:str):
    m1,p1=v3.load_prefix(root,inst,"M1")
    m5raw,p5=v3.load_prefix(root,inst,"M5")
    f,_=v3.build_features(m5raw,inst,"M5")
    mins=f.time.dt.hour*60+f.time.dt.minute
    f["tod_sin"]=np.sin(2*np.pi*mins/1440.0);f["tod_cos"]=np.cos(2*np.pi*mins/1440.0)
    f["target"]=pd.to_numeric(f["fwd_30m_atr"],errors="coerce")
    f["target_end"]=f.time+pd.Timedelta(minutes=FORECAST_HORIZON_MIN)
    if f.time.max()>=DISC_END or m1.time.max()>=DISC_END:raise PermissionError("Cycle6 fence violation")
    return f,m1,p1+p5

def matrix(f,mask):
    X=f.loc[mask,FEATURES].apply(pd.to_numeric,errors="coerce").to_numpy(float)
    y=f.loc[mask,"target"].to_numpy(float)
    return X,y

def fit_preprocess(X):
    med=np.nanmedian(X,axis=0);med=np.where(np.isfinite(med),med,0.0)
    Xi=np.where(np.isfinite(X),X,med)
    mu=Xi.mean(axis=0);sd=Xi.std(axis=0);sd=np.where(sd>1e-9,sd,1.0)
    return med,mu,sd

def transform(X,prep):
    med,mu,sd=prep;Xi=np.where(np.isfinite(X),X,med);return (Xi-mu)/sd

def ridge_fit(X,y,alpha):
    X1=np.column_stack([np.ones(len(X)),X]);pen=np.eye(X1.shape[1]);pen[0,0]=0.0
    return np.linalg.solve(X1.T@X1+alpha*pen,X1.T@y)

def ridge_pred(X,beta):return beta[0]+X@beta[1:]

def pooled_rows(contexts,start,end,target_cutoff):
    Xs=[];ys=[]
    for inst,(f,_,_) in contexts.items():
        mask=((f.time>=start)&(f.time<end)&(f.target_end<=target_cutoff)&np.isfinite(f.target)).to_numpy()
        X,y=matrix(f,mask)
        if len(y):Xs.append(X);ys.append(y)
    if not Xs:return np.empty((0,len(FEATURES))),np.empty(0)
    return np.vstack(Xs),np.concatenate(ys)

def fit_block_model(contexts,block_start):
    window_start=block_start-pd.Timedelta(days=TRAIN_DAYS);valid_start=block_start-pd.Timedelta(days=VALID_DAYS)
    Xold,yold=pooled_rows(contexts,window_start,valid_start,valid_start)
    Xval,yval=pooled_rows(contexts,valid_start,block_start,block_start)
    if len(yold)<500 or len(yval)<100:raise RuntimeError("insufficient pooled causal rows")
    prep=fit_preprocess(Xold);Xot=transform(Xold,prep);Xvt=transform(Xval,prep)
    errors={};models={};preds={}
    for a in ALPHAS:
        beta=ridge_fit(Xot,yold,a);p=ridge_pred(Xvt,beta);errors[a]=float(np.mean((p-yval)**2));models[a]=beta;preds[a]=p
    alpha=min(ALPHAS,key=lambda a:errors[a]);pval=preds[alpha]
    threshold=float(max(0.10,np.quantile(np.abs(pval),0.80)))
    Xfull,yfull=pooled_rows(contexts,window_start,block_start,block_start)
    prep_full=fit_preprocess(Xfull);beta_full=ridge_fit(transform(Xfull,prep_full),yfull,alpha)
    corr=float(np.corrcoef(pval,yval)[0,1]) if np.std(pval)>0 and np.std(yval)>0 else None
    return {"alpha":alpha,"threshold":threshold,"prep":prep_full,"beta":beta_full,"mse_by_alpha":errors,"validation_corr":corr,"train_rows":len(yfull),"validation_rows":len(yval),"window_start":window_start,"valid_start":valid_start}

def predict_block(f,start,end,model):
    mask=((f.time>=start)&(f.time<end)).to_numpy();idx=np.flatnonzero(mask)
    if not len(idx):return []
    X=f.loc[mask,FEATURES].apply(pd.to_numeric,errors="coerce").to_numpy(float);p=ridge_pred(transform(X,model["prep"]),model["beta"]);th=model["threshold"]
    long=p>=th;short=p<=-th;dates=f.date.iloc[idx].to_numpy();signals=[]
    prev_long=False;prev_short=False;prev_date=None
    for k,i in enumerate(idx):
        d=dates[k]
        if prev_date is None or d!=prev_date:prev_long=prev_short=False
        if long[k] and not prev_long:
            signals.append({"signal_index":int(i),"signal_time":f.time.iloc[i],"side":1,"prediction":float(p[k]),"threshold":th,"atr":float(f.atr14.iloc[i])})
        elif short[k] and not prev_short:
            signals.append({"signal_index":int(i),"signal_time":f.time.iloc[i],"side":-1,"prediction":float(p[k]),"threshold":th,"atr":float(f.atr14.iloc[i])})
        prev_long=bool(long[k]);prev_short=bool(short[k]);prev_date=d
    return signals

def execute_mixed(f,m1,signals,inst,friction_ticks):
    if not signals:return []
    times=m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);lookup={int(t):i for i,t in enumerate(times)}
    dates=m1.date.to_numpy();op=m1.open.to_numpy(float);hi=m1.high.to_numpy(float);lo=m1.low.to_numpy(float);cl=m1.close.to_numpy(float);tick=v3.SPECS[inst]["tick"]
    out=[];available=-1
    for sig in sorted(signals,key=lambda z:z["signal_time"]):
        st=pd.Timestamp(sig["signal_time"]);entry_time=st+pd.Timedelta(minutes=5);ei=lookup.get(int(entry_time.value))
        if ei is None or ei<=available:continue
        if dates[ei]!=f.date.iloc[sig["signal_index"]]:continue
        atr=sig["atr"];side=int(sig["side"])
        if not np.isfinite(atr) or atr<=0:continue
        entry=float(op[ei]);stop=entry-side*STOP_ATR*atr;limit=int((entry_time+pd.Timedelta(minutes=TIME_EXIT_MIN)).value)
        xi=int(np.searchsorted(times,limit,side="left")-1);xi=max(xi,ei)
        while xi>ei and dates[xi]!=dates[ei]:xi-=1
        raw=float(cl[xi]);reason="TIME"
        for j in range(ei,xi+1):
            o=float(op[j]);h=float(hi[j]);l=float(lo[j])
            if side==1:
                if o<=stop:xi=j;raw=o;reason="STOP_GAP";break
                if l<=stop:xi=j;raw=stop;reason="STOP";break
            else:
                if o>=stop:xi=j;raw=o;reason="STOP_GAP";break
                if h>=stop:xi=j;raw=stop;reason="STOP";break
        available=xi;cost=friction_ticks*tick;adj_entry=entry+side*cost;adj_exit=raw-side*cost;pnl=side*(adj_exit-adj_entry)
        out.append({"bps":float(10000*pnl/entry),"date":str(dates[ei]),"instrument":inst,"timeframe":"M5","side":side,"prediction":sig["prediction"],"threshold":sig["threshold"],"signal_time":str(st),"entry_time":str(m1.time.iloc[ei]),"exit_time":str(m1.time.iloc[xi]),"reason":reason})
    return out

def gate(metrics_base,metrics_stress):
    b=metrics_base;s=metrics_stress;fail=[]
    if b["pf"]<RESEARCH_GATES["base_pf"]:fail.append("BASE_PF")
    if s["pf"]<RESEARCH_GATES["stress_pf"]:fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if b["trades"]<RESEARCH_GATES["minimum_trades"]:fail.append("TRADES")
    if b["unique_days"]<RESEARCH_GATES["minimum_unique_days"]:fail.append("UNIQUE_DAYS")
    if b["positive_months"]<RESEARCH_GATES["minimum_positive_months"]:fail.append("BASE_MONTHS")
    if s["positive_months"]<RESEARCH_GATES["minimum_positive_months"]:fail.append("STRESS_MONTHS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>RESEARCH_GATES["largest_winner_share"]:fail.append("CONCENTRATION")
    return not fail,fail

def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True);contexts={}
    for inst in ("CNYRUBF","USDRUBF"):contexts[inst]=context(root,inst)
    all_signals={i:[] for i in contexts};blocks=[];start=EVAL_START
    while start<DISC_END:
        end=min(start+pd.Timedelta(days=7),DISC_END);model=fit_block_model(contexts,start);bd={"start":str(start),"end_exclusive":str(end),"alpha":model["alpha"],"threshold":model["threshold"],"mse_by_alpha":model["mse_by_alpha"],"validation_corr":model["validation_corr"],"train_rows":model["train_rows"],"validation_rows":model["validation_rows"],"signals":{}}
        for inst,(f,_,_) in contexts.items():
            sigs=predict_block(f,start,end,model);all_signals[inst]+=sigs;bd["signals"][inst]=len(sigs)
        blocks.append(bd);start=end
    instrument_rows=[];combined_base=[];combined_stress=[]
    for inst,(f,m1,prov) in contexts.items():
        btr=execute_mixed(f,m1,all_signals[inst],inst,1);str_=execute_mixed(f,m1,all_signals[inst],inst,2);bm=v3.metrics(btr);sm=v3.metrics(str_);combined_base+=btr;combined_stress+=str_;instrument_rows.append({"instrument":inst,"base":bm,"stress":sm,"signals":len(all_signals[inst]),"base_trades":btr,"stress_trades":str_,"provenance":prov})
    cb=v3.metrics(combined_base);cs=v3.metrics(combined_stress);passed,fail=gate(cb,cs)
    result={"engine":"cycle6-pooled-causal-ridge-v1","status":"RESEARCH_GATE_PASS_AWAITING_NEW_CONFIRMATION_DATA" if passed else "RESEARCH_GATE_FAIL","data_end_exclusive":str(DISC_END),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"features":FEATURES,"alphas":ALPHAS,"forecast_horizon_min":FORECAST_HORIZON_MIN,"stop_atr":STOP_ATR,"time_exit_min":TIME_EXIT_MIN,"blocks":blocks,"instruments":instrument_rows,"combined":{"base":cb,"stress":cs,"gate_pass":passed,"gate_failures":fail},"research_gates":RESEARCH_GATES}
    compact=json.loads(json.dumps(result,default=v3.jsonable));
    for r in compact["instruments"]:r.pop("base_trades",None);r.pop("stress_trades",None)
    (out/"result.json").write_text(json.dumps(compact,indent=2)+"\n");(out/"combined_base_trades.json").write_text(json.dumps(combined_base,indent=2,default=v3.jsonable)+"\n")
    lines=["# Cycle 6 — Pooled Causal Ridge Forecast","",f"Status: **{result['status']}**",f"Combined BASE: PF={cb['pf']:.3f}, exp={cb['expectancy_bps']}, N={cb['trades']}, days={cb['unique_days']}",f"Combined STRESS: PF={cs['pf']:.3f}, exp={cs['expectancy_bps']}, N={cs['trades']}",f"Gate failures: {fail}",""]
    for r in instrument_rows:lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f} exp={r['base']['expectancy_bps']} N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f} exp={r['stress']['expectancy_bps']} N={r['stress']['trades']}")
    lines += ["","Retired May16-Jul1 confirmation was not read. 2025 TRUE OOS was not read. A research pass still requires genuinely new untouched confirmation data."]
    (out/"report.md").write_text("\n".join(lines)+"\n");print(json.dumps(compact,indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();run(a.data_root,a.output)
