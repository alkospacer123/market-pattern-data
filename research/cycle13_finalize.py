from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path

GATES={"base_pf_min":2.0,"stress_pf_min":1.5,"minimum_trades":30,"minimum_unique_days":15,"minimum_positive_base_months":3,"minimum_positive_stress_months":2,"largest_winner_share_max":0.25}
def load_v3():
    s=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=load_v3()
def month_metrics(trades):
    return {m:v3.metrics([t for t in trades if t["date"].startswith(m)]) for m in sorted({t["date"][:7] for t in trades})}
def gate(g,b,s):
    f=[]
    if b["pf"]<2:f.append("BASE_PF")
    if s["pf"]<1.5:f.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:f.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:f.append("STRESS_EXPECTANCY")
    if b["trades"]<30:f.append("TRADES")
    if b["unique_days"]<15:f.append("UNIQUE_DAYS")
    if b["positive_months"]<3:f.append("BASE_MONTHS")
    if s["positive_months"]<2:f.append("STRESS_MONTHS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>.25:f.append("CONCENTRATION")
    if not(g["total_bps"]+1e-9>=b["total_bps"]>=s["total_bps"]-1e-9):f.append("FRICTION_MONOTONICITY")
    return not f,f
def run(root:Path,out:Path):
    files=sorted(root.rglob("block_result.json"));
    if len(files)!=11:raise RuntimeError(f"expected 11 blocks, got {len(files)}")
    blocks=sorted([json.loads(p.read_text()) for p in files],key=lambda z:z["block_index"])
    if [b["block_index"] for b in blocks]!=list(range(11)):raise RuntimeError("block index mismatch")
    agg={"CNYRUBF":{"g":[],"b":[],"s":[]},"USDRUBF":{"g":[],"b":[],"s":[]}};g=[];b=[];s=[];profiles={}
    for bl in blocks:
        if bl.get("retired_internal_confirmation_accessed") or bl.get("true_oos_2025_accessed"):raise PermissionError("data fence violation")
        for r in bl["instruments"]:
            k=r["instrument"];agg[k]["g"]+=r["gross_trades"];agg[k]["b"]+=r["base_trades"];agg[k]["s"]+=r["stress_trades"];g+=r["gross_trades"];b+=r["base_trades"];s+=r["stress_trades"]
            for t in r["base_trades"]:profiles[t["profile"]]=profiles.get(t["profile"],0)+1
    gm,bm,sm=v3.metrics(g),v3.metrics(b),v3.metrics(s);passed,fail=gate(gm,bm,sm);inst=[]
    for k,x in agg.items():inst.append({"instrument":k,"gross":v3.metrics(x["g"]),"base":v3.metrics(x["b"]),"stress":v3.metrics(x["s"]),"base_months":month_metrics(x["b"]),"stress_months":month_metrics(x["s"])})
    result={"engine":"cycle13-cross-leadlag-v1","status":"RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if passed else "NO_RESEARCH_SURVIVOR","block_count":11,"data_start":"2026-03-02","data_end_exclusive":"2026-05-16","retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"gates":GATES,"gate_pass":passed,"gate_failures":fail,"combined":{"gross":gm,"base":bm,"stress":sm,"base_months":month_metrics(b),"stress_months":month_metrics(s)},"instruments":inst,"profile_counts":profiles,"blocks":[{"block_index":z["block_index"],"start":z["block_start"],"end":z["block_end_exclusive"],"prediction_summary":z["prediction_summary"]} for z in blocks]}
    out.mkdir(parents=True,exist_ok=True);(out/"result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");(out/"base_trades.json").write_text(json.dumps(b,indent=2,default=v3.jsonable)+"\n")
    lines=["# Cycle 13 — Cross-Instrument Lead/Lag Executable-PnL Discovery","",f"Status: **{result['status']}**",f"GROSS PF={gm['pf']:.3f} exp={gm['expectancy_bps']} N={gm['trades']}",f"BASE PF={bm['pf']:.3f} exp={bm['expectancy_bps']} N={bm['trades']} days={bm['unique_days']} months+={bm['positive_months']}",f"STRESS PF={sm['pf']:.3f} exp={sm['expectancy_bps']} months+={sm['positive_months']}",f"Gate={passed}; failures={fail}",f"Profiles={profiles}",""]
    for r in inst:lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f} exp={r['base']['expectancy_bps']} N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f} exp={r['stress']['expectancy_bps']}")
    lines += ["","Research-only. Retired May16-Jul1 and sealed 2025 were not read."];(out/"report.md").write_text("\n".join(lines)+"\n");print("\n".join(lines))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--block-root",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();run(a.block_root,a.output)
