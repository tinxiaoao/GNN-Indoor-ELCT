# MWM calibration and evaluation

The deployments are C-1 = [1], C-2 = [1,2], C-3 = [1,2,4] and C-4 = [1,2,4,8],
evaluated at 2.4, 5 and 28 GHz. Install `environments/mwm-requirements.txt` in a
separate Python environment.

Prepare an authorized input directory using [the input schema](input_schema.md).
It requires actual WI Tx/Rx coordinates and received-power exports, the source
SVG and matching Proposed room ARPs. The supplied configuration template needs
the verified Room-8 inputs before a calculation can run.

From the repository root:

```text
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --output "path/outside/repository/new-mwm-run"
python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"
```

Each run uses the exported receiver positions and writes a new directory with
parameters, full-precision references, room predictions and three 4×4 MAE
matrices. MAE averages all eighteen rooms. `best_observed_vs_proposed.csv`
excludes the diagonal for Table S5; `best_including_diagonal_vs_proposed.csv`
includes it for Table R3. Both use the same full-precision Proposed room data.

The [Rooms 1,2,4,18 archive](../../archives/mwm_rooms_1_2_4_18/README.md)
contains the earlier numerical baseline and its explicit replay commands.
