from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "results" / "intel_replay_1_31" / "_fenced_data"
DEFAULT_OUTPUT = ROOT / "results" / "cycle35_opening_range_structure"
ENGINE = ROOT / "research" / "cycle35_opening_range_structure.py"
INSTRUMENTS = ("CNYRUBF", "USDRUBF")


def run_one(data_root: Path, output_root: Path, instrument: str) -> dict:
    out = output_root / instrument
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-u",
        str(ENGINE),
        "--data-root",
        str(data_root),
        "--instrument",
        instrument,
        "--output",
        str(out),
    ]
    print("\n" + "=" * 78, flush=True)
    print(f"CYCLE35 {instrument}", flush=True)
    print("=" * 78, flush=True)
    print(subprocess.list2cmdline(cmd), flush=True)
    log_path = out / "console.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Cycle35 {instrument} failed rc={proc.returncode}; see {log_path}")

    manifest_path = out / "run_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = {
        "status": manifest["status"],
        "generated": manifest["generated_candidate_evaluations"],
        "deduped": manifest["deduped_discovery_candidates"],
        "discovery_passes": manifest["discovery_passes"],
        "shortlisted": manifest["shortlisted"],
        "survivors": manifest["survivors"],
    }
    print(json.dumps({instrument: row}, indent=2), flush=True)
    return row


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    a = p.parse_args()

    if not ENGINE.exists():
        raise FileNotFoundError(ENGINE)
    if not a.data_root.exists():
        raise FileNotFoundError(
            f"Fenced data root not found: {a.data_root}. Run the Cycle1-31 Intel replay first or pass --data-root."
        )

    a.output.mkdir(parents=True, exist_ok=True)
    results = {}
    for instrument in INSTRUMENTS:
        results[instrument] = run_one(a.data_root, a.output, instrument)

    summary = {
        "cycle": 35,
        "data_root": str(a.data_root),
        "protocol": "research/CYCLE35_PROTOCOL.md",
        "engine": "research/cycle35_opening_range_structure.py",
        "results": results,
    }
    summary_path = a.output / "cycle35_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print("\n" + "=" * 78, flush=True)
    print("CYCLE35 FINISHED", flush=True)
    print(f"RESULTS {a.output}", flush=True)
    print(json.dumps(results, indent=2), flush=True)
    print("=" * 78, flush=True)


if __name__ == "__main__":
    main()
