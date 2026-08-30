from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3")
IG={"base_pf":2.0,"stress_pf":1.5,"base_mean_r":0.30,"stress_mean_r":0.10,"minimum_trades":20,"minimum_days":12,"minimum_base_months":2,"minimum_stress_months":2,"largest_winner_share":0.30,"minimum_target_levels":2}
CG={"base_pf":2.0,"stress_pf":1.5,"base_mean_r":0.30,"stress_mean_r":0.10,"minimum_trades":30,"minimum_days":15,"minimum_base_months":3,"minimum_stress_months":2,"largest_winner_share":0.25,"minimum_profiles":2,"minimum_target_levels":2}

def mean_r(t):
 x=np.asarray([q.get("realized_r",np.nan) for q in t],float);x=x[np.isfinite(x)];return float(x.mean()) if len(x) else None

def bootstrap(t):
 by={}
 for q in t:by.setdefault(q["date"],[]).append(float(q.get("realized_r",np.nan)))
 dates=sorted(by)
 if len(dates)<2:return None
 rng=np.random.default_rng(20260401);z=[]
 for _ in range(1000):
  pick=rng.choice(dates,size=len(dates),replace=True);r=[]
  for d in pick:r.extend(x for x in by[d] if np.isfinite(x))
  if r:z.append(float(np.mean(r)))
 return float(np.quantile(z,.10)) if z else None

def months(t):return {m:v3.metrics([x for x in t if x["date"].startswith(m)]) for m in sorted({x["date"][:7] for x in t})}

def score(tg,tb,ts,gates,individual=False):
 gm,bm,sm=v3.metrics(tg),v3.metrics(tb),v3.metrics(ts);br,sr=mean_r(tb),mean_r(ts);boot=bootstrap(tb);targets=sorted({float(q["target_r"]) for q in tb});profiles=sorted({q["profile"] for q in tb});fail=[]
 if bm["pf"]<gates["base_pf"]:fail.append("BASE_PF")
 if sm["pf"]<gates["stress_pf"]:fail.append("STRESS_PF")
 if br is None or br<gates["base_mean_r"]:fail.append("BASE_MEAN_R")
 if sr is None or sr<gates["stress_mean_r"]:fail.append("STRESS_MEAN_R")
 if boot is None or boot<=0:fail.append("BOOTSTRAP_P10_R")
 if bm["trades"]<gates["minimum_trades"]:fail.append("TRADES")
 if bm["unique_days"]<gates["minimum_days"]:fail.append("UNIQUE_DAYS")
 if bm["positive_months"]<gates["minimum_base_months"]:fail.append("BASE_MONTHS")
 if sm["positive_months"]<gates["minimum_stress_months"]:fail.append("STRESS_MONTHS")
 if bm["largest_winner_share"] is None or bm["largest_winner_share"]>gates["largest_winner_share"]:fail.append("CONCENTRATION")
 if len(targets)<gates["minimum_target_levels"]:fail.append("TARGET_DIVERSITY")
 if not individual and len(profiles)<gates["minimum_profiles"]:fail.append("PROFILE_DIVERSITY")
 if not(gm["total_bps"]+1e-9>=bm["total_bps"]>=sm["total_bps"]-1e-9):fail.append("FRICTION_MONOTONICITY")
 transparent=all("raw_stop_ticks" in q and "floor_active" in q and float(q.get("stop_atr",9))<=0.50 for q in tb)
 if not transparent:fail.append("STOP_TRANSPARENCY")
 return {"pass":not fail,"failures":fail,"gross":gm,"base":bm,"stress":sm,"base_mean_r":br,"stress_mean_r":sr,"bootstrap_p10_base_mean_r":boot,"profiles":profiles,"target_levels":targets,"floor_rate":float(np.mean([bool(q["floor_active"]) for q in tb])) if tb else None,"median_stop_ticks":float(np.median([float(q["raw_stop_ticks"]) for q in tb])) if tb else None,"base_months":months(tb),"stress_months":months(ts)}

def run(root:Path,out:Path):
 fs=sorted(root.rglob("block_result.json"));
 if len(fs)!=11:raise RuntimeError(f"expected 11 blocks, got {len(fs)}")
 blocks=sorted([json.loads(p.read_text()) for p in fs],key=lambda z:z["block_index"])
 if [x["block_index"] for x in blocks]!=list(range(11)):raise RuntimeError("block mismatch")
 agg={k:{"g":[],"b":[],"s":[]} for k in ("CNYRUBF","USDRUBF")};block_summary=[]
 for bl in blocks:
  if bl.get("retired_internal_confirmation_accessed") or bl.get("true_oos_2025_accessed"):raise PermissionError("fence")
  block_summary.append({"block_index":bl["block_index"],"start":bl["block_start"],"end":bl["block_end_exclusive"],"enabled_models":sum(1 for d in bl.get("model_diagnostics",[]) if d.get("qualified_configs",0)>0),"prediction_summary":bl.get("prediction_summary",{})})
  for r in bl["instruments"]:
   k=r["instrument"];agg[k]["g"]+=r["gross_trades"];agg[k]["b"]+=r["base_trades"];agg[k]["s"]+=r["stress_trades"]
 inst=[];survivors=[]
 for k,x in agg.items():
  sc=score(x["g"],x["b"],x["s"],IG,True);sc["instrument"]=k;inst.append(sc)
  if sc["pass"]:survivors.append(k)
 allg=[q for x in agg.values() for q in x["g"]];allb=[q for x in agg.values() for q in x["b"]];alls=[q for x in agg.values() for q in x["s"]];combined=score(allg,allb,alls,CG,False)
 selg=[q for k in survivors for q in agg[k]["g"]];selb=[q for k in survivors for q in agg[k]["b"]];sels=[q for k in survivors for q in agg[k]["s"]];selected=score(selg,selb,sels,CG,False) if survivors else None
 status="INSTRUMENT_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if survivors else "NO_INSTRUMENT_RESEARCH_SURVIVOR"
 res={"engine":"cycle19-instrument-specific-high-r-v1","status":status,"instrument_survivors":survivors,"data_start":"2026-03-02","data_end_exclusive":"2026-05-16","retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"individual_gates":IG,"combined_gates":CG,"instruments":inst,"all_instruments_combined":combined,"survivor_only_portfolio":selected,"blocks":block_summary}
 out.mkdir(parents=True,exist_ok=True);(out/"result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");(out/"base_trades.json").write_text(json.dumps(allb,indent=2,default=v3.jsonable)+"\n")
 lines=["# Cycle 19 — Instrument-Specific High-R Discovery","",f"Status: **{status}**",f"Instrument survivors: {survivors}",""]
 for r in inst:lines.append(f"- {r['instrument']}: pass={r['pass']} BASE PF={r['base']['pf']:.3f} meanR={r['base_mean_r']} N={r['base']['trades']} STRESS PF={r['stress']['pf']:.3f} meanR={r['stress_mean_r']} bootP10={r['bootstrap_p10_base_mean_r']} fail={r['failures']}")
 lines += ["",f"All-instruments combined: BASE PF={combined['base']['pf']:.3f}, STRESS PF={combined['stress']['pf']:.3f}, fail={combined['failures']}","","Research-only. Retired May16-Jul1 and 2025 were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print("\n".join(lines))

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--block-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run(a.block_root,a.output)
