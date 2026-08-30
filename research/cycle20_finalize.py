from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3")
G={"base_pf":2.0,"stress_pf":1.5,"base_mean_r":0.35,"stress_mean_r":0.15,"minimum_trades":20,"minimum_days":12,"minimum_base_months":2,"minimum_stress_months":2,"largest_winner_share":0.30,"minimum_targets":2,"minimum_lookbacks":2}

def mean_r(t):
 x=np.asarray([q.get("realized_r",np.nan) for q in t],float);x=x[np.isfinite(x)];return float(x.mean()) if len(x) else None

def bootstrap(t):
 by={}
 for q in t:by.setdefault(q["date"],[]).append(float(q.get("realized_r",np.nan)))
 ds=sorted(by)
 if len(ds)<2:return None
 rng=np.random.default_rng(20260401);vals=[]
 for _ in range(1000):
  pick=rng.choice(ds,size=len(ds),replace=True);r=[]
  for d in pick:r.extend(v for v in by[d] if np.isfinite(v))
  if r:vals.append(float(np.mean(r)))
 return float(np.quantile(vals,.10)) if vals else None

def monthly(t):return {m:v3.metrics([x for x in t if x["date"].startswith(m)]) for m in sorted({x["date"][:7] for x in t})}
def score(g,b,s):
 gm,bm,sm=v3.metrics(g),v3.metrics(b),v3.metrics(s);br,sr=mean_r(b),mean_r(s);boot=bootstrap(b);targets=sorted({float(q["target_r"]) for q in b});lbs=sorted({int(q["structural_lookback"]) for q in b});fail=[]
 if bm["pf"]<G["base_pf"]:fail.append("BASE_PF")
 if sm["pf"]<G["stress_pf"]:fail.append("STRESS_PF")
 if br is None or br<G["base_mean_r"]:fail.append("BASE_MEAN_R")
 if sr is None or sr<G["stress_mean_r"]:fail.append("STRESS_MEAN_R")
 if boot is None or boot<=0:fail.append("BOOTSTRAP_P10_R")
 if bm["trades"]<G["minimum_trades"]:fail.append("TRADES")
 if bm["unique_days"]<G["minimum_days"]:fail.append("UNIQUE_DAYS")
 if bm["positive_months"]<G["minimum_base_months"]:fail.append("BASE_MONTHS")
 if sm["positive_months"]<G["minimum_stress_months"]:fail.append("STRESS_MONTHS")
 if bm["largest_winner_share"] is None or bm["largest_winner_share"]>G["largest_winner_share"]:fail.append("CONCENTRATION")
 if len(targets)<G["minimum_targets"]:fail.append("TARGET_DIVERSITY")
 if len(lbs)<G["minimum_lookbacks"]:fail.append("LOOKBACK_DIVERSITY")
 if not(gm["total_bps"]+1e-9>=bm["total_bps"]>=sm["total_bps"]-1e-9):fail.append("FRICTION_MONOTONICITY")
 if any(float(q.get("stop_atr_equivalent",99))>0.6000001 or float(q.get("raw_stop_ticks",0))<4.999999 for q in b):fail.append("STOP_POLICY")
 return {"pass":not fail,"failures":fail,"gross":gm,"base":bm,"stress":sm,"base_mean_r":br,"stress_mean_r":sr,"bootstrap_p10_base_mean_r":boot,"target_levels":targets,"structural_lookbacks":lbs,"median_stop_ticks":float(np.median([q["raw_stop_ticks"] for q in b])) if b else None,"median_stop_atr":float(np.median([q["stop_atr_equivalent"] for q in b])) if b else None,"floor_rate":float(np.mean([q["floor_active"] for q in b])) if b else None,"base_months":monthly(b),"stress_months":monthly(s)}

def run(root:Path,out:Path):
 fs=sorted(root.rglob("block_result.json"))
 if len(fs)!=11:raise RuntimeError(f"expected 11 blocks, got {len(fs)}")
 blocks=sorted([json.loads(p.read_text()) for p in fs],key=lambda z:z["block_index"])
 if [x["block_index"] for x in blocks]!=list(range(11)):raise RuntimeError("block mismatch")
 agg={k:{"g":[],"b":[],"s":[]} for k in ("CNYRUBF","USDRUBF")};summ=[]
 for bl in blocks:
  if bl.get("retired_internal_confirmation_accessed") or bl.get("true_oos_2025_accessed"):raise PermissionError("fence violation")
  summ.append({"block_index":bl["block_index"],"start":bl["block_start"],"end":bl["block_end_exclusive"],"enabled_models":sum(1 for d in bl.get("model_diagnostics",[]) if d.get("qualified_configs",0)>0),"prediction_summary":bl.get("prediction_summary",{})})
  for r in bl["instruments"]:
   k=r["instrument"];agg[k]["g"]+=r["gross_trades"];agg[k]["b"]+=r["base_trades"];agg[k]["s"]+=r["stress_trades"]
 inst=[];surv=[]
 for k,x in agg.items():
  sc=score(x["g"],x["b"],x["s"]);sc["instrument"]=k;inst.append(sc)
  if sc["pass"]:surv.append(k)
 status="INSTRUMENT_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if surv else "NO_INSTRUMENT_RESEARCH_SURVIVOR"
 res={"engine":"cycle20-structural-high-r-v1","status":status,"instrument_survivors":surv,"data_start":"2026-03-02","data_end_exclusive":"2026-05-16","retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"gates":G,"instruments":inst,"blocks":summ}
 out.mkdir(parents=True,exist_ok=True);(out/"result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");(out/"base_trades.json").write_text(json.dumps([q for x in agg.values() for q in x["b"]],indent=2,default=v3.jsonable)+"\n")
 lines=["# Cycle 20 — Structural Ultra-Short Stop / 4R–6R","",f"Status: **{status}**",f"Survivors: {surv}",""]
 for r in inst:lines.append(f"- {r['instrument']}: pass={r['pass']} BASE PF={r['base']['pf']:.3f} meanR={r['base_mean_r']} N={r['base']['trades']} STRESS PF={r['stress']['pf']:.3f} meanR={r['stress_mean_r']} bootP10={r['bootstrap_p10_base_mean_r']} medianStopATR={r['median_stop_atr']} fail={r['failures']}")
 lines += ["","Research-only. Retired May16-Jul1 and 2025 were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print("\n".join(lines))
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--block-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run(a.block_root,a.output)
