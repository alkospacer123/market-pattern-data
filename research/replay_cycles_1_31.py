from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
MANIFEST_PATH = RESEARCH / "HISTORICAL_REPLAY_1_31.json"
WORKTREE_BASE = ROOT.parent / "_historical_replay_worktrees"
DEFAULT_RESULTS = ROOT / "results" / "historical_replay_1_31"

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


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def git_head(path: Path = ROOT) -> str:
    return git("rev-parse", "HEAD", cwd=path).stdout.strip()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_data_manifest() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rel in DATA_FILES:
        path = ROOT / rel
        if not path.exists():
            raise FileNotFoundError(f"required replay data file missing: {path}")
        rows.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def ensure_commit(commit: str) -> None:
    probe = git("cat-file", "-e", f"{commit}^{{commit}}", check=False)
    if probe.returncode == 0:
        return
    print(f"FETCH missing historical commit {commit}", flush=True)
    fetch = git("fetch", "origin", commit, check=False)
    if fetch.returncode != 0:
        raise RuntimeError(
            f"cannot fetch historical commit {commit}: {fetch.stderr.strip()}"
        )
    probe = git("cat-file", "-e", f"{commit}^{{commit}}", check=False)
    if probe.returncode != 0:
        raise RuntimeError(f"historical commit unavailable after fetch: {commit}")


def ensure_worktree(snapshot_key: str, commit: str) -> Path:
    ensure_commit(commit)
    path = WORKTREE_BASE / f"{snapshot_key}-{commit[:8]}"
    if path.exists():
        probe = git("rev-parse", "HEAD", cwd=path, check=False)
        if probe.returncode != 0:
            raise RuntimeError(f"existing replay worktree is not a git worktree: {path}")
        actual = probe.stdout.strip()
        if actual != commit:
            raise RuntimeError(
                f"replay worktree SHA mismatch at {path}: expected {commit}, got {actual}"
            )
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    add = git("worktree", "add", "--detach", str(path), commit, check=False)
    if add.returncode != 0:
        raise RuntimeError(
            f"failed to create replay worktree {path}: {add.stderr.strip()}"
        )
    actual = git_head(path)
    if actual != commit:
        raise RuntimeError(
            f"created replay worktree SHA mismatch: expected {commit}, got {actual}"
        )
    return path


def command_text(cmd: list[str]) -> str:
    return subprocess.list2cmdline([str(x) for x in cmd])


