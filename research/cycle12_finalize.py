from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path

GATES={"base_pf_min":2.0,"stress_pf_min":1.5,"minimum_trades":30,"minimum_unique_days":15,"minimum_positive_base_months":3,"minimum_positive_stress_months":2,"largest_winner_share_max":0.25}

def load_v3():
    spec=importlib.util.spec_from_file_location("v3","research/autonomous_search_v3.py");m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
v3=load_v3()

def month_metrics(trades):
    months=sorted({t["date"][:7] for t in trades});return {m:v3.metrics([t for t in trades if t["date"].startswith(m)]) for m in months}

def gate(g,b,s):
    fail=[]
    if b["pf"]<GATES["base_pf_min"]:fail.append("BASE_PF")
    if s["pf"]<GATES["stress_pf_min"]:fail.append("STRESS_PF")
    if b["expectancy_bps"] is None or b["expectancy_bps"]<=0:fail.append("BASE_EXPECTANCY")
    if s["expectancy_bps"] is None or s["expectancy_bps"]<=0:fail.append("STRESS_EXPECTANCY")
    if b["trades"]<GATES["minimum_trades"]:fail.append("TRADES")
    if b["unique_days"]<GATES["minimum_unique_days"]:fail.append("UNIQUE_DAYS")
    if b["positive_months"]<GATES["minimum_positive_base_months"]:fail.append("BASE_MONTHS")
    if s["positive_months"]<GATES["minimum_positive_stress_months"]:fail.append("STRESS_MONTHS")
    if b["largest_winner_share"] is None or b["largest_winner_share"]>GATES["largest_winner_share_max"]:fail.append("CONCENTRATION")
    if not (g["total_bps"]+1e-9>=b["total_bps"]>=s["total_bps"]-1e-9):fail.append("FRICTION_MONOTONICITY")
    return not fail,fail

def run(block_root:Path,out:Path):
    files=sorted(block_root.rglob("block_result.json"));
    if len(files)!=11:raise RuntimeError(f"expected 11 block results, found {len(files)}")
    blocks=[json.loads(p.read_text()) for p in files];blocks.sort(key=lambda x:x["block_index"])
    if [x["block_index"] for x in blocks]!=list(range(11)):raise RuntimeError("block index set mismatch")
    all_g=[];all_b=[];all_s=[];by_inst={"CNYRUBF":{"g":[],"b":[],"s":[]},"USDRUBF":{"g":[],"b":[],"s":[]}};profile_counts={};block_summary=[]
    for block in blocks:
        if block.get("retired_internal_confirmation_accessed") or block.get("true_oos_2025_accessed"):raise PermissionError("data fence violation")
        bs={"block_index":block["block_index"],"start":block["block_start"],"end":block["block_end_exclusive"],"historical_rows":block["diagnostics"]["historical_rows"],"signals":{}}
        for ir in block["instruments"]:
            inst=ir["instrument"];g=ir["gross_trades"];b=ir["base_trades"];s=ir["stress_trades"];all_g+=g;all_b+=b;all_s+=s;by_inst[inst]["g"]+=g;by_inst[inst]["b"]+=b;by_inst[inst]["s"]+=s;bs["signals"][inst]=len(ir["signals"])
            for t in b:profile_counts[t["profile"]]=profile_counts.get(t["profile"],0)+1
        block_summary.append(bs)
    gm,bm,sm=v3.metrics(all_g),v3.metrics(all_b),v3.metrics(all_s);passed,fail=gate(gm,bm,sm);inst_rows=[]
    for inst,x in by_inst.items():inst_rows.append({"instrument":inst,"gross":v3.metrics(x["g"]),"base":v3.metrics(x["b"]),"stress":v3.metrics(x["s"]),"base_months":month_metrics(x["b"]),"stress_months":month_metrics(x["s"])})
    result={"engine":"cycle12-historical-analog-v1","status":"RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if passed else "NO_RESEARCH_SURVIVOR","block_count":11,"data_start":"2026-03-02","data_end_exclusive":"2026-05-16","retired_internal_confirmation_accessed":False,"true_oos_2025_accessed":False,"commission_excluded":True,"gates":GATES,"gate_pass":passed,"gate_failures":fail,"combined":{"gross":gm,"base":bm,"stress":sm,"base_months":month_metrics(all_b),"stress_months":month_metrics(all_s)},"instruments":inst_rows,"profile_counts":profile_counts,"blocks":block_summary}
    out.mkdir(parents=True,exist_ok=True);(out/"result.json").write_text(json.dumps(result,indent=2,default=v3.jsonable)+"\n");(out/"base_trades.json").write_text(json.dumps(all_b,indent=2,default=v3.jsonable)+"\n")
    lines=["# Cycle 12 — Historical Analog Pattern Mining","",f"Status: **{result['status']}**",f"Combined GROSS PF={gm['pf']:.3f} exp={gm['expectancy_bps']} N={gm['trades']} total={gm['total_bps']:.3f} bps",f"Combined BASE PF={bm['pf']:.3f} exp={bm['expectancy_bps']} N={bm['trades']} days={bm['unique_days']} months+={bm['positive_months']} total={bm['total_bps']:.3f} bps",f"Combined STRESS PF={sm['pf']:.3f} exp={sm['expectancy_bps']} months+={sm['positive_months']} total={sm['total_bps']:.3f} bps",f"Gate={passed}; failures={fail}",f"Profile counts={profile_counts}",""]
    for r in inst_rows:lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f} exp={r['base']['expectancy_bps']} N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f} exp={r['stress']['expectancy_bps']} N={r['stress']['trades']}")
    lines += ["","All analog pools use only labels fully closed before each weekly block. March-May remains research data, not fresh OOS. Retired May16-Jul1 and 2025 were not read."]
    (out/"report.md").write_text("\n".join(lines)+"\n");print("\n".join(lines))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--block-root",type=Path,required=True);ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();run(a.block_root,a.output)
