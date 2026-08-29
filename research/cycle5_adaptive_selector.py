from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

DISC_END=pd.Timestamp("2026-05-16")
EVAL_START=pd.Timestamp("2026-02-16")
BLOCK_DAYS=7
TRAIN_DAYS=35
RECENT_DAYS=18
SELECT_MIN_TRADES=8
SELECT_STRESS_PF=1.20
SELECT_RECENT_MIN_TRADES=3
RESEARCH_GATES={
    "base_pf":1.5,"stress_pf":1.2,"base_expectancy_positive":True,"stress_expectancy_positive":True,
    "individual_min_trades":15,"combined_min_trades":30,"combined_min_unique_days":15,
    "minimum_positive_months":2,"largest_winner_share":0.25,
}

def load_module(path:str,name:str):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

v3=load_module("research/autonomous_search_v3.py","v3")
v4=load_module("research/autonomous_search_v4_events.py","v4")

def canonical_models()->list[dict[str,Any]]:
    models=[]
    def add(spec,params):
        models.append({"model_id":f"M{len(models)+1:03d}","spec":spec,"params":params})
    # Mean-reversion/reclaim families: one fixed execution profile.
    for lb in (30,60,120):
        for ext in (0.0,0.25):
            for side in (-1,1):
                add({"family":"rolling_sweep_reclaim","lookback":lb,"extension_atr":ext,"close_margin_atr":0.0,"side":side},(1.25,1.5,60))
    for ext in (0.0,0.25):
        for side in (-1,1):
            add({"family":"prev_day_sweep_reclaim","extension_atr":ext,"wick_min_atr":0.15,"side":side},(1.25,1.5,60))
    # Trend/breakout families.
    for lb in (60,120):
        for comp in (1.5,2.0):
            for side in (-1,1):
                add({"family":"compression_breakout","lookback":lb,"range_atr_max":comp,"body_atr_min":0.5,"side":side},(1.25,2.0,120))
    for hz in (30,60):
        for impulse in (1.5,2.0,3.0):
            for side in (-1,1):
                add({"family":"impulse_pullback","horizon":hz,"impulse_atr_min":impulse,"pullback_body_atr_min":0.3,"side":side},(1.0,2.0,60))
    for ext in (0.0,0.25):
        for side in (-1,1):
            add({"family":"round_level_sweep_reclaim","extension_atr":ext,"body_atr_min":0.2,"side":side},(1.25,1.5,60))
    for lb in (30,60,120):
        for rv in (0.0,1.25):
            for side in (-1,1):
                add({"family":"range_breakout","lookback":lb,"body_atr_min":0.5,"relvol_min":rv,"side":side},(1.25,2.0,120))
    return models

def load_context(root:Path,inst:str):
    m1,prov1=v3.load_prefix(root,inst,"M1")
    m5raw,prov5=v3.load_prefix(root,inst,"M5")
    base,_=v3.build_features(m5raw,inst,"M5")
    x=v4.add_event_features(base,inst,"M5",v3)
    if x.time.max()>=DISC_END or m1.time.max()>=DISC_END:
        raise PermissionError("Cycle5 discovery fence violated")
    return x,m1,prov1+prov5

def build_library_masks(x:pd.DataFrame,models:list[dict[str,Any]]) -> dict[str,np.ndarray]:
    out={}
    for m in models:
        raw=v4.mask_for(x,m["spec"])
        # Store true event onsets globally; later window slicing cannot create fake boundary onsets.
        out[m["model_id"]]=v3.onset(x,raw)
    return out

def sim_metrics(x,exec_f,event_mask,model,inst,start,end,friction):
    w=((x.time>=start)&(x.time<end)).to_numpy()
    trades=v3.simulate(x,exec_f,event_mask&w,int(model["spec"]["side"]),tuple(model["params"]),v3.SPECS[inst]["tick"],friction,"M5")
    return v3.metrics(trades),trades

def select_for_block(x,exec_f,inst,models,masks,block_start):
    train_start=block_start-pd.Timedelta(days=TRAIN_DAYS)
    recent_start=block_start-pd.Timedelta(days=RECENT_DAYS)
    eligible=[]
    for m in models:
        em=masks[m["model_id"]]
        base,_=sim_metrics(x,exec_f,em,m,inst,train_start,block_start,1)
        stress,_=sim_metrics(x,exec_f,em,m,inst,train_start,block_start,2)
        recent,_=sim_metrics(x,exec_f,em,m,inst,recent_start,block_start,2)
        if stress["trades"]<SELECT_MIN_TRADES:continue
        if stress["pf"]<SELECT_STRESS_PF:continue
        if stress["expectancy_bps"] is None or stress["expectancy_bps"]<=0:continue
        if base["expectancy_bps"] is None or base["expectancy_bps"]<=0:continue
        if recent["trades"]<SELECT_RECENT_MIN_TRADES:continue
        if recent["expectancy_bps"] is None or recent["expectancy_bps"]<=0:continue
        score=float(stress["expectancy_bps"]*math.sqrt(stress["trades"]))
        eligible.append({"model":m,"score":score,"trailing_base":base,"trailing_stress":stress,"recent_stress":recent})
    eligible.sort(key=lambda z:z["score"],reverse=True)
    return eligible[0] if eligible else None,len(eligible)

