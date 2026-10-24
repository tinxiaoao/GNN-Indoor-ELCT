"""Run the unchanged Part C calculation in a new disposable work directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main(inputs: Path, output: Path) -> int:
    package = Path(__file__).resolve().parent
    spec = json.loads((package / "external_inputs.json").read_text())
    # The declared input hashes prevent silently using another MWM branch.
    for relative, expected in spec["files"].items():
        path = inputs / Path(relative).name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Confirmed input SHA256 mismatch: " + path.name)
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing results are never overwritten")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(inputs, output / "inputs")
    shutil.copytree(package / "results", output / "results")
    shutil.copytree(package / "code", output / "code", ignore=shutil.ignore_patterns("__pycache__"))
    command = [sys.executable, "-B", "code/recalculate.py", "--root", "."]
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    process = subprocess.run(command, cwd=output, env=environment, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / "run.log").write_text(process.stdout, encoding="utf-8")
    (output / "run_receipt.json").write_text(json.dumps({
        "command": command, "cwd": str(output), "python": sys.version,
        "returncode": process.returncode, "inputs": spec["files"],
        "output_sha256": {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted((output / "replayed").glob("*")) if p.is_file()},
    }, indent=2), encoding="utf-8")
    print(process.stdout, end="")
    return process.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path,
                        help="Exact local inputs produced by prepare_inputs.py")
    parser.add_argument("--output", required=True, type=Path, help="New calculation work directory")
    args = parser.parse_args()
    raise SystemExit(main(args.inputs.resolve(), args.output.resolve()))
