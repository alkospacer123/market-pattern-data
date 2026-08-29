from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

TRAIN_START=pd.Timestamp("2026-01-05")
TRAIN_END=pd.Timestamp("2026-03-01")
DISC_END=pd.Timestamp("2026-05-16")
FOLDS=[
    ("MARCH",pd.Timestamp("2026-03-01"),pd.Timestamp("2026-04-01")),
    ("APRIL",pd.Timestamp("2026-04-01"),pd.Timestamp("2026-05-01")),
    ("MAY15",pd.Timestamp("2026-05-01"),pd.Timestamp("2026-05-16")),
]
WINDOWS=(60,120,240)
ENTRY_ZS=(1.5,2.0,2.5)
EXIT_ZS=(0.25,0.50)
HOLDS=(60,120)
GRID=[(w,e,x,h) for w in WINDOWS for e in ENTRY_ZS for x in EXIT_ZS for h in HOLDS]
GATES={"base_pf_min":1.50,"stress_pf_min":1.20,"minimum_base_trades":20,"minimum_unique_days":12,"minimum_positive_base_folds":3,"minimum_positive_stress_folds":2,"largest_winner_share_max":0.25,"minimum_stable_neighbors":2}
MULT=1000.0

def load_v3():
    spec=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v3=load_v3()

def signal_clock(ts:pd.Timestamp)->bool:
    mins=ts.hour*60+ts.minute
    return (600<=mins<=775) or (840<=mins<=1010)

def load_aligned(root:Path):
    cm5,pc5=v3.load_prefix(root,"CNYRUBF","M5");um5,pu5=v3.load_prefix(root,"USDRUBF","M5")
    cm1,pc1=v3.load_prefix(root,"CNYRUBF","M1");um1,pu1=v3.load_prefix(root,"USDRUBF","M1")
    m5=um5[["time","open","high","low","close","volume","date"]].rename(columns={c:f"u_{c}" for c in ("open","high","low","close","volume")}).merge(cm5[["time","open","high","low","close","volume"]].rename(columns={c:f"c_{c}" for c in ("open","high","low","close","volume")}),on="time",how="inner")
    m5["date"]=m5.time.dt.date;m5["month"]=m5.time.dt.to_period("M").astype(str);m5["spread"]=np.log(m5.u_close/m5.c_close)
    m1=um1[["time","open","high","low","close","date"]].rename(columns={c:f"u_{c}" for c in ("open","high","low","close")}).merge(cm1[["time","open","high","low","close"]].rename(columns={c:f"c_{c}" for c in ("open","high","low","close")}),on="time",how="inner")
    m1["date"]=m1.time.dt.date
    if m5.empty or m1.empty or m5.time.max()>=DISC_END or m1.time.max()>=DISC_END:raise PermissionError("Cycle10 fence violation")
    return m5,m1,pc5+pu5+pc1+pu1

def add_z(m5:pd.DataFrame,window_min:int)->pd.DataFrame:
    f=m5.copy();bars=max(2,window_min//5)
    mean=f.groupby("date",sort=False).spread.transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).mean())
    std=f.groupby("date",sort=False).spread.transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).std())
    f["z"]=(f.spread-mean)/std.replace(0,np.nan)
    return f

def generate_signals(f:pd.DataFrame,entry_z:float)->list[dict[str,Any]]:
    z=f.z.to_numpy(float);dates=f.date.to_numpy();times=f.time.tolist();out=[]
    for i in range(1,len(f)):
        if dates[i]!=dates[i-1] or not signal_clock(times[i]) or not np.isfinite(z[i]) or not np.isfinite(z[i-1]):continue
        if z[i]>=entry_z and z[i-1]<entry_z:
            out.append({"signal_index":i,"signal_time":str(times[i]),"ratio_side":-1,"signal_z":float(z[i])})
        elif z[i]<=-entry_z and z[i-1]>-entry_z:
            out.append({"signal_index":i,"signal_time":str(times[i]),"ratio_side":1,"signal_z":float(z[i])})
    return out

def subset(signals,start,end):return [s for s in signals if start<=pd.Timestamp(s["signal_time"])<end]

