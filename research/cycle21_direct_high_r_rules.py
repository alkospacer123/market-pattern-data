from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp("2026-01-05")
JAN_END = pd.Timestamp("2026-02-01")
DISCOVERY_END = pd.Timestamp("2026-03-01")
FORWARD_END = pd.Timestamp("2026-05-16")
PROFILES = {
    "R1": (0.50, 4.0, 90),
    "R2": (0.50, 5.0, 120),
    "R3": (0.50, 6.0, 120),
    "R4": (0.75, 4.0, 90),
    "R5": (0.75, 5.0, 120),
    "R6": (0.75, 6.0, 120),
}
STATE_NAMES = ("LOW10", "LOW25", "HIGH25", "HIGH10")
BOOTSTRAP_SEED = 20260401
BOOTSTRAP_REPS = 1000


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


v3 = mod("research/autonomous_search_v3.py", "v3")
c18 = mod("research/cycle18_barrier_block.py", "c18")


def jsonable(v):
    if isinstance(v, np.generic):
        return v.item()
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (pd.Timestamp, pd.Period)):
        return str(v)
    raise TypeError(type(v).__name__)


def session_mask(f: pd.DataFrame) -> np.ndarray:
    mins = (f.time.dt.hour * 60 + f.time.dt.minute).to_numpy()
    return (mins >= 9 * 60) & (mins <= 16 * 60 + 50)


def load_context(root: Path, inst: str):
    m5raw, p5 = v3.load_prefix(root, inst, "M5")
    m1, p1 = v3.load_prefix(root, inst, "M1")
    f, features = v3.build_features(m5raw, inst, "M5")
    numeric = []
    for feat in features:
        if feat == "clock_bucket" or feat.startswith("fwd_"):
            continue
        x = pd.to_numeric(f[feat], errors="coerce")
        if x.notna().sum() >= 100:
            numeric.append(feat)
    if f.time.max() >= FORWARD_END or m1.time.max() >= FORWARD_END:
        raise PermissionError("Cycle21 data fence violated")
    return f, m1, numeric, p5 + p1


def fit_state_masks(f: pd.DataFrame, numeric: list[str]):
    jan = ((f.time >= DISC_START) & (f.time < JAN_END)).to_numpy()
    masks: dict[tuple[str, str], np.ndarray] = {}
    cuts = {}
    for feat in numeric:
        vals = pd.to_numeric(f[feat], errors="coerce").to_numpy(float)
        train = vals[jan & np.isfinite(vals)]
        if len(train) < 100:
            continue
        q10, q25, q75, q90 = [float(x) for x in np.quantile(train, [0.10, 0.25, 0.75, 0.90])]
        cuts[feat] = [q10, q25, q75, q90]
        finite = np.isfinite(vals)
        masks[(feat, "LOW10")] = finite & (vals <= q10)
        masks[(feat, "LOW25")] = finite & (vals <= q25)
        masks[(feat, "HIGH25")] = finite & (vals >= q75)
        masks[(feat, "HIGH10")] = finite & (vals >= q90)
    hour = f.time.dt.hour.to_numpy()
    for h in range(9, 17):
        masks[("clock_hour", f"H{h:02d}")] = hour == h
    return masks, cuts


def canonical_rule(parts: tuple[tuple[str, str], ...]) -> str:
    return "&".join(f"{a}:{b}" for a, b in sorted(parts))


def mask_digest(mask: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(mask.astype(np.uint8)).tobytes()).hexdigest()


def build_rules(f: pd.DataFrame, states: dict[tuple[str, str], np.ndarray]):
    eligible = session_mask(f)
    janfeb = ((f.time >= DISC_START) & (f.time < DISCOVERY_END)).to_numpy()
    keys = sorted(states)
    rules = []
    for key in keys:
        rid = canonical_rule((key,))
        rules.append({"rule_id": rid, "parts": (key,), "mask": states[key].copy(), "depth": 1})

    pairs = []
    for i in range(len(keys)):
        a = keys[i]
        for j in range(i + 1, len(keys)):
            b = keys[j]
            if a[0] == b[0]:
                continue
            m = states[a] & states[b]
            if int((m & eligible & janfeb).sum()) < 20:
                continue
            rid = canonical_rule((a, b))
            rank = hashlib.sha256(rid.encode("utf-8")).hexdigest()
            pairs.append((rank, rid, a, b, m))
    pairs.sort(key=lambda z: (z[0], z[1]))
    for _, rid, a, b, m in pairs[:1500]:
        rules.append({"rule_id": rid, "parts": (a, b), "mask": m, "depth": 2})

    # Exact-mask dedupe is deterministic and happens before any outcome evaluation.
    seen = set()
    unique = []
    for r in sorted(rules, key=lambda x: (x["depth"], x["rule_id"])):
        d = mask_digest(r["mask"] & eligible)
        if d in seen:
            continue
        seen.add(d)
        r["mask_digest"] = d
        unique.append(r)
    return unique, {"univariate_count": len(keys), "eligible_pair_count": len(pairs), "retained_pair_cap": min(1500, len(pairs)), "unique_rule_masks": len(unique)}


