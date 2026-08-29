from __future__ import annotations
import argparse, importlib.util
from pathlib import Path
from typing import Any
import numpy as np

spec=importlib.util.spec_from_file_location("cycle9","research/cycle9_equal_level_breakout.py")
c9=importlib.util.module_from_spec(spec);spec.loader.exec_module(c9)

# Technical clarification fixed before Cycle 9 results:
# if one breakout bar qualifies in both directions, skip the bar as ambiguous.
def generate_signals_deterministic(m5,inst:str,variant:dict[str,int])->list[dict[str,Any]]:
    tick=float(c9.v3.SPECS[inst]["tick"]);step=float(c9.v3.SPECS[inst]["round_step"])
    tol=variant["touch_tolerance_ticks"]*tick+1e-12;lb=int(variant["touch_lookback_bars"]);confirm=variant["breakout_confirm_ticks"]*tick
    signals=[];upper_hist={};lower_hist={};triggered_upper=set();triggered_lower=set();current_key=None
    for i,row in m5.iterrows():
        sid=c9.session_id(row.time)
        if sid==0:
            current_key=None;upper_hist={};lower_hist={};triggered_upper=set();triggered_lower=set();continue
        key=(row.date,sid)
        if key!=current_key:
            current_key=key;upper_hist={};lower_hist={};triggered_upper=set();triggered_lower=set()
        lo_idx=i-lb
        for d in (upper_hist,lower_hist):
            for lev in list(d):
                d[lev]=[j for j in d[lev] if j>=lo_idx]
                if not d[lev]:del d[lev]
        armed_up=[lev for lev,hist in upper_hist.items() if len(hist)>=2 and lev not in triggered_upper and row.close>=lev+confirm-1e-12]
        armed_dn=[lev for lev,hist in lower_hist.items() if len(hist)>=2 and lev not in triggered_lower and row.close<=lev-confirm+1e-12]
        if armed_up and armed_dn:
            pass
        elif armed_up:
            lev=max(armed_up)
            signals.append({"signal_index":int(i),"signal_time":str(row.time),"side":1,"level":float(lev),"session":sid,"touches":list(upper_hist[lev])})
            triggered_upper.add(lev)
        elif armed_dn:
            lev=min(armed_dn)
            signals.append({"signal_index":int(i),"signal_time":str(row.time),"side":-1,"level":float(lev),"session":sid,"touches":list(lower_hist[lev])})
            triggered_lower.add(lev)
        hlev=c9.nearest_round(float(row.high),step)
        if abs(float(row.high)-hlev)<=tol:upper_hist.setdefault(hlev,[]).append(int(i))
        llev=c9.nearest_round(float(row.low),step)
        if abs(float(row.low)-llev)<=tol:lower_hist.setdefault(llev,[]).append(int(i))
    signals.sort(key=lambda z:(z["signal_time"],-z["side"]))
    return signals

c9.generate_signals=generate_signals_deterministic

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--data-root",type=Path,default=Path("."));ap.add_argument("--output",type=Path,required=True);a=ap.parse_args();c9.run(a.data_root,a.output)