def execute(f:pd.DataFrame,m1:pd.DataFrame,signals:list[dict[str,Any]],entry_z:float,exit_z:float,max_hold:int,friction_ticks:int)->list[dict[str,Any]]:
    tick_u=float(v3.SPECS["USDRUBF"]["tick"]);tick_c=float(v3.SPECS["CNYRUBF"]["tick"])
    times=m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);lookup={int(t):i for i,t in enumerate(times)};dates=m1.date.to_numpy();uo=m1.u_open.to_numpy(float);co=m1.c_open.to_numpy(float)
    f_times=f.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);z=f.z.to_numpy(float);f_dates=f.date.to_numpy();busy=-1;out=[]
    for sig in signals:
        si=int(sig["signal_index"]);st=pd.Timestamp(sig["signal_time"]);entry_time=st+pd.Timedelta(minutes=5);ei=lookup.get(int(entry_time.value))
        if ei is None or ei<=busy or dates[ei]!=f_dates[si]:continue
        side_u=int(sig["ratio_side"]);side_c=-side_u;ue=float(uo[ei]);ce=float(co[ei]);n_c=max(1,int(round(ue/ce)))
        deadline=min(entry_time+pd.Timedelta(minutes=max_hold),pd.Timestamp(entry_time.date())+pd.Timedelta(hours=17))
        # Default time/17:00 exit at exact synchronized M1 open when available, else last prior synchronized M1 open.
        di=lookup.get(int(deadline.value))
        if di is None:
            di=int(np.searchsorted(times,int(deadline.value),side="right")-1)
        if di<ei or di>=len(m1) or dates[di]!=dates[ei]:continue
        xi=di;reason="TIME" if deadline.hour<17 else "FORCE_1700"
        # Exit signals are known only after an M5 close and execute at that close's next M1 open.
        for j in range(si+1,len(f)):
            if f_dates[j]!=f_dates[si]:break
            exec_time=pd.Timestamp(f.time.iloc[j])+pd.Timedelta(minutes=5)
            if exec_time>deadline:break
            zj=z[j]
            if not np.isfinite(zj):continue
            exit_reason=None
            if side_u==-1:  # short high ratio
                if zj<=exit_z:exit_reason="MEAN_REVERT"
                elif zj>=entry_z+1.0:exit_reason="SPREAD_STOP"
            else:           # long low ratio
                if zj>=-exit_z:exit_reason="MEAN_REVERT"
                elif zj<=-(entry_z+1.0):exit_reason="SPREAD_STOP"
            if exit_reason:
                q=lookup.get(int(exec_time.value))
                if q is not None and q>=ei and q<=di and dates[q]==dates[ei]:xi=q;reason=exit_reason;break
        busy=xi;ux=float(uo[xi]);cx=float(co[xi]);cu=friction_ticks*tick_u;cc=friction_ticks*tick_c
        aue=ue+side_u*cu;aux=ux-side_u*cu;ace=ce+side_c*cc;acx=cx-side_c*cc
        pnl_u=MULT*side_u*(aux-aue);pnl_c=MULT*n_c*side_c*(acx-ace);pnl=pnl_u+pnl_c;notional=MULT*ue+MULT*n_c*ce;bps=10000*pnl/notional
        out.append({"date":str(dates[ei]),"month":str(pd.Timestamp(dates[ei]).to_period("M")),"signal_time":str(st),"entry_time":str(m1.time.iloc[ei]),"exit_time":str(m1.time.iloc[xi]),"ratio_side":side_u,"signal_z":sig["signal_z"],"entry_z":entry_z,"exit_z":exit_z,"max_hold_minutes":max_hold,"hedge_cny_contracts":n_c,"u_entry":ue,"c_entry":ce,"u_exit":ux,"c_exit":cx,"friction_ticks_per_leg_side":friction_ticks,"pnl_rub":float(pnl),"gross_notional_rub":float(notional),"bps":float(bps),"reason":reason})
    return out

def month_total(trades,month):return sum(t["bps"] for t in trades if t["date"].startswith(month))
def model_run(base_m5,m1,params,start,end):
    w,e,x,h=params;f=add_z(base_m5,w);signals=subset(generate_signals(f,e),start,end);gt=execute(f,m1,signals,e,x,h,0);bt=execute(f,m1,signals,e,x,h,1);st=execute(f,m1,signals,e,x,h,2);return f,signals,gt,bt,st

def train_select(m5,m1):
    eligible=[];rows=[]
    for p in GRID:
        _,sig,gt,bt,st=model_run(m5,m1,p,TRAIN_START,TRAIN_END);gm,bm,sm=v3.metrics(gt),v3.metrics(bt),v3.metrics(st)
        months_ok=month_total(bt,"2026-01")>0 and month_total(bt,"2026-02")>0 and month_total(st,"2026-01")>0 and month_total(st,"2026-02")>0
        ok=bm["trades"]>=15 and bm["pf"]>=1.20 and sm["pf"]>=1.0 and (bm["expectancy_bps"] or -1e9)>0 and (sm["expectancy_bps"] or -1e9)>0 and months_ok
        row={"rolling_window_minutes":p[0],"entry_z":p[1],"exit_z":p[2],"max_hold_minutes":p[3],"signals":len(sig),"gross":gm,"base":bm,"stress":sm,"jan_base_bps":month_total(bt,"2026-01"),"feb_base_bps":month_total(bt,"2026-02"),"jan_stress_bps":month_total(st,"2026-01"),"feb_stress_bps":month_total(st,"2026-02"),"eligible":bool(ok),"selection_primary":float(min(bm["pf"],sm["pf"])),"selection_secondary":float(sm["expectancy_bps"] if sm["expectancy_bps"] is not None else -1e9)};rows.append(row)
        if ok:eligible.append(row)
    eligible.sort(key=lambda r:(r["selection_primary"],r["selection_secondary"]),reverse=True);return (eligible[0] if eligible else None),rows