def onsets(f: pd.DataFrame, mask: np.ndarray) -> np.ndarray:
    active = mask & session_mask(f)
    prev = np.r_[False, active[:-1]]
    same = np.r_[False, f.date.to_numpy()[1:] == f.date.to_numpy()[:-1]]
    return active & ~(prev & same)


def make_outcomes(f: pd.DataFrame, m1: pd.DataFrame, inst: str):
    eligible = session_mask(f)
    idx = np.flatnonzero(eligible)
    n = len(f)
    out = {}
    for pid, profile in PROFILES.items():
        for side_name, side in (("LONG", 1), ("SHORT", -1)):
            cols = {
                "gross_bps": np.full(n, np.nan),
                "base_bps": np.full(n, np.nan),
                "stress_bps": np.full(n, np.nan),
                "gross_r": np.full(n, np.nan),
                "base_r": np.full(n, np.nan),
                "stress_r": np.full(n, np.nan),
                "target_hit": np.zeros(n, dtype=bool),
                "raw_stop_ticks": np.full(n, np.nan),
                "floor_active": np.zeros(n, dtype=bool),
            }
            for i in idx:
                raw = c18.raw_trade(f, m1, int(i), inst, side, profile)
                if raw is None:
                    continue
                gb = float(raw["gross_bps"])
                gr = gb / float(raw["risk_bps"])
                bb, br = c18.frictionize(raw, inst, 1)
                sb, sr = c18.frictionize(raw, inst, 2)
                cols["gross_bps"][i] = gb
                cols["base_bps"][i] = bb
                cols["stress_bps"][i] = sb
                cols["gross_r"][i] = gr
                cols["base_r"][i] = br
                cols["stress_r"][i] = sr
                cols["target_hit"][i] = bool(raw["target_hit"])
                cols["raw_stop_ticks"][i] = float(raw["raw_stop_ticks"])
                cols["floor_active"][i] = bool(raw["floor_active"])
            out[(pid, side_name)] = cols
    return out


def stats_for(ix: np.ndarray, cols: dict[str, np.ndarray], f: pd.DataFrame, layer: str):
    if len(ix) == 0:
        return {"n": 0, "pf": 0.0, "expectancy_bps": None, "expectancy_r": None, "dates": 0, "largest_winner_share": None, "target_hit_rate": None, "total_bps": 0.0}
    b = cols[f"{layer}_bps"][ix]
    r = cols[f"{layer}_r"][ix]
    valid = np.isfinite(b) & np.isfinite(r)
    b = b[valid]
    r = r[valid]
    j = ix[valid]
    if len(b) == 0:
        return {"n": 0, "pf": 0.0, "expectancy_bps": None, "expectancy_r": None, "dates": 0, "largest_winner_share": None, "target_hit_rate": None, "total_bps": 0.0}
    gp = float(b[b > 0].sum())
    gl = float(-b[b < 0].sum())
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0.0)
    wins = b[b > 0]
    share = float(wins.max() / wins.sum()) if len(wins) else None
    return {
        "n": int(len(b)), "pf": float(pf), "expectancy_bps": float(b.mean()), "expectancy_r": float(r.mean()),
        "dates": int(f.date.iloc[j].nunique()), "largest_winner_share": share,
        "target_hit_rate": float(cols["target_hit"][j].mean()), "total_bps": float(b.sum()),
    }


def month_stats(on: np.ndarray, cols: dict[str, np.ndarray], f: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, layer: str):
    m = on & ((f.time >= start) & (f.time < end)).to_numpy()
    return stats_for(np.flatnonzero(m), cols, f, layer)


