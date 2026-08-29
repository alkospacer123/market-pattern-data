from __future__ import annotations
import argparse, importlib.util, json, math
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

BASE_ENGINE=Path("research/autonomous_search_v3.py")
TRAIN_START=pd.Timestamp("2026-01-05")
TRAIN_END=pd.Timestamp("2026-03-01")
DISC_END=pd.Timestamp("2026-05-16")
FOLDS=[
    ("WF-03",pd.Timestamp("2026-03-01"),pd.Timestamp("2026-04-01")),
    ("WF-04",pd.Timestamp("2026-04-01"),pd.Timestamp("2026-05-01")),
    ("WF-05",pd.Timestamp("2026-05-01"),pd.Timestamp("2026-05-16")),
]
STOP_GRID=(0.75,1.0,1.25,1.5)
TARGET_GRID=(1.5,2.0,3.0,4.0)
HOLD_GRID=(30,60,120)
EXEC_GRID=[(s,t,h) for s in STOP_GRID for t in TARGET_GRID for h in HOLD_GRID]
GATES={
    "base_pf":2.0,"stress_pf":1.5,"minimum_trades":30,"minimum_unique_days":15,
    "minimum_positive_months":3,"minimum_positive_folds":3,"largest_winner_share":0.25,
    "minimum_plateau_neighbors":2,
}

