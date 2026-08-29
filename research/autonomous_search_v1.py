from __future__ import annotations
import argparse, csv, hashlib, json, math
from pathlib import Path
from time import perf_counter
from typing import Any
import numpy as np
import pandas as pd

DISCOVERY_START = pd.Timestamp('2026-01-05 00:00:00')
DISCOVERY_END = pd.Timestamp('2026-05-16 00:00:00')
FOLDS = [
    ('WF-01','2026-01-05','2026-02-01','2026-02-01','2026-03-01'),
    ('WF-02','2026-01-05','2026-03-01','2026-03-01','2026-04-01'),
    ('WF-03','2026-01-05','2026-04-01','2026-04-01','2026-05-01'),
    ('WF-04','2026-01-05','2026-05-01','2026-05-01','2026-05-16'),
]
SPECS = {
    'CNYRUBF': {'folder':'CNY','tick':0.001,'round_step':0.05,'files':['CNY_2026_Q1.csv','CNY_2026_Q2.csv']},
    'USDRUBF': {'folder':'Si','tick':0.01,'round_step':0.10,'files':['Si_2026_Q1.csv','Si_2026_Q2.csv']},
}
QPROBS=(.10,.25,.75,.90)
QLABELS=np.array(['LE_P10','P10_P25','P25_P75','P75_P90','GE_P90'],dtype=object)
SEARCH_STATES=('LE_P10','P10_P25','P75_P90','GE_P90')
FEATURES=[
 'range_atr','body_atr','body_frac','close_pos','upper_wick_frac','lower_wick_frac',
 'ret_1_atr','ret_3_atr','ret_6_atr','ret_12_atr','ret_24_atr',
 'pos_5','pos_10','pos_20','pos_60','dist_high_10_atr','dist_low_10_atr','dist_high_20_atr','dist_low_20_atr',
 'atr5_atr20','atr10_atr60','relvol20','vol_z20','round_dist_atr','round_pos','dist_pdh_atr','dist_pdl_atr',
 'tod_sin','tod_cos']
COARSE_GRID=[(s,t,h) for s in (.5,1.0) for t in (2.,4.,6.,10.) for h in (12,24,48)]
FULL_GRID=[(s,t,h) for s in (.5,.75,1.0,1.25) for t in (1.5,2.,3.,4.,6.,8.,10.) for h in (6,12,24,48)]


def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def source_paths(root: Path, inst: str) -> list[Path]:
    spec=SPECS[inst]; paths=[root/'2026'/spec['folder']/fn for fn in spec['files']]
    for p in paths:
        if not p.exists(): raise FileNotFoundError(p)
        if '2025' in p.name: raise PermissionError('2025 is sealed')
    return paths


def load_discovery(root: Path, inst: str) -> tuple[pd.DataFrame,list[dict[str,Any]]]:
    rows=[]; provenance=[]
    for p in source_paths(root,inst):
        provenance.append({'path':str(p.relative_to(root)),'sha256':sha256(p),'size':p.stat().st_size})
        with p.open('r',encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f,delimiter=';'); header=next(reader)
            expected=['<TICKER>','<PER>','<DATE>','<TIME>','<OPEN>','<HIGH>','<LOW>','<CLOSE>','<VOL>']
            if header!=expected: raise ValueError(f'schema mismatch: {p}')
            for fields in reader:
                if len(fields)!=9: continue
                dt=pd.to_datetime(fields[2]+fields[3].zfill(6),format='%Y%m%d%H%M%S')
                if not (DISCOVERY_START<=dt<DISCOVERY_END): continue
                if int(fields[1])!=5: raise ValueError(f'expected M5: {p}')
                if fields[0].upper()!=inst: raise ValueError(f'ticker mismatch: {p}')
                rows.append((dt,float(fields[4]),float(fields[5]),float(fields[6]),float(fields[7]),float(fields[8])))
    f=pd.DataFrame(rows,columns=['time','open','high','low','close','volume']).sort_values('time').drop_duplicates('time').reset_index(drop=True)
    if f.empty or f.time.min()<DISCOVERY_START or f.time.max()>=DISCOVERY_END: raise ValueError('discovery fence violation')
    f['date']=f.time.dt.date; f['month']=f.time.dt.to_period('M').astype(str); f['instrument']=inst
    return build_features(f,SPECS[inst]['round_step']),provenance


