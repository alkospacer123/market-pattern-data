from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

DISC_START = pd.Timestamp("2026-01-05")
JAN_END = pd.Timestamp("2026-02-01")
DISC_END = pd.Timestamp("2026-03-01")
FORWARD_END = pd.Timestamp("2026-05-16")
PROFILES = {
    "F1": (0.75, 4.0, 90),
    "F2": (0.75, 5.0, 120),
    "F3": (1.00, 4.0, 120),
    "F4": (1.00, 5.0, 480),
}
BOOTSTRAP_SEED = 20260401
BOOTSTRAP_REPS = 1000
FAMILY_MASK_CAP = 5000


def mod(path: str, name: str):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    assert s.loader is not None
    s.loader.exec_module(m)
    return m


c21 = mod("research/cycle21_direct_high_r_rules.py", "c21")
v3 = c21.v3
c18 = c21.c18
c21.PROFILES = PROFILES


def family(feat: str) -> str | None:
    if feat == "clock_hour": return "clock"
    if feat == "session_pos" or feat.startswith("pos_") or feat.startswith("dist_high_") or feat.startswith("dist_low_"): return "range_position"
    if feat.startswith("ret_") or feat in ("body_atr", "body_frac"): return "return_momentum"
    if feat.startswith("eff_"): return "efficiency"
    if feat == "range_atr" or feat.startswith("vol_"): return "volatility"
    if feat.startswith("relvol_") or feat.startswith("vol_z_"): return "volume"
    if feat in ("dist_pdh_atr", "dist_pdl_atr", "gap_prevclose_atr"): return "previous_day"
    if feat in ("round_dist_atr", "round_pos"): return "round_level"
    if feat in ("close_pos_candle", "upper_wick_frac", "lower_wick_frac"): return "candle_shape"
    return None


def relax_key(key: tuple[str, str]):
    feat, state = key
    return {
        "HIGH10": (feat, "HIGH25"),
        "LOW10": (feat, "LOW25"),
    }.get(state)


def canonical(parts):
    return "&".join(f"{a}:{b}" for a, b in sorted(parts))


def mask_digest(mask):
    return hashlib.sha256(np.packbits(mask.astype(np.uint8)).tobytes()).hexdigest()


def build_family_masks(f: pd.DataFrame, states: dict[tuple[str, str], np.ndarray], base_rules: list[dict]):
    janfeb = ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy()
    eligible = c21.session_mask(f)
    by_family_state: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for key in states:
        fam = family(key[0])
        if fam is not None:
            by_family_state.setdefault((fam, key[1]), []).append(key)
    for z in by_family_state.values(): z.sort()

    generated: list[tuple[str, np.ndarray, str]] = []
    for r in base_rules:
        if r["depth"] != 2:
            continue
        a, b = r["parts"]
        fa, fb = family(a[0]), family(b[0])
        if fa is None or fb is None or fa == fb:
            continue
        exact = states[a] & states[b]
        generated.append((f"EXACT|{canonical((a,b))}", exact, "exact"))
        ra, rb = relax_key(a), relax_key(b)
        if ra in states:
            generated.append((f"RELAX_A|{canonical((ra,b))}", states[ra] & states[b], "relax_a"))
        if rb in states:
            generated.append((f"RELAX_B|{canonical((a,rb))}", states[a] & states[rb], "relax_b"))
        if ra in states and rb in states:
            generated.append((f"RELAX_BOTH|{canonical((ra,rb))}", states[ra] & states[rb], "relax_both"))

        for sub in by_family_state.get((fa, a[1]), []):
            if sub == a or sub[0] == b[0]: continue
            sm = states[sub] & states[b]
            generated.append((f"SUB_A|{canonical((sub,b))}", sm, "sub_a"))
            generated.append((f"OR_SUB_A|{canonical((a,b))}|{canonical((sub,b))}", exact | sm, "or_sub_a"))
        for sub in by_family_state.get((fb, b[1]), []):
            if sub == b or sub[0] == a[0]: continue
            sm = states[a] & states[sub]
            generated.append((f"SUB_B|{canonical((a,sub))}", sm, "sub_b"))
            generated.append((f"OR_SUB_B|{canonical((a,b))}|{canonical((a,sub))}", exact | sm, "or_sub_b"))

    # Pre-outcome target-free observation floor, exact-mask dedupe and SHA cap.
    rows = []
    seen = set()
    for rid, mask, kind in generated:
        if int((mask & janfeb & eligible).sum()) < 20:
            continue
        d = mask_digest(mask & eligible)
        if d in seen:
            continue
        seen.add(d)
        rank = hashlib.sha256(rid.encode("utf-8")).hexdigest()
        rows.append({"family_rule_id": rid, "kind": kind, "mask": mask, "mask_digest": d, "sha_rank": rank})
    rows.sort(key=lambda x: (x["sha_rank"], x["family_rule_id"]))
    return rows[:FAMILY_MASK_CAP], {"generated_raw": len(generated), "unique_eligible_masks": len(rows), "retained_cap": min(FAMILY_MASK_CAP, len(rows))}


