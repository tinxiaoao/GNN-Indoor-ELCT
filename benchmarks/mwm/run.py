"""Run MWM calibration and evaluation from an external input bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np

from input_contract import validate

PACKAGE = Path(__file__).resolve().parent


def _run(inputs: Path, output: Path, checked: dict) -> dict:
    # Numerical imports follow input validation, so incomplete inputs fail before
    # any fitting or cache/output creation.
    sys.path.insert(0, str(PACKAGE / "code"))
    from build_features import build
    from mwm_core import OriginalSVGMWM, write_csv

    if output.exists():
        raise FileExistsError("Choose a new output directory; existing results are never overwritten")
    if output.is_relative_to(PACKAGE.parents[1]) or output.is_relative_to(inputs):
        raise ValueError("Choose a new output directory outside the repository and input bundle")
    case_labels = checked["config"]["case_labels"]
    tx_rooms = checked["config"]["tx_room_ids"]
    arrays, c1_fingerprint = build(inputs, checked)
    preserved = None
    archive = inputs / "C1_parameter_archive.npz"
    if archive.exists():
        if "C1_parameter_archive.npz" not in checked["hashes"]:
            raise ValueError("C-1 parameter archive must be hashed in the input manifest")
        with np.load(archive, allow_pickle=False) as old:
            if str(old["c1_input_fingerprint_sha256"].item()) != c1_fingerprint:
                raise ValueError("C-1 inputs changed; omit the old parameter archive and refit C-1")
            np.testing.assert_array_equal(old["frequency_GHz"], checked["config"]["frequency_GHz"])
            preserved = old["parameters"].copy()
            if (preserved.shape != (3, 4) or not np.isfinite(preserved).all()
                    or (preserved[:, 1:] < 0).any()):
                raise ValueError("Invalid C-1 parameter archive")
            forward = np.empty((3, 18))
            for fi, frequency in enumerate(checked["config"]["frequency_GHz"]):
                theta = preserved[fi]
                for room in range(1, 19):
                    feature = arrays[f"room{room}_features"][0]
                    loss = 32.4 + 20 * np.log10(frequency) + theta[0] + feature @ theta[1:]
                    forward[fi, room - 1] = 10 * np.log10(np.mean(
                        np.power(10., (checked["config"]["P_tx_dBm"] - loss) / 10.)))
            np.testing.assert_allclose(forward, old["C1_ARP_dBm"], rtol=0, atol=1e-10)

    output.mkdir(parents=True, exist_ok=False)
    prepared = output / "inputs"
    prepared.mkdir()
    for name in ("recovery_config.json", "source.svg", "reference_and_proposed.npz"):
        shutil.copy2(inputs / name, prepared / name)
    np.savez_compressed(prepared / "link_features_confirmed.npz", **arrays)
    model = OriginalSVGMWM(prepared)

    predictions = np.empty((3, 4, 4, 18))
    parameters = np.empty((3, 4, 4))
    fits = []; starts = []; parameter_rows = []
    for fi, frequency in enumerate(model.freqs):
        for ci, label in enumerate(case_labels):
            if ci == 0 and preserved is not None:
                theta = preserved[fi]
                predicted = model.predict(frequency, theta)
                residual = predicted[0] - model.targets[fi, 0]
                record = {"origin": "Input-matched C-1 archive", "n_starts": 0,
                          "training_SSE": float(residual @ residual),
                          "training_MAE": float(np.abs(residual).mean()),
                          "selected_start": "", "success": True}
            else:
                record, attempts, predicted, theta = model.fit(
                    float(frequency), ci, model.targets[fi, ci])
                fits.append(record); starts.extend(attempts)
            np.testing.assert_allclose(predicted, model.direct_predict(frequency, theta),
                                       rtol=0, atol=1e-10)
            predictions[fi, ci] = predicted
            parameters[fi, ci] = theta
            parameter_rows.append({"frequency_GHz": float(frequency),
                "calibration_case": label, "origin": record["origin"],
                **dict(zip(("b0", "n", "L_wall", "L_open"), map(float, theta))),
                **{name: record[name] for name in ("training_SSE", "training_MAE",
                    "selected_start", "success", "n_starts")}})

    targets = checked["WI_ARP_dBm"]; proposed = checked["Proposed_ARP_dBm"]
    errors = np.abs(predictions - targets[:, None])
    matrix = errors.mean(axis=-1)
    proposed_mae = np.abs(proposed - targets).mean(axis=-1)
    metadata = {"frequency_GHz": model.freqs, "case_labels": np.asarray(case_labels),
                "room_ids": np.arange(1, 19), "tx_room_ids": np.asarray(tx_rooms),
                "tx_xyz_m": np.asarray(checked["config"]["tx_xyz_m"]),
                "input_fingerprint_sha256": np.asarray(checked["fingerprint"]),
                "c1_input_fingerprint_sha256": np.asarray(c1_fingerprint)}
    np.savez_compressed(output / "results.npz", **metadata, parameters=parameters,
        WI_ARP_dBm=targets, Proposed_ARP_dBm=proposed, MWM_ARP_dBm=predictions,
        MWM_AE_dB=errors, MWM_MAE_dB=matrix)
    np.savez_compressed(output / "reference_and_proposed.npz", **metadata,
                        WI_ARP_dBm=targets, Proposed_ARP_dBm=proposed)
    write_csv(output / "parameters.csv", parameter_rows)
    write_csv(output / "references.csv", [
        {"frequency_GHz": float(f), "case": label, "room": r + 1,
         "WI_ARP_dBm": float(targets[fi, ci, r]),
         "Proposed_ARP_dBm": float(proposed[fi, ci, r])}
        for fi, f in enumerate(model.freqs) for ci, label in enumerate(case_labels)
        for r in range(18)])
    write_csv(output / "room_predictions.csv", [
        {"frequency_GHz": float(f), "calibration": source, "evaluation": target,
         "room": r + 1, "WI_ARP_dBm": float(targets[fi, ej, r]),
         "predicted_ARP_dBm": float(predictions[fi, ci, ej, r]),
         "AE_dB": float(errors[fi, ci, ej, r])}
        for fi, f in enumerate(model.freqs) for ci, source in enumerate(case_labels)
        for ej, target in enumerate(case_labels) for r in range(18)])
    write_csv(output / "Table_R2_fullprecision.csv", [
        {"frequency_GHz": float(f), "calibration": source,
         **{f"MAE_{target}_dB": float(matrix[fi, ci, ej])
            for ej, target in enumerate(case_labels)}}
        for fi, f in enumerate(model.freqs) for ci, source in enumerate(case_labels)])
    comparisons = []
    for fi, f in enumerate(model.freqs):
        for ej in (1, 2, 3):
            for ci in (1, 2, 3):
                if ci == ej:
                    continue
                baseline = matrix[fi, 0, ej]; alternative = matrix[fi, ci, ej]
                reduction = baseline - alternative
                comparisons.append({"frequency_GHz": float(f),
                    "evaluation_case": case_labels[ej], "calibration_source": case_labels[ci],
                    "C1_MAE_dB": float(baseline), "alternative_MAE_dB": float(alternative),
                    "reduction_dB": float(reduction),
                    "reduction_percent": float(100 * reduction / baseline) if baseline else ""})
    write_csv(output / "matched_comparisons.csv", comparisons)
    for include_diagonal, filename in (
        (False, "best_observed_vs_proposed.csv"),
        (True, "best_including_diagonal_vs_proposed.csv")):
        rows = []
        for fi, f in enumerate(model.freqs):
            for ej, target in enumerate(case_labels):
                candidates = [ci for ci in range(4) if include_diagonal or ci != ej]
                selected = min(candidates, key=lambda ci: matrix[fi, ci, ej])
                value = float(matrix[fi, selected, ej]); reference = float(proposed_mae[fi, ej])
                rows.append({"frequency_GHz": float(f), "evaluation_case": target,
                    "calibration_source": case_labels[selected], "MWM_MAE_dB": value,
                    "Proposed_MAE_dB": reference, "gap_dB": value - reference})
        write_csv(output / filename, rows)
    np.savez_compressed(output / "C1_parameter_archive.npz", frequency_GHz=model.freqs,
        parameters=parameters[:, 0], C1_ARP_dBm=predictions[:, 0, 0],
        c1_input_fingerprint_sha256=np.asarray(c1_fingerprint))
    (output / "fit_records.json").write_text(json.dumps(fits, indent=2) + "\n", encoding="utf-8")
    (output / "start_records.json").write_text(json.dumps(starts, indent=2) + "\n", encoding="utf-8")
    receipt = {"input_fingerprint_sha256": checked["fingerprint"],
               "c1_input_fingerprint_sha256": c1_fingerprint, "input_sha256": checked["hashes"],
               "Rx_total": checked["Rx_total"], "new_parameter_fits": len(fits),
               "preserved_C1": preserved is not None, "MAE_matrix_entries": int(matrix.size),
               "derived_input_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in prepared.iterdir() if p.is_file()},
               "output_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in output.iterdir() if p.is_file()}}
    (output / "run_receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return {"input_fingerprint_sha256": checked["fingerprint"], "Rx_total": checked["Rx_total"],
            "new_parameter_fits": len(fits), "preserved_C1": preserved is not None,
            "room_predictions": int(predictions.size), "MAE_matrix_entries": int(matrix.size)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path,
                        help="Verified input bundle described in input_schema.md")
    parser.add_argument("--output", type=Path, help="New result directory outside the repository")
    parser.add_argument("--validate-only", action="store_true", help="Check source inputs without fitting")
    args = parser.parse_args()
    checked = validate(args.inputs.resolve())
    if args.validate_only:
        # Geometry and room membership form part of validation, even without fitting.
        sys.path.insert(0, str(PACKAGE / "code"))
        from build_features import build
        _, c1_fingerprint = build(args.inputs.resolve(), checked)
        print(json.dumps({"case_labels": checked["config"]["case_labels"],
            "tx_room_ids": checked["config"]["tx_room_ids"],
            "Rx_total": checked["Rx_total"], "input_fingerprint_sha256": checked["fingerprint"],
            "c1_input_fingerprint_sha256": c1_fingerprint}, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required for calculation")
    print(json.dumps(_run(args.inputs.resolve(), args.output.resolve(), checked), indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, FileNotFoundError, FileExistsError, KeyError, AssertionError) as error:
        print("MWM inputs/calculation: " + str(error), file=sys.stderr)
        raise SystemExit(2)