def _day_roll(f: pd.DataFrame, col: str, window: int, fn: str, shift: int=1) -> pd.Series:
    def calc(s):
        x=s.shift(shift).rolling(window,min_periods=window)
        return getattr(x,fn)()
    return f.groupby('date',sort=False)[col].transform(calc)


def build_features(f: pd.DataFrame, round_step: float) -> pd.DataFrame:
    prev=f.close.shift(1)
    tr=pd.concat([f.high-f.low,(f.high-prev).abs(),(f.low-prev).abs()],axis=1).max(axis=1)
    f['atr14']=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    f['atr20']=tr.rolling(20,min_periods=20).mean()
    rng=(f.high-f.low).replace(0,np.nan)
    f['range_atr']=rng/f.atr20
    f['body_atr']=(f.close-f.open)/f.atr20
    f['body_frac']=(f.close-f.open)/rng
    f['close_pos']=(f.close-f.low)/rng
    f['upper_wick_frac']=(f.high-np.maximum(f.open,f.close))/rng
    f['lower_wick_frac']=(np.minimum(f.open,f.close)-f.low)/rng
    for w in (1,3,6,12,24):
        lag=f.groupby('date',sort=False).close.shift(w)
        f[f'ret_{w}_atr']=(f.close-lag)/f.atr20
    for w in (5,10,20,60):
        rh=_day_roll(f,'high',w,'max'); rl=_day_roll(f,'low',w,'min'); rr=(rh-rl).replace(0,np.nan)
        f[f'pos_{w}']=(f.close-rl)/rr
        f[f'dist_high_{w}_atr']=(rh-f.close)/f.atr20
        f[f'dist_low_{w}_atr']=(f.close-rl)/f.atr20
    f['atr5_atr20']=tr.groupby(f.date).transform(lambda s:s.shift(1).rolling(5,min_periods=5).mean())/f.atr20
    atr60=tr.groupby(f.date).transform(lambda s:s.shift(1).rolling(60,min_periods=60).mean())
    atr10=tr.groupby(f.date).transform(lambda s:s.shift(1).rolling(10,min_periods=10).mean())
    f['atr10_atr60']=atr10/atr60
    med20=f.groupby('date',sort=False).volume.transform(lambda s:s.shift(1).rolling(20,min_periods=20).median())
    mean20=f.groupby('date',sort=False).volume.transform(lambda s:s.shift(1).rolling(20,min_periods=20).mean())
    std20=f.groupby('date',sort=False).volume.transform(lambda s:s.shift(1).rolling(20,min_periods=20).std())
    f['relvol20']=f.volume/med20; f['vol_z20']=(f.volume-mean20)/std20
    nearest=np.floor(f.close/round_step+0.5)*round_step
    f['round_dist_atr']=(f.close-nearest)/f.atr20; f['round_pos']=(f.close%round_step)/round_step
    daily=f.groupby('date').agg(dh=('high','max'),dl=('low','min')); pdaily=daily.shift(1)
    f['prev_day_high']=f.date.map(pdaily.dh); f['prev_day_low']=f.date.map(pdaily.dl)
    f['dist_pdh_atr']=(f.prev_day_high-f.close)/f.atr20; f['dist_pdl_atr']=(f.close-f.prev_day_low)/f.atr20
    mins=f.time.dt.hour*60+f.time.dt.minute; f['tod_sin']=np.sin(2*np.pi*mins/1440);f['tod_cos']=np.cos(2*np.pi*mins/1440)
    for h in (6,12,24):
        future=f.groupby('date',sort=False).close.shift(-h)
        f[f'fwd_{h}_atr']=(future-f.close)/f.atr20
    return f


