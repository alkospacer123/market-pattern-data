from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_engine():
    path = ROOT / "research" / "cycle33_completed_h1_regime.py"
    spec = importlib.util.spec_from_file_location("cycle33_completed_h1_regime", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=ROOT / "results" / "intel_replay_1_31" / "_fenced_data",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "cycle33_completed_h1_regime",
    )
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    output = args.output.resolve()
    if not data_root.exists():
        raise FileNotFoundError(
            f"fenced data root not found: {data_root}. "
            "Pass --data-root pointing to the Cycle1-31 fenced mirror."
        )
    if (data_root / "2025").exists():
        raise PermissionError("TRUE OOS 2025 must remain sealed")

    engine = load_engine()
    output.mkdir(parents=True, exist_ok=True)

    summary = {"cycle": 33, "data_root": str(data_root), "results": {}}
    for instrument in ("CNYRUBF", "USDRUBF"):
        out = output / instrument
        print("=" * 78, flush=True)
        print(f"CYCLE 33 {instrument}", flush=True)
        print("=" * 78, flush=True)
        engine.run(data_root, instrument, out)
        manifest = json.loads((out / "run_manifest.json").read_text(encoding="utf-8"))
        summary["results"][instrument] = {
            "status": manifest["status"],
            "generated": manifest["generated_candidate_evaluations"],
            "deduped": manifest["deduped_discovery_candidates"],
            "discovery_passes": manifest["discovery_passes"],
            "shortlisted": manifest["shortlisted"],
            "survivors": manifest["survivors"],
        }

    (output / "cycle33_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("=" * 78, flush=True)
    print("CYCLE 33 FINISHED", flush=True)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
