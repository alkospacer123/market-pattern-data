from __future__ import annotations
import argparse, csv, hashlib, json, math
from pathlib import Path
from time import perf_counter
from typing import Any
import numpy as np
import pandas as pd

DISCOVERY_START = pd.Timestamp("2026-01-05 00:00:00")
DISCOVERY_TRAIN_END = pd.Timestamp("2026-03-01 00:00:00")
DISCOVERY_END = pd.Timestamp("2026-05-16 00:00:00")
FOLDS = [
    ("WF-03","2026-01-05","2026-03-01","2026-03-01","2026-04-01"),
    ("WF-04","2026-01-05","2026-04-01","2026-04-01","2026-05-01"),
    ("WF-05","2026-01-05","2026-05-01","2026-05-01","2026-05-16"),
]
SPECS = {
    "CNYRUBF": {"folder":"CNY","tick":0.001,"round_step":0.05},
    "USDRUBF": {"folder":"Si","tick":0.01,"round_step":0.10},
}
TF_MINUTES = {"M1":1,"M5":5}
QPROBS=(.10,.25,.75,.90)
QLABELS=np.array(["LE_P10","P10_P25","P25_P75","P75_P90","GE_P90"],dtype=object)
SEARCH_STATES=("LOW25","HIGH25","LOW10","HIGH10")
TIME_STATES=("PRE_09","09_12","12_15","15_18","18_PLUS")
RETURN_MINUTES=(5,15,30,60,120)
POSITION_MINUTES=(15,30,60,120,240)
EFF_MINUTES=(15,30,60,120)
EFFECT_HORIZONS=(15,30,60)
COARSE_GRID=[(s,t,h) for s in (.5,1.0,1.5) for t in (1.5,2.,3.,4.,6.) for h in (15,30,60,120)]
FULL_GRID=[(s,t,h) for s in (.5,.75,1.0,1.25,1.5) for t in (1.5,2.,3.,4.,6.,8.) for h in (15,30,60,120)]
GATES={
    "base_pf":2.0, "stress_pf":1.5, "minimum_trades":30, "minimum_unique_days":15,
    "minimum_positive_months":3, "minimum_positive_folds":3, "largest_winner_share":.25,
    "minimum_plateau_neighbors":2,
}

def prefix_digest_line(digest, raw_line: str) -> None:
    digest.update(raw_line.encode("utf-8"))

def source_paths(root: Path, inst: str, tf: str) -> list[Path]:
    folder=root/"2026"/SPECS[inst]["folder"]
    prefix=SPECS[inst]["folder"]
    if tf=="M1":
        paths=[folder/f"{prefix}_2026_Q1_M1.csv",folder/f"{prefix}_2026_Q2_M1.csv"]
    else:
        paths=[folder/f"{prefix}_2026_Q1.csv",folder/f"{prefix}_2026_Q2.csv"]
    for p in paths:
        if not p.exists(): raise FileNotFoundError(p)
        if "2025" in str(p): raise PermissionError("2025 TRUE OOS is sealed")
    return paths

def load_prefix(root: Path, inst: str, tf: str) -> tuple[pd.DataFrame,list[dict[str,Any]]]:
    per=TF_MINUTES[tf]
    rows=[]; provenance=[]
    expected=["<TICKER>","<PER>","<DATE>","<TIME>","<OPEN>","<HIGH>","<LOW>","<CLOSE>","<VOL>"]
    for p in source_paths(root,inst,tf):
        digest=hashlib.sha256(); accepted=0; stopped=False
        with p.open("r",encoding="utf-8-sig",newline="") as stream:
            header_line=stream.readline()
            header=next(csv.reader([header_line],delimiter=";"))
            if header!=expected: raise ValueError(f"schema mismatch: {p}")
            prefix_digest_line(digest,header_line)
            for raw_line in stream:
                fields=next(csv.reader([raw_line],delimiter=";"))
                if len(fields)!=9: continue
                dt=pd.to_datetime(fields[2]+fields[3].zfill(6),format="%Y%m%d%H%M%S")
                if dt>=DISCOVERY_END:
                    stopped=True
                    break
                prefix_digest_line(digest,raw_line)
                if dt<DISCOVERY_START: continue
                if int(fields[1])!=per: raise ValueError(f"PER mismatch in {p}")
                if fields[0].upper()!=inst: raise ValueError(f"ticker mismatch in {p}")
                rows.append((dt,float(fields[4]),float(fields[5]),float(fields[6]),float(fields[7]),float(fields[8])))
                accepted+=1
        provenance.append({
            "path":str(p.relative_to(root)),"timeframe":tf,"discovery_rows":accepted,
            "discovery_prefix_sha256":digest.hexdigest(),"stopped_at_confirmation_boundary":bool(stopped),
            "full_file_hash_not_computed":True,
        })
    f=pd.DataFrame(rows,columns=["time","open","high","low","close","volume"])
    f=f.sort_values("time",kind="mergesort").drop_duplicates("time").reset_index(drop=True)
    if f.empty or f.time.min()<DISCOVERY_START or f.time.max()>=DISCOVERY_END:
        raise ValueError("discovery boundary violation")
    f["date"]=f.time.dt.date
    f["month"]=f.time.dt.to_period("M").astype(str)
    f["instrument"]=inst
    f["timeframe"]=tf
    return f,provenance

