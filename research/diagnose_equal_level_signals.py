from pathlib import Path
import importlib.util
import pandas as pd

spec=importlib.util.spec_from_file_location('v3','research/autonomous_search_v3.py')
v3=importlib.util.module_from_spec(spec);spec.loader.exec_module(v3)
f,_=v3.load_prefix(Path('.'),'CNYRUBF','M5')
checks=[
 ('2026-01-12 11:20','SHORT',11.60),
 ('2026-01-15 10:25','LONG',11.45),
 ('2026-02-06 11:55','LONG',11.20),
 ('2026-03-16 10:25','SHORT',11.70),
]
for ts,side,level in checks:
    t=pd.Timestamp(ts);i=f.index[f.time==t]
    print('\n===',ts,side,'LEVEL',level,'===')
    if len(i)==0:
        print('MISSING');continue
    i=int(i[0]);print(f.loc[max(0,i-5):i+2,['time','open','high','low','close','volume']].to_string(index=False))
    print('last two highs',f.loc[i-1:i,'high'].tolist(),'last two lows',f.loc[i-1:i,'low'].tolist())
    print('current high/low',f.loc[i,'high'],f.loc[i,'low'],'prev high/low',f.loc[i-1,'high'],f.loc[i-1,'low'])
