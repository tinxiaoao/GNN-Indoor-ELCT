"""Prepare an authorized source copy or hand existing integer maps to Geo-ELCT."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import zipfile


ARCHIVE_SHA256 = "b52bb52c693d2ce52cd11354a87ffc1250708b7ba5b1dc4ee83829daa0547667"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_source(archive):
    archive = Path(archive)
    digest = sha256(archive)
    with zipfile.ZipFile(archive) as source:
        files = [item for item in source.infolist() if not item.is_dir()]
        names = {item.filename for item in files}
        checkpoints = [item.filename for item in files
                       if PurePosixPath(item.filename).suffix.lower() in
                       {".pth", ".pt", ".ckpt", ".safetensors"}]
    return {"archive_sha256": digest, "matches_audited_archive": digest == ARCHIVE_SHA256,
            "file_count": len(files), "checkpoint_members": checkpoints,
            "actual_entry": "graphgym/main.py" if "VecFloorSeg-master/graphgym/main.py" in names else None,
            "full_inference_status": "NOT_RUN_MISSING_BOUND_GNN_CHECKPOINT_AND_ENVIRONMENT"}


def prepare_source(archive, out):
    archive, out = Path(archive).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError("Choose a new source-copy directory")
    report = inspect_source(archive)
    if not report["matches_audited_archive"]:
        raise ValueError("Archive differs from the audited source; inspect its provenance separately")
    with zipfile.ZipFile(archive) as source:
        plan = []
        for item in source.infolist():
            name = PurePosixPath(item.filename)
            if (name.is_absolute() or ".." in name.parts or "\\" in item.filename
                    or any(":" in part for part in name.parts)
                    or not name.parts or name.parts[0] != "VecFloorSeg-master"
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError("Unsafe archive member")
            if item.is_dir():
                continue
            target = out.joinpath(*name.parts[1:])
            if not target.is_relative_to(out):
                raise ValueError("Archive target escapes the new directory")
            plan.append((item, target))
        out.mkdir(parents=True)
        for item, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    (out / "local_preparation_manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return report


def map_record(path):
    from PIL import Image
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode not in {"P", "L", "I", "I;16"}:
            raise ValueError("Supply an integer-label PNG, not a rendered RGB visualization")
        image.load()
        labels = sorted(set(image.getdata()))
        if any(value < 0 or value > 255 for value in labels):
            raise ValueError("Labels must fit the existing uint8 map interface")
        return {"sha256": sha256(path), "width": image.width, "height": image.height,
                "mode": image.mode, "labels": labels}


def export_maps(wall, icon, rough, source_type, evidence, out):
    wall, icon, out = Path(wall).resolve(), Path(icon).resolve(), Path(out).resolve()
    if out.exists():
        raise FileExistsError("Choose a new map handoff directory")
    records = {"wall": map_record(wall), "icon": map_record(icon)}
    if (records["wall"]["width"], records["wall"]["height"]) != (records["icon"]["width"], records["icon"]["height"]):
        raise ValueError("Wall and icon dimensions differ")
    if source_type == "model_prediction" and evidence is None:
        raise ValueError("Model prediction requires an external inference evidence JSON")
    evidence_data = None
    if evidence is not None:
        evidence_data = json.loads(Path(evidence).read_text(encoding="utf8"))
        for key in ("checkpoint_sha256", "config_sha256", "inference_command"):
            if not isinstance(evidence_data.get(key), str) or not evidence_data[key]:
                raise ValueError("Evidence needs checkpoint_sha256, config_sha256 and inference_command")
        for key in ("checkpoint_sha256", "config_sha256"):
            value = evidence_data[key]
            if len(value) != 64 or any(char not in "0123456789abcdefABCDEF" for char in value):
                raise ValueError("Evidence hash must be SHA256")
    if rough is not None:
        from PIL import Image
        with Image.open(rough) as background:
            if background.size != (records["wall"]["width"], records["wall"]["height"]):
                raise ValueError("Background dimensions differ")
    out.mkdir(parents=True)
    for source, name in [(wall, "wall_svg.png"), (icon, "icon_svg.png")]:
        shutil.copyfile(source, out / name)
    if rough is not None:
        shutil.copyfile(rough, out / "svgImg_roughcast.png")
    report = {"operation": "byte_preserving_existing_map_handoff", "source_type_declared": source_type,
              "maps": records, "inference_run_here": False, "resizing_or_label_remapping": False,
              "external_evidence_verified": False, "external_evidence": evidence_data}
    (out / "map_handoff.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["inspect-source", "prepare-source"]:
        item = sub.add_parser(command)
        item.add_argument("--archive", type=Path, required=True)
        if command == "prepare-source":
            item.add_argument("--out", type=Path, required=True)
    maps = sub.add_parser("export-maps", help="Copy existing label maps; does not perform GNN inference")
    for name in ["wall", "icon", "out"]:
        maps.add_argument("--" + name, type=Path, required=True)
    maps.add_argument("--rough", type=Path)
    maps.add_argument("--source-type", choices=["unknown", "annotation_derived", "model_prediction"], required=True)
    maps.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect-source":
            result = inspect_source(args.archive)
        elif args.command == "prepare-source":
            result = prepare_source(args.archive, args.out)
        else:
            result = export_maps(args.wall, args.icon, args.rough, args.source_type, args.evidence, args.out)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(2, f"{type(error).__name__}: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
