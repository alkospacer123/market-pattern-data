from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

DISC_END = pd.Timestamp("2026-05-16")
EVAL_START = pd.Timestamp("2026-03-02")
BLOCK_DAYS = 7
TRAIN_DAYS = 56
VALID_DAYS = 14
PROFILES = {
    "S1": (0.75, 3.0, 90), "S2": (0.75, 4.0, 120), "S3": (0.75, 5.0, 480),
    "S4": (1.00, 3.0, 90), "S5": (1.00, 4.0, 120), "S6": (1.00, 5.0, 480),
    "S7": (1.25, 3.0, 120), "S8": (1.25, 4.0, 480), "S9": (1.25, 5.0, 480),
}
PARAM_GRID = [
    {"max_leaf_nodes": a, "min_samples_leaf": b, "l2_regularization": c}
    for a in (7, 15, 31) for b in (20, 40) for c in (1.0, 10.0)
]
MODEL_CONST = {"learning_rate": 0.05, "max_iter": 120, "early_stopping": False, "random_state": 20260401}
REG_QUANTILES = (0.95, 0.975)
PROB_QUANTILE = 0.75


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c16 = mod("research/cycle16_sparse_block.py", "c16")
c18 = mod("research/cycle18_barrier_block.py", "c18")
v3 = c18.v3

# Frozen Cycle-22 execution geometry: moderate ATR stops, explicitly no 5-tick floor.
c18.PROFILES = PROFILES
c18.MIN_STOP_TICKS = 0.0


def broad_clock(ts: pd.Timestamp) -> bool:
    mins = ts.hour * 60 + ts.minute
    return 9 * 60 <= mins <= 16 * 60 + 50


# Cycle-16 feature builder delegates completed-M1 construction to Cycle-14.
# Freeze the broader Cycle-22 eligibility before any data are loaded.
c16.c14f.c14.c11.signal_clock = broad_clock


def block_bounds(i: int):
    s = EVAL_START + pd.Timedelta(days=BLOCK_DAYS * i)
    if s >= DISC_END:
        raise ValueError("block out of range")
    return s, min(s + pd.Timedelta(days=BLOCK_DAYS), DISC_END)


def stats(df: pd.DataFrame, mask: np.ndarray, pid: str, sn: str, layer: str):
    b = c18.stats(
        df.loc[mask, f"{layer}_bps_{pid}_{sn}"],
        df.loc[mask, f"{layer}_r_{pid}_{sn}"],
        df.loc[mask, "date"],
        df.loc[mask, f"target_hit_{pid}_{sn}"],
        df.loc[mask, f"raw_stop_ticks_{pid}_{sn}"],
        df.loc[mask, f"floor_active_{pid}_{sn}"],
    )
    return b


