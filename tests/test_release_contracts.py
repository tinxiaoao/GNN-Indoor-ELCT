"""Bounded wrapper contracts; scientific failures are reported separately."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from geo_elct import api
from geo_elct.__main__ import main
from experiments.run_existing_cases import read_cases, run_cases


class ReleaseContracts(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("GEO_ELCT_TEST_TMP", Path(__file__).resolve().parents[1] / "runs"))
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="contract_", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def manifest(self, source_type="annotation_derived", modes=None):
        case = {"name": "supplied_case", "source_type": source_type,
                "modes": modes if modes is not None else ["none"], "sha256": {}}
        for key in ("wall", "icon", "rough"):
            path = self.base / (key + ".bin")
            path.write_bytes(key.encode("ascii"))
            case[key] = path.name
            case["sha256"][key] = hashlib.sha256(path.read_bytes()).hexdigest()
        path = self.base / "cases.json"
        path.write_text(json.dumps({"cases": [case]}), encoding="utf-8")
        return path, case

    def test_default_none_ignores_filename_clues(self):
        with patch("geo_elct.__main__.extract", return_value={}) as extract, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["extract", "--wall", "building_B_full_clean.png", "--icon", "icon.png", "--out", "unwritten"]), 0)
        self.assertEqual(extract.call_args.kwargs["mode"], "none")
        self.assertEqual(extract.call_args.kwargs["source_type"], "unknown")

    def test_three_explicit_mode_identities_forwarded(self):
        for mode in ("none", "legacy_revised", "reference_faithful"):
            with self.subTest(mode=mode), patch("geo_elct.__main__.extract", return_value={}) as extract, redirect_stdout(io.StringIO()):
                main(["extract", "--wall", "wall.png", "--icon", "icon.png", "--out", "unwritten", "--mode", mode])
                self.assertEqual(extract.call_args.kwargs["mode"], mode)

    def test_ambiguous_mode_full_rejected_before_io(self):
        with self.assertRaises(ValueError):
            api.extract("missing_wall", "missing_icon", "missing_rough", "unused", mode="full")

    def test_existing_output_is_preserved(self):
        out = self.base / "old_run"
        out.mkdir()
        marker = out / "user_edit.txt"
        marker.write_text("preserve", encoding="utf-8")
        with patch.object(api, "verify_source_manifest", return_value=[]), patch.object(api, "file_record", return_value={"width": 2, "height": 2}):
            with self.assertRaises(FileExistsError):
                api.extract("wall", "icon", "rough", out)
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")
        self.assertEqual([p.name for p in out.iterdir()], ["user_edit.txt"])

    def test_configuration_reads_mode_and_checks_input_hash(self):
        config = {"schema_version": 1, "extraction": {"mode": "legacy_revised", "lightweight": False},
                  "maps": {key: {"path": key + ".png", "sha256": "expected"} for key in ("wall", "icon", "rough")},
                  "outputs": {"directory": "result"}, "input_source_type": "annotation_derived"}
        path = self.base / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        with patch.object(api, "file_record", return_value={"sha256": "expected", "width": 2, "height": 2}):
            loaded = api.load_case(path)
        self.assertEqual(loaded["mode"], "legacy_revised")
        self.assertEqual(loaded["source_type"], "annotation_derived")
        self.assertEqual(loaded["out"], self.base / "result")
        with patch.object(api, "file_record", return_value={"sha256": "changed", "width": 2, "height": 2}):
            with self.assertRaises(ValueError):
                api.load_case(path)

    def test_unread_numerical_config_overrides_are_rejected(self):
        path = self.base / "config.json"
        path.write_text(json.dumps({"schema_version": 1, "extraction": {"overlap_threshold": 0.1}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            api.load_case(path)

    def test_driver_forwards_source_type_and_explicit_mode(self):
        manifest, _ = self.manifest(modes=["reference_faithful"])
        result = subprocess.CompletedProcess([], 0, "mocked CLI contract; no extraction", "")
        with patch("experiments.run_existing_cases.subprocess.run", return_value=result) as run, redirect_stdout(io.StringIO()):
            report = run_cases(manifest, self.base / "driver_run")
        argv = run.call_args.args[0]
        self.assertEqual(argv[argv.index("--source-type") + 1], "annotation_derived")
        self.assertEqual(argv[argv.index("--mode") + 1], "reference_faithful")
        self.assertNotIn("--reference", argv)
        self.assertEqual(report["execution_count"], 1)

    def test_driver_requires_explicit_modes_and_source_enum(self):
        manifest, _ = self.manifest(modes=[])
        with self.assertRaises(ValueError):
            read_cases(manifest)
        manifest, _ = self.manifest(source_type="unverified_GNN_output")
        with self.assertRaises(ValueError):
            read_cases(manifest)

    def test_driver_rejects_changed_input_before_output(self):
        manifest, case = self.manifest()
        (self.base / case["wall"]).write_bytes(b"changed")
        out = self.base / "must_not_exist"
        with self.assertRaises(ValueError):
            run_cases(manifest, out)
        self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
