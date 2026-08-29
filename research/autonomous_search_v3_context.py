from __future__ import annotations
import argparse, json, importlib.util
from pathlib import Path

def load_engine():
    spec=importlib.util.spec_from_file_location("autonomous_search_v3","research/autonomous_search_v3.py")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod

def run_context(data_root: Path, output: Path, inst: str, tf: str):
    e=load_engine(); output.mkdir(parents=True,exist_ok=True)
    provenance=[]
    m1raw,p=e.load_prefix(data_root,inst,"M1"); provenance+=p
    if tf=="M1":
        sig,features=e.build_features(m1raw,inst,"M1")
    else:
        raw,p=e.load_prefix(data_root,inst,"M5"); provenance+=p
        sig,features=e.build_features(raw,inst,"M5")
    if sig.time.max()>=e.DISCOVERY_END or m1raw.time.max()>=e.DISCOVERY_END:
        raise PermissionError("internal confirmation fence violated")
    print("DISCOVER",inst,tf,flush=True)
    cands,_=e.train_candidates(sig,m1raw,features,inst,tf)
    print("FROZEN",len(cands),flush=True)
    evaluated=[]
    for k,c in enumerate(cands,1):
        row=dict(c);row["candidate_id"]=f"A3-{inst}-{tf}-{k:03d}";row["instrument"]=inst;row["timeframe"]=tf
        ev=e.evaluate_frozen(row,sig,m1raw,features,inst,tf)
        promising=ev["base"]["pf"]>=1.25 and (ev["base"]["expectancy_bps"] or -1e9)>0 and ev["base"]["trades"]>=15 and ev["base"].get("positive_folds",0)>=2
        plateau=e.forward_plateau(row,sig,m1raw,features,inst,tf) if promising else []
        stable=sum(x["stable_neighbor"] for x in plateau)
        passed,fail=e.gate_result(ev,stable)
        out={**row,"validation":ev,"plateau":plateau,"stable_neighbor_count":stable,
             "gate_pass":bool(passed),"gate_failures":fail,"replication":{"classification":"deferred_cross_context"}}
        out["rank_score"]=float(e.candidate_rank(out)); evaluated.append(out)
        if k%10==0:print("EVALUATED",k,"/",len(cands),flush=True)
    evaluated.sort(key=lambda x:(x["gate_pass"],x["rank_score"]),reverse=True)
    survivors=[x for x in evaluated if x["gate_pass"]]
    near=[x for x in evaluated if not x["gate_pass"] and x["validation"]["base"]["pf"]>=1.5 and (x["validation"]["base"]["expectancy_bps"] or -1e9)>0][:20]
    manifest={"status":"SURVIVOR_FOUND" if survivors else "NO_SURVIVOR_YET","engine_version":"autonomous-search-v3-context",
              "instrument":inst,"timeframe":tf,"methodology":"JAN_FEB_STABILITY_DISCOVERY_THEN_FROZEN_MAR_MAY_WALK_FORWARD",
              "discovery_start":str(e.DISCOVERY_START),"discovery_train_end_exclusive":str(e.DISCOVERY_TRAIN_END),
              "discovery_end_exclusive":str(e.DISCOVERY_END),"internal_confirmation_accessed":False,"true_oos_2025_accessed":False,
              "full_file_hashes_computed":False,"source_modified":False,"frozen_candidates":len(cands),
              "survivor_count":len(survivors),"gates":e.GATES,"provenance":provenance}
    (output/"run_manifest.json").write_text(json.dumps(manifest,indent=2,default=e.jsonable)+"\n")
    (output/"evaluated_candidates.json").write_text(json.dumps(evaluated,indent=2,default=e.jsonable)+"\n")
    (output/"survivors.json").write_text(json.dumps(survivors,indent=2,default=e.jsonable)+"\n")
    (output/"near_candidates.json").write_text(json.dumps(near,indent=2,default=e.jsonable)+"\n")
    lines=[f"# Autonomous Search v3 {inst} {tf}","",f"Status: **{manifest['status']}**",
           f"Frozen candidates: {len(cands)}",f"Strict survivors: {len(survivors)}","","## Top candidates"]
    for x in evaluated[:15]:
        b=x["validation"]["base"];s=x["validation"]["stress"]
        lines.append(f"- {x['candidate_id']} rule={x['rule']} side={x['side']} params={x['params']} BASE PF={b['pf']:.3f} exp={b['expectancy_bps']} N={b['trades']} folds={b.get('positive_folds')} STRESS PF={s['pf']:.3f} exp={s['expectancy_bps']} neighbors={x['stable_neighbor_count']} gate={x['gate_pass']} fail={x['gate_failures']}")
    (output/"report.md").write_text("\n".join(lines)+"\n")
    print(json.dumps(manifest,indent=2,default=e.jsonable))

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,required=True);ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--instrument",choices=["CNYRUBF","USDRUBF"],required=True);ap.add_argument("--timeframe",choices=["M1","M5"],required=True)
    a=ap.parse_args();run_context(a.data_root,a.output,a.instrument,a.timeframe)
