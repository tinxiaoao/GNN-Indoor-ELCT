"""Validate C-1 through C-4 inputs before creating outputs or fitting models."""
from __future__ import annotations

import hashlib
import csv
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

CASE_LABELS = ["C-1", "C-2", "C-3", "C-4"]
TX_ROOMS = [1, 2, 4, 8]
FREQUENCIES = [2.4, 5.0, 28.0]
CORE_FILES = ("recovery_config.json", "source.svg", "wi_samples.npz",
              "reference_and_proposed.npz")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def member(folder: Path, relative: str) -> Path:
    path = (folder / relative).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise ValueError("Missing or invalid input file: " + relative)
    return path


def validate_configuration(cfg: dict) -> None:
    if cfg.get("case_labels") != CASE_LABELS or cfg.get("tx_room_ids") != TX_ROOMS:
        raise ValueError("Formal configurations must be C-1={1}, C-2={1,2}, "
                         "C-3={1,2,4}, C-4={1,2,4,8}")
    if cfg.get("case_tx_room_ids") != [TX_ROOMS[:i] for i in range(1, 5)]:
        raise ValueError("Cumulative transmitter configurations differ")
    if cfg.get("validation_status") != "verified_wi_inputs":
        raise ValueError("Verified Room-8 WI inputs are required: actual Tx coordinates, "
                         "2.4/5/28 GHz source projects and received powers, exact Rx "
                         "coordinates, and matching Proposed room ARPs")
    trusted = json.loads((Path(__file__).parent / "inputs/recovery_config.json").read_text(encoding="utf-8"))
    for field in ("svg_sha256", "scale_units_per_m", "P_tx_dBm", "distance_min_m"):
        if cfg.get(field) != trusted[field]:
            raise ValueError("Fixed Building C benchmark setting differs: " + field)
    mapping = lambda config: [(r["room_id"], r["svg_id"]) for r in config.get("rooms", [])]
    if mapping(cfg) != mapping(trusted):
        raise ValueError("Building C room-to-SVG mapping differs from the fixed room identities")
    if cfg.get("coordinate_frame") != "wireless_insite_local_m":
        raise ValueError("Tx and Rx coordinates must use the WI local metre frame")
    try:
        tx = np.asarray(cfg["tx_xyz_m"], dtype=float)
        transform = np.asarray(cfg["wi_to_svg_m"], dtype=float)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Verified transmitter coordinates and WI-to-SVG transform are required") from error
    if tx.shape != (4, 3) or not np.isfinite(tx).all():
        raise ValueError("Four verified Tx xyz coordinates are required; no centroid fallback is used")
    np.testing.assert_allclose(tx[:3], trusted["tx_xyz_m"][:3], rtol=0, atol=1e-9,
                               err_msg="The verified C-1/C-2/C-3 transmitter locations differ")
    if (transform.shape != (3, 3) or not np.isfinite(transform).all()
            or not np.array_equal(transform[2], [0., 0., 1.])
            or not np.allclose(transform[:2, :2].T @ transform[:2, :2], np.eye(2),
                               rtol=0, atol=1e-10)):
        raise ValueError("WI-to-SVG transform must be a verified metre-preserving affine transform")
    if cfg.get("frequency_GHz") != FREQUENCIES:
        raise ValueError("Expected frequencies are 2.4, 5 and 28 GHz")
    if [r["room_id"] for r in cfg.get("rooms", [])] != list(range(1, 19)):
        raise ValueError("Room order must be 1 through 18")
    if not np.isfinite(float(cfg["P_tx_dBm"])):
        raise ValueError("Transmitter power must be finite")
    if not float(cfg["scale_units_per_m"]) > 0 or not float(cfg["distance_min_m"]) > 0:
        raise ValueError("Geometry scale and minimum model distance must be positive")


