from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
GATES={"base_pf_min":2.0,"stress_pf_min":1.5,"minimum_trades":30,"minimum_unique_days":15,"minimum_positive_base_months":3,"minimum_positive_stress_months":2,"largest_winner_share_max":0.25}
def loadv3():
 s=importlib.util.spec_from_file_location('v3','research/autonomous_search_v3.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v3=loadv3()
def mm(t):return {m:v3.metrics([x for x in t if x['date'].startswith(m)]) for m in sorted({x['date'][:7] for x in t})}
def gate(g,b,s):
 f=[]
 if b['pf']<2:f+=['BASE_PF']
 if s['pf']<1.5:f+=['STRESS_PF']
 if b['expectancy_bps'] is None or b['expectancy_bps']<=0:f+=['BASE_EXPECTANCY']
 if s['expectancy_bps'] is None or s['expectancy_bps']<=0:f+=['STRESS_EXPECTANCY']
 if b['trades']<30:f+=['TRADES']
 if b['unique_days']<15:f+=['UNIQUE_DAYS']
 if b['positive_months']<3:f+=['BASE_MONTHS']
 if s['positive_months']<2:f+=['STRESS_MONTHS']
 if b['largest_winner_share'] is None or b['largest_winner_share']>.25:f+=['CONCENTRATION']
 if not(g['total_bps']+1e-9>=b['total_bps']>=s['total_bps']-1e-9):f+=['FRICTION_MONOTONICITY']
 return not f,f
def run(root:Path,out:Path):
 fs=sorted(root.rglob('block_result.json'))
 if len(fs)!=11:raise RuntimeError(f'expected 11 blocks, got {len(fs)}')
 blocks=sorted([json.loads(p.read_text()) for p in fs],key=lambda z:z['block_index'])
 if [x['block_index'] for x in blocks]!=list(range(11)):raise RuntimeError('block mismatch')
 agg={k:{'g':[],'b':[],'s':[]} for k in ('CNYRUBF','USDRUBF')};g=[];b=[];s=[];pc={};enabled=[]
 for bl in blocks:
  if bl.get('retired_internal_confirmation_accessed') or bl.get('true_oos_2025_accessed'):raise PermissionError('fence')
  enabled.append({'block_index':bl['block_index'],'start':bl['block_start'],'end':bl['block_end_exclusive'],'enabled_models':sum(1 for d in bl['model_diagnostics'] if d.get('qualified_configs',0)>0),'prediction_summary':bl['prediction_summary']})
  for r in bl['instruments']:
   k=r['instrument'];agg[k]['g']+=r['gross_trades'];agg[k]['b']+=r['base_trades'];agg[k]['s']+=r['stress_trades'];g+=r['gross_trades'];b+=r['base_trades'];s+=r['stress_trades']
   for t in r['base_trades']:pc[t['profile']]=pc.get(t['profile'],0)+1
 gm,bm,sm=v3.metrics(g),v3.metrics(b),v3.metrics(s);passed,fail=gate(gm,bm,sm);inst=[]
 for k,x in agg.items():inst.append({'instrument':k,'gross':v3.metrics(x['g']),'base':v3.metrics(x['b']),'stress':v3.metrics(x['s']),'base_months':mm(x['b']),'stress_months':mm(x['s'])})
 res={'engine':'cycle16-sparse-consensus-v1','status':'RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION' if passed else 'NO_RESEARCH_SURVIVOR','block_count':11,'data_start':'2026-03-02','data_end_exclusive':'2026-05-16','retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,'commission_excluded':True,'gates':GATES,'gate_pass':passed,'gate_failures':fail,'combined':{'gross':gm,'base':bm,'stress':sm,'base_months':mm(b),'stress_months':mm(s)},'instruments':inst,'profile_counts':pc,'blocks':enabled}
 out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(res,indent=2,default=v3.jsonable)+'\n');(out/'base_trades.json').write_text(json.dumps(b,indent=2,default=v3.jsonable)+'\n')
 lines=['# Cycle 16 — Sparse Consensus High-PF Discovery','',f"Status: **{res['status']}**",f"GROSS PF={gm['pf']:.3f} exp={gm['expectancy_bps']} N={gm['trades']}",f"BASE PF={bm['pf']:.3f} exp={bm['expectancy_bps']} N={bm['trades']} days={bm['unique_days']} months+={bm['positive_months']}",f"STRESS PF={sm['pf']:.3f} exp={sm['expectancy_bps']} months+={sm['positive_months']}",f"Gate={passed}; failures={fail}",f"Profiles={pc}",'']
 for r in inst:lines.append(f"- {r['instrument']}: BASE PF={r['base']['pf']:.3f} exp={r['base']['expectancy_bps']} N={r['base']['trades']}; STRESS PF={r['stress']['pf']:.3f} exp={r['stress']['expectancy_bps']}")
 lines+=['','Research-only. No fallback to unqualified validation models. Retired May16-Jul1 and 2025 were not read.'];(out/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--block-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.block_root,a.output)
