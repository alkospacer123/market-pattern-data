from __future__ import annotations
import argparse, importlib.util, math
from pathlib import Path

SPEC=importlib.util.spec_from_file_location("cycle4","research/autonomous_search_v4_events.py")
v4=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(v4)
e=v4.load_engine()

def score_train_fixed(base_trades, stress_trades, effect):
    mb=e.metrics(base_trades);ms=e.metrics(stress_trades)
    if mb["trades"]<18 or ms["trades"]<18:
        return -1e9
    if mb["expectancy_bps"] is None or ms["expectancy_bps"] is None:
        return -1e9
    return (
        math.log(max(min(mb["pf"],10),1e-6))
        + .55*math.log(max(min(ms["pf"],10),1e-6))
        + .04*mb["expectancy_bps"]
        + .025*ms["expectancy_bps"]
        + .25*effect["score"]
    )

# Technical hotfix only: same formula, now with the execution engine explicitly bound.
v4.score_train=score_train_fixed

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--data-root",type=Path,default=Path("."))
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--instrument",choices=["CNYRUBF","USDRUBF"],required=True)
    ap.add_argument("--timeframe",choices=["M1","M5"],required=True)
    a=ap.parse_args()
    v4.run_context(a.data_root,a.output,a.instrument,a.timeframe)