def _wi_project(path: Path) -> tuple[list[dict], dict[int, np.ndarray]]:
    """Read WI XML Tx coordinates and its explicit/grid Rx coordinates."""
    root = ET.fromstring(path.read_text(encoding="utf-8").replace("::", "__"))
    transmitters = []
    receivers: dict[int, list[np.ndarray]] = {}
    for item in root.iter("TxRxSet"):
        description = item.find(".//ShortDescription")
        if description is None:
            continue
        name = list(description)[0].get("Value", "")
        match = re.fullmatch(r"Room_(\d+)(?:_.*)?", name)
        if not match:
            raise ValueError("Unmapped WI Tx/Rx room name: " + name)
        room = int(match[1])
        points = np.asarray([[float(list(point.find(axis))[0].get("Value"))
                              for axis in ("X", "Y", "Z")]
                             for point in item.iter("remcom__rxapi__CartesianPoint")])
        scalar = lambda key: float(list(item.find(".//" + key))[0].get("Value"))
        if item.find(".//Transmitter") is not None:
            if points.shape != (1, 3):
                raise ValueError("Each transmitter must have exactly one verified location")
            transmitters.append({"room_id": room, "xyz": points[0],
                                 "power": scalar("InputPower"),
                                 "frequency_GHz": scalar("CarrierFrequency") / 1e9})
        elif item.find(".//Receiver") is not None:
            if item.find(".//remcom__rxapi__GridSet") is not None:
                spacing = scalar("Spacing")
                def count(length):
                    quotient = length / spacing
                    nearest = round(quotient)
                    if abs(quotient - nearest) <= 1e-10:
                        quotient = nearest
                    return math.floor(quotient) + 1
                nx = count(scalar("LengthX")); ny = count(scalar("LengthY"))
                xx, yy = np.meshgrid(np.arange(nx) * spacing, np.arange(ny) * spacing)
                angle = math.radians(scalar("PlanarRotation"))
                rotation = np.array([[math.cos(angle), -math.sin(angle)],
                                     [math.sin(angle), math.cos(angle)]])
                xy = np.column_stack((xx.ravel(), yy.ravel())) @ rotation.T + points[0, :2]
                points = np.column_stack((xy, np.full(len(xy), points[0, 2])))
            if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
                raise ValueError("Invalid WI receiver coordinates")
            receivers.setdefault(room, []).append(points)
    return transmitters, {room: np.concatenate(parts) for room, parts in receivers.items()}


def _sorted_xyz(xyz: np.ndarray) -> np.ndarray:
    rounded = np.round(xyz, 8)
    return rounded[np.lexsort((rounded[:, 2], rounded[:, 1], rounded[:, 0]))]


def _csv_rows(folder: Path, paths: list[str], fields: set[str]):
    for name in paths:
        with member(folder, name).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not fields.issubset(reader.fieldnames or []):
                raise ValueError("Missing normalized source-export CSV columns in " + name)
            for row in reader:
                yield row


def _verify_power_exports(folder: Path, paths: list[str], raw: dict) -> None:
    seen = set()
    for row in _csv_rows(folder, paths, {"frequency_GHz", "tx_room", "room", "rx_index", "power_dBm"}):
        fi = FREQUENCIES.index(float(row["frequency_GHz"]))
        ti = TX_ROOMS.index(int(row["tx_room"]))
        room = int(row["room"]); index = int(row["rx_index"]) - 1
        key = (fi, ti, room, index)
        if room not in raw or index not in range(raw[room].shape[2]) or key in seen:
            raise ValueError("Duplicate or invalid source WI frequency/Tx/room/Rx record")
        value = float(row["power_dBm"]); expected = raw[room][fi, ti, index]
        if value != expected and not np.isclose(value, expected, rtol=0, atol=1e-10):
            raise ValueError("WI sample power differs from its source-export CSV")
        seen.add(key)
    if len(seen) != sum(values.size for values in raw.values()):
        raise ValueError("Source WI power exports do not cover every frequency/Tx/Rx sample")


def _verify_proposed_exports(folder: Path, paths: list[str], proposed: np.ndarray) -> None:
    seen = set()
    for row in _csv_rows(folder, paths, {"frequency_GHz", "case", "room", "Proposed_ARP_dBm"}):
        fi = FREQUENCIES.index(float(row["frequency_GHz"]))
        ci = CASE_LABELS.index(row["case"]); room = int(row["room"]) - 1
        key = (fi, ci, room)
        if room not in range(18) or key in seen:
            raise ValueError("Duplicate or invalid source Proposed room record")
        np.testing.assert_allclose(float(row["Proposed_ARP_dBm"]), proposed[fi, ci, room],
                                   rtol=0, atol=1e-10, equal_nan=False,
                                   err_msg="Proposed reference differs from its source-export CSV")
        seen.add(key)
    if len(seen) != proposed.size:
        raise ValueError("Source Proposed exports do not cover every frequency/case/room")


