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
SIGNAL_GRID=[{"touch_tolerance_ticks":t,"touch_lookback_bars":lb,"breakout_confirm_ticks":c} for t in (0,1) for lb in (3,6,12) for c in (1,2)]
STOP_BUFFERS=(3,5,8,13)
TARGET_RRS=(2.0,3.0,4.0)
EXEC_GRID=[(b,r) for b in STOP_BUFFERS for r in TARGET_RRS]
GATES={"base_pf_min":1.50,"stress_pf_min":1.20,"minimum_base_trades":20,"minimum_unique_days":12,"minimum_positive_base_folds":3,"minimum_positive_stress_folds":2,"largest_winner_share_max":0.25,"minimum_stable_execution_neighbors":1}

def load_v3():
    spec=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v3=load_v3()

def session_id(ts:pd.Timestamp)->int:
    mins=ts.hour*60+ts.minute
    if 600<=mins<=775:return 1
    if 840<=mins<=1010:return 2
    return 0

def nearest_round(px:float,step:float)->float:
    return round(px/step)*step

def generate_signals(m5:pd.DataFrame,inst:str,variant:dict[str,int])->list[dict[str,Any]]:
    tick=float(v3.SPECS[inst]["tick"]);step=float(v3.SPECS[inst]["round_step"])
    tol=variant["touch_tolerance_ticks"]*tick+1e-12;lb=int(variant["touch_lookback_bars"]);confirm=variant["breakout_confirm_ticks"]*tick
    signals=[];upper_hist={};lower_hist={};triggered_upper=set();triggered_lower=set();current_key=None
    for i,row in m5.iterrows():
        sid=session_id(row.time)
        if sid==0:
            current_key=None;upper_hist={};lower_hist={};triggered_upper=set();triggered_lower=set();continue
        key=(row.date,sid)
        if key!=current_key:
            current_key=key;upper_hist={};lower_hist={};triggered_upper=set();triggered_lower=set()
        # Prune histories before checking breakout. Only earlier completed candles count.
        lo_idx=i-lb
        for d in (upper_hist,lower_hist):
            for lev in list(d):
                d[lev]=[j for j in d[lev] if j>=lo_idx]
                if not d[lev]:del d[lev]
        armed_up=[lev for lev,hist in upper_hist.items() if len(hist)>=2 and lev not in triggered_upper and row.close>=lev+confirm-1e-12]
        armed_dn=[lev for lev,hist in lower_hist.items() if len(hist)>=2 and lev not in triggered_lower and row.close<=lev-confirm+1e-12]
        if armed_up:
            lev=max(armed_up)
            signals.append({"signal_index":int(i),"signal_time":str(row.time),"side":1,"level":float(lev),"session":sid,"touches":list(upper_hist[lev])})
            triggered_upper.add(lev)
        if armed_dn:
            lev=min(armed_dn)
            signals.append({"signal_index":int(i),"signal_time":str(row.time),"side":-1,"level":float(lev),"session":sid,"touches":list(lower_hist[lev])})
            triggered_lower.add(lev)
        # Add current candle touches only after breakout decision.
        hlev=nearest_round(float(row.high),step)
        if abs(float(row.high)-hlev)<=tol:
            upper_hist.setdefault(hlev,[]).append(int(i))
        llev=nearest_round(float(row.low),step)
        if abs(float(row.low)-llev)<=tol:
            lower_hist.setdefault(llev,[]).append(int(i))
    signals.sort(key=lambda z:(z["signal_time"],-z["side"]))
    return signals

def subset(signals,start,end):return [s for s in signals if start<=pd.Timestamp(s["signal_time"])<end]

