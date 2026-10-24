"""Independently recompute room AE and 18-room MAE from Part C predictions.

Checking the frozen results alone validates arithmetic, not a new model run.
Pass a newly computed results.npz to compare it with the frozen reference.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import numpy as np


def verify(results: Path, prediction_atol: float = 1e-8) -> dict:
    package = Path(__file__).resolve().parent
    with np.load(results, allow_pickle=False) as current:
        predictions = current["MWM_ARP_dBm"]
        targets = current["WI_ARP_dBm"]
        parameters = current["parameters"]
        assert predictions.shape == (3, 4, 4, 18)
        assert targets.shape == (3, 4, 18)
        assert parameters.shape == (3, 4, 4)
        errors = np.abs(predictions - targets[:, None, :, :])
        means = np.sum(errors, axis=3) / 18
        np.testing.assert_allclose(current["MWM_AE_dB"], errors, rtol=0, atol=1e-12)
        np.testing.assert_allclose(current["MWM_MAE_dB"], means, rtol=0, atol=1e-12)
        with np.load(package / "results/results.npz", allow_pickle=False) as frozen:
            np.testing.assert_array_equal(targets, frozen["WI_ARP_dBm"])
            np.testing.assert_array_equal(parameters[:, 0], frozen["parameters"][:, 0])
            difference = float(np.max(np.abs(predictions - frozen["MWM_ARP_dBm"])))
            np.testing.assert_allclose(predictions, frozen["MWM_ARP_dBm"], rtol=0,
                                       atol=prediction_atol)
        with (package / "results/Table_R2_fullprecision.csv").open(encoding="utf-8-sig") as stream:
            table = np.asarray([[float(row["MAE_" + case + "_dB"])
                                 for case in ("C-1", "C-2", "C-3", "C-4v")]
                                for row in csv.DictReader(stream)]).reshape(3, 4, 4)
        np.testing.assert_array_equal(np.round(means, 2), np.round(table, 2))
    return {"room_predictions": predictions.size, "parameter_sets": 12,
            "MAE_matrix_entries": means.size, "averaged_rooms": 18,
            "max_prediction_delta_from_frozen_dB": difference,
            "prediction_atol_dB": prediction_atol,
            "scope": "new calculation comparison" if results.resolve() !=
                     (package / "results/results.npz").resolve() else "frozen-reference arithmetic only"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).parent / "results/results.npz")
    args = parser.parse_args()
    print(json.dumps(verify(args.results), indent=2))