def build_features(raw: pd.DataFrame, inst: str, tf: str) -> tuple[pd.DataFrame,list[str]]:
    f=raw.copy(); m=TF_MINUTES[tf]
    prev=f.close.shift(1)
    tr=pd.concat([f.high-f.low,(f.high-prev).abs(),(f.low-prev).abs()],axis=1).max(axis=1)
    f["atr14"]=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    f["atr20"]=tr.rolling(20,min_periods=20).mean()
    rng=(f.high-f.low).replace(0,np.nan)
    features=[]
    def add(name, values):
        f[name]=values; features.append(name)
    add("range_atr",rng/f.atr20)
    add("body_atr",(f.close-f.open)/f.atr20)
    add("body_frac",(f.close-f.open)/rng)
    add("close_pos_candle",(f.close-f.low)/rng)
    add("upper_wick_frac",(f.high-np.maximum(f.open,f.close))/rng)
    add("lower_wick_frac",(np.minimum(f.open,f.close)-f.low)/rng)
    for mins in RETURN_MINUTES:
        bars=max(1,mins//m); lag=f.groupby("date",sort=False).close.shift(bars)
        add(f"ret_{mins}m_atr",(f.close-lag)/f.atr20)
    for mins in POSITION_MINUTES:
        bars=max(2,mins//m)
        rh=f.groupby("date",sort=False).high.transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).max())
        rl=f.groupby("date",sort=False).low.transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).min())
        rr=(rh-rl).replace(0,np.nan)
        add(f"pos_{mins}m",(f.close-rl)/rr)
        add(f"dist_high_{mins}m_atr",(rh-f.close)/f.atr20)
        add(f"dist_low_{mins}m_atr",(f.close-rl)/f.atr20)
    absdiff=f.close.diff().abs()
    for mins in EFF_MINUTES:
        bars=max(2,mins//m); lag=f.groupby("date",sort=False).close.shift(bars)
        path=absdiff.groupby(f.date).transform(lambda s,b=bars:s.rolling(b,min_periods=b).sum())
        add(f"eff_{mins}m",(f.close-lag).abs()/path.replace(0,np.nan))
    def prior_tr_mean(mins):
        bars=max(2,mins//m)
        return tr.groupby(f.date).transform(lambda s,b=bars:s.shift(1).rolling(b,min_periods=b).mean())
    add("vol_15m_60m",prior_tr_mean(15)/prior_tr_mean(60))
    add("vol_30m_120m",prior_tr_mean(30)/prior_tr_mean(120))
    vb=max(4,60//m)
    vmed=f.groupby("date",sort=False).volume.transform(lambda s,b=vb:s.shift(1).rolling(b,min_periods=b).median())
    vmean=f.groupby("date",sort=False).volume.transform(lambda s,b=vb:s.shift(1).rolling(b,min_periods=b).mean())
    vstd=f.groupby("date",sort=False).volume.transform(lambda s,b=vb:s.shift(1).rolling(b,min_periods=b).std())
    add("relvol_60m",f.volume/vmed.replace(0,np.nan))
    add("vol_z_60m",(f.volume-vmean)/vstd.replace(0,np.nan))
    step=SPECS[inst]["round_step"]
    nearest=np.floor(f.close/step+0.5)*step
    add("round_dist_atr",(f.close-nearest)/f.atr20)
    add("round_pos",(f.close%step)/step)
    daily=f.groupby("date").agg(dh=("high","max"),dl=("low","min"),dc=("close","last"))
    previous=daily.shift(1)
    f["prev_day_high"]=f.date.map(previous.dh); f["prev_day_low"]=f.date.map(previous.dl); f["prev_day_close"]=f.date.map(previous.dc)
    add("dist_pdh_atr",(f.prev_day_high-f.close)/f.atr20)
    add("dist_pdl_atr",(f.close-f.prev_day_low)/f.atr20)
    add("gap_prevclose_atr",(f.open-f.prev_day_close)/f.atr20)
    prefix_hi=f.groupby("date",sort=False).high.cummax(); prefix_lo=f.groupby("date",sort=False).low.cummin()
    add("session_pos",(f.close-prefix_lo)/(prefix_hi-prefix_lo).replace(0,np.nan))
    mins=f.time.dt.hour*60+f.time.dt.minute
    f["clock_bucket"]=np.select(
        [mins<540,(mins>=540)&(mins<720),(mins>=720)&(mins<900),(mins>=900)&(mins<1080)],
        ["PRE_09","09_12","12_15","15_18"], default="18_PLUS"
    )
    features.append("clock_bucket")
    for mins in EFFECT_HORIZONS:
        bars=max(1,mins//m); future=f.groupby("date",sort=False).close.shift(-bars)
        f[f"fwd_{mins}m_atr"]=(future-f.close)/f.atr20
    return f,features

def fit_states(f: pd.DataFrame, features: list[str], train_mask: np.ndarray) -> tuple[dict[str,np.ndarray],dict[str,list[float]]]:
    states={}; cuts={}
    for feat in features:
        if feat=="clock_bucket":
            states[feat]=f[feat].astype(str).to_numpy()
            cuts[feat]=[]
            continue
        x=pd.to_numeric(f.loc[train_mask,feat],errors="coerce").dropna()
        if len(x)<100: continue
        c=np.quantile(x,QPROBS)
        if len(np.unique(c))<4: continue
        vals=pd.to_numeric(f[feat],errors="coerce").to_numpy(float)
        st=np.full(len(f),"MISSING",dtype=object); ok=np.isfinite(vals)
        st[ok]=QLABELS[np.searchsorted(c,vals[ok],side="left")]
        states[feat]=st; cuts[feat]=[float(v) for v in c]
    return states,cuts

def feature_search_states(feat: str) -> tuple[str,...]:
    return TIME_STATES if feat=="clock_bucket" else SEARCH_STATES

def rule_mask(states: dict[str,np.ndarray], rule: tuple[tuple[str,str],...], n: int) -> np.ndarray:
    mask=np.ones(n,dtype=bool)
    for feat,state in rule:
        if feat not in states: return np.zeros(n,dtype=bool)
        arr=states[feat]
        if feat=="clock_bucket":
            mask &= arr==state
        elif state=="LOW25":
            mask &= np.isin(arr,("LE_P10","P10_P25"))
        elif state=="HIGH25":
            mask &= np.isin(arr,("P75_P90","GE_P90"))
        elif state=="LOW10":
            mask &= arr=="LE_P10"
        elif state=="HIGH10":
            mask &= arr=="GE_P90"
        else:
            return np.zeros(n,dtype=bool)
    return mask

def onset(f: pd.DataFrame, raw_mask: np.ndarray) -> np.ndarray:
    prev=np.r_[False,raw_mask[:-1]]; same=np.r_[False,f.date.to_numpy()[1:]==f.date.to_numpy()[:-1]]
    return raw_mask & ~(prev & same)

def future_effect(f: pd.DataFrame, sig: np.ndarray, side: int) -> dict[str,Any] | None:
    idx=np.flatnonzero(sig)
    if len(idx)<12: return None
    medians=[]; means=[]; wins=[]; valid_all=np.ones(len(idx),bool); arrays=[]
    for mins in EFFECT_HORIZONS:
        y=pd.to_numeric(f[f"fwd_{mins}m_atr"],errors="coerce").to_numpy(float)[idx]
        arrays.append(y); valid_all &= np.isfinite(y)
    if valid_all.sum()<12: return None
    idx2=idx[valid_all]
    for y in arrays:
        z=side*y[valid_all]; medians.append(float(np.median(z))); means.append(float(np.mean(z))); wins.append(float(np.mean(z>0)))
    weeks=pd.to_datetime(f.time.iloc[idx2]).dt.to_period("W").astype(str).to_numpy()
    z30=side*pd.to_numeric(f["fwd_30m_atr"],errors="coerce").to_numpy(float)[idx2]
    weekly=[float(np.median(z30[weeks==w])) for w in np.unique(weeks) if (weeks==w).sum()>=2]
    months=f.month.iloc[idx2].to_numpy()
    monthly=[float(np.median(z30[months==mo])) for mo in np.unique(months) if (months==mo).sum()>=4]
    positive_h=sum(x>0 for x in medians); positive_weeks=sum(x>0 for x in weekly); positive_months=sum(x>0 for x in monthly); days=int(f.date.iloc[idx2].nunique())
    if days<8 or positive_h<2 or len(monthly)<2 or positive_months<2: return None
    score=.38*min(medians)+.22*np.median(medians)+.13*np.mean(means)+.08*(min(wins)-.5)+.025*positive_weeks+.08*positive_months
    return {"score":float(score),"n":int(len(idx2)),"days":days,"medians":medians,"means":means,"wins":wins,
            "positive_horizons":positive_h,"positive_weeks":positive_weeks,"positive_months":positive_months}

def beam_rules(f: pd.DataFrame, states: dict[str,np.ndarray], features: list[str], train_mask: np.ndarray, tf: str) -> list[dict[str,Any]]:
    min_events=28 if tf=="M1" else 14
    first=[]
    for feat in features:
        if feat not in states: continue
        for st in feature_search_states(feat):
            sig=onset(f,rule_mask(states,((feat,st),),len(f)))&train_mask
            for side in (1,-1):
                q=future_effect(f,sig,side)
                if q and q["n"]>=min_events:first.append({"rule":((feat,st),),"side":side,"effect":q})
    first.sort(key=lambda x:x["effect"]["score"],reverse=True)
    second=[]; seen=set()
    for row in first[:55]:
        rule=row["rule"];side=row["side"];used={x[0] for x in rule}
        for feat in features:
            if feat in used or feat not in states:continue
            for st in feature_search_states(feat):
                nr=tuple(sorted(rule+((feat,st),)));key=(nr,side)
                if key in seen:continue
                seen.add(key);sig=onset(f,rule_mask(states,nr,len(f)))&train_mask;q=future_effect(f,sig,side)
                if q and q["n"]>=min_events:second.append({"rule":nr,"side":side,"effect":q})
    seeds=[]
    for mins in (15,30,60):
        pairs=[
            (("dist_pdh_atr","LOW25"),(f"pos_{mins}m","HIGH25")),
            (("dist_pdh_atr","LOW25"),(f"dist_high_{mins}m_atr","LOW25")),
            ((f"pos_{mins}m","HIGH25"),("clock_bucket","09_12")),
            ((f"pos_{mins}m","HIGH25"),("clock_bucket","12_15")),
            ((f"pos_{mins}m","HIGH25"),("clock_bucket","15_18")),
        ]
        for pair in pairs:
            rule=tuple(sorted(pair))
            if all(feat in states for feat,_ in rule):
                for side in (-1,1):
                    q=future_effect(f,onset(f,rule_mask(states,rule,len(f)))&train_mask,side)
                    if q and q["n"]>=min_events:seeds.append({"rule":rule,"side":side,"effect":q})
    combined=first[:45]+sorted(second,key=lambda x:x["effect"]["score"],reverse=True)[:150]+seeds
    best={}
    for row in combined:
        key=(row["rule"],row["side"])
        if key not in best or row["effect"]["score"]>best[key]["effect"]["score"]:best[key]=row
    return sorted(best.values(),key=lambda x:x["effect"]["score"],reverse=True)[:180]

_FRAME_ARRAY_CACHE={}
_LAST_RAW_SIM={"key":None,"trades":None}

def _frame_arrays(f: pd.DataFrame) -> dict[str,Any]:
    key=id(f)
    cached=_FRAME_ARRAY_CACHE.get(key)
    if cached is not None:
        return cached
    times=f["time"].to_numpy(dtype="datetime64[ns]").astype(np.int64)
    day=(times//86_400_000_000_000).astype(np.int64)
    n=len(f)
    day_end=np.empty(n,dtype=np.int64)
    e=n-1
    while e>=0:
        s=e
        d=day[e]
        while s-1>=0 and day[s-1]==d:
            s-=1
        day_end[s:e+1]=e
        e=s-1
    cached={
        "time":times,
        "day":day,
        "day_end":day_end,
        "open":f["open"].to_numpy(float),
        "high":f["high"].to_numpy(float),
        "low":f["low"].to_numpy(float),
        "close":f["close"].to_numpy(float),
        "date_str":np.asarray([str(x) for x in f["date"].to_numpy()],dtype=object),
        "instrument":str(f["instrument"].iloc[0]) if len(f) else "",
        "lookup":{int(t):i for i,t in enumerate(times)},
    }
    _FRAME_ARRAY_CACHE[key]=cached
    return cached

def _simulate_raw(signal_f: pd.DataFrame, exec_f: pd.DataFrame, signal_mask: np.ndarray, side: int,
                  params: tuple[float,float,int], tf: str) -> list[dict[str,Any]]:
    stop_atr,target_r,hold_minutes=params
    sig_mask=onset(signal_f,signal_mask)
    signal_ix=np.flatnonzero(sig_mask)
    sarr=_frame_arrays(signal_f)
    earr=_frame_arrays(exec_f)
    atrs=signal_f["atr14"].to_numpy(float)
    tf_ns=TF_MINUTES[tf]*60_000_000_000
    hold_ns=int(hold_minutes)*60_000_000_000
    out=[]
    available_exec=-1
    for i in signal_ix:
        available_ns=int(sarr["time"][i])+tf_ns
        ei=earr["lookup"].get(available_ns)
        if ei is None or ei<=available_exec or earr["day"][ei]!=sarr["day"][i]:
            continue
        atr=float(atrs[i])
        if not np.isfinite(atr) or atr<=0:
            continue
        entry=float(earr["open"][ei])
        risk=float(stop_atr)*atr
        stop=entry-side*risk
        target=entry+side*risk*float(target_r)
        limit_ns=available_ns+hold_ns
        xi=int(np.searchsorted(earr["time"],limit_ns,side="left")-1)
        if xi<ei:
            xi=ei
        day_end=int(earr["day_end"][ei])
        if xi>day_end:
            xi=day_end
        raw=float(earr["close"][xi])
        reason="TIME"
        for j in range(ei,xi+1):
            o=float(earr["open"][j]);h=float(earr["high"][j]);l=float(earr["low"][j])
            if side==1:
                if o<=stop:
                    xi=j;raw=o;reason="STOP_GAP";break
                if o>=target:
                    xi=j;raw=target;reason="TARGET_GAP_CONSERVATIVE";break
                hit_s=l<=stop;hit_t=h>=target
            else:
                if o>=stop:
                    xi=j;raw=o;reason="STOP_GAP";break
                if o<=target:
                    xi=j;raw=target;reason="TARGET_GAP_CONSERVATIVE";break
                hit_s=h>=stop;hit_t=l<=target
            if hit_s:
                xi=j;raw=stop;reason="STOP_FIRST_TIE" if hit_t else "STOP";break
            if hit_t:
                xi=j;raw=target;reason="TARGET";break
        available_exec=xi
        out.append({
            "_entry":entry,"_raw_exit":float(raw),
            "date":str(earr["date_str"][ei]),
            "instrument":earr["instrument"],
            "timeframe":tf,
            "signal_time":str(pd.Timestamp(int(sarr["time"][i]))),
            "entry_time":str(pd.Timestamp(int(earr["time"][ei]))),
            "exit_time":str(pd.Timestamp(int(earr["time"][xi]))),
            "reason":reason,
        })
    return out

def simulate(signal_f: pd.DataFrame, exec_f: pd.DataFrame, signal_mask: np.ndarray, side: int,
             params: tuple[float,float,int], tick: float, friction_ticks: int, tf: str) -> list[dict[str,Any]]:
    key=(id(signal_f),id(exec_f),id(signal_mask),int(side),tuple(params),tf)
    if _LAST_RAW_SIM["key"]==key:
        raw_trades=_LAST_RAW_SIM["trades"]
    else:
        raw_trades=_simulate_raw(signal_f,exec_f,signal_mask,side,params,tf)
        _LAST_RAW_SIM["key"]=key
        _LAST_RAW_SIM["trades"]=raw_trades
    cost=float(friction_ticks)*float(tick)
    out=[]
    for x in raw_trades:
        entry=float(x["_entry"]); raw_exit=float(x["_raw_exit"])
        adj_entry=entry+side*cost
        adj_exit=raw_exit-side*cost
        pnl=side*(adj_exit-adj_entry)
        y={k:v for k,v in x.items() if not k.startswith("_")}
        y["bps"]=float(10000*pnl/entry)
        out.append(y)
    return out

def metrics(trades: list[dict[str,Any]]) -> dict[str,Any]:
    if not trades:
        return {"trades":0,"pf":0.0,"expectancy_bps":None,"total_bps":0.0,"win_rate":0.0,"positive_months":0,"largest_winner_share":None,"unique_days":0}
    b=np.fromiter((float(x["bps"]) for x in trades),dtype=float,count=len(trades))
    gp=float(b[b>0].sum());gl=float(-b[b<0].sum())
    pf=gp/gl if gl else (np.inf if gp else 0.0)
    months=np.asarray([x["date"][:7] for x in trades],dtype=object)
    positive_months=sum(float(b[months==mo].sum())>0 for mo in np.unique(months))
    wins=b[b>0]
    share=float(wins.max()/wins.sum()) if len(wins) else np.nan
    return {"trades":len(b),"pf":float(pf),"expectancy_bps":float(b.mean()),"total_bps":float(b.sum()),
            "win_rate":float((b>0).mean()),"positive_months":int(positive_months),
            "largest_winner_share":float(share) if np.isfinite(share) else None,
            "unique_days":len({x["date"] for x in trades})}

def objective(base: dict[str,Any], stress: dict[str,Any], effect_score: float) -> float:
    if base["trades"]<8 or stress["trades"]<8 or base["expectancy_bps"] is None or stress["expectancy_bps"] is None:return -1e9
    share=base["largest_winner_share"] if base["largest_winner_share"] is not None else 1.0
    return math.log(max(min(base["pf"],10),1e-6))+.55*math.log(max(min(stress["pf"],10),1e-6))+.04*base["expectancy_bps"]+.025*stress["expectancy_bps"]+.30*effect_score-.8*max(0,share-.35)

def param_neighbors(params: tuple[float,float,int]) -> list[tuple[float,float,int]]:
    stops=(.5,.75,1.0,1.25,1.5);targets=(1.5,2.,3.,4.,6.,8.);holds=(15,30,60,120);s,t,h=params;out=[]
    for arr,val,pos in ((stops,s,0),(targets,t,1),(holds,h,2)):
        k=arr.index(val)
        for j in (k-1,k+1):
            if 0<=j<len(arr):p=[s,t,h];p[pos]=arr[j];out.append(tuple(p))
    return out

def discovery_month_metrics(trades: list[dict[str,Any]]) -> list[dict[str,Any]]:
    return [metrics([t for t in trades if t["date"].startswith(month)]) for month in ("2026-01","2026-02")]

def stable_discovery(base_months: list[dict[str,Any]], stress_months: list[dict[str,Any]], tf: str) -> bool:
    min_month_trades=8 if tf=="M1" else 5
    for b,s in zip(base_months,stress_months):
        if b["trades"]<min_month_trades or s["trades"]<min_month_trades:return False
        if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:return False
        if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:return False
    return True

def train_candidates(signal_f: pd.DataFrame, exec_f: pd.DataFrame, features: list[str], inst: str, tf: str) -> tuple[list[dict[str,Any]],dict[str,list[float]]]:
    discovery=((signal_f.time>=DISCOVERY_START)&(signal_f.time<DISCOVERY_TRAIN_END)).to_numpy()
    states,cuts=fit_states(signal_f,features,discovery)
    rules=beam_rules(signal_f,states,features,discovery,tf)
    scored=[]
    for row in rules[:90]:
        raw=rule_mask(states,row["rule"],len(signal_f))&discovery
        for params in COARSE_GRID:
            bt=simulate(signal_f,exec_f,raw,row["side"],params,SPECS[inst]["tick"],1,tf)
            st=simulate(signal_f,exec_f,raw,row["side"],params,SPECS[inst]["tick"],2,tf)
            b=metrics(bt);s=metrics(st)
            if b["trades"]<18 or s["trades"]<18:continue
            bm=discovery_month_metrics(bt);sm=discovery_month_metrics(st)
            if not stable_discovery(bm,sm,tf):continue
            sc=objective(b,s,row["effect"]["score"])
            if sc>-1e8:scored.append((sc,row,params,b,s,bm,sm))
    scored.sort(key=lambda x:x[0],reverse=True)
    rule_keys=[];rule_map={}
    for sc,row,params,b,s,bm,sm in scored:
        key=(row["rule"],row["side"])
        if key not in rule_map:rule_map[key]=row;rule_keys.append(key)
        if len(rule_keys)>=24:break
    refined=[]
    for key in rule_keys:
        row=rule_map[key];raw=rule_mask(states,row["rule"],len(signal_f))&discovery;grid_metrics={}
        for params in FULL_GRID:
            bt=simulate(signal_f,exec_f,raw,row["side"],params,SPECS[inst]["tick"],1,tf)
            st=simulate(signal_f,exec_f,raw,row["side"],params,SPECS[inst]["tick"],2,tf)
            b=metrics(bt);s=metrics(st)
            bm=discovery_month_metrics(bt);sm=discovery_month_metrics(st)
            sc=objective(b,s,row["effect"]["score"])
            grid_metrics[params]=(b,s,sc,bm,sm)
        for params,(b,s,sc,bm,sm) in grid_metrics.items():
            if sc<=-1e8 or not stable_discovery(bm,sm,tf):continue
            robust_neighbors=0
            for np_ in param_neighbors(params):
                if np_ not in grid_metrics:continue
                nb,ns,_,nbm,nsm=grid_metrics[np_]
                if stable_discovery(nbm,nsm,tf) and nb["pf"]>=1.15 and ns["pf"]>=1.0:robust_neighbors+=1
            refined.append({"rule":row["rule"],"side":row["side"],"params":params,"effect":row["effect"],
                            "train_base":b,"train_stress":s,"train_score":float(sc),
                            "train_months_base":bm,"train_months_stress":sm,
                            "train_plateau_neighbors":robust_neighbors})
    refined.sort(key=lambda x:(x["train_plateau_neighbors"],x["train_score"]),reverse=True)
    kept=[];counts={}
    for r in refined:
        key=(r["rule"],r["side"]);counts[key]=counts.get(key,0)
        if counts[key]>=4 or r["train_plateau_neighbors"]<1:continue
        kept.append(r);counts[key]+=1
        if len(kept)>=50:break
    return kept,cuts

_VALIDATION_STATE_CACHE={}
def validation_states(signal_f: pd.DataFrame, features: list[str], train_start: str, train_end: str) -> dict[str,np.ndarray]:
    key=(id(signal_f),train_start,train_end)
    if key not in _VALIDATION_STATE_CACHE:
        mask=((signal_f.time>=pd.Timestamp(train_start))&(signal_f.time<pd.Timestamp(train_end))).to_numpy()
        states,_=fit_states(signal_f,features,mask)
        _VALIDATION_STATE_CACHE[key]=states
    return _VALIDATION_STATE_CACHE[key]

def evaluate_frozen(candidate: dict[str,Any], signal_f: pd.DataFrame, exec_f: pd.DataFrame, features: list[str], inst: str, tf: str) -> dict[str,Any]:
    all_b=[];all_s=[];fold_b=[];fold_s=[]
    for fold_id,ts,te,vs,ve in FOLDS:
        states=validation_states(signal_f,features,ts,te);val=((signal_f.time>=pd.Timestamp(vs))&(signal_f.time<pd.Timestamp(ve))).to_numpy();raw=rule_mask(states,tuple(tuple(x) for x in candidate["rule"]),len(signal_f))&val
        tb=simulate(signal_f,exec_f,raw,int(candidate["side"]),tuple(candidate["params"]),SPECS[inst]["tick"],1,tf);tsr=simulate(signal_f,exec_f,raw,int(candidate["side"]),tuple(candidate["params"]),SPECS[inst]["tick"],2,tf)
        mb=metrics(tb);ms=metrics(tsr);mb["fold_id"]=fold_id;ms["fold_id"]=fold_id;fold_b.append(mb);fold_s.append(ms);all_b+=tb;all_s+=tsr
    mb=metrics(all_b);ms=metrics(all_s);mb["positive_folds"]=sum((x["expectancy_bps"] is not None and x["expectancy_bps"]>0) for x in fold_b);ms["positive_folds"]=sum((x["expectancy_bps"] is not None and x["expectancy_bps"]>0) for x in fold_s)
    return {"base":mb,"stress":ms,"fold_base":fold_b,"fold_stress":fold_s}

def forward_plateau(candidate: dict[str,Any], signal_f: pd.DataFrame, exec_f: pd.DataFrame, features: list[str], inst: str, tf: str) -> list[dict[str,Any]]:
    rows=[]
    for p in param_neighbors(tuple(candidate["params"])):
        c=dict(candidate);c["params"]=p;ev=evaluate_frozen(c,signal_f,exec_f,features,inst,tf)
        ok=ev["base"]["pf"]>=1.5 and (ev["base"]["expectancy_bps"] or -1e9)>0 and ev["stress"]["pf"]>=1.1 and (ev["stress"]["expectancy_bps"] or -1e9)>0 and ev["base"].get("positive_folds",0)>=2
        rows.append({"params":p,"base":ev["base"],"stress":ev["stress"],"stable_neighbor":bool(ok)})
    return rows

def gate_result(ev: dict[str,Any], stable_neighbors: int) -> tuple[bool,list[str]]:
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
    if stable_neighbors<GATES["minimum_plateau_neighbors"]:fail.append("PARAMETER_PLATEAU")
    return not fail,fail

def replication(candidate: dict[str,Any], contexts: dict[tuple[str,str],dict[str,Any]], source_inst: str, tf: str) -> dict[str,Any]:
    other="USDRUBF" if source_inst=="CNYRUBF" else "CNYRUBF";ctx=contexts[(other,tf)];ev=evaluate_frozen(candidate,ctx["signal"],ctx["exec"],ctx["features"],other,tf)
    strong=ev["base"]["pf"]>1 and (ev["base"]["expectancy_bps"] or -1e9)>0 and ev["base"].get("positive_folds",0)>=2
    return {"instrument":other,"base":ev["base"],"stress":ev["stress"],"classification":"directionally_consistent" if strong else "failed_replication"}

def candidate_rank(row: dict[str,Any]) -> float:
    b=row["validation"]["base"];s=row["validation"]["stress"]
    if b["expectancy_bps"] is None or s["expectancy_bps"] is None:return -1e9
    return math.log(max(min(b["pf"],10),1e-6))+.6*math.log(max(min(s["pf"],10),1e-6))+.04*b["expectancy_bps"]+.02*s["expectancy_bps"]+.12*b.get("positive_folds",0)+.08*row["stable_neighbor_count"]-.5*max(0,(b["largest_winner_share"] or 1)-.25)

def jsonable(v):
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,tuple):return list(v)
    if isinstance(v,pd.Timestamp):return str(v)
    raise TypeError(type(v).__name__)

def run(data_root: Path, output: Path) -> dict[str,Any]:
    t0=perf_counter();output.mkdir(parents=True,exist_ok=True);contexts={};provenance=[]
    for inst in SPECS:
        m1raw,p=load_prefix(data_root,inst,"M1");provenance+=p;m1feat,m1features=build_features(m1raw,inst,"M1")
        for tf in ("M1","M5"):
            if tf=="M1":sig=m1feat;features=m1features
            else:raw,p=load_prefix(data_root,inst,"M5");provenance+=p;sig,features=build_features(raw,inst,"M5")
            contexts[(inst,tf)]={"signal":sig,"exec":m1raw,"features":features}
    if any(ctx["signal"].time.max()>=DISCOVERY_END or ctx["exec"].time.max()>=DISCOVERY_END for ctx in contexts.values()):raise PermissionError("internal confirmation fence violated")
    frozen=[]
    for inst in SPECS:
        for tf in ("M1","M5"):
            ctx=contexts[(inst,tf)];print("DISCOVER",inst,tf,flush=True);cands,cuts=train_candidates(ctx["signal"],ctx["exec"],ctx["features"],inst,tf);print("JAN_CANDIDATES",inst,tf,len(cands),flush=True)
            for k,c in enumerate(cands):row=dict(c);row["candidate_id"]=f"A3-{inst}-{tf}-{k+1:03d}";row["instrument"]=inst;row["timeframe"]=tf;frozen.append(row)
    evaluated=[]
    for i,c in enumerate(frozen,1):
        ctx=contexts[(c["instrument"],c["timeframe"])];ev=evaluate_frozen(c,ctx["signal"],ctx["exec"],ctx["features"],c["instrument"],c["timeframe"])
        promising=ev["base"]["pf"]>=1.25 and (ev["base"]["expectancy_bps"] or -1e9)>0 and ev["base"]["trades"]>=15 and ev["base"].get("positive_folds",0)>=2
        plateau=forward_plateau(c,ctx["signal"],ctx["exec"],ctx["features"],c["instrument"],c["timeframe"]) if promising else [];stable_neighbors=sum(x["stable_neighbor"] for x in plateau);passed,fail=gate_result(ev,stable_neighbors);rep=replication(c,contexts,c["instrument"],c["timeframe"]) if promising else {"classification":"not_tested"}
        row={**c,"validation":ev,"plateau":plateau,"stable_neighbor_count":stable_neighbors,"gate_pass":bool(passed),"gate_failures":fail,"replication":rep};row["rank_score"]=float(candidate_rank(row));evaluated.append(row)
        if i%20==0:print("EVALUATED",i,"/",len(frozen),flush=True)
    evaluated.sort(key=lambda x:(x["gate_pass"],x["rank_score"]),reverse=True);survivors=[x for x in evaluated if x["gate_pass"]];near=[x for x in evaluated if not x["gate_pass"] and x["validation"]["base"]["pf"]>=1.5 and (x["validation"]["base"]["expectancy_bps"] or -1e9)>0][:20]
    manifest={"status":"SURVIVOR_FOUND" if survivors else "NO_SURVIVOR_YET","engine_version":"autonomous-search-v3-fast","methodology":"JAN_FEB_STABILITY_DISCOVERY_THEN_FROZEN_MAR_MAY_WALK_FORWARD","discovery_start":str(DISCOVERY_START),"discovery_train_end_exclusive":str(DISCOVERY_TRAIN_END),"discovery_end_exclusive":str(DISCOVERY_END),"internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"full_file_hashes_computed":False,"source_modified":False,"contexts":["CNYRUBF/M1","CNYRUBF/M5","USDRUBF/M1","USDRUBF/M5"],"frozen_candidates":len(frozen),"survivor_count":len(survivors),"gates":GATES,"elapsed_seconds":perf_counter()-t0,"provenance":provenance}
    (output/"run_manifest.json").write_text(json.dumps(manifest,indent=2,default=jsonable)+"\n");(output/"frozen_january_candidates.json").write_text(json.dumps(frozen,indent=2,default=jsonable)+"\n");(output/"evaluated_candidates.json").write_text(json.dumps(evaluated,indent=2,default=jsonable)+"\n");(output/"survivors.json").write_text(json.dumps(survivors,indent=2,default=jsonable)+"\n");(output/"near_candidates.json").write_text(json.dumps(near,indent=2,default=jsonable)+"\n")
    report=["# Autonomous Search v3","",f"Status: **{manifest['status']}**",f"Frozen Jan-Feb candidates: {len(frozen)}",f"Strict survivors: {len(survivors)}","","## Method","Candidate semantics and execution parameters are selected only from Jan-Feb, with positive BASE and STRESS expectancy required separately in both discovery months. The rule is frozen before March and evaluated on March, April, and 1-15 May. Numeric states use broad/strict tail aliases (25% and 10%); clock time uses fixed non-refitted buckets. Quantile cutpoints are refit only from data preceding each validation block. M5 signals execute on exact M1 opens.","","## Gates",json.dumps(GATES,sort_keys=True),"","## Top candidates"]
    for x in evaluated[:15]:
        b=x["validation"]["base"];s=x["validation"]["stress"]
        report.append(f"- {x['candidate_id']} {x['instrument']} {x['timeframe']} rule={x['rule']} side={x['side']} params={x['params']} BASE PF={b['pf']:.3f} exp={b['expectancy_bps']} N={b['trades']} folds={b.get('positive_folds')} STRESS PF={s['pf']:.3f} exp={s['expectancy_bps']} neighbors={x['stable_neighbor_count']} rep={x['replication'].get('classification')} gate={x['gate_pass']} fail={x['gate_failures']}")
    report+=["","Internal confirmation not accessed. 2025 TRUE OOS not accessed. Q2 readers stop at the confirmation boundary; no full-file hashes are computed."];(output/"report.md").write_text("\n".join(report)+"\n");return manifest

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);args=ap.parse_args();print(json.dumps(run(args.data_root,args.output),indent=2,default=jsonable))