def execute(m5,m1,signals,inst,buffer_ticks,rr,friction_ticks):
    tick=float(v3.SPECS[inst]["tick"]);cost=friction_ticks*tick
    times=m1.time.to_numpy(dtype="datetime64[ns]").astype(np.int64);lookup={int(t):i for i,t in enumerate(times)}
    op=m1.open.to_numpy(float);hi=m1.high.to_numpy(float);lo=m1.low.to_numpy(float);cl=m1.close.to_numpy(float);dates=m1.date.to_numpy();busy=-1;out=[]
    for sig in signals:
        st=pd.Timestamp(sig["signal_time"]);et=st+pd.Timedelta(minutes=5);ei=lookup.get(int(et.value))
        if ei is None or ei<=busy:continue
        signal_date=m5.date.iloc[int(sig["signal_index"])]
        if dates[ei]!=signal_date:continue
        side=int(sig["side"]);level=float(sig["level"]);entry=float(op[ei])
        if side==1 and entry<=level:continue
        if side==-1 and entry>=level:continue
        stop=level-buffer_ticks*tick if side==1 else level+buffer_ticks*tick
        risk=side*(entry-stop)
        if risk<=0:continue
        target=entry+side*rr*risk
        force=pd.Timestamp(signal_date)+pd.Timedelta(hours=17);fi=lookup.get(int(force.value))
        if fi is not None and fi>=ei and dates[fi]==signal_date:
            last=fi-1;xi=fi;raw=float(op[fi]);reason="FORCE_1700_OPEN"
        else:
            last=int(np.searchsorted(times,int(force.value),side="left")-1)
            if last<ei or dates[last]!=signal_date:continue
            xi=last;raw=float(cl[last]);reason="FORCE_LAST_CLOSE"
        for j in range(ei,last+1):
            o,h,l=float(op[j]),float(hi[j]),float(lo[j])
            if side==1:
                if o<=stop:xi,raw,reason=j,o,"STOP_GAP";break
                if o>=target:xi,raw,reason=j,o,"TARGET_GAP";break
                if l<=stop:xi,raw,reason=j,stop,"STOP";break
                if h>=target:xi,raw,reason=j,target,"TARGET";break
            else:
                if o>=stop:xi,raw,reason=j,o,"STOP_GAP";break
                if o<=target:xi,raw,reason=j,o,"TARGET_GAP";break
                if h>=stop:xi,raw,reason=j,stop,"STOP";break
                if l<=target:xi,raw,reason=j,target,"TARGET";break
        busy=xi;ae=entry+side*cost;ax=raw-side*cost;pnl=side*(ax-ae);bps=10000*pnl/entry
        out.append({"instrument":inst,"date":str(dates[ei]),"side":side,"signal_time":str(st),"entry_time":str(m1.time.iloc[ei]),"exit_time":str(m1.time.iloc[xi]),"level":level,"entry":entry,"stop":stop,"target":target,"buffer_ticks":buffer_ticks,"rr":rr,"friction_ticks_per_side":friction_ticks,"raw_exit":raw,"bps":float(bps),"reason":reason})
    return out

def train_execution(m5,m1,signals,inst):
    ss=subset(signals,TRAIN_START,TRAIN_END);eligible=[];grid=[]
    for bfr,rr in EXEC_GRID:
        gt=execute(m5,m1,ss,inst,bfr,rr,0);bt=execute(m5,m1,ss,inst,bfr,rr,1);st=execute(m5,m1,ss,inst,bfr,rr,2)
        gm,bm,sm=v3.metrics(gt),v3.metrics(bt),v3.metrics(st)
        ok=bm["trades"]>=12 and bm["pf"]>1 and sm["pf"]>1 and (bm["expectancy_bps"] or -1e9)>0 and (sm["expectancy_bps"] or -1e9)>0
        row={"stop_buffer_ticks":bfr,"target_rr":rr,"gross":gm,"base":bm,"stress":sm,"eligible":bool(ok),"selection_primary":float(min(bm["pf"],sm["pf"])),"selection_secondary":float(sm["expectancy_bps"] if sm["expectancy_bps"] is not None else -1e9)}
        grid.append(row)
        if ok:eligible.append(row)
    eligible.sort(key=lambda x:(x["selection_primary"],x["selection_secondary"]),reverse=True)
    return (eligible[0] if eligible else None),grid

def eval_folds(m5,m1,signals,inst,bfr,rr):
    folds=[];gb=[];bb=[];sb=[]
    for fid,start,end in FOLDS:
        ss=subset(signals,start,end);gt=execute(m5,m1,ss,inst,bfr,rr,0);bt=execute(m5,m1,ss,inst,bfr,rr,1);st=execute(m5,m1,ss,inst,bfr,rr,2)
        gm,bm,sm=v3.metrics(gt),v3.metrics(bt),v3.metrics(st);folds.append({"fold_id":fid,"gross":gm,"base":bm,"stress":sm});gb+=gt;bb+=bt;sb+=st
    gm,bm,sm=v3.metrics(gb),v3.metrics(bb),v3.metrics(sb);bm["positive_folds"]=sum(x["base"]["expectancy_bps"] is not None and x["base"]["expectancy_bps"]>0 for x in folds);sm["positive_folds"]=sum(x["stress"]["expectancy_bps"] is not None and x["stress"]["expectancy_bps"]>0 for x in folds)
    return {"gross":gm,"base":bm,"stress":sm,"folds":folds,"base_trades":bb,"stress_trades":sb}

def neighbors(bfr,rr):
    out=[];bi=STOP_BUFFERS.index(bfr);ri=TARGET_RRS.index(rr)
    for j in (bi-1,bi+1):
        if 0<=j<len(STOP_BUFFERS):out.append((STOP_BUFFERS[j],rr))
    for j in (ri-1,ri+1):
        if 0<=j<len(TARGET_RRS):out.append((bfr,TARGET_RRS[j]))
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
    if stable<GATES["minimum_stable_execution_neighbors"]:fail.append("EXECUTION_PLATEAU")
    return not fail,fail