def month(on, cols, f, start, end, layer):
    return c21.month_stats(on, cols, f, start, end, layer)


def passes_development(on, cols, f, target_r):
    jb, js = month(on, cols, f, DISC_START, JAN_END, "base"), month(on, cols, f, DISC_START, JAN_END, "stress")
    fb, fs = month(on, cols, f, JAN_END, DISC_END, "base"), month(on, cols, f, JAN_END, DISC_END, "stress")
    ix = np.flatnonzero(on & ((f.time >= DISC_START) & (f.time < DISC_END)).to_numpy())
    b, s = c21.stats_for(ix, cols, f, "base"), c21.stats_for(ix, cols, f, "stress")
    be = 1.0 / (target_r + 1.0)
    def mok(x, y):
        return x["n"] >= 8 and x["dates"] >= 5 and x["expectancy_r"] is not None and x["expectancy_r"] >= 0.10 and y["expectancy_r"] is not None and y["expectancy_r"] > 0 and x["pf"] >= 1.25
    ok = (mok(jb, js) and mok(fb, fs) and b["n"] >= 22 and b["dates"] >= 12 and b["pf"] >= 2.0 and s["pf"] >= 1.5
          and b["expectancy_r"] is not None and b["expectancy_r"] >= 0.35 and s["expectancy_r"] is not None and s["expectancy_r"] >= 0.15
          and b["target_hit_rate"] is not None and b["target_hit_rate"] >= be + 0.04 and b["largest_winner_share"] is not None and b["largest_winner_share"] <= 0.30)
    return bool(ok), {"january_base": jb, "january_stress": js, "february_base": fb, "february_stress": fs, "combined_base": b, "combined_stress": s}


def bootstrap_q10(ix, rvals, f):
    good = ix[np.isfinite(rvals[ix])]
    if len(good) == 0: return None
    d = f.date.iloc[good].to_numpy(); v = rvals[good]; ud = np.asarray(sorted(set(d)), dtype=object)
    if len(ud) < 2: return None
    by = {x: v[d == x] for x in ud}; rng = np.random.default_rng(BOOTSTRAP_SEED); means = np.empty(BOOTSTRAP_REPS)
    for i in range(BOOTSTRAP_REPS):
        sample = rng.choice(ud, len(ud), replace=True); means[i] = np.concatenate([by[x] for x in sample]).mean()
    return float(np.quantile(means, .10))


def forward(on, cols, f):
    mask = on & ((f.time >= DISC_END) & (f.time < FORWARD_END)).to_numpy(); ix = np.flatnonzero(mask)
    g, b, s = c21.stats_for(ix, cols, f, "gross"), c21.stats_for(ix, cols, f, "base"), c21.stats_for(ix, cols, f, "stress")
    bp = sp = 0; months = {}
    for mo in ("2026-03", "2026-04", "2026-05"):
        p = pd.Period(mo, freq="M"); st = p.start_time; en = min(p.end_time + pd.Timedelta(nanoseconds=1), FORWARD_END)
        mb, ms = month(on, cols, f, st, en, "base"), month(on, cols, f, st, en, "stress"); months[mo] = {"base": mb, "stress": ms}
        bp += mb["total_bps"] > 0; sp += ms["total_bps"] > 0
    q10 = bootstrap_q10(ix, cols["base_r"], f); mono = g["total_bps"] + 1e-9 >= b["total_bps"] >= s["total_bps"] - 1e-9
    passed = (b["pf"] >= 2 and s["pf"] >= 1.5 and b["expectancy_r"] is not None and b["expectancy_r"] >= .30 and s["expectancy_r"] is not None and s["expectancy_r"] >= .10
              and b["n"] >= 20 and b["dates"] >= 12 and bp >= 2 and sp >= 2 and q10 is not None and q10 > 0
              and b["largest_winner_share"] is not None and b["largest_winner_share"] <= .25 and mono)
    return {"gate_pass": bool(passed), "gross": g, "base": b, "stress": s, "bootstrap_p10_base_mean_r": q10, "positive_base_months": int(bp), "positive_stress_months": int(sp), "months": months, "friction_monotonicity": bool(mono)}


