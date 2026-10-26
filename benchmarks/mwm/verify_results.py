"""Verify full-precision room errors and selection rules in a user-generated run."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from input_contract import FREQUENCIES, validate_configuration


def verify(folder: Path) -> dict:
    receipt = json.loads((folder / "run_receipt.json").read_text(encoding="utf-8"))
    source_hashes = receipt["input_sha256"]
    source_fingerprint = hashlib.sha256(json.dumps(source_hashes, sort_keys=True,
                                                   separators=(",", ":")).encode()).hexdigest()
    if source_fingerprint != receipt["input_fingerprint_sha256"]:
        raise ValueError("Run receipt input fingerprint differs")
    for name, expected in receipt["output_sha256"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Output file differs from its run receipt: " + name)
    for name, expected in receipt["derived_input_sha256"].items():
        path = (folder / "inputs" / name).resolve()
        if not path.is_relative_to((folder / "inputs").resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Derived input differs from its run receipt: " + name)
    for name in ("recovery_config.json", "source.svg", "reference_and_proposed.npz"):
        if receipt["derived_input_sha256"].get(name) != source_hashes[name]:
            raise ValueError("Prepared input differs from its source fingerprint: " + name)
    config = json.loads((folder / "inputs/recovery_config.json").read_text(encoding="utf-8"))
    validate_configuration(config)
    case_labels = config["case_labels"]
    tx_rooms = config["tx_room_ids"]
    with np.load(folder / "results.npz", allow_pickle=False) as result:
        for name, expected in (("frequency_GHz", FREQUENCIES), ("case_labels", case_labels),
                               ("tx_room_ids", tx_rooms), ("room_ids", np.arange(1, 19))):
            np.testing.assert_array_equal(result[name], expected)
        predicted = result["MWM_ARP_dBm"]; target = result["WI_ARP_dBm"]
        parameters = result["parameters"]; proposed = result["Proposed_ARP_dBm"]
        tx = result["tx_xyz_m"]
        if predicted.shape != (3, 4, 4, 18) or target.shape != (3, 4, 18) or parameters.shape != (3, 4, 4):
            raise ValueError("Invalid prediction, reference or parameter dimensions")
        if proposed.shape != (3, 4, 18) or tx.shape != (4, 3):
            raise ValueError("Invalid Proposed reference or transmitter dimensions")
        if not all(np.isfinite(a).all() for a in (predicted, target, parameters, proposed, tx)):
            raise ValueError("Nonfinite calculation results")
        error = np.abs(predicted - target[:, None]); mean = error.sum(axis=3) / 18
        np.testing.assert_allclose(result["MWM_AE_dB"], error, rtol=0, atol=1e-12)
        np.testing.assert_allclose(result["MWM_MAE_dB"], mean, rtol=0, atol=1e-12)
        proposed_mae = np.abs(proposed - target).mean(axis=-1)
        fingerprint = str(result["input_fingerprint_sha256"].item())
        if fingerprint != source_fingerprint:
            raise ValueError("Results and run receipt use different input fingerprints")
        np.testing.assert_array_equal(tx, config["tx_xyz_m"])
    with (folder / "Table_R2_fullprecision.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 12:
        raise ValueError("Expected twelve calibration rows in Table R2")
    table = []
    for fi, frequency in enumerate(FREQUENCIES):
        for ci, label in enumerate(case_labels):
            row = rows[fi * 4 + ci]
            if float(row["frequency_GHz"]) != frequency or row["calibration"] != label:
                raise ValueError("Table R2 row labels or frequencies differ")
            table.append([float(row[f"MAE_{case}_dB"]) for case in case_labels])
    np.testing.assert_allclose(np.asarray(table).reshape(3, 4, 4), mean, rtol=0, atol=1e-12)
    for include_diagonal, name in ((False, "best_observed_vs_proposed.csv"),
                                    (True, "best_including_diagonal_vs_proposed.csv")):
        with (folder / name).open(encoding="utf-8-sig", newline="") as stream:
            best = list(csv.DictReader(stream))
        if len(best) != 12:
            raise ValueError("Expected twelve best-model comparison rows")
        for fi, frequency in enumerate(FREQUENCIES):
            for ej, case in enumerate(case_labels):
                row = best[fi * 4 + ej]
                options = [ci for ci in range(4) if include_diagonal or ci != ej]
                selected = min(options, key=lambda ci: mean[fi, ci, ej])
                if (float(row["frequency_GHz"]) != frequency or row["evaluation_case"] != case
                        or row["calibration_source"] != case_labels[selected]):
                    raise ValueError("Best-model comparison labels differ")
                for field, expected in (("MWM_MAE_dB", mean[fi, selected, ej]),
                                         ("Proposed_MAE_dB", proposed_mae[fi, ej]),
                                         ("gap_dB", mean[fi, selected, ej] - proposed_mae[fi, ej])):
                    np.testing.assert_allclose(float(row[field]), expected, rtol=0, atol=1e-12)
    with (folder / "matched_comparisons.csv").open(encoding="utf-8-sig", newline="") as stream:
        matched = list(csv.DictReader(stream))
    expected_rows = [(fi, ci, ej) for fi in range(3) for ej in (1, 2, 3)
                     for ci in (1, 2, 3) if ci != ej]
    if len(matched) != len(expected_rows):
        raise ValueError("Expected eighteen matched-comparison rows")
    for row, (fi, ci, ej) in zip(matched, expected_rows):
        if (float(row["frequency_GHz"]) != FREQUENCIES[fi]
                or row["evaluation_case"] != case_labels[ej]
                or row["calibration_source"] != case_labels[ci]):
            raise ValueError("Matched-comparison labels differ")
        baseline = mean[fi, 0, ej]; alternative = mean[fi, ci, ej]
        reduction = baseline - alternative
        for field, expected in (("C1_MAE_dB", baseline), ("alternative_MAE_dB", alternative),
                                 ("reduction_dB", reduction)):
            np.testing.assert_allclose(float(row[field]), expected, rtol=0, atol=1e-12)
        if baseline:
            np.testing.assert_allclose(float(row["reduction_percent"]), 100 * reduction / baseline,
                                       rtol=0, atol=1e-12)
        elif row["reduction_percent"] != "":
            raise ValueError("A zero baseline must leave percentage reduction unavailable")
    return {"room_predictions": int(predicted.size), "MAE_matrix_entries": int(mean.size),
            "averaged_rooms": 18, "input_fingerprint_sha256": fingerprint}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path, help="New result directory")
    args = parser.parse_args()
    print(json.dumps(verify(args.results.resolve()), indent=2))
