from __future__ import annotations
import csv, hashlib, json, math, importlib.util
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

FREEZE_PATH=Path("research/frozen_candidate_A3-USDRUBF-M5-049.json")
ENGINE_PATH=Path("research/autonomous_search_v3.py")
CONF_START=pd.Timestamp("2026-05-16 00:00:00")
CONF_MID=pd.Timestamp("2026-06-16 00:00:00")
CONF_END=pd.Timestamp("2026-07-02 00:00:00")
DISC_START=pd.Timestamp("2026-01-05 00:00:00")
CONFIRMATION_GATES={
    "base_pf_min":2.0,
    "stress_pf_min":1.5,
    "base_expectancy_positive":True,
    "stress_expectancy_positive":True,
    "minimum_trades":12,
    "minimum_unique_days":10,
    "largest_winner_share_max":0.25,
    "require_positive_base_both_subperiods":True,
    "require_positive_stress_both_subperiods":True,
    "minimum_trades_per_subperiod":3,
    "require_gross_ge_base_ge_stress":True,
}
EXPECTED_FREEZE_SHA256="1441d289085552d2c5b8635bf2f93ea4b5dbb746de7c6edc6995396e34d10da0"

def load_engine():
    spec=importlib.util.spec_from_file_location("autonomous_search_v3",ENGINE_PATH)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def verify_freeze() -> dict[str,Any]:
    freeze=json.loads(FREEZE_PATH.read_text())
    got=freeze.get("freeze_sha256")
    payload=dict(freeze);payload.pop("freeze_sha256",None)
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    recomputed=hashlib.sha256(canonical).hexdigest()
    if got!=EXPECTED_FREEZE_SHA256 or recomputed!=EXPECTED_FREEZE_SHA256:
        raise RuntimeError(f"freeze hash mismatch got={got} recomputed={recomputed}")
    if freeze["selection_source"]["internal_confirmation_accessed_at_freeze"]:
        raise RuntimeError("freeze record says confirmation was already accessed")
    if freeze["true_oos_2025"]["status"]!="SEALED":
        raise RuntimeError("2025 TRUE OOS is not sealed")
    return freeze

def load_through(root: Path, inst: str, tf: str, end_exclusive: pd.Timestamp):
    e=load_engine()
    folder=root/"2026"/e.SPECS[inst]["folder"]
    prefix=e.SPECS[inst]["folder"]
    if tf=="M1":
        paths=[folder/f"{prefix}_2026_Q1_M1.csv",folder/f"{prefix}_2026_Q2_M1.csv"]
    else:
        paths=[folder/f"{prefix}_2026_Q1.csv",folder/f"{prefix}_2026_Q2.csv"]
    rows=[];prov=[];expected=["<TICKER>","<PER>","<DATE>","<TIME>","<OPEN>","<HIGH>","<LOW>","<CLOSE>","<VOL>"]
    for p in paths:
        if "2025" in str(p):
            raise PermissionError("2025 TRUE OOS is sealed")
        digest=hashlib.sha256(); accepted=0; stopped=False
        with p.open("r",encoding="utf-8-sig",newline="") as stream:
            header_line=stream.readline();header=next(csv.reader([header_line],delimiter=";"))
            if header!=expected: raise ValueError(f"schema mismatch {p}")
            digest.update(header_line.encode())
            for raw_line in stream:
                fields=next(csv.reader([raw_line],delimiter=";"))
                if len(fields)!=9: continue
                dt=pd.to_datetime(fields[2]+fields[3].zfill(6),format="%Y%m%d%H%M%S")
                if dt>=end_exclusive:
                    stopped=True;break
                digest.update(raw_line.encode())
                if dt<DISC_START: continue
                if int(fields[1])!=e.TF_MINUTES[tf]: raise ValueError("PER mismatch")
                if fields[0].upper()!=inst: raise ValueError("ticker mismatch")
                rows.append((dt,float(fields[4]),float(fields[5]),float(fields[6]),float(fields[7]),float(fields[8])))
                accepted+=1
        prov.append({"path":str(p.relative_to(root)),"rows_before_confirmation_end":accepted,
                     "prefix_sha256":digest.hexdigest(),"stopped_at_confirmation_end":stopped,
                     "full_file_hash_not_computed":True})
    f=pd.DataFrame(rows,columns=["time","open","high","low","close","volume"])
    f=f.sort_values("time",kind="mergesort").drop_duplicates("time").reset_index(drop=True)
    f["date"]=f.time.dt.date;f["month"]=f.time.dt.to_period("M").astype(str);f["instrument"]=inst;f["timeframe"]=tf
    if f.empty or f.time.max()>=end_exclusive:
        raise ValueError("confirmation loader boundary violation")
    return f,prov

