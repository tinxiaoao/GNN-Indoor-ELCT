"""Validate an external MWM input bundle before creating outputs or fitting models."""
from __future__ import annotations

import hashlib
import csv
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np

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
    if not isinstance(cfg, dict):
        raise ValueError("The configuration must be a JSON object")
    labels = cfg.get("case_labels")
    if (not isinstance(labels, list) or len(labels) != 4
            or any(not isinstance(label, str) or not label.strip()
                   or any(character in label for character in "\r\n\0") for label in labels)
            or len(set(labels)) != 4):
        raise ValueError("Provide four unique, nonempty case labels")
    tx_rooms = cfg.get("tx_room_ids")
    if (not isinstance(tx_rooms, list) or len(tx_rooms) != 4
            or any(type(room) is not int or room not in range(1, 19) for room in tx_rooms)
            or len(set(tx_rooms)) != 4):
        raise ValueError("Provide four unique transmitter room IDs from 1 through 18")
    cases = cfg.get("case_tx_room_ids")
    if (not isinstance(cases, list) or len(cases) != 4
            or any(not isinstance(case, list) or any(type(room) is not int for room in case)
                   for case in cases)
            or cases != [tx_rooms[:i] for i in range(1, 5)]):
        raise ValueError("Cumulative transmitter configurations differ from the declared Tx order")
    if cfg.get("validation_status") != "verified_wi_inputs":
        raise ValueError("Provide verified source projects, Tx/Rx coordinates and room references")
    if cfg.get("svg") != "source.svg":
        raise ValueError("The configured source geometry must be source.svg")
    if not isinstance(cfg.get("svg_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", cfg["svg_sha256"]):
        raise ValueError("Provide the lowercase SHA256 of source.svg")
    rooms = cfg.get("rooms")
    if (not isinstance(rooms, list) or len(rooms) != 18
            or any(not isinstance(record, dict) or type(record.get("room_id")) is not int
                   for record in rooms)
            or [record["room_id"] for record in rooms] != list(range(1, 19))):
        raise ValueError("Room records must appear in order 1 through 18")
    svg_ids = [record.get("svg_id") for record in rooms]
    if (any(not isinstance(identifier, str) or not identifier.strip() for identifier in svg_ids)
            or len(set(svg_ids)) != 18):
        raise ValueError("Map every room to a unique, nonempty SVG polygon ID")
    if cfg.get("coordinate_frame") != "wireless_insite_local_m":
        raise ValueError("Tx and Rx coordinates must use the WI local metre frame")
    def numeric_matrix(field: str, rows: int, columns: int) -> np.ndarray:
        values = cfg[field]
        if (not isinstance(values, list) or len(values) != rows
                or any(not isinstance(row, list) or len(row) != columns
                       or any(type(value) not in (int, float) for value in row) for row in values)):
            raise ValueError("Invalid numeric matrix: " + field)
        return np.asarray(values, dtype=float)
    try:
        tx = numeric_matrix("tx_xyz_m", 4, 3)
        transform = numeric_matrix("wi_to_svg_m", 3, 3)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        raise ValueError("Provide transmitter coordinates and the WI-to-SVG transform") from error
    if tx.shape != (4, 3) or not np.isfinite(tx).all():
        raise ValueError("Provide four finite Tx xyz coordinates")
    if (transform.shape != (3, 3) or not np.isfinite(transform).all()
            or not np.array_equal(transform[2], [0., 0., 1.])
            or not np.allclose(transform[:2, :2].T @ transform[:2, :2], np.eye(2),
                               rtol=0, atol=1e-10)):
        raise ValueError("WI-to-SVG transform must be a metre-preserving affine transform")
    if cfg.get("frequency_GHz") != FREQUENCIES:
        raise ValueError("Expected frequencies are 2.4, 5 and 28 GHz")
    for field in ("P_tx_dBm", "scale_units_per_m", "distance_min_m"):
        value = cfg.get(field)
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise ValueError("Provide a finite numeric configuration field: " + field)
        if field != "P_tx_dBm" and value <= 0:
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


def _verify_power_exports(folder: Path, paths: list[str], raw: dict, tx_rooms: list[int]) -> None:
    seen = set()
    for row in _csv_rows(folder, paths, {"frequency_GHz", "tx_room", "room", "rx_index", "power_dBm"}):
        fi = FREQUENCIES.index(float(row["frequency_GHz"]))
        ti = tx_rooms.index(int(row["tx_room"]))
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


def _verify_proposed_exports(folder: Path, paths: list[str], proposed: np.ndarray,
                             case_labels: list[str]) -> None:
    seen = set()
    for row in _csv_rows(folder, paths, {"frequency_GHz", "case", "room", "Proposed_ARP_dBm"}):
        fi = FREQUENCIES.index(float(row["frequency_GHz"]))
        ci = case_labels.index(row["case"]); room = int(row["room"]) - 1
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
    validate_configuration(cfg)
    tx_rooms = cfg["tx_room_ids"]
    case_labels = cfg["case_labels"]
    manifest = json.loads(member(folder, "input_manifest.json").read_text(encoding="utf-8"))
    hashes = manifest.get("files", {})
    if not isinstance(hashes, dict) or not all(name in hashes for name in CORE_FILES):
        raise ValueError("Input manifest must hash the config, SVG, WI samples and room references")
    for name, expected in hashes.items():
        if not isinstance(name, str) or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Input manifest entries require relative paths and lowercase SHA256 hashes")
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
        np.testing.assert_array_equal(samples["tx_room_ids"], tx_rooms)
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
        raise ValueError("Provide one complete WI XML source project per frequency")
    for project in projects:
        if project["path"] not in hashes:
            raise ValueError("WI project must appear in the hashed input manifest")
        txs, project_rx = _wi_project(member(folder, project["path"]))
        if sorted(t["room_id"] for t in txs) != sorted(tx_rooms):
            raise ValueError("WI source transmitter rooms must match the declared Tx room IDs")
        for tx in txs:
            index = tx_rooms.index(tx["room_id"])
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
    _verify_power_exports(folder, exports, raw, tx_rooms)
    proposed_exports = manifest.get("proposed_exports", [])
    if not proposed_exports or any(name not in hashes for name in proposed_exports):
        raise ValueError("Hash and retain the matching Proposed room-power exports")
    with np.load(member(folder, "reference_and_proposed.npz"), allow_pickle=False) as refs:
        for name, expected in (("frequency_GHz", FREQUENCIES), ("case_labels", case_labels),
                               ("tx_room_ids", tx_rooms), ("tx_xyz_m", cfg["tx_xyz_m"]),
                               ("room_ids", np.arange(1, 19))):
            np.testing.assert_array_equal(refs[name], expected)
        np.testing.assert_allclose(refs["WI_ARP_dBm"], target, rtol=0, atol=1e-10)
        proposed = refs["Proposed_ARP_dBm"].copy()
        if proposed.shape != (3, 4, 18) or not np.isfinite(proposed).all():
            raise ValueError("Matching full-precision Proposed ARPs are required")
    _verify_proposed_exports(folder, proposed_exports, proposed, case_labels)
    return {"config": cfg, "fingerprint": fingerprint, "hashes": hashes,
            "rx": rx, "WI_ARP_dBm": target, "Proposed_ARP_dBm": proposed,
            "Rx_total": sum(len(points) for points in rx.values())}