def run_instrument(root:Path,inst:str):
    x,exec_f,prov=load_context(root,inst);models=canonical_models();masks=build_library_masks(x,models)
    all_base=[];all_stress=[];blocks=[]
    start=EVAL_START
    while start<DISC_END:
        end=min(start+pd.Timedelta(days=BLOCK_DAYS),DISC_END)
        chosen,neligible=select_for_block(x,exec_f,inst,models,masks,start)
        if chosen is None:
            blocks.append({"start":str(start),"end_exclusive":str(end),"eligible_models":0,"selected":None,"base":v3.metrics([]),"stress":v3.metrics([])})
        else:
            m=chosen["model"];em=masks[m["model_id"]]
            mb,tb=sim_metrics(x,exec_f,em,m,inst,start,end,1);ms,ts=sim_metrics(x,exec_f,em,m,inst,start,end,2)
            all_base+=tb;all_stress+=ts
            blocks.append({"start":str(start),"end_exclusive":str(end),"eligible_models":neligible,"selected":m,
                           "selection_score":chosen["score"],"trailing_base":chosen["trailing_base"],"trailing_stress":chosen["trailing_stress"],"recent_stress":chosen["recent_stress"],
                           "base":mb,"stress":ms})
        start=end
    base=v3.metrics(all_base);stress=v3.metrics(all_stress)
    return {"instrument":inst,"base":base,"stress":stress,"blocks":blocks,"base_trades":all_base,"stress_trades":all_stress,"provenance":prov,"library_size":len(models)}

def individual_gate(row):
    b=row["base"];s=row["stress"];fail=[]
    if b["pf"]<RESEARCH_GATES["base_pf"]:fail.append("BASE_PF")
    if s["pf"]<RESEARCH_GATES["stress_pf"]:fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if b["trades"]<RESEARCH_GATES["individual_min_trades"]:fail.append("TRADES")
    if b["positive_months"]<RESEARCH_GATES["minimum_positive_months"]:fail.append("BASE_MONTHS")
    if s["positive_months"]<RESEARCH_GATES["minimum_positive_months"]:fail.append("STRESS_MONTHS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>RESEARCH_GATES["largest_winner_share"]:fail.append("CONCENTRATION")
    return not fail,fail

def combined_gate(b,s):
    fail=[]
    if b["pf"]<RESEARCH_GATES["base_pf"]:fail.append("BASE_PF")
    if s["pf"]<RESEARCH_GATES["stress_pf"]:fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if b["trades"]<RESEARCH_GATES["combined_min_trades"]:fail.append("TRADES")
    if b["unique_days"]<RESEARCH_GATES["combined_min_unique_days"]:fail.append("UNIQUE_DAYS")
    if b["positive_months"]<RESEARCH_GATES["minimum_positive_months"]:fail.append("BASE_MONTHS")
    if s["positive_months"]<RESEARCH_GATES["minimum_positive_months"]:fail.append("STRESS_MONTHS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>RESEARCH_GATES["largest_winner_share"]:fail.append("CONCENTRATION")
    return not fail,fail

def run(root:Path,out:Path):
    out.mkdir(parents=True,exist_ok=True)
    rows=[run_instrument(root,"CNYRUBF"),run_instrument(root,"USDRUBF")]
    combined_base=[t for r in rows for t in r["base_trades"]];combined_stress=[t for r in rows for t in r["stress_trades"]]
    cb=v3.metrics(combined_base);cs=v3.metrics(combined_stress);cpass,cfail=combined_gate(cb,cs)
    for r in rows:
        p,f=individual_gate(r);r["research_gate_pass"]=p;r["research_gate_failures"]=f
    result={"engine":"cycle5-causal-weekly-selector-v1","status":"RESEARCH_GATE_PASS_AWAITING_NEW_CONFIRMATION_DATA" if cpass else "RESEARCH_GATE_FAIL",
            "data_end_exclusive":str(DISC_END),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,
            "library_size":len(canonical_models()),"selector":{"train_days":TRAIN_DAYS,"recent_days":RECENT_DAYS,"block_days":BLOCK_DAYS,"min_stress_trades":SELECT_MIN_TRADES,"min_stress_pf":SELECT_STRESS_PF,"recent_min_trades":SELECT_RECENT_MIN_TRADES,"score":"stress_expectancy_bps * sqrt(stress_trades)"},
            "research_gates":RESEARCH_GATES,"instruments":rows,"combined":{"base":cb,"stress":cs,"research_gate_pass":cpass,"research_gate_failures":cfail}}
    # Keep trade lists in separate files, omit from compact result duplicate.
    compact=json.loads(json.dumps(result,default=v3.jsonable))
    for r in compact["instruments"]:
        r.pop("base_trades",None);r.pop("stress_trades",None)
    (out/"result.json").write_text(json.dumps(compact,indent=2)+"\n")
    (out/"combined_base_trades.json").write_text(json.dumps(combined_base,indent=2,default=v3.jsonable)+"\n")
    lines=["# Cycle 5 — Causal Adaptive Weekly Selector","",f"Status: **{result['status']}**","",f"Library: {len(canonical_models())} fixed M5 models.",f"Evaluation: {EVAL_START.date()} through 2026-05-15; weekly model choice uses only prior 35/18-day windows.",""]
    for r in rows:
        b=r["base"];s=r["stress"]
        lines.append(f"- {r['instrument']}: BASE PF={b['pf']:.3f}, exp={b['expectancy_bps']}, N={b['trades']}; STRESS PF={s['pf']:.3f}, exp={s['expectancy_bps']}, N={s['trades']}; gate={r['research_gate_pass']} fail={r['research_gate_failures']}")
    lines += ["",f"Combined: BASE PF={cb['pf']:.3f}, exp={cb['expectancy_bps']}, N={cb['trades']}; STRESS PF={cs['pf']:.3f}, exp={cs['expectancy_bps']}, N={cs['trades']}; gate={cpass}; fail={cfail}.","","Retired May16-Jul1 confirmation was not read. 2025 TRUE OOS was not read. Even a research gate pass requires genuinely new untouched confirmation data."]
    (out/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(compact,indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();run(a.data_root,a.output)