def fit_states(f: pd.DataFrame, train: np.ndarray) -> tuple[dict[str,np.ndarray],dict[str,list[float]]]:
    states={};cuts={}
    for feat in FEATURES:
        x=pd.to_numeric(f.loc[train,feat],errors='coerce').dropna()
        if len(x)<100: continue
        c=np.quantile(x,QPROBS)
        if len(np.unique(c))<4: continue
        vals=pd.to_numeric(f[feat],errors='coerce').to_numpy(float); st=np.full(len(f),'MISSING',dtype=object); ok=np.isfinite(vals)
        st[ok]=QLABELS[np.searchsorted(c,vals[ok],side='left')]
        states[feat]=st; cuts[feat]=[float(v) for v in c]
    return states,cuts


def rule_mask(states: dict[str,np.ndarray], rule: tuple[tuple[str,str],...], n: int) -> np.ndarray:
    m=np.ones(n,bool)
    for feat,state in rule:
        if feat not in states:return np.zeros(n,bool)
        m &= states[feat]==state
    return m


def onset(f: pd.DataFrame, mask: np.ndarray) -> np.ndarray:
    prev=np.r_[False,mask[:-1]]; same=np.r_[False,f.date.to_numpy()[1:]==f.date.to_numpy()[:-1]]
    return mask & ~(prev & same)


def quick_score(frames, states_by_inst, rule, side, train_by_inst):
    pooled=[]; med_inst=[]; win_inst=[]; month_effects=[]; total=0
    for inst,f in frames.items():
        raw=rule_mask(states_by_inst[inst],rule,len(f)); sig=onset(f,raw)&train_by_inst[inst]
        y=f.fwd_12_atr.to_numpy(float); ok=sig&np.isfinite(y)
        if ok.sum()<10:return None
        z=side*y[ok]; total+=len(z);pooled.extend(z.tolist());med_inst.append(float(np.median(z)));win_inst.append(float(np.mean(z>0)))
        months=f.loc[ok,'month'].to_numpy()
        for m in np.unique(months):
            zz=z[months==m]
            if len(zz)>=3:month_effects.append(float(np.median(zz)))
    if total<30:return None
    a=np.asarray(pooled);posm=sum(x>0 for x in month_effects)
    score=.50*min(med_inst)+.30*np.median(a)+.15*np.mean(a)+.05*(min(win_inst)-.5)+.03*posm
    return {'n':total,'score':float(score),'median':float(np.median(a)),'mean':float(np.mean(a)),'min_inst_median':float(min(med_inst)),'pos_months':int(posm)}


def beam_rules(frames, states, train, smoke=False):
    first=[]
    for feat in FEATURES:
      for st in SEARCH_STATES:
       for side in (1,-1):
        q=quick_score(frames,states,((feat,st),),side,train)
        if q:first.append((q['score'],((feat,st),),side,q))
    first.sort(reverse=True,key=lambda x:x[0]); beam=first[:(10 if smoke else 30)]
    second=[]
    for _,rule,side,_ in beam:
      used={x[0] for x in rule}
      for feat in FEATURES:
       if feat in used:continue
       for st in SEARCH_STATES:
        nr=tuple(sorted(rule+((feat,st),)))
        q=quick_score(frames,states,nr,side,train)
        if q:second.append((q['score'],nr,side,q))
    second.sort(reverse=True,key=lambda x:x[0]); third=[]
    for _,rule,side,_ in second[:(6 if smoke else 20)]:
      used={x[0] for x in rule}
      for feat in FEATURES:
       if feat in used:continue
       for st in SEARCH_STATES:
        nr=tuple(sorted(rule+((feat,st),)))
        q=quick_score(frames,states,nr,side,train)
        if q:third.append((q['score'],nr,side,q))
    allr=first+second+third; best={}
    for row in allr:
        key=(row[1],row[2]);best[key]=max(best.get(key,row),row,key=lambda x:x[0])
    return sorted(best.values(),reverse=True,key=lambda x:x[0])[:(20 if smoke else 80)]