def validate(folder: Path) -> dict:
    folder = folder.resolve()
    config_path = member(folder, "recovery_config.json")
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    # Reject the incomplete distributed template before reading any old arrays.
    validate_configuration(cfg)
    manifest = json.loads(member(folder, "input_manifest.json").read_text(encoding="utf-8"))
    hashes = manifest.get("files", {})
    if not all(name in hashes for name in CORE_FILES):
        raise ValueError("Input manifest must hash the config, SVG, WI samples and room references")
    for name, expected in hashes.items():
        if digest(member(folder, name)) != expected:
            raise ValueError("Input SHA256 mismatch: " + name)
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True,
                                            separators=(",", ":")).encode()).hexdigest()
    if manifest.get("input_fingerprint_sha256") != fingerprint:
        raise ValueError("Input fingerprint differs from the source-file manifest")
    checks = manifest.get("verification", {})
    for name in ("tx_room_membership", "coordinate_transform", "rx_coordinates",
                 "linear_power_aggregation", "proposed_same_configuration"):
        if checks.get(name) is not True:
            raise ValueError("Required input verification is missing: " + name)
    if digest(folder / "source.svg") != cfg.get("svg_sha256"):
        raise ValueError("SVG SHA256 differs from the configuration")

    with np.load(member(folder, "wi_samples.npz"), allow_pickle=False) as samples:
        np.testing.assert_array_equal(samples["frequency_GHz"], FREQUENCIES)
        np.testing.assert_array_equal(samples["tx_room_ids"], TX_ROOMS)
        np.testing.assert_array_equal(samples["tx_xyz_m"], cfg["tx_xyz_m"])
        np.testing.assert_array_equal(samples["room_ids"], np.arange(1, 19))
        rx = {}; raw = {}; target = np.empty((3, 4, 18))
        for room in range(1, 19):
            xyz = samples[f"room{room}_xyz_m"].copy()
            powers = samples[f"room{room}_WI_dBm"]
            if xyz.ndim != 2 or xyz.shape[1] != 3 or len(xyz) == 0 or not np.isfinite(xyz).all():
                raise ValueError(f"Invalid actual receiver list in room {room}")
            if (powers.shape != (3, 4, len(xyz)) or np.isnan(powers).any()
                    or np.isposinf(powers).any()):
                raise ValueError(f"Invalid frequency/Tx/Rx power layout in room {room}")
            linear = np.power(10., powers / 10.)
            target[:, :, room - 1] = 10 * np.log10(np.cumsum(linear, axis=1).mean(axis=2))
            rx[room] = xyz; raw[room] = powers.copy()
    if not np.isfinite(target).all():
        raise ValueError("All 216 cumulative WI room ARPs must be finite")

    projects = manifest.get("wi_projects", [])
    if sorted(p.get("frequency_GHz") for p in projects) != FREQUENCIES:
        raise ValueError("Provide one full C-4 WI XML source project per frequency")
    for project in projects:
        if project["path"] not in hashes:
            raise ValueError("WI project must appear in the hashed input manifest")
        txs, project_rx = _wi_project(member(folder, project["path"]))
        if sorted(t["room_id"] for t in txs) != TX_ROOMS:
            raise ValueError("WI source project must place transmitters in Rooms 1,2,4,8")
        for tx in txs:
            index = TX_ROOMS.index(tx["room_id"])
            np.testing.assert_allclose(tx["xyz"], cfg["tx_xyz_m"][index], rtol=0, atol=1e-9)
            np.testing.assert_allclose(tx["power"], cfg["P_tx_dBm"], rtol=0, atol=1e-12)
            np.testing.assert_allclose(tx["frequency_GHz"], project["frequency_GHz"], rtol=0, atol=1e-12)
        if set(project_rx) != set(rx):
            raise ValueError("WI source receiver rooms differ from the sample arrays")
        for room in rx:
            np.testing.assert_allclose(_sorted_xyz(project_rx[room]), _sorted_xyz(rx[room]),
                                       rtol=0, atol=1e-7,
                                       err_msg=f"Actual WI Rx coordinates differ in room {room}")
    exports = manifest.get("wi_power_exports", [])
    if not exports or any(name not in hashes for name in exports):
        raise ValueError("Hash and retain the original WI received-power exports")
    _verify_power_exports(folder, exports, raw)
    proposed_exports = manifest.get("proposed_exports", [])
    if not proposed_exports or any(name not in hashes for name in proposed_exports):
        raise ValueError("Hash and retain the matching Proposed room-power exports")
    with np.load(member(folder, "reference_and_proposed.npz"), allow_pickle=False) as refs:
        for name, expected in (("frequency_GHz", FREQUENCIES), ("case_labels", CASE_LABELS),
                               ("tx_room_ids", TX_ROOMS), ("tx_xyz_m", cfg["tx_xyz_m"]),
                               ("room_ids", np.arange(1, 19))):
            np.testing.assert_array_equal(refs[name], expected)
        np.testing.assert_allclose(refs["WI_ARP_dBm"], target, rtol=0, atol=1e-10)
        proposed = refs["Proposed_ARP_dBm"].copy()
        if proposed.shape != (3, 4, 18) or not np.isfinite(proposed).all():
            raise ValueError("Matching full-precision Proposed ARPs are required")
    _verify_proposed_exports(folder, proposed_exports, proposed)
    return {"config": cfg, "fingerprint": fingerprint, "hashes": hashes,
            "rx": rx, "WI_ARP_dBm": target, "Proposed_ARP_dBm": proposed,
            "Rx_total": sum(len(points) for points in rx.values())}
