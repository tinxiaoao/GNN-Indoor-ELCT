"""Run only manifest-listed existing inputs; never generate or select perturbations.

The manifest is local user data, not a shipped dataset. Paths resolve relative to
its directory. Expected SHA256 values bind the case to the selected input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MODES = ("none", "legacy_revised", "reference_faithful", "correction_v2")
SOURCE_TYPES = ("unknown", "annotation_derived", "model_prediction")
PROJECT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_cases(manifest: Path) -> list[dict]:
    payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
    cases = payload["cases"]
    if not cases:
        raise ValueError("The manifest contains no cases")
    names = set()
    for case in cases:
        name = case["name"]
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in name):
            raise ValueError(f"Unsafe case name: {name!r}")
        if name in names:
            raise ValueError(f"Duplicate case name: {name}")
        names.add(name)
        if case.get("source_type", "unknown") not in SOURCE_TYPES:
            raise ValueError(f"Unknown source_type for {name}; retain perturbation lineage in a separate field")
        if not case.get("modes") or any(mode not in MODES for mode in case["modes"]):
            raise ValueError(f"Case {name} requires explicit modes chosen from {MODES}")
        if len(case["modes"]) != len(set(case["modes"])):
            raise ValueError(f"Repeated modes in {name}")
        resolved = {}
        for field in ("wall", "icon", "rough"):
            path = (manifest.parent / case[field]).resolve()
            actual = sha256(path)
            if actual != case["sha256"][field]:
                raise ValueError(f"SHA256 mismatch for {name}/{field}")
            resolved[field] = str(path)
        case["resolved_inputs"] = resolved
    return cases


def run_cases(manifest: Path, out: Path, python: str = sys.executable,
              opening_aggregation: str = "by_thickness_v1") -> dict:
    if opening_aggregation not in ("by_thickness_v1", "legacy_width_sum"):
        raise ValueError("Unknown opening aggregation")
    manifest, out = manifest.resolve(), out.resolve()
    cases = read_cases(manifest)
    # Protect all previous output, including user edits and incomplete runs.
    out.mkdir(parents=True, exist_ok=False)
    (out / "logs").mkdir()
    (out / "environment").mkdir()
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", MPLBACKEND="Agg",
               MPLCONFIGDIR=str(out / "environment" / "matplotlib"))
    records = []
    for case in cases:
        for mode in case["modes"]:
            run = out / "runs" / case["name"] / mode
            command = [python, "-B", "-m", "geo_elct", "extract", "--mode", mode,
                       "--opening-aggregation", opening_aggregation,
                       "--source-type", case.get("source_type", "unknown")]
            for field in ("wall", "icon", "rough"):
                path = Path(case["resolved_inputs"][field])
                if sha256(path) != case["sha256"][field]:
                    raise ValueError(f"Input changed during suite: {case['name']}/{field}")
                command.extend(["--" + field, str(path)])
            command.extend(["--out", str(run)])
            started = time.perf_counter()
            completed = subprocess.run(command, cwd=PROJECT, env=env, text=True,
                                       encoding="utf-8", errors="replace", capture_output=True)
            log = out / "logs" / f"{case['name']}_{mode}.log"
            log.write_text(completed.stdout + "\n[stderr]\n" + completed.stderr, encoding="utf-8")
            record = {"case": case["name"], "sample_id": case.get("sample_id"),
                      "source_type": case.get("source_type", "unknown"), "mode": mode,
                      "command": command, "cwd": str(PROJECT), "out": str(run),
                      "elapsed_seconds": time.perf_counter() - started,
                      "returncode": completed.returncode, "log": str(log),
                      "input_sha256": case["sha256"]}
            records.append(record)
            (out / "commands.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
            print(json.dumps({k: record[k] for k in ("case", "mode", "returncode", "elapsed_seconds")}), flush=True)
    report = {"manifest_sha256": sha256(manifest), "case_count": len(cases),
              "opening_aggregation": opening_aggregation,
              "execution_count": len(records),
              "execution_success_count": sum(row["returncode"] == 0 for row in records),
              "interpretation": "Process exit success is not a geometry, topology, or table correctness result.",
              "commands": records}
    (out / "execution_summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--opening-aggregation", choices=("by_thickness_v1", "legacy_width_sum"),
                        default="by_thickness_v1")
    args = parser.parse_args()
    result = run_cases(args.manifest, args.out, args.python, args.opening_aggregation)
    return 0 if result["execution_count"] == result["execution_success_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