def load_engine():
    spec=importlib.util.spec_from_file_location("v3",BASE_ENGINE)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def add_event_features(f: pd.DataFrame, inst: str, tf: str, e) -> pd.DataFrame:
    x=f.copy();m=e.TF_MINUTES[tf]
    tick=e.SPECS[inst]["tick"];step=e.SPECS[inst]["round_step"]
    prev=x.close.shift(1)
    tr=pd.concat([x.high-x.low,(x.high-prev).abs(),(x.low-prev).abs()],axis=1).max(axis=1)
    if "atr14" not in x:x["atr14"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    atr=x.atr14.replace(0,np.nan)
    candle_range=(x.high-x.low).replace(0,np.nan)
    x["body_abs_atr"]=(x.close-x.open).abs()/atr
    x["body_dir_atr"]=(x.close-x.open)/atr
    x["close_pos"]=(x.close-x.low)/candle_range
    x["upper_wick_atr"]=(x.high-np.maximum(x.open,x.close))/atr
    x["lower_wick_atr"]=(np.minimum(x.open,x.close)-x.low)/atr
    for mins in (15,30,60,120):
        bars=max(2,mins//m)
        x[f"rh_{mins}"]=x.groupby("date",sort=False).high.transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).max())
        x[f"rl_{mins}"]=x.groupby("date",sort=False).low.transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).min())
        rr=(x[f"rh_{mins}"]-x[f"rl_{mins}"]).replace(0,np.nan)
        x[f"rr_{mins}_atr"]=rr/atr
        lag=x.groupby("date",sort=False).close.shift(bars)
        x[f"ret_{mins}_atr"]=(x.close-lag)/atr
    # Previous day levels, only from completed previous day.
    daily=x.groupby("date").agg(dh=("high","max"),dl=("low","min"),dc=("close","last"))
    prevd=daily.shift(1)
    x["pdh"]=x.date.map(prevd.dh);x["pdl"]=x.date.map(prevd.dl);x["pdc"]=x.date.map(prevd.dc)
    # Relative volume from prior 60 minutes only.
    vb=max(4,60//m)
    med=x.groupby("date",sort=False).volume.transform(lambda s,b=vb:s.shift(1).rolling(b,min_periods=b).median())
    x["relvol"]=x.volume/med.replace(0,np.nan)
    # Round levels surrounding current open; no future information.
    nearest=np.floor(x.open/step+0.5)*step
    x["round_nearest"]=nearest
    x["round_dist_open_atr"]=(x.open-nearest)/atr
    x["tick"]=tick
    return x

def pattern_specs(tf: str) -> list[dict[str,Any]]:
    specs=[]
    # 1) Rolling sweep/reclaim. Sweep extension is measured beyond prior level; close must reclaim.
    for lb in (15,30,60,120):
        for ext in (0.0,0.10,0.25):
            for close_margin in (0.0,0.05):
                specs.append({"family":"rolling_sweep_reclaim","lookback":lb,"extension_atr":ext,"close_margin_atr":close_margin,"side":-1})
                specs.append({"family":"rolling_sweep_reclaim","lookback":lb,"extension_atr":ext,"close_margin_atr":close_margin,"side":1})
    # 2) Previous-day sweep/reclaim.
    for ext in (0.0,0.10,0.25,0.50):
        for wick in (0.0,0.15,0.30):
            specs.append({"family":"prev_day_sweep_reclaim","extension_atr":ext,"wick_min_atr":wick,"side":-1})
            specs.append({"family":"prev_day_sweep_reclaim","extension_atr":ext,"wick_min_atr":wick,"side":1})
    # 3) Compression -> breakout continuation.
    for lb in (30,60,120):
        for compress in (1.0,1.5,2.0,3.0):
            for body in (0.25,0.50,0.75):
                specs.append({"family":"compression_breakout","lookback":lb,"range_atr_max":compress,"body_atr_min":body,"side":1})
                specs.append({"family":"compression_breakout","lookback":lb,"range_atr_max":compress,"body_atr_min":body,"side":-1})
    # 4) Impulse -> pullback. Current candle retraces opposite impulse but does not erase origin.
    for horizon in (15,30,60):
        for impulse in (1.0,1.5,2.0,3.0):
            for retrace in (0.15,0.30,0.50):
                specs.append({"family":"impulse_pullback","horizon":horizon,"impulse_atr_min":impulse,"pullback_body_atr_min":retrace,"side":1})
                specs.append({"family":"impulse_pullback","horizon":horizon,"impulse_atr_min":impulse,"pullback_body_atr_min":retrace,"side":-1})
    # 5) Round-level sweep/reclaim.
    for ext in (0.0,0.10,0.25):
        for body in (0.0,0.20,0.40):
            specs.append({"family":"round_level_sweep_reclaim","extension_atr":ext,"body_atr_min":body,"side":-1})
            specs.append({"family":"round_level_sweep_reclaim","extension_atr":ext,"body_atr_min":body,"side":1})
    # 6) Plain range breakout, optionally volume-confirmed.
    for lb in (15,30,60,120):
        for body in (0.25,0.50,0.75,1.0):
            for rv in (0.0,1.25,1.75):
                specs.append({"family":"range_breakout","lookback":lb,"body_atr_min":body,"relvol_min":rv,"side":1})
                specs.append({"family":"range_breakout","lookback":lb,"body_atr_min":body,"relvol_min":rv,"side":-1})
    return specs

def mask_for(x: pd.DataFrame,spec: dict[str,Any]) -> np.ndarray:
    atr=x.atr14.to_numpy(float);o=x.open.to_numpy(float);h=x.high.to_numpy(float);l=x.low.to_numpy(float);c=x.close.to_numpy(float)
    side=int(spec["side"]);fam=spec["family"]
    ok=np.isfinite(atr)&(atr>0)
    if fam=="rolling_sweep_reclaim":
        lb=spec["lookback"];rh=x[f"rh_{lb}"].to_numpy(float);rl=x[f"rl_{lb}"].to_numpy(float);ext=spec["extension_atr"]*atr;mar=spec["close_margin_atr"]*atr
        if side==-1:m=ok&np.isfinite(rh)&(h>=rh+ext)&(c<=rh-mar)
        else:m=ok&np.isfinite(rl)&(l<=rl-ext)&(c>=rl+mar)
    elif fam=="prev_day_sweep_reclaim":
        pdh=x.pdh.to_numpy(float);pdl=x.pdl.to_numpy(float);ext=spec["extension_atr"]*atr;wick=spec["wick_min_atr"]*atr
        if side==-1:m=ok&np.isfinite(pdh)&(h>=pdh+ext)&(c<pdh)&((h-np.maximum(o,c))>=wick)
        else:m=ok&np.isfinite(pdl)&(l<=pdl-ext)&(c>pdl)&((np.minimum(o,c)-l)>=wick)
    elif fam=="compression_breakout":
        lb=spec["lookback"];rh=x[f"rh_{lb}"].to_numpy(float);rl=x[f"rl_{lb}"].to_numpy(float);rr=x[f"rr_{lb}_atr"].to_numpy(float);body=x.body_dir_atr.to_numpy(float)
        if side==1:m=ok&np.isfinite(rh)&np.isfinite(rr)&(rr<=spec["range_atr_max"])&(c>rh)&(body>=spec["body_atr_min"])
        else:m=ok&np.isfinite(rl)&np.isfinite(rr)&(rr<=spec["range_atr_max"])&(c<rl)&(body<=-spec["body_atr_min"])
    elif fam=="impulse_pullback":
        hz=spec["horizon"];ret=x[f"ret_{hz}_atr"].to_numpy(float);body=x.body_dir_atr.to_numpy(float);bars=max(2,hz//(5 if x.timeframe.iloc[0]=="M5" else 1));origin=x.groupby("date",sort=False).close.shift(bars).to_numpy(float)
        if side==1:m=ok&np.isfinite(ret)&np.isfinite(origin)&(ret>=spec["impulse_atr_min"])&(body<=-spec["pullback_body_atr_min"])&(c>origin)
        else:m=ok&np.isfinite(ret)&np.isfinite(origin)&(ret<=-spec["impulse_atr_min"])&(body>=spec["pullback_body_atr_min"])&(c<origin)
    elif fam=="round_level_sweep_reclaim":
        level=x.round_nearest.to_numpy(float);ext=spec["extension_atr"]*atr;body=x.body_dir_atr.to_numpy(float)
        if side==-1:m=ok&(h>=level+ext)&(c<level)&(body<=-spec["body_atr_min"])
        else:m=ok&(l<=level-ext)&(c>level)&(body>=spec["body_atr_min"])
    elif fam=="range_breakout":
        lb=spec["lookback"];rh=x[f"rh_{lb}"].to_numpy(float);rl=x[f"rl_{lb}"].to_numpy(float);body=x.body_dir_atr.to_numpy(float);rv=x.relvol.to_numpy(float);rvmin=spec["relvol_min"]
        volok=np.ones(len(x),bool) if rvmin<=0 else (np.isfinite(rv)&(rv>=rvmin))
        if side==1:m=ok&np.isfinite(rh)&(c>rh)&(body>=spec["body_atr_min"])&volok
        else:m=ok&np.isfinite(rl)&(c<rl)&(body<=-spec["body_atr_min"])&volok
    else:raise ValueError(fam)
    return np.asarray(m,dtype=bool)

def effect_quality(x: pd.DataFrame,mask: np.ndarray,side:int,e) -> dict[str,Any]|None:
    # Use the same causal future-effect function as v3, with current candle excluded.
    return e.future_effect(x,e.onset(x,mask),side)

def month_metrics(e,trades,months=("2026-01","2026-02")):
    return [e.metrics([t for t in trades if t["date"].startswith(m)]) for m in months]

def stable_train(e,b,s,tf):
    bm=month_metrics(e,b);sm=month_metrics(e,s);minimum=8 if tf=="M1" else 5
    for x,y in zip(bm,sm):
        if x["trades"]<minimum or y["trades"]<minimum:return False
        if x["expectancy_bps"] is None or x["expectancy_bps"]<=0:return False
        if y["expectancy_bps"] is None or y["expectancy_bps"]<=0:return False
    return True

def score_train(b,s,effect):
    mb=e.metrics(b);ms=e.metrics(s)
    if mb["trades"]<18 or ms["trades"]<18:return -1e9
    if mb["expectancy_bps"] is None or ms["expectancy_bps"] is None:return -1e9
    return math.log(max(min(mb["pf"],10),1e-6))+.55*math.log(max(min(ms["pf"],10),1e-6))+.04*mb["expectancy_bps"]+.025*ms["expectancy_bps"]+.25*effect["score"]

def exec_neighbors(p):
    s,t,h=p;out=[]
    for arr,val,pos in ((STOP_GRID,s,0),(TARGET_GRID,t,1),(HOLD_GRID,h,2)):
        k=arr.index(val)
        for j in (k-1,k+1):
            if 0<=j<len(arr):q=[s,t,h];q[pos]=arr[j];out.append(tuple(q))
    return out

def train_candidates(x,exec_f,inst,tf,e):
    train=((x.time>=TRAIN_START)&(x.time<TRAIN_END)).to_numpy();specs=pattern_specs(tf);rows=[]
    for i,spec in enumerate(specs,1):
        raw=mask_for(x,spec)&train;events=e.onset(x,raw);n=int(events.sum())
        min_events=28 if tf=="M1" else 14
        if n<min_events:continue
        effect=effect_quality(x,raw,int(spec["side"]),e)
        if effect is None:continue
        best=[]
        for p in EXEC_GRID:
            b=e.simulate(x,exec_f,raw,int(spec["side"]),p,e.SPECS[inst]["tick"],1,tf)
            s=e.simulate(x,exec_f,raw,int(spec["side"]),p,e.SPECS[inst]["tick"],2,tf)
            if not stable_train(e,b,s,tf):continue
            sc=score_train(b,s,effect)
            if sc>-1e8:best.append((sc,p,e.metrics(b),e.metrics(s)))
        best.sort(reverse=True,key=lambda z:z[0])
        for sc,p,mb,ms in best[:3]:
            rows.append({"spec":spec,"params":p,"effect":effect,"train_score":float(sc),"train_base":mb,"train_stress":ms})
    rows.sort(key=lambda r:r["train_score"],reverse=True)
    # Keep diversity: no more than 4 parameterizations per family/side/lookback or horizon signature.
    kept=[];cnt={}
    for r in rows:
        s=r["spec"];sig=(s["family"],s["side"],s.get("lookback"),s.get("horizon"));cnt[sig]=cnt.get(sig,0)
        if cnt[sig]>=4:continue
        kept.append(r);cnt[sig]+=1
        if len(kept)>=80:break
    return kept

def evaluate_forward(c,x,exec_f,inst,tf,e):
    raw_all=mask_for(x,c["spec"]);allb=[];alls=[];fb=[];fs=[]
    for fid,start,end in FOLDS:
        mask=raw_all&((x.time>=start)&(x.time<end)).to_numpy()
        b=e.simulate(x,exec_f,mask,int(c["spec"]["side"]),tuple(c["params"]),e.SPECS[inst]["tick"],1,tf)
        s=e.simulate(x,exec_f,mask,int(c["spec"]["side"]),tuple(c["params"]),e.SPECS[inst]["tick"],2,tf)
        mb=e.metrics(b);ms=e.metrics(s);mb["fold_id"]=fid;ms["fold_id"]=fid;fb.append(mb);fs.append(ms);allb+=b;alls+=s
    mb=e.metrics(allb);ms=e.metrics(alls);mb["positive_folds"]=sum((q["expectancy_bps"] is not None and q["expectancy_bps"]>0) for q in fb);ms["positive_folds"]=sum((q["expectancy_bps"] is not None and q["expectancy_bps"]>0) for q in fs)
    return {"base":mb,"stress":ms,"fold_base":fb,"fold_stress":fs}

def plateau(c,x,exec_f,inst,tf,e):
    rows=[]
    for p in exec_neighbors(tuple(c["params"])):
        q=dict(c);q["params"]=p;ev=evaluate_forward(q,x,exec_f,inst,tf,e);b=ev["base"];s=ev["stress"]
        stable=b["pf"]>=1.5 and (b["expectancy_bps"] or -1e9)>0 and s["pf"]>=1.1 and (s["expectancy_bps"] or -1e9)>0 and b.get("positive_folds",0)>=2
        rows.append({"params":p,"base":b,"stress":s,"stable_neighbor":bool(stable)})
    return rows

def gate(ev,neighbors):
    b=ev["base"];s=ev["stress"];fail=[]
    if b["pf"]<GATES["base_pf"]:fail.append("BASE_PF")
    if s["pf"]<GATES["stress_pf"]:fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if b["trades"]<GATES["minimum_trades"]:fail.append("TRADES")
    if b["unique_days"]<GATES["minimum_unique_days"]:fail.append("UNIQUE_DAYS")
    if b["positive_months"]<GATES["minimum_positive_months"]:fail.append("POSITIVE_MONTHS")
    if b.get("positive_folds",0)<GATES["minimum_positive_folds"]:fail.append("BASE_FOLDS")
    if s.get("positive_folds",0)<GATES["minimum_positive_folds"]:fail.append("STRESS_FOLDS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>GATES["largest_winner_share"]:fail.append("CONCENTRATION")
    if neighbors<GATES["minimum_plateau_neighbors"]:fail.append("PARAMETER_PLATEAU")
    return not fail,fail

def rank(r):
    b=r["validation"]["base"];s=r["validation"]["stress"]
    if b["expectancy_bps"] is None or s["expectancy_bps"] is None:return -1e9
    return math.log(max(min(b["pf"],10),1e-6))+.6*math.log(max(min(s["pf"],10),1e-6))+.04*b["expectancy_bps"]+.02*s["expectancy_bps"]+.15*b.get("positive_folds",0)+.08*r["stable_neighbor_count"]

def run_context(root:Path,out:Path,inst:str,tf:str):
    e=load_engine();out.mkdir(parents=True,exist_ok=True)
    exec_f,prov1=e.load_prefix(root,inst,"M1")
    if tf=="M1":raw=exec_f
    else:raw,prov2=e.load_prefix(root,inst,"M5")
    x0,_=e.build_features(raw,inst,tf);x=add_event_features(x0,inst,tf,e)
    if x.time.max()>=DISC_END or exec_f.time.max()>=DISC_END:raise PermissionError("Cycle4 fence violation")
    print("EVENT_DISCOVERY",inst,tf,flush=True);cands=train_candidates(x,exec_f,inst,tf,e);print("FROZEN_CANDIDATES",len(cands),flush=True)
    evaluated=[]
    for i,c in enumerate(cands,1):
        ev=evaluate_forward(c,x,exec_f,inst,tf,e)
        promising=ev["base"]["pf"]>=1.25 and (ev["base"]["expectancy_bps"] or -1e9)>0 and ev["base"]["trades"]>=15 and ev["base"].get("positive_folds",0)>=2
        pl=plateau(c,x,exec_f,inst,tf,e) if promising else [];neighbors=sum(q["stable_neighbor"] for q in pl);passed,fail=gate(ev,neighbors)
        row={**c,"candidate_id":f"E4-{inst}-{tf}-{i:03d}","instrument":inst,"timeframe":tf,"validation":ev,"plateau":pl,"stable_neighbor_count":neighbors,"gate_pass":passed,"gate_failures":fail};row["rank_score"]=rank(row);evaluated.append(row)
    evaluated.sort(key=lambda r:(r["gate_pass"],r["rank_score"]),reverse=True)
    survivors=[r for r in evaluated if r["gate_pass"]]
    manifest={"engine":"cycle4-events-v1","instrument":inst,"timeframe":tf,"status":"DISCOVERY_SURVIVOR_FOUND_AWAITING_NEW_CONFIRMATION_DATA" if survivors else "NO_DISCOVERY_SURVIVOR_YET","frozen_candidates":len(cands),"survivors":len(survivors),"data_end_exclusive":str(DISC_END),"retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"gates":GATES}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,default=e.jsonable)+"\n")
    (out/"evaluated.json").write_text(json.dumps(evaluated,indent=2,default=e.jsonable)+"\n")
    (out/"survivors.json").write_text(json.dumps(survivors,indent=2,default=e.jsonable)+"\n")
    lines=[f"# Cycle 4 Events — {inst} {tf}","",f"Status: **{manifest['status']}**",f"Candidates: {len(cands)}",f"Survivors: {len(survivors)}","", "## Top"]
    for r in evaluated[:20]:
        b=r["validation"]["base"];s=r["validation"]["stress"]
        lines.append(f"- {r['candidate_id']} {r['spec']} params={r['params']} BASE PF={b['pf']:.3f} exp={b['expectancy_bps']} N={b['trades']} folds={b.get('positive_folds')} STRESS PF={s['pf']:.3f} exp={s['expectancy_bps']} folds={s.get('positive_folds')} neighbors={r['stable_neighbor_count']} gate={r['gate_pass']} fail={r['gate_failures']}")
    lines += ["","Retired May16-Jul1 confirmation was not read. 2025 TRUE OOS was not read. Any survivor awaits new untouched confirmation data."]
    (out/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(manifest,indent=2))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);ap.add_argument("--instrument",choices=["CNYRUBF","USDRUBF"],required=True);ap.add_argument("--timeframe",choices=["M1","M5"],required=True);a=ap.parse_args();run_context(a.data_root,a.output,a.instrument,a.timeframe)
