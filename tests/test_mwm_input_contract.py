"""Exercise external-input boundaries with synthetic, temporary source files."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mwm_contract", ROOT / "benchmarks/mwm/input_contract.py")
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def configuration():
    tx_rooms = [16, 9, 3, 12]
    return {
        "case_labels": ["single", "pair", "triple", "combined"],
        "tx_room_ids": tx_rooms,
        "case_tx_room_ids": [tx_rooms[:i] for i in range(1, 5)],
        "frequency_GHz": [2.4, 5.0, 28.0],
        "validation_status": "verified_wi_inputs",
        "svg": "source.svg", "svg_sha256": "a" * 64,
        "coordinate_frame": "wireless_insite_local_m",
        "tx_xyz_m": [[1., 2., 1.5], [3., 4., 1.5], [5., 6., 1.5], [7., 8., 1.5]],
        "wi_to_svg_m": [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
        "P_tx_dBm": 15., "scale_units_per_m": 1., "distance_min_m": 1.,
        "rooms": [{"room_id": r, "svg_id": f"space-{r}"} for r in range(1, 19)],
    }


def refresh_manifest(folder):
    path = folder / "input_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"] = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                         for name in manifest["files"]}
    manifest["input_fingerprint_sha256"] = hashlib.sha256(json.dumps(
        manifest["files"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")


def make_bundle(folder):
    cfg = configuration()
    centres = {room: (float(50 + room * 4), 0.) for room in range(1, 19)}
    centres.update({room: tuple(xyz[:2]) for room, xyz in zip(cfg["tx_room_ids"], cfg["tx_xyz_m"])})
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg")
    for room, (x, y) in centres.items():
        space = ET.SubElement(svg, "g", {"class": "Space", "id": f"space-{room}"})
        points = " ".join(f"{a},{b}" for a, b in ((x-.4, y-.4), (x+.4, y-.4),
                                                   (x+.4, y+.4), (x-.4, y+.4)))
        ET.SubElement(space, "polygon", points=points)
    ET.ElementTree(svg).write(folder / "source.svg", encoding="utf-8")
    cfg["svg_sha256"] = hashlib.sha256((folder / "source.svg").read_bytes()).hexdigest()
    (folder / "recovery_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    metadata = {"frequency_GHz": np.asarray(cfg["frequency_GHz"]),
                "tx_room_ids": np.asarray(cfg["tx_room_ids"]),
                "tx_xyz_m": np.asarray(cfg["tx_xyz_m"]), "room_ids": np.arange(1, 19)}
    samples = dict(metadata)
    targets = np.empty((3, 4, 18))
    export_rows = []
    for room in range(1, 19):
        powers = np.asarray([[[-40. - room - fi - ti] for ti in range(4)] for fi in range(3)])
        samples[f"room{room}_xyz_m"] = np.asarray([[*centres[room], 1.]])
        samples[f"room{room}_WI_dBm"] = powers
        targets[:, :, room - 1] = 10 * np.log10(np.cumsum(10. ** (powers / 10.), axis=1).mean(axis=2))
        for fi, frequency in enumerate(cfg["frequency_GHz"]):
            for ti, tx_room in enumerate(cfg["tx_room_ids"]):
                export_rows.append([frequency, tx_room, room, 1, powers[fi, ti, 0]])
    np.savez(folder / "wi_samples.npz", **samples)
    np.savez(folder / "reference_and_proposed.npz", **metadata,
             case_labels=np.asarray(cfg["case_labels"]), WI_ARP_dBm=targets, Proposed_ARP_dBm=targets)
    with (folder / "powers.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_GHz", "tx_room", "room", "rx_index", "power_dBm"])
        writer.writerows(export_rows)
    with (folder / "proposed.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_GHz", "case", "room", "Proposed_ARP_dBm"])
        writer.writerows([frequency, case, room, targets[fi, ci, room - 1]]
                         for fi, frequency in enumerate(cfg["frequency_GHz"])
                         for ci, case in enumerate(cfg["case_labels"]) for room in range(1, 19))
    projects = []
    for index, frequency in enumerate(cfg["frequency_GHz"]):
        root = ET.Element("Project")
        def entry(room, xyz, transmitter=False):
            item = ET.SubElement(root, "TxRxSet")
            ET.SubElement(ET.SubElement(item, "ShortDescription"), "String", Value=f"Room_{room}")
            ET.SubElement(item, "Transmitter" if transmitter else "Receiver")
            point = ET.SubElement(item, "remcom__rxapi__CartesianPoint")
            for axis, value in zip(("X", "Y", "Z"), xyz):
                ET.SubElement(ET.SubElement(point, axis), "Double", Value=str(value))
            if transmitter:
                for key, value in (("InputPower", cfg["P_tx_dBm"]), ("CarrierFrequency", frequency * 1e9)):
                    ET.SubElement(ET.SubElement(item, key), "Double", Value=str(value))
        for room, xyz in zip(cfg["tx_room_ids"], cfg["tx_xyz_m"]):
            entry(room, xyz, True)
        for room in range(1, 19):
            entry(room, [*centres[room], 1.])
        name = f"project-{index}.xml"
        ET.ElementTree(root).write(folder / name, encoding="utf-8")
        projects.append({"frequency_GHz": frequency, "path": name})
    names = [*CONTRACT.CORE_FILES, "powers.csv", "proposed.csv", *(p["path"] for p in projects)]
    manifest = {"files": {name: "" for name in names}, "wi_projects": projects,
                "wi_power_exports": ["powers.csv"], "proposed_exports": ["proposed.csv"],
                "verification": {name: True for name in ("tx_room_membership", "coordinate_transform",
                    "rx_coordinates", "linear_power_aggregation", "proposed_same_configuration")}}
    (folder / "input_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    refresh_manifest(folder)
    return cfg


class MWMExternalInputContractTests(unittest.TestCase):
    def test_configuration_accepts_external_labels_and_transmitter_order(self):
        CONTRACT.validate_configuration(configuration())

    def test_invalid_metadata_and_numerical_fields_are_rejected(self):
        invalid = [
            ("case_labels", ["same"] * 4), ("case_labels", ["one", "two", "three", ""]),
            ("tx_room_ids", [1, 2, 3, 19]), ("tx_room_ids", [1, 2, 3, True]),
            ("tx_room_ids", [1, 2, 3, 3]), ("case_tx_room_ids", [[16]] * 4),
            ("svg", "different.svg"), ("svg_sha256", "not-a-sha"), ("validation_status", "pending"),
            ("tx_xyz_m", [[1, 2, 3]] * 3), ("tx_xyz_m", [[1, 2, float("nan")]] * 4),
            ("tx_xyz_m", [[1, 2, "3"]] * 4),
            ("wi_to_svg_m", [[2, 0, 0], [0, 2, 0], [0, 0, 1]]),
            ("wi_to_svg_m", [[1, 0, 0], [0, 1, 0], [0.1, 0, 1]]),
            ("P_tx_dBm", float("inf")), ("scale_units_per_m", float("inf")),
            ("scale_units_per_m", True), ("distance_min_m", 0),
        ]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                cfg = configuration()
                cfg[field] = value
                with self.assertRaises(ValueError):
                    CONTRACT.validate_configuration(cfg)
        for field, value in (("room_id", 1), ("svg_id", "space-1")):
            cfg = configuration()
            cfg["rooms"][-1][field] = value
            with self.subTest(room_field=field), self.assertRaises(ValueError):
                CONTRACT.validate_configuration(cfg)

    def test_external_bundle_has_consistent_custom_metadata(self):
        with tempfile.TemporaryDirectory(prefix="mwm-input-test-") as temporary:
            folder = Path(temporary)
            cfg = make_bundle(folder)
            checked = CONTRACT.validate(folder)
            self.assertEqual(checked["config"]["tx_room_ids"], cfg["tx_room_ids"])
            self.assertEqual(checked["config"]["case_labels"], cfg["case_labels"])
            self.assertEqual(checked["Rx_total"], 18)

    def test_matching_hashes_do_not_replace_source_coordinate_checks(self):
        with tempfile.TemporaryDirectory(prefix="mwm-input-test-") as temporary:
            folder = Path(temporary)
            make_bundle(folder)
            path = folder / "project-0.xml"
            tree = ET.parse(path)
            tree.find(".//remcom__rxapi__CartesianPoint/X/Double").set("Value", "999")
            tree.write(path, encoding="utf-8")
            refresh_manifest(folder)
            with self.assertRaises(AssertionError):
                CONTRACT.validate(folder)

    def test_modified_file_fails_its_real_source_hash(self):
        with tempfile.TemporaryDirectory(prefix="mwm-input-test-") as temporary:
            folder = Path(temporary)
            make_bundle(folder)
            with (folder / "powers.csv").open("a", encoding="utf-8") as stream:
                stream.write("unexpected source change\n")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                CONTRACT.validate(folder)

    def test_cli_requires_an_external_input_directory(self):
        program = ROOT / "benchmarks/mwm/run.py"
        help_result = subprocess.run([sys.executable, "-B", str(program), "--help"],
                                     capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        missing = subprocess.run([sys.executable, "-B", str(program)], capture_output=True, text=True)
        self.assertEqual(missing.returncode, 2)
        self.assertIn("--inputs", missing.stderr)


if __name__ == "__main__":
    unittest.main()