def passes_discovery(on: np.ndarray, cols: dict[str, np.ndarray], f: pd.DataFrame, target_r: float):
    jan_b = month_stats(on, cols, f, DISC_START, JAN_END, "base")
    jan_s = month_stats(on, cols, f, DISC_START, JAN_END, "stress")
    feb_b = month_stats(on, cols, f, JAN_END, DISCOVERY_END, "base")
    feb_s = month_stats(on, cols, f, JAN_END, DISCOVERY_END, "stress")
    disc = on & ((f.time >= DISC_START) & (f.time < DISCOVERY_END)).to_numpy()
    ix = np.flatnonzero(disc)
    base = stats_for(ix, cols, f, "base")
    stress = stats_for(ix, cols, f, "stress")
    be = 1.0 / (target_r + 1.0)

    def monthly_ok(b, s):
        return (b["n"] >= 6 and b["dates"] >= 4 and b["expectancy_r"] is not None and b["expectancy_r"] >= 0.10
                and s["expectancy_r"] is not None and s["expectancy_r"] > 0 and b["pf"] >= 1.25
                and b["target_hit_rate"] is not None and b["target_hit_rate"] >= be)

    ok = (monthly_ok(jan_b, jan_s) and monthly_ok(feb_b, feb_s)
          and base["n"] >= 16 and base["dates"] >= 10 and base["pf"] >= 2.0 and stress["pf"] >= 1.35
          and base["expectancy_r"] is not None and base["expectancy_r"] >= 0.35
          and stress["expectancy_r"] is not None and stress["expectancy_r"] >= 0.10
          and base["expectancy_bps"] is not None and base["expectancy_bps"] > 0
          and stress["expectancy_bps"] is not None and stress["expectancy_bps"] > 0
          and base["target_hit_rate"] is not None and base["target_hit_rate"] >= be + 0.04
          and base["largest_winner_share"] is not None and base["largest_winner_share"] <= 0.35)
    return bool(ok), {"january_base": jan_b, "january_stress": jan_s, "february_base": feb_b, "february_stress": feb_s, "combined_base": base, "combined_stress": stress}


def bootstrap_q10(ix: np.ndarray, rvals: np.ndarray, f: pd.DataFrame):
    good = ix[np.isfinite(rvals[ix])]
    if len(good) == 0:
        return None
    dates = f.date.iloc[good].to_numpy()
    vals = rvals[good]
    ud = np.array(sorted(set(dates)), dtype=object)
    if len(ud) < 2:
        return None
    by = {d: vals[dates == d] for d in ud}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = np.empty(BOOTSTRAP_REPS, float)
    for k in range(BOOTSTRAP_REPS):
        sample = rng.choice(ud, size=len(ud), replace=True)
        z = np.concatenate([by[d] for d in sample])
        means[k] = z.mean()
    return float(np.quantile(means, 0.10))


def evaluate_forward(on: np.ndarray, cols: dict[str, np.ndarray], f: pd.DataFrame):
    fm = on & ((f.time >= DISCOVERY_END) & (f.time < FORWARD_END)).to_numpy()
    ix = np.flatnonzero(fm)
    g = stats_for(ix, cols, f, "gross")
    b = stats_for(ix, cols, f, "base")
    s = stats_for(ix, cols, f, "stress")
    months = {}
    positive_b = positive_s = 0
    for mo in ("2026-03", "2026-04", "2026-05"):
        p = pd.Period(mo, freq="M")
        st = p.start_time
        en = min(p.end_time + pd.Timedelta(nanoseconds=1), FORWARD_END)
        mb = month_stats(on, cols, f, st, en, "base")
        ms = month_stats(on, cols, f, st, en, "stress")
        months[mo] = {"base": mb, "stress": ms}
        if mb["total_bps"] > 0:
            positive_b += 1
        if ms["total_bps"] > 0:
            positive_s += 1
    q10 = bootstrap_q10(ix, cols["base_r"], f)
    monotone = g["total_bps"] + 1e-9 >= b["total_bps"] >= s["total_bps"] - 1e-9
    passed = (b["pf"] >= 2.0 and s["pf"] >= 1.5 and b["expectancy_r"] is not None and b["expectancy_r"] >= 0.30
              and s["expectancy_r"] is not None and s["expectancy_r"] >= 0.10 and q10 is not None and q10 > 0
              and b["n"] >= 20 and b["dates"] >= 12 and positive_b >= 2 and positive_s >= 2
              and b["largest_winner_share"] is not None and b["largest_winner_share"] <= 0.30 and monotone)
    return {"gate_pass": bool(passed), "gross": g, "base": b, "stress": s, "bootstrap_p10_base_mean_r": q10,
            "positive_base_months": positive_b, "positive_stress_months": positive_s, "months": months, "friction_monotonicity": bool(monotone)}