def simulate(f, signal_mask, side, params, tick, friction):
    stop_atr,target_r,hold=params; sig=np.flatnonzero(onset(f,signal_mask)); out=[];available=-1;n=len(f)
    for i in sig:
        ei=i+1
        if ei>=n or ei<=available or f.date.iloc[ei]!=f.date.iloc[i]:continue
        atr=float(f.atr14.iloc[i])
        if not np.isfinite(atr) or atr<=0:continue
        entry=float(f.open.iloc[ei]);risk=stop_atr*atr;stop=entry-side*risk;target=entry+side*risk*target_r
        jmax=min(ei+hold-1,n-1)
        while jmax>ei and f.date.iloc[jmax]!=f.date.iloc[ei]:jmax-=1
        if f.date.iloc[jmax]!=f.date.iloc[ei]:continue
        xi=jmax;raw=float(f.close.iloc[xi]);reason='TIME'
        for j in range(ei,jmax+1):
            o,h,l=float(f.open.iloc[j]),float(f.high.iloc[j]),float(f.low.iloc[j])
            if side==1:
                if o<=stop:xi=j;raw=o;reason='STOP_GAP';break
                if o>=target:xi=j;raw=target;reason='TARGET_GAP_CONSERVATIVE';break
                hs=l<=stop;ht=h>=target
            else:
                if o>=stop:xi=j;raw=o;reason='STOP_GAP';break
                if o<=target:xi=j;raw=target;reason='TARGET_GAP_CONSERVATIVE';break
                hs=h>=stop;ht=l<=target
            if hs:xi=j;raw=stop;reason='STOP_FIRST_TIE' if ht else 'STOP';break
            if ht:xi=j;raw=target;reason='TARGET';break
        available=xi;ae=entry+side*friction*tick;ax=raw-side*friction*tick;pnl=side*(ax-ae);bps=10000*pnl/entry
        out.append({'bps':float(bps),'pnl':float(pnl),'date':str(f.date.iloc[ei]),'instrument':str(f.instrument.iloc[ei]),'reason':reason})
    return out


def metrics(trades):
    if not trades:return {'trades':0,'pf':0.0,'expectancy_bps':None,'total_bps':0.0,'positive_months':0,'largest_winner_share':None,'unique_days':0,'positive_folds':0}
    b=np.asarray([x['bps'] for x in trades],float);gp=b[b>0].sum();gl=-b[b<0].sum();pf=gp/gl if gl else (np.inf if gp else 0.)
    months=np.asarray([str(pd.Period(x['date'],freq='M')) for x in trades]);pm=sum(b[months==m].sum()>0 for m in np.unique(months));wins=b[b>0];share=wins.max()/wins.sum() if len(wins) else np.nan
    return {'trades':len(b),'pf':float(pf),'expectancy_bps':float(b.mean()),'total_bps':float(b.sum()),'win_rate':float((b>0).mean()),'positive_months':int(pm),'largest_winner_share':float(share) if np.isfinite(share) else None,'unique_days':len(set(x['date'] for x in trades))}


def eval_candidate(frames, states, rule, side, params, selection, friction):
    trades=[];per={}
    for inst,f in frames.items():
        m=rule_mask(states[inst],rule,len(f))&selection[inst]
        z=simulate(f,m,side,params,SPECS[inst]['tick'],friction);per[inst]=metrics(z);trades+=z
    m=metrics(trades);m['per_instrument']=per
    return m,trades


def objective(base,stress):
    if base['trades']<25 or stress['trades']<25:return -1e9
    if base['expectancy_bps'] is None or stress['expectancy_bps'] is None:return -1e9
    share=base['largest_winner_share'] if base['largest_winner_share'] is not None else 1.0
    return math.log(max(min(base['pf'],10),1e-6))+.55*math.log(max(min(stress['pf'],10),1e-6))+.05*base['expectancy_bps']+.03*stress['expectancy_bps']-.8*max(0,share-.25)


