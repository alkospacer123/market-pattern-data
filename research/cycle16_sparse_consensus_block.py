from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

DISC_END=pd.Timestamp('2026-05-16'); EVAL_START=pd.Timestamp('2026-03-02'); BLOCK_DAYS=7; TRAIN_DAYS=56; VALID_DAYS=14
PROFILES={'P1':(0.75,1.5,30),'P2':(1.00,2.0,60),'P3':(1.25,2.0,60),'P4':(1.50,3.0,120)}
PARAM_GRID=[{'max_leaf_nodes':a,'min_samples_leaf':b,'l2_regularization':c} for a in (7,15,31) for b in (20,50) for c in (1.0,10.0)]
MODEL_CONST={'learning_rate':0.05,'max_iter':120,'early_stopping':False,'random_state':1616}
MICRO_WINDOWS=(5,15,30); CROSS_H=(5,15,30,60)

def mod(path,name):
    s=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
v3=mod('research/autonomous_search_v3.py','v3'); c11=mod('research/cycle11_nonlinear_pnl_block.py','c11')

def block_bounds(i):
    s=EVAL_START+pd.Timedelta(days=BLOCK_DAYS*i)
    if s>=DISC_END: raise ValueError('block out of range')
    return s,min(s+pd.Timedelta(days=BLOCK_DAYS),DISC_END)

def longest_run(signs,val):
    best=cur=0
    for x in signs:
        if x==val: cur+=1; best=max(best,cur)
        else: cur=0
    return best