def mclose(a,b,tol=1e-9):
    if a is None or b is None:return a is b
    if isinstance(a,(int,str,bool)) or isinstance(b,(int,str,bool)):return a==b
    return math.isclose(float(a),float(b),rel_tol=0,abs_tol=tol)

def verify_discovery_reproduction(e,freeze,root: Path):
    m1,_=e.load_prefix(root,"USDRUBF","M1")
    m5raw,_=e.load_prefix(root,"USDRUBF","M5")
    m5,features=e.build_features(m5raw,"USDRUBF","M5")
    candidate={"rule":tuple((x["feature"],x["state"]) for x in freeze["rule"]),
               "side":-1,"params":(freeze["execution"]["stop_atr14"],freeze["execution"]["target_r"],freeze["execution"]["max_hold_minutes"])}
    ev=e.evaluate_frozen(candidate,m5,m1,features,"USDRUBF","M5")
    stored=freeze["discovery_result"]["validation"]
    checks={}
    for layer in ("base","stress"):
        for k in ("trades","pf","expectancy_bps","total_bps","win_rate","positive_months","largest_winner_share","unique_days","positive_folds"):
            ok=mclose(ev[layer][k],stored[layer][k],1e-8)
            checks[f"{layer}.{k}"]=ok
    if not all(checks.values()):
        raise RuntimeError("discovery reproduction mismatch: "+json.dumps({k:v for k,v in checks.items() if not v}))
    return {"passed":True,"checks":checks,"recomputed":ev},candidate

def discovery_replication(e,root: Path,candidate):
    m1,_=e.load_prefix(root,"CNYRUBF","M1")
    m5raw,_=e.load_prefix(root,"CNYRUBF","M5")
    m5,features=e.build_features(m5raw,"CNYRUBF","M5")
    return e.evaluate_frozen(candidate,m5,m1,features,"CNYRUBF","M5")

def subset_metrics(e,trades,start,end):
    return e.metrics([t for t in trades if start.date()<=pd.Timestamp(t["date"]).date()<end.date()])