def train_fold(frames, fold, smoke=False):
    name,ts,te,vs,ve=fold;train={inst:((f.time>=pd.Timestamp(ts))&(f.time<pd.Timestamp(te))).to_numpy() for inst,f in frames.items()}; val={inst:((f.time>=pd.Timestamp(vs))&(f.time<pd.Timestamp(ve))).to_numpy() for inst,f in frames.items()}
    states={};cuts={}
    for inst,f in frames.items():states[inst],cuts[inst]=fit_states(f,train[inst])
    rules=beam_rules(frames,states,train,smoke=smoke); coarse=[]
    for _,rule,side,q in rules[:(8 if smoke else 30)]:
        for params in COARSE_GRID:
            b,_=eval_candidate(frames,states,rule,side,params,train,1);s,_=eval_candidate(frames,states,rule,side,params,train,2);sc=objective(b,s)
            if sc>-1e8:coarse.append((sc,rule,side,params,b,s,q))
    coarse.sort(reverse=True,key=lambda x:x[0]);refine_rules=[]
    for row in coarse[:(4 if smoke else 12)]:
        key=(row[1],row[2])
        if key not in refine_rules:refine_rules.append(key)
    refined=[]
    for rule,side in refine_rules:
      for params in (COARSE_GRID if smoke else FULL_GRID):
        b,_=eval_candidate(frames,states,rule,side,params,train,1);s,_=eval_candidate(frames,states,rule,side,params,train,2);sc=objective(b,s)
        if sc>-1e8:refined.append((sc,rule,side,params,b,s))
    refined.sort(reverse=True,key=lambda x:x[0]);top=[]
    for row in refined[:(5 if smoke else 20)]:
        sc,rule,side,params,b,s=row;vb,tb=eval_candidate(frames,states,rule,side,params,val,1);vsr,tsr=eval_candidate(frames,states,rule,side,params,val,2)
        top.append({'fold':name,'score':sc,'rule':rule,'side':side,'params':params,'train_base':b,'train_stress':s,'val_base':vb,'val_stress':vsr,'val_trades_base':tb,'val_trades_stress':tsr})
    return {'fold':fold,'states':states,'cuts':cuts,'train':train,'val':val,'top':top}


def candidate_key(row):
    return (tuple(tuple(x) for x in row['rule']),int(row['side']),tuple(row['params']))


def oof_evaluate(frames, fold_runs, candidates):
    results=[]
    for rule,side,params in candidates:
        allb=[];alls=[];fold_b=[];fold_s=[]
        for fr in fold_runs:
            b,tb=eval_candidate(frames,fr['states'],rule,side,params,fr['val'],1);s,ts=eval_candidate(frames,fr['states'],rule,side,params,fr['val'],2)
            allb+=tb;alls+=ts;fold_b.append(b);fold_s.append(s)
        mb=metrics(allb);ms=metrics(alls);positive_folds=sum((x['expectancy_bps'] or -1e9)>0 for x in fold_b);stress_positive_folds=sum((x['expectancy_bps'] or -1e9)>0 for x in fold_s)
        mb['positive_folds']=positive_folds;ms['positive_folds']=stress_positive_folds
        gate=(mb['pf']>=2.0 and mb['expectancy_bps'] is not None and mb['expectancy_bps']>0 and ms['pf']>=1.5 and ms['expectancy_bps'] is not None and ms['expectancy_bps']>0 and mb['trades']>=30 and mb['unique_days']>=15 and mb['positive_months']>=3 and positive_folds>=3 and stress_positive_folds>=3 and (mb['largest_winner_share'] is not None and mb['largest_winner_share']<=.25))
        score=objective(mb,ms)+.15*positive_folds
        results.append({'rule':rule,'side':side,'params':params,'oof_base':mb,'oof_stress':ms,'fold_base':fold_b,'fold_stress':fold_s,'gate_pass':bool(gate),'score':float(score)})
    results.sort(reverse=True,key=lambda x:(x['gate_pass'],x['score']))
    return results


def adaptive_system(fold_runs):
    base_tr=[];stress_tr=[];selections=[]
    for fr in fold_runs:
        if not fr['top']:continue
        champ=fr['top'][0];base_tr+=champ['val_trades_base'];stress_tr+=champ['val_trades_stress'];selections.append({k:v for k,v in champ.items() if not k.startswith('val_trades')})
    return {'base':metrics(base_tr),'stress':metrics(stress_tr),'selections':selections}


def jsonable(v):
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,tuple):return list(v)
    raise TypeError(type(v).__name__)


