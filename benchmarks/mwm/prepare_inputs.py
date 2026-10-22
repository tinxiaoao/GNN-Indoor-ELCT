"""Extract the exact authorized local Part C inputs into a new directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def prepare(archive: Path, output: Path) -> dict:
    specification = json.loads(Path(__file__).with_name("external_inputs.json").read_text())
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != specification["archive_sha256"]:
        raise ValueError("Source package SHA256 differs from the confirmed handoff")
    if output.exists():
        raise FileExistsError("Choose a new output directory; existing inputs are never overwritten")
    # Read and verify every whitelisted member before creating the output.
    extracted = {}
    with zipfile.ZipFile(archive) as package:
        for relative, expected in specification["files"].items():
            content = package.read(specification["archive_prefix"] + relative)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Input SHA256 mismatch: " + relative)
            extracted[Path(relative).name] = content
    output.mkdir(parents=True, exist_ok=False)
    for name, content in extracted.items():
        (output / name).write_bytes(content)
    receipt = {"archive_sha256": actual, "files": specification["files"]}
    (output / "preparation_receipt.json").write_text(json.dumps(receipt, indent=2))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-package", required=True, type=Path,
                        help="Authorized local R1Q6_WI_Confirmed_Reproducible.zip")
    parser.add_argument("--output", required=True, type=Path, help="New local input directory")
    args = parser.parse_args()
    receipt = prepare(args.source_package.resolve(), args.output.resolve())
    print(json.dumps({"verified_input_files": len(receipt["files"]),
                      "archive_sha256": receipt["archive_sha256"]}, indent=2))
