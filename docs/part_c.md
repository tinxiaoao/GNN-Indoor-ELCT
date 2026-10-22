# Part C: MWM calibration and cross-configuration evaluation

This benchmark uses only `R1Q6_WI_Confirmed_Reproducible.zip` identified by the
handoff `SOURCE_INDEX.json`; its SHA256 is
`33215a47777ca560169213c5ba5ba529f82d7a9d1d62b3d2f5dc8e320dbfabf4`.
The archived three C-1 parameter sets are retained exactly. Nine additional
parameter sets are recalibrated using only the 18 WI room ARPs for their own
frequency and calibration configuration. Eight fixed starts are used per new
fit; converged starts are selected by training SSE. Evaluation-configuration
errors do not select the fit. The historical optimizer settings were unavailable;
the explicit settings in `code/mwm_core.py` belong to this recovered benchmark.

| Supplementary item | Program or data | Meaning |
| --- | --- | --- |
| Part C geometry and forward model | `benchmarks/mwm/code/rebuild_svg.py` | Reconstructs 11,480 receiver points from the external SVG; checks the fixed C-1 forward calculation |
| Calibration protocol | `benchmarks/mwm/code/mwm_core.py` | Unchanged objective, constraints, analytic derivatives and multistart selection |
| Table S3 | `benchmarks/mwm/code/recalculate.py`, `results/Table_R2_fullprecision.csv` | 48 calibration/evaluation MAEs at 2.4, 5 and 28 GHz |
| Table S4 | `results/parameters.csv`, `results/results.npz` | 12 sets of four parameters; full precision in the files |
| Table S5 | `results/best_observed_vs_proposed.csv` | Lowest off-diagonal MWM MAE for each evaluation target, paired with its saved Proposed reference |
| Independent arithmetic | `benchmarks/mwm/verify_results.py` | Recomputes every AE and each 18-room mean from 864 room predictions |

Paths in the table under `results/` are relative to `benchmarks/mwm/`.

The fixed configurations are C-1 = {1}, C-2 = {1,2}, C-3 = {1,2,4}, and
C-4v = {1,2,4,18}; see `configs/mwm_validation.json` and the unchanged
`benchmarks/mwm/inputs/recovery_config.json`. The distinct Room-8 deployment
{1,2,4,8} is recorded as `Room8-showcase` in
`configs/mwm_room8_illustration.json`. It has no Part C WI reference array and
must not inherit the C-4v label or its data.

Install and run from the release root:

```text
python -m venv .venv-mwm
# Activate the new environment using the command for your platform.
python -m pip install -r environments/mwm-requirements.txt
python benchmarks/mwm/code/recalculate.py --help
python benchmarks/mwm/verify_results.py
python benchmarks/mwm/prepare_inputs.py --source-package "path/to/R1Q6_WI_Confirmed_Reproducible.zip" --output "runs/part-c-inputs"
python benchmarks/mwm/run.py --inputs "runs/part-c-inputs" --output "runs/part-c-calculation"
python benchmarks/mwm/verify_results.py --results "runs/part-c-calculation/replayed/results.npz"
```

The source package must be obtained through an authorized local copy. The
candidate excludes its SVG and geometry arrays because the handoff does not
establish their redistribution license. `prepare_inputs.py` validates the whole
archive hash and nine whitelisted input-member hashes before extracting into a
new local directory. `run.py` validates those input hashes and creates a fresh
working copy, where the original entry may rebuild geometry files safely.
Neither command writes into the handoff or existing frozen references. The
wrapper and preparation tools are new release interfaces; the numerical code
has no modifications.

Actual release checks on 2026-10-15 used isolated Python 3.11.10, NumPy 1.26.4,
SciPy 1.13.1 and Shapely 2.0.6. The numerical files were imported from the isolated
environment. The installation of this environment was assembled locally; a
fresh online dependency installation was not validated. The historical package
manifest lists Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0 and Shapely 2.1.2 and is
retained only as source provenance.

| Executed check | Result |
| --- | --- |
| CLI help for both original entry points and all release wrappers | Passed |
| Hash-verified extraction of the exact designated inputs | Passed, 9 files |
| New SVG reconstruction and nine recalibrations | Passed; all 72 starts converged |
| Archived C-1 parameter preservation | Exact equality for all three sets |
| New 864 room predictions versus frozen predictions | Maximum difference 8.526512829121202e-14 dB; original absolute tolerance 1e-8 dB retained |
| Independent AE and 18-room MAE recomputation | Passed, 864 AE values and 48 matrix entries |
| Parameter comparison | 12 sets; maximum numerical difference 7.638334409421077e-14 |
| Read-only comparison with Supplementary Tables S3–S5 | All 48 S3 values, 48 S4 parameter displays and 9 S5 ranges matched; S3 stars and bold entries matched |
| Relocated benchmark under an independent temporary path containing spaces | Full recalculation and new-result verification passed with `PYTHONPATH` removed |

ARP is in dBm, AE and MAE are in dB, and frequency is in GHz. MAE uses all
18 rooms. Rounding to two decimals is for display only; parameter display in
Table S4 uses six decimals. A star denotes calibration-fit error, while bold
marks the lowest **non-diagonal** prediction MAE for each evaluation target.
No 17-room mean or new reference selection is used.

Room 18 retains the archived geometric-centroid transmitter assumption; its
exact WI xyz has not been independently supplied. The SVG-reconstructed
receiver grid has not been certified equal to a WI coordinate export. The
program reads fixed WI and Proposed room references; it does not execute WI,
regenerate the Proposed results, or establish a newly simulated WI baseline.