def run(data_root: Path, output: Path, smoke=False):
    t0=perf_counter();output.mkdir(parents=True,exist_ok=True);frames={};prov=[]
    for inst in SPECS:
        frames[inst],p=load_discovery(data_root,inst);prov+=p
    before={x['path']:x['sha256'] for x in prov}
    folds=FOLDS[:1] if smoke else FOLDS;fold_runs=[]
    for fold in folds:
        print('SEARCH',fold[0],flush=True);fr=train_fold(frames,fold,smoke=smoke);fold_runs.append(fr)
        print('TOP',fold[0],[(x['rule'],x['side'],x['params'],round(x['val_base']['pf'],3),round(x['val_stress']['pf'],3),x['val_base']['trades']) for x in fr['top'][:5]],flush=True)
    candidate_set=[];seen=set()
    for fr in fold_runs:
        for row in fr['top']:
            key=candidate_key(row)
            if key not in seen:seen.add(key);candidate_set.append(key)
    oof=oof_evaluate(frames,fold_runs,candidate_set);survivors=[x for x in oof if x['gate_pass']]
    adaptive=adaptive_system(fold_runs)
    after={}
    for inst in SPECS:
        for p in source_paths(data_root,inst):after[str(p.relative_to(data_root))]=sha256(p)
    if before!=after:raise RuntimeError('source hashes changed')
    manifest={'status':'SURVIVOR_FOUND' if survivors else 'NO_SURVIVOR_YET','engine_version':'autonomous-search-v1','discovery_start':str(DISCOVERY_START),'discovery_end_exclusive':str(DISCOVERY_END),'internal_confirmation_accessed':False,'true_oos_2025_accessed':False,'source_modified':False,'source_hashes_unchanged':True,'sources':prov,'folds':[x[0] for x in folds],'candidate_count':len(oof),'survivor_count':len(survivors),'elapsed_seconds':perf_counter()-t0}
    (output/'run_manifest.json').write_text(json.dumps(manifest,indent=2,default=jsonable)+'\n')
    clean_folds=[]
    for fr in fold_runs:
        clean_folds.append({'fold':fr['fold'],'cuts':fr['cuts'],'top':[{k:v for k,v in x.items() if not k.startswith('val_trades')} for x in fr['top']]})
    (output/'fold_results.json').write_text(json.dumps(clean_folds,indent=2,default=jsonable)+'\n')
    (output/'oof_candidates.json').write_text(json.dumps(oof,indent=2,default=jsonable)+'\n')
    (output/'survivors.json').write_text(json.dumps(survivors,indent=2,default=jsonable)+'\n')
    (output/'adaptive_system.json').write_text(json.dumps(adaptive,indent=2,default=jsonable)+'\n')
    report=['# Autonomous Search v1','',f"Status: **{manifest['status']}**",'',f"Candidates evaluated OOF: {len(oof)}",f"PF>=2 survivors: {len(survivors)}",'', '## Gates','BASE PF >= 2.0; STRESS PF >= 1.5; both expectancies > 0; >=30 trades; >=15 unique days; >=3 positive months; >=3 positive walk-forward folds in BASE and STRESS; largest winner <=25% of gross winners.','', '## Top OOF']
    for x in oof[:10]:report.append(f"- {x['rule']} side={x['side']} params={x['params']}: BASE PF={x['oof_base']['pf']:.3f}, exp={x['oof_base']['expectancy_bps']:.3f} bps, N={x['oof_base']['trades']}; STRESS PF={x['oof_stress']['pf']:.3f}, exp={x['oof_stress']['expectancy_bps']:.3f}; gate={x['gate_pass']}")
    report+=['','## Adaptive monthly machine',f"BASE PF={adaptive['base']['pf']:.3f}, exp={adaptive['base']['expectancy_bps']}, N={adaptive['base']['trades']}",f"STRESS PF={adaptive['stress']['pf']:.3f}, exp={adaptive['stress']['expectancy_bps']}, N={adaptive['stress']['trades']}",'','2025 not accessed. Internal confirmation not accessed. Source CSV hashes unchanged.']
    (output/'report.md').write_text('\n'.join(report)+'\n')
    return manifest,oof,adaptive

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--data-root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--smoke',action='store_true');args=ap.parse_args();m,o,a=run(args.data_root,args.output,args.smoke);print(json.dumps({'manifest':m,'top_oof':o[:3],'adaptive':a},indent=2,default=jsonable))