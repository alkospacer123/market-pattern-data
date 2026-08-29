from __future__ import annotations
import argparse, importlib.util
from pathlib import Path
import numpy as np
import pandas as pd

spec=importlib.util.spec_from_file_location('c14','research/cycle14_m1_micro_block.py')
c14=importlib.util.module_from_spec(spec);spec.loader.exec_module(c14)


def build_dataset_fast(root:Path,inst:str):
    f,m1,_,prov=c14.c11.load_context(root,inst);f=c14.c11.add_labels(f,m1,inst)
    times_ns=m1.time.to_numpy(dtype='datetime64[ns]').astype(np.int64);idxmap={int(t):i for i,t in enumerate(times_ns)}
    dates=m1.date.to_numpy();op=m1.open.to_numpy(float);hi=m1.high.to_numpy(float);lo=m1.low.to_numpy(float);cl=m1.close.to_numpy(float);vol=m1.volume.to_numpy(float)
    rows=[]
    for i,r in f.iterrows():
        if not c14.c11.signal_clock(r.time):continue
        atr=float(r.atr14)
        if not np.isfinite(atr) or atr<=0:continue
        last_time=pd.Timestamp(r.time)+pd.Timedelta(minutes=4);li=idxmap.get(int(last_time.value))
        if li is None:continue
        micro={};ok=True
        for n in c14.WINDOWS:
            si=li-n+1
            if si<0 or dates[si]!=dates[li]:ok=False;break
            # Exact contiguous minute timestamps.
            if int(times_ns[li]-times_ns[si]) != (n-1)*60_000_000_000:ok=False;break
            cc=cl[si:li+1];oo=op[si:li+1];hh=hi[si:li+1];ll=lo[si:li+1];vv=vol[si:li+1]
            d=np.diff(cc);sg=np.sign(d);absd=np.abs(d);net=cc[-1]-oo[0];path=absd.sum();rms=float(np.sqrt(np.mean(d*d))) if len(d) else 0.0;hr=float(hh.max()-ll.min());den=max(hr,1e-12);half=max(1,n//2);first_ret=cc[half-1]-oo[0];second_ret=cc[-1]-oo[half] if half<n else 0.0;vm=float(np.median(vv));vmean=float(np.mean(vv));vstd=float(np.std(vv));pv=d*vv[1:] if len(d) else np.array([]);pvden=float(np.abs(pv).sum());p=f'm{n}_'
            micro[p+'net_atr']=net/atr;micro[p+'abs_path_atr']=path/atr;micro[p+'rms_atr']=rms/atr;micro[p+'eff']=abs(net)/path if path>1e-12 else 0.0;micro[p+'frac_pos']=float(np.mean(sg>0)) if len(sg) else 0.0;micro[p+'frac_neg']=float(np.mean(sg<0)) if len(sg) else 0.0;micro[p+'sign_change']=float(np.mean(sg[1:]!=sg[:-1])) if len(sg)>1 else 0.0;micro[p+'run_pos']=c14.longest_run(sg,1);micro[p+'run_neg']=c14.longest_run(sg,-1);micro[p+'close_pos']=(cc[-1]-ll.min())/den;micro[p+'range_atr']=hr/atr;micro[p+'max_abs_atr']=(absd.max()/atr) if len(absd) else 0.0;micro[p+'last_ret_atr']=(d[-1]/atr) if len(d) else 0.0;micro[p+'half_diff_atr']=(first_ret-second_ret)/atr;micro[p+'last_vol_med']=vv[-1]/vm if vm>0 else np.nan;micro[p+'vol_cv']=vstd/vmean if vmean>0 else np.nan;micro[p+'max_vol_share']=float(vv.max()/vv.sum()) if vv.sum()>0 else np.nan;micro[p+'pv_imbalance']=float(pv.sum()/pvden) if pvden>0 else 0.0
        if not ok:continue
        row={'time':r.time,'date':r.date,'instrument':inst,'signal_index':int(i),'inst_flag':0.0 if inst=='CNYRUBF' else 1.0};row.update(micro);mins=r.time.hour*60+r.time.minute;row['tod_sin']=float(np.sin(2*np.pi*mins/1440));row['tod_cos']=float(np.cos(2*np.pi*mins/1440))
        for feat in ('ret_5m_atr','body_atr','range_atr','close_pos_candle','dist_pdh_atr','dist_pdl_atr','round_dist_atr','session_pos'):row['ctx_'+feat]=r[feat]
        for pid in c14.PROFILES:
            for side in ('LONG','SHORT'):
                row[f'label_{pid}_{side}']=f[f'label_{pid}_{side}'].iloc[i];row[f'exit_{pid}_{side}']=f[f'exit_{pid}_{side}'].iloc[i]
        rows.append(row)
    return f,m1,pd.DataFrame(rows),prov

c14.build_dataset=build_dataset_fast

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--data-root',type=Path,default=Path('.'));a.add_argument('--output',type=Path,required=True);a.add_argument('--block-index',type=int,required=True);z=a.parse_args();c14.run(z.data_root,z.output,z.block_index)
