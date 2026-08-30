from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np

GATES={"base_pf_min":2.0,"stress_pf_min":1.5,"base_mean_r_min":0.30,"stress_mean_r_min":0.10,"bootstrap_q10_base_mean_r_min":0.0,"minimum_trades":30,"minimum_unique_days":15,"minimum_positive_base_months":3,"minimum_positive_stress_months":2,"largest_winner_share_max":0.25,"minimum_profiles":2,"minimum_target_r_levels":2}
SEED=20260401

def loadv3():
 s=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=loadv3()

def month_metrics(t):return {m:v3.metrics([x for x in t if x["date"].startswith(m)]) for m in sorted({x["date"][:7] for x in t})}

def rstats(t):
 r=np.asarray([x.get("realized_r",np.nan) for x in t],float);r=r[np.isfinite(r)]
 return {"n":int(len(r)),"mean_r":float(r.mean()) if len(r) else None,"median_r":float(np.median(r)) if len(r) else None,"target_hit_rate":float(np.mean([bool(x.get("target_hit")) for x in t])) if t else None}

def day_boot_q10(t,reps=2000):
 by={}
 for x in t:
  r=x.get("realized_r")
  if r is not None and np.isfinite(float(r)):by.setdefault(x["date"],[]).append(float(r))
 days=sorted(by)
 if not days:return None
 rng=np.random.default_rng(SEED);vals=[]
 for _ in range(reps):
  picked=rng.choice(days,size=len(days),replace=True);sample=[]
  for d in picked:sample.extend(by[str(d)])
  vals.append(float(np.mean(sample)))
 return float(np.quantile(vals,0.10))

def gate(g,b,s,br,sr,q10,profiles,target_levels):
 f=[]
 if b["pf"]<GATES["base_pf_min"]:f.append("BASE_PF")
 if s["pf"]<GATES["stress_pf_min"]:f.append("STRESS_PF")
 if br["mean_r"] is None or br["mean_r"]<GATES["base_mean_r_min"]:f.append("BASE_MEAN_R")
 if sr["mean_r"] is None or sr["mean_r"]<GATES["stress_mean_r_min"]:f.append("STRESS_MEAN_R")
 if q10 is None or q10<=GATES["bootstrap_q10_base_mean_r_min"]:f.append("BOOTSTRAP_Q10")
 if b["trades"]<GATES["minimum_trades"]:f.append("TRADES")
 if b["unique_days"]<GATES["minimum_unique_days"]:f.append("UNIQUE_DAYS")
 if b["positive_months"]<GATES["minimum_positive_base_months"]:f.append("BASE_MONTHS")
 if s["positive_months"]<GATES["minimum_positive_stress_months"]:f.append("STRESS_MONTHS")
 if b["largest_winner_share"] is None or b["largest_winner_share"]>GATES["largest_winner_share_max"]:f.append("CONCENTRATION")
 if len(profiles)<GATES["minimum_profiles"]:f.append("PROFILE_DIVERSITY")
 if len(target_levels)<GATES["minimum_target_r_levels"]:f.append("TARGET_R_DIVERSITY")
 if not(g["total_bps"]+1e-9>=b["total_bps"]>=s["total_bps"]-1e-9):f.append("FRICTION_MONOTONICITY")
 return not f,f

def run(root,out):
 fs=sorted(root.rglob("block_result.json"))
 if len(fs)!=11:raise RuntimeError(f"expected 11 blocks, got {len(fs)}")
 blocks=sorted([json.loads(p.read_text()) for p in fs],key=lambda z:z["block_index"])
 if [x["block_index"] for x in blocks]!=list(range(11)):raise RuntimeError("block mismatch")
 agg={k:{"g":[],"b":[],"s":[]} for k in ("CNYRUBF","USDRUBF")};g=[];b=[];s=[];enabled=[]
 for bl in blocks:
  if bl.get("retired_internal_confirmation_accessed") or bl.get("true_oos_2025_accessed"):raise PermissionError("fence")
  enabled.append({"block_index":bl["block_index"],"start":bl["block_start"],"end":bl["block_end_exclusive"],"enabled_models":sum(1 for d in bl["model_diagnostics"] if d.get("qualified_configs",0)>0),"prediction_summary":bl["prediction_summary"]})
  for r in bl["instruments"]:
   k=r["instrument"];agg[k]["g"]+=r["gross_trades"];agg[k]["b"]+=r["base_trades"];agg[k]["s"]+=r["stress_trades"];g+=r["gross_trades"];b+=r["base_trades"];s+=r["stress_trades"]
 gm,bm,sm=v3.metrics(g),v3.metrics(b),v3.metrics(s);br,sr=rstats(b),rstats(s);q10=day_boot_q10(b);profiles=sorted({x["profile"] for x in b});targets=sorted({float(x["target_r"]) for x in b});passed,fail=gate(gm,bm,sm,br,sr,q10,profiles,targets);inst=[]
 for k,x in agg.items():inst.append({"instrument":k,"gross":v3.metrics(x["g"]),"base":v3.metrics(x["b"]),"stress":v3.metrics(x["s"]),"base_r":rstats(x["b"]),"stress_r":rstats(x["s"]),"base_months":month_metrics(x["b"]),"stress_months":month_metrics(x["s"])})
 res={"engine":"cycle17-high-r-expectancy-v1","status":"RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if passed else "NO_RESEARCH_SURVIVOR","block_count":11,"data_start":"2026-03-02","data_end_exclusive":"2026-05-16","retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"gates":GATES,"gate_pass":passed,"gate_failures":fail,"combined":{"gross":gm,"base":bm,"stress":sm,"base_r":br,"stress_r":sr,"bootstrap_q10_base_mean_r":q10,"base_months":month_metrics(b),"stress_months":month_metrics(s)},"executed_profiles":profiles,"executed_target_r_levels":targets,"instruments":inst,"blocks":enabled}
 out.mkdir(parents=True,exist_ok=True);(out/"result.json").write_text(json.dumps(res,indent=2,default=v3.jsonable)+"\n");(out/"base_trades.json").write_text(json.dumps(b,indent=2,default=v3.jsonable)+"\n")
 lines=["# Cycle 17 — Autonomous High-R Expectancy Discovery","",f"Status: **{res['status']}**",f"GROSS PF={gm['pf']:.3f} exp={gm['expectancy_bps']} N={gm['trades']}",f"BASE PF={bm['pf']:.3f} exp={bm['expectancy_bps']} meanR={br['mean_r']} N={bm['trades']} days={bm['unique_days']} months+={bm['positive_months']}",f"STRESS PF={sm['pf']:.3f} exp={sm['expectancy_bps']} meanR={sr['mean_r']} months+={sm['positive_months']}",f"Day-bootstrap BASE meanR q10={q10}",f"Gate={passed}; failures={fail}",f"Profiles={profiles}; target-R levels={targets}",""]
 for r in inst:lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f} exp={r['base']['expectancy_bps']} meanR={r['base_r']['mean_r']} N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f} meanR={r['stress_r']['mean_r']}")
 lines+=["","Research-only. Every tested target is >=3R. Retired May16-Jul1 and 2025 TRUE OOS were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print("\n".join(lines))

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("--block-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run(a.block_root,a.output)