def fit_one(ip: pd.DataFrame, features: list[str], pid: str, sn: str, start: pd.Timestamp):
    ws = start - pd.Timedelta(days=TRAIN_DAYS)
    vs = start - pd.Timedelta(days=VALID_DAYS)
    yc = f"stress_r_{pid}_{sn}"
    ec = f"exit_{pid}_{sn}"
    hc = f"target_hit_{pid}_{sn}"
    old = ip[(ip.time >= ws) & (ip.time < vs) & ip[yc].notna() & (ip[ec] < vs)].copy()
    val = ip[(ip.time >= vs) & (ip.time < start) & ip[yc].notna() & (ip[ec] < start)].copy()
    full = ip[(ip.time >= ws) & (ip.time < start) & ip[yc].notna() & (ip[ec] < start)].copy()
    if len(old) < 150 or len(val) < 120 or len(full) < 300 or old[hc].nunique() < 2 or full[hc].nunique() < 2:
        return None
    Xo = c18.clean_X(old, features)
    yo = old[yc].to_numpy(float)
    co = old[hc].astype(int).to_numpy()
    Xv = c18.clean_X(val, features)
    Xf = c18.clean_X(full, features)
    yf = full[yc].to_numpy(float)
    cf = full[hc].astype(int).to_numpy()
    qualified = []
    all_diag = []
    target_r = float(PROFILES[pid][1])
    min_hit = 1.0 / (target_r + 1.0) + 0.05

    for hp in PARAM_GRID:
        reg = HistGradientBoostingRegressor(**MODEL_CONST, **hp)
        clf = HistGradientBoostingClassifier(**MODEL_CONST, **hp)
        reg.fit(Xo, yo)
        clf.fit(Xo, co)
        rp = reg.predict(Xv)
        cp = clf.predict_proba(Xv)[:, 1]
        pthr = float(np.quantile(cp, PROB_QUANTILE))
        for q in REG_QUANTILES:
            rthr = float(np.quantile(rp, q))
            mask = (rp >= rthr) & (cp >= pthr)
            b = stats(val, mask, pid, sn, "base")
            s = stats(val, mask, pid, sn, "stress")
            good = (
                s["n"] >= 12 and s["dates"] >= 5 and s["pf"] >= 1.60
                and s["expectancy_r"] is not None and s["expectancy_r"] >= 0.20
                and b["pf"] >= 2.00 and b["expectancy_r"] is not None and b["expectancy_r"] >= 0.30
                and b["expectancy_bps"] is not None and b["expectancy_bps"] > 0
                and s["expectancy_bps"] is not None and s["expectancy_bps"] > 0
                and s["target_hit_rate"] is not None and s["target_hit_rate"] >= min_hit
                and s["largest_winner_share"] is not None and s["largest_winner_share"] <= 0.40
                and s["median_stop_ticks"] is not None and s["median_stop_ticks"] >= 8.0
            )
            d = {
                "qualified": bool(good), "reg_quantile": q, "reg_threshold": float(rthr),
                "prob_threshold": pthr, "base": b, "stress": s, "minimum_hit_rate": min_hit, "hp": hp,
            }
            all_diag.append(d)
            if good:
                qualified.append(d)

    def rank(d):
        return (
            d["stress"]["expectancy_r"] if d["stress"]["expectancy_r"] is not None else -1e9,
            d["stress"]["pf"], min(d["base"]["pf"], d["stress"]["pf"]),
            d["stress"]["target_hit_rate"] or 0.0, d["stress"]["dates"],
        )

    if not qualified:
        return {"enabled": False, "diagnostic": {"profile": pid, "side": sn, "old_rows": len(old), "val_rows": len(val), "full_rows": len(full), "qualified_configs": 0, "best_unqualified": max(all_diag, key=rank)}}

    best = max(qualified, key=rank)
    reg = HistGradientBoostingRegressor(**MODEL_CONST, **best["hp"])
    clf = HistGradientBoostingClassifier(**MODEL_CONST, **best["hp"])
    reg.fit(Xf, yf)
    clf.fit(Xf, cf)
    return {
        "enabled": True, "reg": reg, "clf": clf, "reg_threshold": best["reg_threshold"],
        "prob_threshold": best["prob_threshold"],
        "diagnostic": {"profile": pid, "side": sn, "old_rows": len(old), "val_rows": len(val), "full_rows": len(full), "qualified_configs": len(qualified), "selected": best},
    }