def run(root: Path, out: Path, inst: str):
    out.mkdir(parents=True, exist_ok=True)
    f, m1, numeric, provenance = c21.load_context(root, inst)
    states, cuts = c21.fit_state_masks(f, numeric)
    base_rules, base_inventory = c21.build_rules(f, states)
    family_masks, family_inventory = build_family_masks(f, states, base_rules)
    outcomes = c21.make_outcomes(f, m1, inst)
    passes = []
    for i, r in enumerate(family_masks, 1):
        on = c21.onsets(f, r["mask"])
        for pid, profile in PROFILES.items():
            for side in ("LONG", "SHORT"):
                ok, dev = passes_development(on, outcomes[(pid, side)], f, float(profile[1]))
                if ok:
                    score = (min(dev["january_base"]["expectancy_r"], dev["february_base"]["expectancy_r"]), min(dev["combined_base"]["pf"], dev["combined_stress"]["pf"]), dev["combined_stress"]["expectancy_r"], dev["combined_base"]["dates"])
                    passes.append({"family_rule_id": r["family_rule_id"], "kind": r["kind"], "mask_digest": r["mask_digest"], "profile": pid, "profile_tuple": profile, "side": side, "development": dev, "score": score})
        if i % 500 == 0: print("EVALUATED_FAMILIES", i, "/", len(family_masks), "passes", len(passes), flush=True)
    passes.sort(key=lambda x: (x["score"][0], x["score"][1], x["score"][2], x["score"][3], x["family_rule_id"]), reverse=True)
    shortlist = []; count = {}
    for p in passes:
        k = (p["mask_digest"], p["side"]); count[k] = count.get(k, 0)
        if count[k] >= 2: continue
        shortlist.append(p); count[k] += 1
        if len(shortlist) >= 40: break
    byid = {r["family_rule_id"]: r for r in family_masks}; evaluated = []
    for p in shortlist:
        r = byid[p["family_rule_id"]]; on = c21.onsets(f, r["mask"]); q = dict(p); q.pop("score", None); q["forward"] = forward(on, outcomes[(p["profile"], p["side"])], f); evaluated.append(q)
    evaluated.sort(key=lambda x: (x["forward"]["gate_pass"], x["forward"]["stress"]["pf"], x["forward"]["base"]["pf"], x["forward"]["base"]["expectancy_r"] or -1e9), reverse=True)
    survivors = [x for x in evaluated if x["forward"]["gate_pass"]]
    result = {"engine": "cycle23-high-r-rule-family-v1", "instrument": inst, "status": "FAMILY_HIGH_R_RESEARCH_SURVIVOR_AWAITING_NEW_CONFIRMATION" if survivors else "NO_FAMILY_HIGH_R_RESEARCH_SURVIVOR", "data_end_exclusive": str(FORWARD_END), "retired_internal_confirmation_accessed": False, "true_oos_2025_accessed": False, "commission_excluded": True, "profiles": PROFILES, "feature_count": len(numeric), "base_rule_inventory": base_inventory, "family_inventory": family_inventory, "development_pass_count": len(passes), "shortlist_count": len(shortlist), "survivor_count": len(survivors), "evaluated_shortlist": evaluated, "survivors": survivors, "january_cutpoints": cuts, "provenance": provenance}
    (out / "result.json").write_text(json.dumps(result, indent=2, default=c21.jsonable) + "\n")
    (out / "survivors.json").write_text(json.dumps(survivors, indent=2, default=c21.jsonable) + "\n")
    lines = [f"# Cycle 23 — {inst}", "", f"Status: **{result['status']}**", f"Family masks: {len(family_masks)}", f"Jan-Feb passes: {len(passes)}", f"Shortlist: {len(shortlist)}", f"Survivors: {len(survivors)}", "", "## Top forward"]
    for x in evaluated[:20]:
        z=x["forward"]; lines.append(f"- {x['family_rule_id']} {x['side']} {x['profile']}: BASE PF={z['base']['pf']:.3f} meanR={z['base']['expectancy_r']} N={z['base']['n']}; STRESS PF={z['stress']['pf']:.3f} meanR={z['stress']['expectancy_r']}; bootP10={z['bootstrap_p10_base_mean_r']}; gate={z['gate_pass']}")
    lines += ["", "Research-only. March-May has already been inspected in prior cycles. Retired May16-Jul1 and 2025 were not read."]
    (out / "report.md").write_text("\n".join(lines)+"\n"); print("STATUS", result["status"], "PASSES", len(passes), "SURVIVORS", len(survivors), flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("--data-root", type=Path, default=Path(".")); p.add_argument("--output", type=Path, required=True); p.add_argument("--instrument", choices=["CNYRUBF","USDRUBF"], required=True); a=p.parse_args(); run(a.data_root,a.output,a.instrument)