def micro_for_bar(m1,end_time,atr):
    last=pd.Timestamp(end_time)+pd.Timedelta(minutes=4); out={}
    if not np.isfinite(atr) or atr<=0: return None
    for n in MICRO_WINDOWS:
        first=last-pd.Timedelta(minutes=n-1); w=m1[(m1.time>=first)&(m1.time<=last)].copy()
        if len(w)!=n or w.date.nunique()!=1: return None
        tt=w.time.tolist()
        if any(tt[k]-tt[k-1]!=pd.Timedelta(minutes=1) for k in range(1,len(tt))): return None
        close=w.close.to_numpy(float); op=w.open.to_numpy(float); high=w.high.to_numpy(float); low=w.low.to_numpy(float); vol=w.volume.to_numpy(float)
        d=np.diff(close); sg=np.sign(d); absd=np.abs(d); net=close[-1]-op[0]; path=absd.sum(); rms=float(np.sqrt(np.mean(d*d))) if len(d) else 0.0; hr=float(high.max()-low.min())
        denom=max(hr,1e-12); half=max(1,n//2); first_ret=close[half-1]-op[0]; second_ret=close[-1]-op[half] if half<n else 0.0
        vm=float(np.median(vol)); vmean=float(np.mean(vol)); vstd=float(np.std(vol)); pv=d*vol[1:] if len(d) else np.array([]); pvden=float(np.abs(pv).sum()); p=f'm{n}_'
        out[p+'net_atr']=net/atr; out[p+'abs_path_atr']=path/atr; out[p+'rms_atr']=rms/atr; out[p+'eff']=abs(net)/path if path>1e-12 else 0.0
        out[p+'frac_pos']=float(np.mean(sg>0)) if len(sg) else 0.0; out[p+'frac_neg']=float(np.mean(sg<0)) if len(sg) else 0.0; out[p+'sign_change']=float(np.mean(sg[1:]!=sg[:-1])) if len(sg)>1 else 0.0
        out[p+'run_pos']=longest_run(sg,1); out[p+'run_neg']=longest_run(sg,-1); out[p+'close_pos']=(close[-1]-low.min())/denom; out[p+'range_atr']=hr/atr
        out[p+'max_abs_atr']=(absd.max()/atr) if len(absd) else 0.0; out[p+'last_ret_atr']=(d[-1]/atr) if len(d) else 0.0; out[p+'half_diff_atr']=(first_ret-second_ret)/atr
        out[p+'last_vol_med']=vol[-1]/vm if vm>0 else np.nan; out[p+'vol_cv']=vstd/vmean if vmean>0 else np.nan; out[p+'max_vol_share']=float(vol.max()/vol.sum()) if vol.sum()>0 else np.nan; out[p+'pv_imbalance']=float(pv.sum()/pvden) if pvden>0 else 0.0
    return out

def add_base_stress_labels(f,m1,inst):
    eligible=np.array([c11.signal_clock(t) for t in f.time],dtype=bool); tick=float(v3.SPECS[inst]['tick'])
    for pid,p in PROFILES.items():
        for side,name in ((1,'LONG'),(-1,'SHORT')):
            yb=np.full(len(f),np.nan); ys=np.full(len(f),np.nan); ex=np.full(len(f),np.datetime64('NaT'),dtype='datetime64[ns]')
            for i in np.flatnonzero(eligible):
                r=c11.isolated_trade(f,m1,int(i),inst,side,p,1)
                if r is None: continue
                yb[i]=r['bps']; ys[i]=r['bps']-(20000.0*tick/float(r['raw_entry'])); ex[i]=np.datetime64(r['exit_time'])
            f[f'base_{pid}_{name}']=yb; f[f'stress_{pid}_{name}']=ys; f[f'exit_{pid}_{name}']=ex
    f['eligible_clock']=eligible; return f

def load_context(root,inst):
    f,m1,base_feats,prov=c11.load_context(root,inst)
    if f.time.max()>=DISC_END or m1.time.max()>=DISC_END: raise PermissionError('Cycle16 fence violation')
    f=add_base_stress_labels(f,m1,inst); rows=[]
    for i,r in f.iterrows():
        if not bool(r.eligible_clock): continue
        micro=micro_for_bar(m1,r.time,float(r.atr14))
        if micro is None: continue
        row={'time':r.time,'date':r.date,'instrument':inst,'signal_index':int(i),'inst_flag':0.0 if inst=='CNYRUBF' else 1.0}
        for feat in base_feats:
            if feat!='inst_flag': row['ctx_'+feat]=r[feat]
        row.update(micro)
        for pid in PROFILES:
            for side in ('LONG','SHORT'):
                row[f'base_{pid}_{side}']=r[f'base_{pid}_{side}']; row[f'stress_{pid}_{side}']=r[f'stress_{pid}_{side}']; row[f'exit_{pid}_{side}']=r[f'exit_{pid}_{side}']
        rows.append(row)
    return f,m1,pd.DataFrame(rows),prov

def add_cross(cny,usd):
    cm=cny.set_index('time'); um=usd.set_index('time'); common=cm.index.intersection(um.index).sort_values(); a=cm.loc[common].copy(); b=um.loc[common].copy(); x=pd.DataFrame({'time':common})
    for h in CROSS_H:
        ca=pd.to_numeric(a['ctx_ret_%dm_atr'%h],errors='coerce').to_numpy(); ub=pd.to_numeric(b['ctx_ret_%dm_atr'%h],errors='coerce').to_numpy(); x[f'x_ret_diff_{h}m']=ca-ub; x[f'x_sign_agree_{h}m']=np.where(np.isfinite(ca)&np.isfinite(ub),np.sign(ca)*np.sign(ub),np.nan)
    c=pd.to_numeric(a['ctx_ret_5m_atr'],errors='coerce').reset_index(drop=True); u=pd.to_numeric(b['ctx_ret_5m_atr'],errors='coerce').reset_index(drop=True); cs=c.shift(1); us=u.shift(1)
    x['x_corr_prior_12']=cs.rolling(12,min_periods=8).corr(us); x['x_corr_prior_36']=cs.rolling(36,min_periods=20).corr(us); cov=cs.rolling(36,min_periods=20).cov(us); var=us.rolling(36,min_periods=20).var(); x['x_beta_prior_36']=cov/var.replace(0,np.nan); x['x_residual_current']=c-x['x_beta_prior_36']*u
    cross_cols=[c for c in x.columns if c!='time']; return cny.merge(x,on='time',how='left'),usd.merge(x,on='time',how='left'),cross_cols

def feat_cols(df,cross_cols):
    cols=[c for c in df.columns if c.startswith('ctx_') or c.startswith('m')]; cols+=list(cross_cols)+['inst_flag']; return sorted(set(cols))
def clean_X(df,cols):
    X=df[cols].apply(pd.to_numeric,errors='coerce').to_numpy(dtype=float,copy=True); X[~np.isfinite(X)]=np.nan; return X
def pf_exp(y):
    y=np.asarray(y,float); y=y[np.isfinite(y)]
    if not len(y): return 0.0,None
    gp=y[y>0].sum(); gl=-y[y<0].sum(); return (float(gp/gl) if gl else (float('inf') if gp else 0.0)),float(y.mean())
def winner_share(y):
    y=np.asarray(y,float); y=y[np.isfinite(y)]; pos=y[y>0]
    return None if not len(pos) else float(pos.max()/pos.sum())
def pos(x): return x is not None and x>0

def fit_model(ds,cols,target,pid,side,start):
    ws=start-pd.Timedelta(days=TRAIN_DAYS); vs=start-pd.Timedelta(days=VALID_DAYS); bc=f'base_{pid}_{side}'; sc=f'stress_{pid}_{side}'; ec=f'exit_{pid}_{side}'
    old=ds[(ds.instrument==target)&(ds.time>=ws)&(ds.time<vs)&ds[bc].notna()&(ds[ec]<vs)].copy(); val=ds[(ds.instrument==target)&(ds.time>=vs)&(ds.time<start)&ds[bc].notna()&(ds[ec]<start)].copy(); full=ds[(ds.instrument==target)&(ds.time>=ws)&(ds.time<start)&ds[bc].notna()&(ds[ec]<start)].copy()
    if len(old)<100 or len(val)<12 or len(full)<150: return None
    Xo=clean_X(old,cols); yo=old[bc].to_numpy(float); Xv=clean_X(val,cols); yvb=val[bc].to_numpy(float); yvs=val[sc].to_numpy(float); Xf=clean_X(full,cols); yf=full[bc].to_numpy(float); candidates=[]
    for hp in PARAM_GRID:
        m=HistGradientBoostingRegressor(**MODEL_CONST,**hp); m.fit(Xo,yo); p=m.predict(Xv); q=float(np.quantile(p,.95)); sel=p>=q; tb=yvb[sel]; ts=yvs[sel]; dates=val.date.to_numpy()[sel]
        bpf,bex=pf_exp(tb); spf,sex=pf_exp(ts); wsx=winner_share(tb); nd=len(set(dates.tolist())); qualified=(len(tb)>=12 and bpf>=2.0 and spf>=1.3 and pos(bex) and pos(sex) and nd>=4 and wsx is not None and wsx<=0.35); rank=(min(bpf,spf),sex if sex is not None else -1e9,nd) if qualified else None
        candidates.append({'hp':hp,'p95':q,'tail_n':int(len(tb)),'base_pf':bpf,'stress_pf':spf,'base_exp':bex,'stress_exp':sex,'dates':nd,'largest_base_winner_share':wsx,'qualified':qualified,'rank':rank})
    qualified=[z for z in candidates if z['qualified']]
    if not qualified:
        return {'disabled':True,'diag':{'target':target,'profile':pid,'side':side,'old_rows':len(old),'validation_rows':len(val),'full_rows':len(full),'qualified_count':0,'best_unqualified':max(candidates,key=lambda z:(min(z['base_pf'],z['stress_pf']),z['stress_exp'] if z['stress_exp'] is not None else -1e9))}}
    best=max(qualified,key=lambda z:z['rank']); model=HistGradientBoostingRegressor(**MODEL_CONST,**best['hp']); model.fit(Xf,yf)
    return {'disabled':False,'model':model,'threshold':float(best['p95']),'diag':{'target':target,'profile':pid,'side':side,'old_rows':len(old),'validation_rows':len(val),'full_rows':len(full),'qualified_count':len(qualified),'selected':{k:v for k,v in best.items() if k!='rank'}}}

def choose_signals(ds,cols,models,start,end):
    out={'CNYRUBF':[],'USDRUBF':[]}; summary={}
    for target in out:
        q=ds[(ds.instrument==target)&(ds.time>=start)&(ds.time<end)].sort_values('time'); last_state=None; counts={}
        for _,r in q.iterrows():
            X=clean_X(pd.DataFrame([r]),cols); dirs={1:[],-1:[]}
            for side_name,side in (('LONG',1),('SHORT',-1)):
                for pid in PROFILES:
                    fit=models.get((target,pid,side_name))
                    if not fit or fit.get('disabled'): continue
                    pred=float(fit['model'].predict(X)[0]); thr=float(fit['threshold'])
                    if pred>=thr: dirs[side].append((pred,pid,thr))
            lok=len(dirs[1])>=2; sok=len(dirs[-1])>=2
            state=None if (lok==sok) else ((1,tuple(sorted(x[1] for x in dirs[1]))) if lok else (-1,tuple(sorted(x[1] for x in dirs[-1]))))
            if state is None: last_state=None; continue
            side=state[0]; pred,pid,thr=max(dirs[side],key=lambda z:z[0])
            if state!=last_state:
                out[target].append({'signal_index':int(r.signal_index),'signal_time':str(r.time),'side':side,'profile':pid,'predicted_base_bps':pred,'threshold':thr,'consensus_profiles':list(state[1]),'consensus_size':len(state[1])}); counts[pid]=counts.get(pid,0)+1
            last_state=state
        summary[target]={'state_onsets':len(out[target]),'profiles':counts}
    return out,summary

def run(root,out,index):
    start,end=block_bounds(index); out.mkdir(parents=True,exist_ok=True); contexts={}; frames=[]; prov=[]
    for inst in ('CNYRUBF','USDRUBF'):
        f,m1,ds,p=load_context(root,inst); contexts[inst]=(f,m1); frames.append(ds); prov+=p
    cny,usd,cross_cols=add_cross(frames[0],frames[1]); pool=pd.concat([cny,usd],ignore_index=True,sort=False); cols=feat_cols(pool,cross_cols); models={}; diags=[]
    for target in ('CNYRUBF','USDRUBF'):
        for pid in PROFILES:
            for side in ('LONG','SHORT'):
                fit=fit_model(pool,cols,target,pid,side,start); models[(target,pid,side)]=fit
                if fit: diags.append(fit['diag'])
    sigs,summary=choose_signals(pool,cols,models,start,end); inst=[]
    for target,(f,m1) in contexts.items():
        g=c11.execute_mixed(f,m1,sigs[target],target,0); b=c11.execute_mixed(f,m1,sigs[target],target,1); s=c11.execute_mixed(f,m1,sigs[target],target,2); inst.append({'instrument':target,'signals':sigs[target],'gross_trades':g,'base_trades':b,'stress_trades':s,'gross':v3.metrics(g),'base':v3.metrics(b),'stress':v3.metrics(s)})
    result={'engine':'cycle16-sparse-consensus-v1','block_index':index,'block_start':str(start),'block_end_exclusive':str(end),'retired_internal_confirmation_accessed':False,'true_oos_2025_accessed':False,'commission_excluded':True,'feature_count':len(cols),'model_diagnostics':diags,'prediction_summary':summary,'instruments':inst,'provenance':prov}
    (out/'block_result.json').write_text(json.dumps(result,indent=2,default=v3.jsonable)+'\n'); print(json.dumps({'block':index,'features':len(cols),'qualified_models':sum(not models[k].get('disabled') for k in models if models[k]),'summary':summary},indent=2))
if __name__=='__main__':
    a=argparse.ArgumentParser(); a.add_argument('--data-root',type=Path,default=Path('.')); a.add_argument('--output',type=Path,required=True); a.add_argument('--block-index',type=int,required=True); z=a.parse_args(); run(z.data_root,z.output,z.block_index)