def run(root: Path, outdir: Path, inst: str):
    outdir.mkdir(parents=True, exist_ok=True)
    f, m1, numeric, provenance = load_context(root, inst)
    states, cuts = fit_state_masks(f, numeric)
    rules, inventory = build_rules(f, states)
    print("RULE_INVENTORY", inst, inventory, flush=True)
    outcomes = make_outcomes(f, m1, inst)
    passing = []
    for ri, rule in enumerate(rules, 1):
        on = onsets(f, rule["mask"])
        for pid, profile in PROFILES.items():
            for side_name in ("LONG", "SHORT"):
                cols = outcomes[(pid, side_name)]
                ok, disc = passes_discovery(on, cols, f, float(profile[1]))
                if ok:
                    rank = (min(disc["january_base"]["expectancy_r"], disc["february_base"]["expectancy_r"]),
                            min(disc["combined_base"]["pf"], disc["combined_stress"]["pf"]),
                            disc["combined_stress"]["expectancy_r"], disc["combined_base"]["dates"], rule["rule_id"])
                    passing.append({"rule_id": rule["rule_id"], "parts": rule["parts"], "mask_digest": rule["mask_digest"], "depth": rule["depth"],
                                    "profile": pid, "profile_tuple": profile, "side": side_name, "discovery": disc, "rank": rank})
        if ri % 250 == 0:
            print("EVALUATED_RULES", ri, "/", len(rules), "passes", len(passing), flush=True)

    passing.sort(key=lambda x: (x["rank"][0], x["rank"][1], x["rank"][2], x["rank"][3], x["rule_id"]), reverse=True)
    shortlist = []
    counts = {}
    for c in passing:
        k = (c["mask_digest"], c["side"])
        if counts.get(k, 0) >= 2:
            continue
        shortlist.append(c)
        counts[k] = counts.get(k, 0) + 1
        if len(shortlist) >= 30:
            break

    rule_by_id = {r["rule_id"]: r for r in rules}
    evaluated = []
    for c in shortlist:
        r = rule_by_id[c["rule_id"]]
        on = onsets(f, r["mask"])
        fw = evaluate_forward(on, outcomes[(c["profile"], c["side"])], f)
        row = dict(c)
        row.pop("rank", None)
        row["forward"] = fw
        evaluated.append(row)
    survivors = [x for x in evaluated if x["forward"]["gate_pass"]]
    evaluated.sort(key=lambda x: (x["forward"]["gate_pass"], x["forward"]["stress"]["pf"], x["forward"]["base"]["pf"], x["forward"]["base"]["expectancy_r"] or -1e9), reverse=True)

    result = {
        "engine": "cycle21-direct-high-r-rules-v1", "instrument": inst,
        "status": "HIGH_R_RULE_SURVIVOR_AWAITING_NEW_CONFIRMATION" if survivors else "NO_HIGH_R_RULE_SURVIVOR",
        "data_end_exclusive": str(FORWARD_END), "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False,
        "commission_excluded": True, "profile_family": PROFILES, "feature_count": len(numeric), "state_count": len(states),
        "rule_inventory": inventory, "discovery_pass_count": len(passing), "shortlist_count": len(shortlist), "survivor_count": len(survivors),
        "january_cutpoints": cuts, "evaluated_shortlist": evaluated, "survivors": survivors, "provenance": provenance,
    }
    (outdir / "result.json").write_text(json.dumps(result, indent=2, default=jsonable) + "\n")
    (outdir / "survivors.json").write_text(json.dumps(survivors, indent=2, default=jsonable) + "\n")
    lines = [f"# Cycle 21 — {inst}", "", f"Status: **{result['status']}**", f"Unique rules: {len(rules)}", f"Jan-Feb passes: {len(passing)}", f"Frozen shortlist: {len(shortlist)}", f"Forward survivors: {len(survivors)}", "", "## Forward shortlist"]
    for x in evaluated[:20]:
        q = x["forward"]
        lines.append(f"- {x['rule_id']} {x['side']} {x['profile']} ({x['profile_tuple'][1]}R): BASE PF={q['base']['pf']:.3f} meanR={q['base']['expectancy_r']} N={q['base']['n']}; STRESS PF={q['stress']['pf']:.3f} meanR={q['stress']['expectancy_r']}; bootP10={q['bootstrap_p10_base_mean_r']}; gate={q['gate_pass']}")
    lines += ["", "Research-only. Retired May16-Jul1 and 2025 were not read."]
    (outdir / "report.md").write_text("\n".join(lines) + "\n")
    print("STATUS", result["status"], "PASSES", len(passing), "SURVIVORS", len(survivors), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=Path("."))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--instrument", choices=["CNYRUBF", "USDRUBF"], required=True)
    a = p.parse_args()
    run(a.data_root, a.output, a.instrument)