def choose(pool: pd.DataFrame, features: list[str], models: dict, start: pd.Timestamp, end: pd.Timestamp):
    out = {"CNYRUBF": [], "USDRUBF": []}
    summary = {}
    for inst in out:
        q = pool[(pool.instrument == inst) & (pool.time >= start) & (pool.time < end)].sort_values("time")
        last = None
        counts = {}
        for _, r in q.iterrows():
            X = c18.clean_X(pd.DataFrame([r]), features)
            by = {1: [], -1: []}
            for pid, p in PROFILES.items():
                for sn, side in (("LONG", 1), ("SHORT", -1)):
                    fit = models.get((inst, pid, sn))
                    if not fit or not fit.get("enabled"):
                        continue
                    rp = float(fit["reg"].predict(X)[0])
                    cp = float(fit["clf"].predict_proba(X)[0, 1])
                    if rp >= fit["reg_threshold"] and cp >= fit["prob_threshold"] and rp >= 0.20:
                        by[side].append((rp, cp, pid, float(p[1])))
            long_ok, short_ok = bool(by[1]), bool(by[-1])
            if long_ok and short_ok:
                last = None
                continue
            if not long_ok and not short_ok:
                last = None
                continue
            side = 1 if long_ok else -1
            if last == side:
                continue
            rp, cp, pid, tr = max(by[side], key=lambda z: (z[0], z[1], z[3]))
            fit = models[(inst, pid, "LONG" if side == 1 else "SHORT")]
            out[inst].append({
                "signal_index": int(r.signal_index), "signal_time": str(r.time), "side": side, "profile": pid,
                "predicted_base_r": rp, "predicted_stress_r": rp, "predicted_hit_probability": cp,
                "reg_threshold": fit["reg_threshold"], "prob_threshold": fit["prob_threshold"],
            })
            counts[pid] = counts.get(pid, 0) + 1
            last = side
        summary[inst] = {"state_onsets": len(out[inst]), "profiles": counts}
    return out, summary


def execute(f, m1, signals, inst, friction_ticks):
    trades = c18.execute(f, m1, signals, inst, friction_ticks)
    for t in trades:
        t["predicted_stress_r"] = t.pop("predicted_base_r", None)
    return trades


def run(root: Path, out: Path, index: int):
    start, end = block_bounds(index)
    out.mkdir(parents=True, exist_ok=True)
    contexts, pool, features, prov = c16.combine_features(root)
    # Defensive full-session check: Cycle-22 pool must actually include the expanded hours.
    hours = sorted(set(pd.to_datetime(pool.time).dt.hour.tolist()))
    if not set(range(9, 17)).issubset(set(hours)):
        raise RuntimeError(f"Cycle22 broad-session feature pool incomplete: hours={hours}")
    pool = c18.add_labels(pool, contexts)
    models = {}
    diag = []
    for inst in ("CNYRUBF", "USDRUBF"):
        ip = pool[pool.instrument.eq(inst)].copy()
        for pid in PROFILES:
            for sn in ("LONG", "SHORT"):
                fit = fit_one(ip, features, pid, sn, start)
                models[(inst, pid, sn)] = fit
                if fit:
                    d = dict(fit["diagnostic"])
                    d["instrument"] = inst
                    diag.append(d)
    sigs, summary = choose(pool, features, models, start, end)
    inst_rows = []
    for inst, (f, m1) in contexts.items():
        g = execute(f, m1, sigs[inst], inst, 0)
        b = execute(f, m1, sigs[inst], inst, 1)
        s = execute(f, m1, sigs[inst], inst, 2)
        inst_rows.append({"instrument": inst, "signals": sigs[inst], "gross_trades": g, "base_trades": b, "stress_trades": s, "gross": v3.metrics(g), "base": v3.metrics(b), "stress": v3.metrics(s)})
    res = {
        "engine": "cycle22-stress-first-cost-margin-v1", "block_index": index,
        "block_start": str(start), "block_end_exclusive": str(end),
        "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False,
        "commission_excluded": True, "feature_count": len(features), "profiles": PROFILES,
        "reg_quantiles": REG_QUANTILES, "prob_quantile": PROB_QUANTILE,
        "model_diagnostics": diag, "prediction_summary": summary, "instruments": inst_rows, "provenance": prov,
    }
    (out / "block_result.json").write_text(json.dumps(res, indent=2, default=v3.jsonable) + "\n")
    print(json.dumps({"block": index, "features": len(features), "enabled_models": sum(1 for x in models.values() if x and x.get("enabled")), "summary": summary}, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=Path("."))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--block-index", type=int, required=True)
    a = p.parse_args()
    run(a.data_root, a.output, a.block_index)