def run_inst(root,inst):
    m5,p5=v3.load_prefix(root,inst,"M5");m1,p1=v3.load_prefix(root,inst,"M1")
    if m5.time.max()>=DISC_END or m1.time.max()>=DISC_END:raise PermissionError("Cycle9 fence violation")
    rows=[]
    for variant in SIGNAL_GRID:
        sig=generate_signals(m5,inst,variant);sel,train_grid=train_execution(m5,m1,sig,inst);row={"variant":variant,"signals":len(sig),"selected_execution":sel,"training_grid":train_grid}
        if sel is None:
            row.update({"gate_pass":False,"gate_failures":["TRAIN_SELECTION"],"status":"NO_TRAIN_ELIGIBLE_EXECUTION","rank_score":-1e9});rows.append(row);continue
        bfr=int(sel["stop_buffer_ticks"]);rr=float(sel["target_rr"]);ev=eval_folds(m5,m1,sig,inst,bfr,rr);nrows=[];stable=0
        for nb,nr in neighbors(bfr,rr):
            nev=eval_folds(m5,m1,sig,inst,nb,nr);b,s=nev["base"],nev["stress"];ok=b["pf"]>=1.25 and s["pf"]>=1.0 and (b["expectancy_bps"] or -1e9)>0 and (s["expectancy_bps"] or -1e9)>0;stable+=int(ok);nrows.append({"stop_buffer_ticks":nb,"target_rr":nr,"base":b,"stress":s,"stable":bool(ok)})
        passed,fail=gate(ev,stable);b,s=ev["base"],ev["stress"];score=math.log(max(min(b["pf"],10),1e-9))+0.65*math.log(max(min(s["pf"],10),1e-9))+0.03*(b["expectancy_bps"] or -100)+0.02*(s["expectancy_bps"] or -100)+0.12*stable
        row.update({"validation":{k:v for k,v in ev.items() if k not in ("base_trades","stress_trades")},"execution_neighbors":nrows,"stable_execution_neighbors":stable,"gate_pass":passed,"gate_failures":fail,"status":"FORWARD_RESEARCH_PASS" if passed else "FORWARD_RESEARCH_FAIL","rank_score":float(score),"base_trades":ev["base_trades"],"stress_trades":ev["stress_trades"]});rows.append(row)
    rows.sort(key=lambda x:(x["gate_pass"],x["rank_score"]),reverse=True);return {"instrument":inst,"rows":rows,"survivors":sum(x["gate_pass"] for x in rows),"provenance":p5+p1}

def compact(x):return {k:v for k,v in x.items() if k not in ("base_trades","stress_trades")}

def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True);results=[run_inst(root,"CNYRUBF"),run_inst(root,"USDRUBF")];status="RESEARCH_ONLY_AWAITING_NEW_CONFIRMATION_DATA" if any(r["survivors"] for r in results) else "NO_RESEARCH_SURVIVOR";cr=[]
    for r in results:
        cr.append({"instrument":r["instrument"],"survivors":r["survivors"],"provenance":r["provenance"],"rows":[compact(x) for x in r["rows"]]})
        if r["rows"] and "base_trades" in r["rows"][0]:
            (out/f"best_{r['instrument']}_base_trades.json").write_text(json.dumps(r["rows"][0]["base_trades"],indent=2,default=v3.jsonable)+"\n")
    manifest={"engine":"cycle9-equal-level-liquidity-breakout-v1","status":status,"data_end_exclusive":str(DISC_END),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"signal_grid":SIGNAL_GRID,"stop_buffers":STOP_BUFFERS,"target_rrs":TARGET_RRS,"gates":GATES,"results":cr};(out/"result.json").write_text(json.dumps(manifest,indent=2,default=v3.jsonable)+"\n")
    lines=["# Cycle 9 — Equal-Level Liquidity Breakout","",f"Status: **{status}**",""]
    for r in results:
        lines += [f"## {r['instrument']}",f"Survivors: {r['survivors']} / {len(r['rows'])}"]
        for x in r["rows"]:
            if "validation" not in x:lines.append(f"- {x['variant']} | no Jan-Feb eligible execution");continue
            se=x["selected_execution"];b=x["validation"]["base"];s=x["validation"]["stress"];lines.append(f"- {x['variant']} -> stop={se['stop_buffer_ticks']}t RR={se['target_rr']} | BASE PF={b['pf']:.3f} exp={b['expectancy_bps']} N={b['trades']} folds={b.get('positive_folds')} | STRESS PF={s['pf']:.3f} exp={s['expectancy_bps']} folds={s.get('positive_folds')} | neighbors={x['stable_execution_neighbors']} gate={x['gate_pass']} fail={x['gate_failures']}")
        lines.append("")
    lines += ["March-May is retrospective robustness data, not untouched OOS.","Retired May16-Jul1 data and 2025 TRUE OOS were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print(json.dumps(manifest,indent=2,default=v3.jsonable))
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();run(a.data_root,a.output)
