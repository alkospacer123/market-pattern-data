from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np

GATES={"base_pf_min":2.0,"stress_pf_min":1.5,"base_mean_r_min":0.30,"stress_mean_r_min":0.10,"bootstrap_p10_mean_r_min":0.0,"minimum_trades":30,"minimum_unique_days":15,"minimum_positive_base_months":3,"minimum_positive_stress_months":2,"largest_winner_share_max":0.25,"minimum_profiles":2,"minimum_target_levels":2}

def mod(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=mod("research/autonomous_search_v3.py","v3")

def monthly(trades):return {m:v3.metrics([x for x in trades if x["date"].startswith(m)]) for m in sorted({x["date"][:7] for x in trades})}
def mean_r(t):
 x=np.asarray([q.get("realized_r",np.nan) for q in t],float);x=x[np.isfinite(x)];return float(x.mean()) if len(x) else None

def bootstrap_p10(t):
 by={}
 for q in t:by.setdefault(q["date"],[]).append(float(q.get("realized_r",np.nan)))
 dates=sorted(by)
 if len(dates)<2:return None
 rng=np.random.default_rng(20260401);vals=[]
 for _ in range(1000):
  pick=rng.choice(dates,size=len(dates),replace=True);r=[]
  for d in pick:r.extend(x for x in by[d] if np.isfinite(x))
  if r:vals.append(float(np.mean(r)))
 return float(np.quantile(vals,.10)) if vals else None

def gate(g,b,s):
 bm,sm=v3.metrics(b),v3.metrics(s);gm=v3.metrics(g);br,sr=mean_r(b),mean_r(s);boot=bootstrap_p10(b);profiles=sorted({q["profile"] for q in b});targets=sorted({float(q["target_r"]) for q in b});fail=[]
 if bm["pf"]<GATES["base_pf_min"]:fail.append("BASE_PF")
 if sm["pf"]<GATES["stress_pf_min"]:fail.append("STRESS_PF")
 if br is None or br<GATES["base_mean_r_min"]:fail.append("BASE_MEAN_R")
 if sr is None or sr<GATES["stress_mean_r_min"]:fail.append("STRESS_MEAN_R")
 if boot is None or boot<=GATES["bootstrap_p10_mean_r_min"]:fail.append("BOOTSTRAP_P10_R")
 if bm["trades"]<GATES["minimum_trades"]:fail.append("TRADES")
 if bm["unique_days"]<GATES["minimum_unique_days"]:fail.append("UNIQUE_DAYS")
 if bm["positive_months"]<GATES["minimum_positive_base_months"]:fail.append("BASE_MONTHS")
 if sm["positive_months"]<GATES["minimum_positive_stress_months"]:fail.append("STRESS_MONTHS")
 if bm["largest_winner_share"] is None or bm["largest_winner_share"]>GATES["largest_winner_share_max"]:fail.append("CONCENTRATION")
 if len(profiles)<GATES["minimum_profiles"]:fail.append("PROFILE_DIVERSITY")
 if len(targets)<GATES["minimum_target_levels"]:fail.append("TARGET_DIVERSITY")
 if not(gm["total_bps"]+1e-9>=bm["total_bps"]>=sm["total_bps"]-1e-9):fail.append("FRICTION_MONOTONICITY")
 transparent=all("raw_stop_ticks" in q and "floor_active" in q and float(q.get("stop_atr",9))<=0.50 for q in b)
 if not transparent:fail.append("STOP_TRANSPARENCY")
 return not fail,fail,{"gross":gm,"base":bm,"stress":sm,"base_mean_r":br,"stress_mean_r":sr,"bootstrap_p10_base_mean_r":boot,"profiles":profiles,"target_levels":targets,"floor_rate":float(np.mean([bool(q["floor_active"]) for q in b])) if b else None,"median_raw_stop_ticks":float(np.median([float(q["raw_stop_ticks"]) for q in b])) if b else None}

def run(root:Path,out:Path):
 fs=sorted(root.rglob("block_result.json"));
 if len(fs)!=11:raise RuntimeError(f"expected 11 blocks, got {len(fs)}")
 blocks=sorted([json.loads(p.read_text()) for p in fs],key=lambda z:z["block_index"])
 if [x["block_index"] for x in blocks]!=list(range(11)):raise RuntimeError("block mismatch")
 g=[];b=[];s=[];agg={k:{"g":[],"b":[],"s":[]} for k in ("CNYRUBF","USDRUBF")};block_summary=[]
 for bl in blocks:
  if bl.get("retired_internal_confirmation_accessed") or bl.get("true_oos_2025_accessed"):raise PermissionError("data fence violation")
  enabled=sum(1 for d in bl.get("model_diagnostics",[]) if d.get("qualified_configs",0)>0);block_summary.append({"block_index":bl["block_index"],"start":bl["block_start"],"end":bl["block_end_exclusive"],"enabled_models":enabled,"prediction_summary":bl.get("prediction_summary",{})})
  for r in bl["instruments"]:
   k=r["instrument"];agg[k]["g"]+=r["gross_trades"];agg[k]["b"]+=r["base_trades"];agg[k]["s"]+=r["stress_trades"];g+=r["gross_trades"];b+=r["base_trades"];s+=r["stress_trades"]
 passed,fail,summary=gate(g,b,s);inst=[]
 for k,x in agg.items():inst.append({"instrument":k,"gross":v3.metrics(x["g"]),"base":v3.metrics(x["b"]),"stress":v3.metrics(x["s"]),"base_mean_r":mean_r(x["b"]),"stress_mean_r":mean_r(x["s"]),"base_months":monthly(x["b"]),"stress_months":monthly(x["s"])})
 res={"engine":"cycle18-ultrashort-barrier-v1","status":"RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if passed else "NO_RESEARCH_SURVIVOR","block_count":11,"data_start":"2026-03-02","data_end_exclusive":"2026-05-16","retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"gates":GATES,"gate_pass":passed,"gate_failures":fail,"combined":summary,"combined_base_months":monthly(b),"combined_stress_months":monthly(s),"instruments":inst,"blocks":block_summary}
 out.mkdir(parents=True,exist_ok=True);(out/"result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");(out/"base_trades.json").write_text(json.dumps(b,indent=2,default=v3.jsonable)+"\n")
 bm,sm=summary["base"],summary["stress"];lines=["# Cycle 18 — Ultra-Short Stop Barrier Mining","",f"Status: **{res['status']}**",f"GROSS PF={summary['gross']['pf']:.3f} exp={summary['gross']['expectancy_bps']} N={summary['gross']['trades']}",f"BASE PF={bm['pf']:.3f} exp={bm['expectancy_bps']} meanR={summary['base_mean_r']} N={bm['trades']} days={bm['unique_days']}",f"STRESS PF={sm['pf']:.3f} exp={sm['expectancy_bps']} meanR={summary['stress_mean_r']}",f"Bootstrap P10 BASE meanR={summary['bootstrap_p10_base_mean_r']}",f"Median raw stop={summary['median_raw_stop_ticks']} ticks; 5-tick floor rate={summary['floor_rate']}",f"Profiles={summary['profiles']}; targets={summary['target_levels']}",f"Gate={passed}; failures={fail}",""]
 for r in inst:lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f} exp={r['base']['expectancy_bps']} meanR={r['base_mean_r']} N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f} exp={r['stress']['expectancy_bps']} meanR={r['stress_mean_r']}")
 lines += ["","Research-only. Retired May16-Jul1 and 2025 were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print("\n".join(lines))

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--block-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run(a.block_root,a.output)