def run_task(
    cmd: list[str],
    *,
    cwd: Path,
    task_dir: Path,
    resume: bool,
    dry_run: bool,
) -> bool:
    task_dir.mkdir(parents=True, exist_ok=True)
    success = task_dir / ".SUCCESS"
    failed = task_dir / ".FAILED"
    log_path = task_dir / "run.log"
    command_path = task_dir / "command.txt"
    command_path.write_text(command_text(cmd) + "\n", encoding="utf-8")

    if resume and success.exists():
        print(f"SKIP SUCCESS {task_dir}", flush=True)
        return True

    if dry_run:
        print(f"DRY RUN {command_text(cmd)}", flush=True)
        return True

    success.unlink(missing_ok=True)
    failed.unlink(missing_ok=True)

    started = now()
    print(f"[{started}] START {task_dir}", flush=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n===== START {started} =====\n")
        log.write(command_text(cmd) + "\n\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        finished = now()
        log.write(f"\n===== EXIT {proc.returncode} {finished} =====\n")

    if proc.returncode == 0:
        success.write_text(finished + "\n", encoding="utf-8")
        print(f"[{finished}] SUCCESS {task_dir}", flush=True)
        return True

    failed.write_text(
        f"returncode={proc.returncode}\ntime={finished}\n",
        encoding="utf-8",
    )
    print(
        f"[{finished}] FAILED rc={proc.returncode} {task_dir} -- see {log_path}",
        flush=True,
    )
    return False


def script_cmd(code_root: Path, script: str, *args: str) -> list[str]:
    script_path = code_root / "research" / script
    if not script_path.exists():
        raise FileNotFoundError(f"replay script missing in pinned snapshot: {script_path}")
    return [sys.executable, "-u", str(script_path), *[str(x) for x in args]]


def copy_audit_sources(cycle: dict[str, Any], code_root: Path, cycle_dir: Path) -> None:
    dst = cycle_dir / "audit_sources"
    dst.mkdir(parents=True, exist_ok=True)
    names = [cycle.get("script"), cycle.get("finalizer")]
    cid = int(cycle["id"])
    protocol = f"CYCLE{cid}_PROTOCOL.md"
    if (code_root / "research" / protocol).exists():
        names.append(protocol)
    for name in names:
        if not name:
            continue
        src = code_root / "research" / str(name)
        if src.exists():
            shutil.copy2(src, dst / src.name)


def run_single(cycle: dict[str, Any], code_root: Path, cycle_dir: Path, resume: bool, dry_run: bool) -> bool:
    out = cycle_dir / "run"
    cmd = script_cmd(
        code_root,
        cycle["script"],
        "--data-root", str(ROOT),
        "--output", str(out),
    )
    return run_task(cmd, cwd=code_root, task_dir=out, resume=resume, dry_run=dry_run)


def run_matrix(cycle: dict[str, Any], code_root: Path, cycle_dir: Path, resume: bool, dry_run: bool) -> bool:
    ok = True
    for instrument in cycle["instruments"]:
        for timeframe in cycle["timeframes"]:
            out = cycle_dir / f"{instrument}-{timeframe}"
            cmd = script_cmd(
                code_root,
                cycle["script"],
                "--data-root", str(ROOT),
                "--output", str(out),
                "--instrument", instrument,
                "--timeframe", timeframe,
            )
            task_ok = run_task(cmd, cwd=code_root, task_dir=out, resume=resume, dry_run=dry_run)
            ok = task_ok and ok
    return ok


def run_per_instrument(cycle: dict[str, Any], code_root: Path, cycle_dir: Path, resume: bool, dry_run: bool) -> bool:
    ok = True
    for instrument in cycle["instruments"]:
        out = cycle_dir / instrument
        cmd = script_cmd(
            code_root,
            cycle["script"],
            "--data-root", str(ROOT),
            "--instrument", instrument,
            "--output", str(out),
        )
        task_ok = run_task(cmd, cwd=code_root, task_dir=out, resume=resume, dry_run=dry_run)
        ok = task_ok and ok
    return ok


def run_blocked(cycle: dict[str, Any], code_root: Path, cycle_dir: Path, resume: bool, dry_run: bool) -> bool:
    blocks_root = cycle_dir / "blocks"
    all_blocks_ok = True
    for block_index in range(int(cycle["blocks"])):
        out = blocks_root / f"block{block_index:02d}"
        cmd = script_cmd(
            code_root,
            cycle["script"],
            "--data-root", str(ROOT),
            "--block-index", str(block_index),
            "--output", str(out),
        )
        block_ok = run_task(cmd, cwd=code_root, task_dir=out, resume=resume, dry_run=dry_run)
        all_blocks_ok = block_ok and all_blocks_ok

    final_dir = cycle_dir / "final"
    if not all_blocks_ok and not dry_run:
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / ".SKIPPED_DUE_TO_BLOCK_FAILURE").write_text(now() + "\n", encoding="utf-8")
        print(f"SKIP FINALIZER cycle{int(cycle['id']):02d}: one or more blocks failed", flush=True)
        return False

    cmd = script_cmd(
        code_root,
        cycle["finalizer"],
        "--block-root", str(blocks_root),
        "--output", str(final_dir),
    )
    final_ok = run_task(cmd, cwd=code_root, task_dir=final_dir, resume=resume, dry_run=dry_run)
    return all_blocks_ok and final_ok


def inventory_json_files(cycle_dir: Path) -> list[str]:
    return sorted(str(p.relative_to(cycle_dir)) for p in cycle_dir.rglob("*.json"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-cycle", type=int, default=1)
    ap.add_argument("--to-cycle", type=int, default=31)
    ap.add_argument("--run-id", default="replay01")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.from_cycle < 1 or args.to_cycle > 31 or args.from_cycle > args.to_cycle:
        raise SystemExit("cycle range must satisfy 1 <= from <= to <= 31")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8-sig"))
    run_root = DEFAULT_RESULTS / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)

    data_manifest = build_data_manifest()
    save_json(run_root / "data_manifest.json", data_manifest)
    shutil.copy2(MANIFEST_PATH, run_root / "HISTORICAL_REPLAY_1_31.json")
    shutil.copy2(Path(__file__), run_root / "replay_cycles_1_31.py")

    metadata = {
        "started_at": now(),
        "controller_git_head": git_head(),
        "python": sys.executable,
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "from_cycle": args.from_cycle,
        "to_cycle": args.to_cycle,
        "run_id": args.run_id,
        "resume": args.resume,
        "dry_run": args.dry_run,
        "data_files": data_manifest,
        "fences": {
            "retired_2026_05_16_to_2026_07_01_replayed": False,
            "true_oos_2025_accessed_by_controller": False,
        },
    }
    save_json(run_root / "run_metadata.json", metadata)

    snapshot_roots: dict[str, Path] = {}
    selected = [
        c for c in manifest["cycles"]
        if args.from_cycle <= int(c["id"]) <= args.to_cycle
    ]

    summary: list[dict[str, Any]] = []
    for cycle in selected:
        cid = int(cycle["id"])
        cycle_dir = run_root / f"cycle{cid:02d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        save_json(cycle_dir / "cycle_manifest.json", cycle)

        print("", flush=True)
        print("=" * 78, flush=True)
        print(f"CYCLE {cid:02d} | {cycle['name']} | {cycle['mode']}", flush=True)
        print("=" * 78, flush=True)

        if cycle["mode"] == "HISTORICAL_GAP":
            status = {
                "cycle": cid,
                "name": cycle["name"],
                "status": "NOT_PRESENT_IN_HISTORY",
                "reason": cycle["reason"],
                "finished_at": now(),
            }
            save_json(cycle_dir / "cycle_status.json", status)
            summary.append(status)
            print(f"CYCLE {cid:02d}: historical numbering gap; no fabricated replay", flush=True)
            continue

        snapshot_key = cycle["snapshot"]
        snapshot = manifest["snapshots"][snapshot_key]
        if snapshot_key not in snapshot_roots:
            snapshot_roots[snapshot_key] = ensure_worktree(snapshot_key, snapshot["commit"])
        code_root = snapshot_roots[snapshot_key]

        copy_audit_sources(cycle, code_root, cycle_dir)
        save_json(
            cycle_dir / "code_snapshot.json",
            {
                "snapshot": snapshot_key,
                "commit": snapshot["commit"],
                "worktree": str(code_root),
                "verified_head": git_head(code_root),
            },
        )

        started = now()
        ok = False
        error: str | None = None
        try:
            mode = cycle["mode"]
            if mode == "SINGLE":
                ok = run_single(cycle, code_root, cycle_dir, args.resume, args.dry_run)
            elif mode == "INSTRUMENT_TIMEFRAME_MATRIX":
                ok = run_matrix(cycle, code_root, cycle_dir, args.resume, args.dry_run)
            elif mode == "PER_INSTRUMENT":
                ok = run_per_instrument(cycle, code_root, cycle_dir, args.resume, args.dry_run)
            elif mode == "BLOCKED":
                ok = run_blocked(cycle, code_root, cycle_dir, args.resume, args.dry_run)
            else:
                raise ValueError(f"unknown replay mode: {mode}")
        except Exception as exc:
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            print(f"CYCLE {cid:02d} CONTROLLER ERROR: {error}", flush=True)

        status_name = "DRY_RUN_OK" if args.dry_run and ok else ("SUCCESS" if ok else "FAILED")
        status = {
            "cycle": cid,
            "name": cycle["name"],
            "status": status_name,
            "started_at": started,
            "finished_at": now(),
            "error": error,
            "snapshot": snapshot_key,
            "snapshot_commit": snapshot["commit"],
            "json_artifacts": inventory_json_files(cycle_dir),
        }
        save_json(cycle_dir / "cycle_status.json", status)
        summary.append(status)

    counts: dict[str, int] = {}
    for row in summary:
        counts[row["status"]] = counts.get(row["status"], 0) + 1

    final = {
        "finished_at": now(),
        "run_id": args.run_id,
        "from_cycle": args.from_cycle,
        "to_cycle": args.to_cycle,
        "counts": counts,
        "cycles": summary,
    }
    save_json(run_root / "replay_summary.json", final)

    print("", flush=True)
    print("=" * 78, flush=True)
    print("HISTORICAL REPLAY RANGE FINISHED", flush=True)
    print(f"RESULTS: {run_root}", flush=True)
    print(f"COUNTS: {counts}", flush=True)
    print("=" * 78, flush=True)

    failures = [x for x in summary if x["status"] == "FAILED"]
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