def confirmation_gate(base,stress,gross,sub):
    fail=[]
    if base["pf"]<CONFIRMATION_GATES["base_pf_min"]:fail.append("BASE_PF")
    if stress["pf"]<CONFIRMATION_GATES["stress_pf_min"]:fail.append("STRESS_PF")
    if base["expectancy_bps"] is None or base["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if stress["expectancy_bps"] is None or stress["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if base["trades"]<CONFIRMATION_GATES["minimum_trades"]:fail.append("TRADES")
    if base["unique_days"]<CONFIRMATION_GATES["minimum_unique_days"]:fail.append("UNIQUE_DAYS")
    if base["largest_winner_share"] is None or base["largest_winner_share"]>CONFIRMATION_GATES["largest_winner_share_max"]:fail.append("CONCENTRATION")
    for name,row in sub.items():
        if row["base"]["trades"]<CONFIRMATION_GATES["minimum_trades_per_subperiod"]:fail.append(f"{name}_TRADES")
        if row["base"]["expectancy_bps"] is None or row["base"]["expectancy_bps"]<=0:fail.append(f"{name}_BASE")
        if row["stress"]["expectancy_bps"] is None or row["stress"]["expectancy_bps"]<=0:fail.append(f"{name}_STRESS")
    if not (gross["total_bps"]+1e-9>=base["total_bps"]>=stress["total_bps"]-1e-9):fail.append("FRICTION_CONSERVATION")
    return not fail,fail

def main():
    root=Path(".");out=Path("results/internal-confirmation-A3-USDRUBF-M5-049");out.mkdir(parents=True,exist_ok=True)
    freeze=verify_freeze();e=load_engine()
    reproduction,candidate=verify_discovery_reproduction(e,freeze,root)
    replication=discovery_replication(e,root,candidate)
    print("DISCOVERY_REPRODUCTION_OK",flush=True)
    print("OPENING_INTERNAL_CONFIRMATION_2026_05_16_TO_2026_07_01",flush=True)
    m1,p1=load_through(root,"USDRUBF","M1",CONF_END)
    m5raw,p5=load_through(root,"USDRUBF","M5",CONF_END)
    m5,features=e.build_features(m5raw,"USDRUBF","M5")
    train=((m5.time>=DISC_START)&(m5.time<CONF_START)).to_numpy()
    states,cuts=e.fit_states(m5,features,train)
    val=((m5.time>=CONF_START)&(m5.time<CONF_END)).to_numpy()
    rule=tuple((x["feature"],x["state"]) for x in freeze["rule"])
    raw=e.rule_mask(states,rule,len(m5))&val
    gross_tr=e.simulate(m5,m1,raw,-1,(1.25,1.5,120),e.SPECS["USDRUBF"]["tick"],0,"M5")
    base_tr=e.simulate(m5,m1,raw,-1,(1.25,1.5,120),e.SPECS["USDRUBF"]["tick"],1,"M5")
    stress_tr=e.simulate(m5,m1,raw,-1,(1.25,1.5,120),e.SPECS["USDRUBF"]["tick"],2,"M5")
    gross=e.metrics(gross_tr);base=e.metrics(base_tr);stress=e.metrics(stress_tr)
    sub={
      "IC-A":{"start":str(CONF_START),"end_exclusive":str(CONF_MID),
              "base":subset_metrics(e,base_tr,CONF_START,CONF_MID),"stress":subset_metrics(e,stress_tr,CONF_START,CONF_MID)},
      "IC-B":{"start":str(CONF_MID),"end_exclusive":str(CONF_END),
              "base":subset_metrics(e,base_tr,CONF_MID,CONF_END),"stress":subset_metrics(e,stress_tr,CONF_MID,CONF_END)},
    }
    passed,fail=confirmation_gate(base,stress,gross,sub)
    result={
      "candidate_id":freeze["candidate_id"],"freeze_sha256":freeze["freeze_sha256"],
      "status":"INTERNAL_CONFIRMATION_PASSED" if passed else "INTERNAL_CONFIRMATION_FAILED",
      "confirmation_window":{"start_inclusive":str(CONF_START),"end_exclusive":str(CONF_END)},
      "gates":CONFIRMATION_GATES,"gate_pass":passed,"gate_failures":fail,
      "gross":gross,"base":base,"stress":stress,"subperiods":sub,
      "quantile_cutpoints":{k:v for k,v in cuts.items() if k in ("dist_high_120m_atr","dist_low_15m_atr")},
      "discovery_reproduction":reproduction,
      "cross_instrument_discovery_replication_CNYRUBF":replication,
      "provenance":p1+p5,
      "true_oos_2025_accessed":False,
      "commission_excluded":True,
      "trade_count_conserved":len(gross_tr)==len(base_tr)==len(stress_tr),
    }
    (out/"confirmation_result.json").write_text(json.dumps(result,indent=2,default=e.jsonable)+"\n")
    (out/"confirmation_trades_base.json").write_text(json.dumps(base_tr,indent=2,default=e.jsonable)+"\n")
    lines=["# Internal Confirmation — A3-USDRUBF-M5-049","",f"Status: **{result['status']}**",
           f"Window: {CONF_START} to {CONF_END} (Moscow, end exclusive)",
           f"BASE: PF={base['pf']:.3f}, exp={base['expectancy_bps']}, N={base['trades']}, days={base['unique_days']}",
           f"STRESS: PF={stress['pf']:.3f}, exp={stress['expectancy_bps']}, N={stress['trades']}",
           f"GROSS total bps={gross['total_bps']:.3f}; BASE={base['total_bps']:.3f}; STRESS={stress['total_bps']:.3f}",
           f"Failures: {fail}","",
           "2025 TRUE OOS was not accessed by this run."]
    (out/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(result,indent=2,default=e.jsonable))

if __name__=="__main__":
    main()
