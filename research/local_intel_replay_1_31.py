from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DEFAULT_OUTPUT = ROOT / "results" / "intel_replay_1_31"
FENCED_DATA = DEFAULT_OUTPUT / "_fenced_data"
CUTOFF_DATE = 20260516  # exclusive: retired May16-Jul1 is never exposed

DATA_FILES = [
    "2026/CNY/CNY_2026_Q1_M1.csv",
    "2026/CNY/CNY_2026_Q2_M1.csv",
    "2026/CNY/CNY_2026_Q1.csv",
    "2026/CNY/CNY_2026_Q2.csv",
    "2026/Si/Si_2026_Q1_M1.csv",
    "2026/Si/Si_2026_Q2_M1.csv",
    "2026/Si/Si_2026_Q1.csv",
    "2026/Si/Si_2026_Q2.csv",
]

CYCLES: list[dict[str, Any]] = [
    {"id": 1, "name": "Autonomous Search v1", "mode": "SINGLE", "script": "research/autonomous_search_v1.py", "workflow": "autonomous-search-v1.yml"},
    {"id": 2, "name": "Autonomous Search v2", "mode": "SINGLE", "script": "research/autonomous_search_v2_fast_runner.py", "workflow": "autonomous-search-v2.yml"},
    {"id": 3, "name": "Autonomous Search v3", "mode": "SINGLE", "script": "research/autonomous_search_v3.py", "workflow": "autonomous-search-v3.yml"},
    {"id": 4, "name": "Causal Event Search", "mode": "INSTRUMENT_TIMEFRAME", "script": "research/cycle4_event_search_fixed_runner.py", "workflow": "cycle4-event-search.yml", "instruments": ["CNYRUBF", "USDRUBF"], "timeframes": ["M1", "M5"]},
    {"id": 5, "name": "Adaptive Selector", "mode": "SINGLE", "script": "research/cycle5_adaptive_selector.py", "workflow": "cycle5-adaptive-selector.yml"},
    {"id": 6, "name": "Pooled Ridge", "mode": "SINGLE", "script": "research/cycle6_pooled_ridge.py", "workflow": "cycle6-pooled-ridge.yml"},
    {"id": 7, "name": "Equal Levels", "mode": "SINGLE", "script": "research/cycle7_equal_levels.py", "workflow": "cycle7-equal-levels.yml"},
    {"id": 8, "name": "Passive Retest", "mode": "SINGLE", "script": "research/cycle8_passive_retest.py", "workflow": "cycle8-passive-retest.yml"},
    {"id": 9, "name": "Equal-Level Breakout", "mode": "SINGLE", "script": "research/cycle9_equal_level_breakout_runner.py", "workflow": "cycle9-equal-level-breakout.yml"},
    {"id": 10, "name": "Relative Value", "mode": "SINGLE", "script": "research/cycle10_relative_value.py", "workflow": "cycle10-relative-value.yml"},
    {"id": 11, "name": "Nonlinear Executable PnL", "mode": "BLOCKED", "script": "research/cycle11_nonlinear_pnl_fixed_runner.py", "finalizer": "research/cycle11_finalize.py", "blocks": 11, "workflow": "cycle11-nonlinear-pnl.yml"},
    {"id": 12, "name": "Historical Analog Mining", "mode": "BLOCKED", "script": "research/cycle12_analog_block.py", "finalizer": "research/cycle12_finalize.py", "blocks": 11, "workflow": "cycle12-historical-analog.yml"},
    {"id": 13, "name": "Cross Lead/Lag", "mode": "BLOCKED", "script": "research/cycle13_cross_leadlag_block.py", "finalizer": "research/cycle13_finalize.py", "blocks": 11, "workflow": "cycle13-cross-leadlag.yml"},
    {"id": 14, "name": "M1 Microstructure", "mode": "BLOCKED", "script": "research/cycle14_m1_micro_fast_runner.py", "finalizer": "research/cycle14_finalize.py", "blocks": 11, "workflow": "cycle14-m1-micro.yml"},
    {"id": 15, "name": "Full-Session Causal Executable-PnL", "mode": "PREREGISTERED_NOT_IMPLEMENTED", "protocol": "research/CYCLE15_PROTOCOL.md", "reason": "Protocol exists, but no executable Cycle15 engine/workflow/finalizer is present in the repository. Replay does not fabricate a result."},
    {"id": 16, "name": "Sparse Consensus High-PF", "mode": "BLOCKED", "script": "research/cycle16_sparse_consensus_block.py", "finalizer": "research/cycle16_finalize.py", "blocks": 11, "workflow": "cycle16-sparse-consensus.yml"},
    {"id": 17, "name": "High-R Expectancy", "mode": "BLOCKED", "script": "research/cycle17_high_r_block.py", "finalizer": "research/cycle17_finalize.py", "blocks": 11, "workflow": "cycle17-high-r-expectancy.yml"},
    {"id": 18, "name": "Ultra-Short Barrier", "mode": "BLOCKED", "script": "research/cycle18_barrier_block.py", "finalizer": "research/cycle18_finalize.py", "blocks": 11, "workflow": "cycle18-ultrashort-barrier.yml"},
    {"id": 19, "name": "Instrument High-R", "mode": "BLOCKED", "script": "research/cycle19_instrument_block.py", "finalizer": "research/cycle19_finalize.py", "blocks": 11, "workflow": "cycle19-instrument-high-r.yml"},
    {"id": 20, "name": "Structural High-R", "mode": "BLOCKED", "script": "research/cycle20_structural_block.py", "finalizer": "research/cycle20_finalize.py", "blocks": 11, "workflow": "cycle20-structural-high-r.yml"},
    {"id": 21, "name": "Direct High-R Rules", "mode": "INSTRUMENT", "script": "research/cycle21_direct_high_r_rules.py", "workflow": "cycle21-direct-high-r-rules.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 22, "name": "Stress First", "mode": "BLOCKED", "script": "research/cycle22_stress_first_block.py", "finalizer": "research/cycle22_finalize.py", "blocks": 11, "workflow": "cycle22-stress-first.yml"},
    {"id": 23, "name": "Rule Family", "mode": "INSTRUMENT", "script": "research/cycle23_rule_family.py", "workflow": "cycle23-rule-family.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 24, "name": "Fixed Point Structural", "mode": "INSTRUMENT", "script": "research/cycle24_fixed_point_structural.py", "workflow": "cycle24-fixed-point-structural.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 25, "name": "Direct Structural Target", "mode": "INSTRUMENT", "script": "research/cycle25_direct_structural_target.py", "workflow": "cycle25-direct-structural-target.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 26, "name": "Sparse High-R Ensemble", "mode": "INSTRUMENT", "script": "research/cycle26_sparse_high_r_ensemble.py", "workflow": None, "note": "Executable engine exists and accepts --instrument; no Cycle26 workflow is present.", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 27, "name": "Fixed Stop Structural Event", "mode": "INSTRUMENT", "script": "research/cycle27_fixed_stop_structural_event.py", "workflow": "cycle27-fixed-stop-structural-event.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 28, "name": "M1 Fixed Stop Micro", "mode": "INSTRUMENT", "script": "research/cycle28_m1_fixed_stop_micro.py", "workflow": "cycle28-m1-fixed-stop-micro.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 29, "name": "Structure-Aligned Passive", "mode": "INSTRUMENT", "script": "research/cycle29_structure_aligned_passive.py", "workflow": "cycle29-structure-aligned-passive.yml", "instruments": ["CNYRUBF", "USDRUBF"], "note": "The separate CNY recovery workflow is not a new cycle; both instruments are replayed here."},
    {"id": 30, "name": "Passive Probe Reclaim", "mode": "INSTRUMENT", "script": "research/cycle30_reclaim_entry.py", "workflow": "cycle30-passive-probe-reclaim.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
    {"id": 31, "name": "Double Touch Reclaim", "mode": "INSTRUMENT", "script": "research/cycle31_double_touch_reclaim.py", "workflow": "cycle31-double-touch-reclaim.yml", "instruments": ["CNYRUBF", "USDRUBF"]},
]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head() -> str:
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout.strip() if p.returncode == 0 else "UNKNOWN"


def build_fenced_data(root_out: Path) -> Path:
    dst_root = root_out / "_fenced_data"
    manifest = []
    for rel in DATA_FILES:
        src = ROOT / rel
        if not src.exists():
            raise FileNotFoundError(src)
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        kept = 0
        skipped = 0
        with src.open("r", encoding="utf-8-sig", newline="") as inf, dst.open("w", encoding="utf-8", newline="") as outf:
            reader = csv.reader(inf, delimiter=";")
            writer = csv.writer(outf, delimiter=";", lineterminator="\n")
            try:
                header = next(reader)
            except StopIteration:
                raise ValueError(f"empty data file: {src}")
            writer.writerow(header)
            for row in reader:
                if len(row) < 4:
                    continue
                try:
                    date = int(row[2])
                except ValueError:
                    continue
                if date >= CUTOFF_DATE:
                    skipped += 1
                    continue
                writer.writerow(row)
                kept += 1
        manifest.append({"source": rel, "source_sha256": sha256(src), "fenced": str(dst.relative_to(root_out)), "rows_kept": kept, "rows_retired_not_exposed": skipped, "fenced_sha256": sha256(dst)})
    save_json(root_out / "fenced_data_manifest.json", {"cutoff_exclusive": "2026-05-16", "true_oos_2025_exposed": False, "files": manifest})
    return dst_root


def command_text(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd)


def run_task(cmd: list[str], task_dir: Path, *, resume: bool, dry_run: bool) -> bool:
    task_dir.mkdir(parents=True, exist_ok=True)
    success = task_dir / ".SUCCESS"
    failed = task_dir / ".FAILED"
    (task_dir / "command.txt").write_text(command_text(cmd) + "\n", encoding="utf-8")
    if resume and success.exists():
        print(f"SKIP SUCCESS {task_dir.relative_to(ROOT)}", flush=True)
        return True
    if dry_run:
        print("DRY RUN", command_text(cmd), flush=True)
        return True
    success.unlink(missing_ok=True)
    failed.unlink(missing_ok=True)
    print("RUN", command_text(cmd), flush=True)
    with (task_dir / "console.log").open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True)
    if proc.returncode == 0:
        success.write_text(now() + "\n", encoding="utf-8")
        return True
    failed.write_text(f"returncode={proc.returncode}\ntime={now()}\n", encoding="utf-8")
    print(f"FAILED rc={proc.returncode}; see {task_dir / 'console.log'}", flush=True)
    return False


def copy_audit_sources(cycle: dict[str, Any], cycle_dir: Path) -> None:
    dst = cycle_dir / "audit_sources"
    dst.mkdir(parents=True, exist_ok=True)
    cid = cycle["id"]
    candidates = [cycle.get("script"), cycle.get("finalizer"), cycle.get("protocol"), f"research/CYCLE{cid}_PROTOCOL.md"]
    wf = cycle.get("workflow")
    if wf:
        candidates.append(f".github/workflows/{wf}")
    seen = set()
    for rel in candidates:
        if not rel or rel in seen:
            continue
        seen.add(rel)
        src = ROOT / rel
        if src.exists():
            shutil.copy2(src, dst / src.name)


def pycmd(script: str, *args: str) -> list[str]:
    p = ROOT / script
    if not p.exists():
        raise FileNotFoundError(p)
    return [PYTHON, "-u", str(p), *map(str, args)]


def run_cycle(cycle: dict[str, Any], cycle_dir: Path, data_root: Path, *, resume: bool, dry_run: bool) -> bool:
    mode = cycle["mode"]
    if mode == "PREREGISTERED_NOT_IMPLEMENTED":
        status = {"cycle": cycle["id"], "name": cycle["name"], "status": "PREREGISTERED_NOT_IMPLEMENTED", "reason": cycle["reason"], "finished_at": now()}
        save_json(cycle_dir / "cycle_status.json", status)
        print("AUDIT ONLY:", cycle["reason"], flush=True)
        return True

    if mode == "SINGLE":
        out = cycle_dir / "run"
        cmd = pycmd(cycle["script"], "--data-root", str(data_root), "--output", str(out))
        return run_task(cmd, out, resume=resume, dry_run=dry_run)

    if mode == "INSTRUMENT_TIMEFRAME":
        ok = True
        for inst in cycle["instruments"]:
            for tf in cycle["timeframes"]:
                out = cycle_dir / f"{inst}-{tf}"
                cmd = pycmd(cycle["script"], "--data-root", str(data_root), "--output", str(out), "--instrument", inst, "--timeframe", tf)
                ok = run_task(cmd, out, resume=resume, dry_run=dry_run) and ok
        return ok

    if mode == "INSTRUMENT":
        ok = True
        for inst in cycle["instruments"]:
            out = cycle_dir / inst
            cmd = pycmd(cycle["script"], "--data-root", str(data_root), "--instrument", inst, "--output", str(out))
            ok = run_task(cmd, out, resume=resume, dry_run=dry_run) and ok
        return ok

    if mode == "BLOCKED":
        blocks = cycle_dir / "blocks"
        block_ok = True
        for i in range(int(cycle["blocks"])):
            out = blocks / f"block{i:02d}"
            cmd = pycmd(cycle["script"], "--data-root", str(data_root), "--block-index", str(i), "--output", str(out))
            block_ok = run_task(cmd, out, resume=resume, dry_run=dry_run) and block_ok
        if not block_ok and not dry_run:
            return False
        final = cycle_dir / "final"
        cmd = pycmd(cycle["finalizer"], "--block-root", str(blocks), "--output", str(final))
        return run_task(cmd, final, resume=resume, dry_run=dry_run) and block_ok

    raise ValueError(f"unknown mode {mode}")


def result_inventory(cycle_dir: Path) -> list[str]:
    return sorted(str(p.relative_to(cycle_dir)) for p in cycle_dir.rglob("*.json") if p.name != "cycle_status.json")


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay historical autonomous research Cycles 1-31 locally on Intel using repository workflow semantics.")
    ap.add_argument("--from-cycle", type=int, default=1)
    ap.add_argument("--to-cycle", type=int, default=31)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (1 <= args.from_cycle <= args.to_cycle <= 31):
        raise SystemExit("Require 1 <= from-cycle <= to-cycle <= 31")

    root_out = args.output.resolve()
    root_out.mkdir(parents=True, exist_ok=True)
    data_root = build_fenced_data(root_out)
    save_json(root_out / "run_metadata.json", {"started_at": now(), "git_head": git_head(), "python": PYTHON, "from_cycle": args.from_cycle, "to_cycle": args.to_cycle, "resume": args.resume, "dry_run": args.dry_run, "data_root": str(data_root), "retired_2026_05_16_to_2026_07_01_exposed": False, "true_oos_2025_exposed": False})

    selected = [c for c in CYCLES if args.from_cycle <= c["id"] <= args.to_cycle]
    summary = []
    for c in selected:
        cid = c["id"]
        cycle_dir = root_out / f"cycle{cid:02d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        copy_audit_sources(c, cycle_dir)
        save_json(cycle_dir / "cycle_definition.json", c)
        print("\n" + "=" * 78, flush=True)
        print(f"CYCLE {cid:02d} | {c['name']} | {c['mode']}", flush=True)
        print("=" * 78, flush=True)
        started = now()
        error = None
        try:
            ok = run_cycle(c, cycle_dir, data_root, resume=args.resume, dry_run=args.dry_run)
        except KeyboardInterrupt:
            save_json(cycle_dir / "cycle_status.json", {"cycle": cid, "name": c["name"], "status": "INTERRUPTED", "started_at": started, "finished_at": now()})
            raise
        except Exception as e:
            ok = False
            error = f"{type(e).__name__}: {e}"
            print("CONTROLLER ERROR", error, flush=True)
        existing = None
        status_path = cycle_dir / "cycle_status.json"
        if status_path.exists() and c["mode"] == "PREREGISTERED_NOT_IMPLEMENTED":
            existing = json.loads(status_path.read_text(encoding="utf-8"))
        if existing is not None:
            status = existing
        else:
            status = {"cycle": cid, "name": c["name"], "mode": c["mode"], "status": "DRY_RUN_OK" if args.dry_run else ("COMPLETED" if ok else "FAILED"), "started_at": started, "finished_at": now(), "error": error, "result_json_files": result_inventory(cycle_dir)}
            save_json(status_path, status)
        summary.append(status)
        save_json(root_out / "audit_summary.json", summary)

    print("\n" + "=" * 78, flush=True)
    print("REPLAY RANGE FINISHED", flush=True)
    print("RESULTS", root_out, flush=True)
    print("=" * 78, flush=True)
    return 0 if all(s["status"] in {"COMPLETED", "DRY_RUN_OK", "PREREGISTERED_NOT_IMPLEMENTED"} for s in summary) else 2


if __name__ == "__main__":
    raise SystemExit(main())