def eval_folds(m5,m1,p):
    folds=[];gb=[];bb=[];sb=[]
    for fid,start,end in FOLDS:
        _,sig,gt,bt,st=model_run(m5,m1,p,start,end);gm,bm,sm=v3.metrics(gt),v3.metrics(bt),v3.metrics(st);folds.append({"fold_id":fid,"signals":len(sig),"gross":gm,"base":bm,"stress":sm});gb+=gt;bb+=bt;sb+=st
    gm,bm,sm=v3.metrics(gb),v3.metrics(bb),v3.metrics(sb);bm["positive_folds"]=sum(q["base"]["expectancy_bps"] is not None and q["base"]["expectancy_bps"]>0 for q in folds);sm["positive_folds"]=sum(q["stress"]["expectancy_bps"] is not None and q["stress"]["expectancy_bps"]>0 for q in folds);return {"gross":gm,"base":bm,"stress":sm,"folds":folds,"base_trades":bb,"stress_trades":sb}

def neighbors(p):
    vals=(WINDOWS,ENTRY_ZS,EXIT_ZS,HOLDS);out=[]
    for k,arr in enumerate(vals):
        i=arr.index(p[k])
        for j in (i-1,i+1):
            if 0<=j<len(arr):q=list(p);q[k]=arr[j];out.append(tuple(q))
    return out

def gate(ev,stable):
    b,s=ev["base"],ev["stress"];fail=[]
    if b["pf"]<GATES["base_pf_min"]:fail.append("BASE_PF")
    if s["pf"]<GATES["stress_pf_min"]:fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if b["trades"]<GATES["minimum_base_trades"]:fail.append("TRADES")
    if b["unique_days"]<GATES["minimum_unique_days"]:fail.append("UNIQUE_DAYS")
    if b.get("positive_folds",0)<GATES["minimum_positive_base_folds"]:fail.append("BASE_FOLDS")
    if s.get("positive_folds",0)<GATES["minimum_positive_stress_folds"]:fail.append("STRESS_FOLDS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>GATES["largest_winner_share_max"]:fail.append("CONCENTRATION")
    if stable<GATES["minimum_stable_neighbors"]:fail.append("PARAMETER_PLATEAU")
    return not fail,fail

def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True);m5,m1,prov=load_aligned(root);selected,train_grid=train_select(m5,m1)
    result={"engine":"cycle10-cny-usd-relative-value-v1","data_end_exclusive":str(DISC_END),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"contract_multiplier":1000,"training_grid":train_grid,"selected":selected,"provenance":prov,"gates":GATES}
    if selected is None:
        result.update({"status":"NO_TRAIN_ELIGIBLE_MODEL","gate_pass":False,"gate_failures":["TRAIN_SELECTION"]})
    else:
        p=(int(selected["rolling_window_minutes"]),float(selected["entry_z"]),float(selected["exit_z"]),int(selected["max_hold_minutes"]));ev=eval_folds(m5,m1,p);nrows=[];stable=0
        for q in neighbors(p):
            nev=eval_folds(m5,m1,q);b,s=nev["base"],nev["stress"];ok=b["pf"]>=1.20 and s["pf"]>=1.0 and (b["expectancy_bps"] or -1e9)>0 and (s["expectancy_bps"] or -1e9)>0;stable+=int(ok);nrows.append({"params":{"rolling_window_minutes":q[0],"entry_z":q[1],"exit_z":q[2],"max_hold_minutes":q[3]},"base":b,"stress":s,"stable":bool(ok)})
        passed,fail=gate(ev,stable);result.update({"status":"RESEARCH_ONLY_AWAITING_NEW_CONFIRMATION_DATA" if passed else "FORWARD_RESEARCH_FAIL","validation":{k:v for k,v in ev.items() if k not in ("base_trades","stress_trades")},"stable_neighbors":stable,"neighbor_results":nrows,"gate_pass":passed,"gate_failures":fail});(out/"base_trades.json").write_text(json.dumps(ev["base_trades"],indent=2,default=v3.jsonable)+"\n");(out/"stress_trades.json").write_text(json.dumps(ev["stress_trades"],indent=2,default=v3.jsonable)+"\n")
    (out/"result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n")
    lines=["# Cycle 10 — CNY/USDRUB Relative-Value Spread","",f"Status: **{result['status']}**",f"Jan-Feb eligible model: {selected}",""]
    if "validation" in result:
        b=result["validation"]["base"];s=result["validation"]["stress"];lines += [f"Mar-May BASE: PF={b['pf']:.3f}, exp={b['expectancy_bps']}, N={b['trades']}, days={b['unique_days']}, folds={b.get('positive_folds')}",f"Mar-May STRESS: PF={s['pf']:.3f}, exp={s['expectancy_bps']}, N={s['trades']}, folds={s.get('positive_folds')}",f"Stable neighbors: {result['stable_neighbors']}",f"Gate failures: {result['gate_failures']}"]
    lines += ["","March-May is retrospective robustness data, not untouched OOS.","Retired May16-Jul1 data and 2025 TRUE OOS were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print(json.dumps(result,indent=2,default=v3.jsonable))
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();run(a.data_root,a.output)
