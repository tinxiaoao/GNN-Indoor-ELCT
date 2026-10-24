# MWM calibration and cross-configuration evaluation

C-1 uses Room 1, C-2 uses Rooms 1 and 2, C-3 uses Rooms 1, 2 and 4,
and C-4 uses Rooms 1, 2, 4 and 8. The frequencies are 2.4, 5 and 28 GHz.
See [the configuration](../configs/mwm_validation.json) and
[the input schema](../benchmarks/mwm/input_schema.md).

Use actual WI transmitter and receiver coordinates, a verified transformation
to the source SVG, individual received-power exports and matching Proposed room
ARPs. Receiver counts come from those exports. The Room-8 inputs are required
before a new calculation can run.

```text
python -m pip install -r environments/mwm-requirements.txt
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --output "path/outside/repository/new-mwm-run"
python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"
```

The model sums transmitter powers in linear units, averages actual samples
within each room and converts the room average to dBm. Calibration uses only
the eighteen room ARPs of the chosen training configuration. The fixed eight
starts, nonnegative slope/interface-loss constraints and training-SSE selection
rule are in `benchmarks/mwm/code/mwm_core.py`. C-1 parameters are retained only
when their input fingerprint and forward calculation match; otherwise C-1 is
fitted with the same rule as the other configurations.

| Output | Contents |
| --- | --- |
| `reference_and_proposed.npz`, `references.csv` | Three frequencies × four configurations × eighteen full-precision WI and Proposed room ARPs |
| `parameters.csv`, `results.npz` | Twelve parameter sets and input fingerprints |
| `room_predictions.csv` | 864 MWM predictions and absolute errors |
| `Table_R2_fullprecision.csv` | Three full 4×4 calibration/evaluation MAE matrices, also used for Table S3 |
| `matched_comparisons.csv` | Comparisons with the C-1-calibrated model for the same evaluation configuration |
| `best_including_diagonal_vs_proposed.csv` | Lowest MWM MAE including diagonal entries, for Table R3 |
| `best_observed_vs_proposed.csv` | Lowest MWM MAE excluding diagonal entries, for Table S5 |

ARP is in dBm; AE and MAE are in dB. MAE uses all eighteen rooms.
Keep full precision for calculation and round only for table display.
The runner does not execute Wireless InSite or regenerate the Proposed model.

The [Rooms 1,2,4,18 archive](../archives/mwm_rooms_1_2_4_18/README.md) preserves
its original references and a separate replay entry point.
