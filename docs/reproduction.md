# Supplementary material and executable correspondence

Run all commands from the release root in the environment for that module.
Every output directory must be new. Frozen results are evaluation targets only.

| Document section | Program | Configuration/input | Command | Output |
| --- | --- | --- | --- | --- |
| Part A, Algorithm S1 | `geo_elct/api.py`, `correction_v2.py`, baseline extraction modules | `examples/synthetic_two_rooms/case.json`; real `configs/building_A/B/C.json` after local preparation | `python -m geo_elct extract --config examples/synthetic_two_rooms/case.json --mode correction_v2 --out runs/part-a` | Two XLSX tables, mask, raw/canonical records and separate diagnostics |
| Part B, perturbation construction | `experiments/perturbations/` two preserved generators | Unchanged `settings.json`, seeds 0–4, authorized clean maps | `python -m experiments.perturbations.generate_reference_faithful_perturbations --help` | Perturbed maps, settings and operation manifests; no recovery claim |
| Part B, fixed-input extraction | `scripts/prepare_fixed_inputs.py`, `experiments/run_existing_cases.py` | `experiments/fixed_inputs.json` (43 identities in two distinct families plus three clean buildings) | `python -m experiments.run_existing_cases --manifest local/fixed/cases.json --out runs/part-b` | New individual extractions, commands and execution status |
| Part B, independent evaluation | `experiments/compare_outputs.py` and two retained evaluators | Separately supplied clean output and new perturbed output | `python -m experiments.compare_outputs --reference reference_results/synthetic_two_rooms --candidate runs/part-a --out runs/part-b-evaluation` | Full cells, mask-IoU/IDs, external records, legacy and strict metrics |
| Part C, S3–S5 | Unchanged `benchmarks/mwm/code/mwm_core.py`, `rebuild_svg.py`, `recalculate.py`; new isolated wrapper | `configs/mwm_validation.json`, designated hash-verified external input ZIP | `python benchmarks/mwm/run.py --inputs local/mwm-inputs --output runs/part-c` | Nine new fits plus three retained C-1 fits, 864 predictions, 48 MAEs |
| Part C, arithmetic check | `benchmarks/mwm/verify_results.py` | Explicit new calculation NPZ, or frozen NPZ by default | `python benchmarks/mwm/verify_results.py --results runs/part-c/replayed/results.npz` | AE/18-room MAE arithmetic verification |

Part A matches the explicit v2 decision structure; default `none` has not changed.
Its exact frozen module SHA256 is
`32cbc81b680c1838a782a6639ee4e2438a06f1a8afb55ff1462bf9a7f222ecf0`.
This hash comes from actual source/provenance verification, not a literal hash
printed in the Supplementary DOCX. Historical identity `correction_v2.0`, CLI
mode `correction_v2` and packaging version are separate concepts.

The existing package was checked against original B code at
`code/R1-Q4/indoor_topology`; all nine source and packaged identities match.
Algorithm ASTs match after only recorded import/docstring/path-bootstrap
normalization. Original `code/indoor_topology` is the separate frozen A variant:
B has a callable entry, correction helpers/evaluators and eight `.ptp()` to
`np.ptp()` changes in exterior handling. This preparation retained the existing
working B package and added no algorithm changes. MATLAB core/material bytes
match both source locations exactly. GNN upstream is recorded separately.

Part B's description refers to GNN outputs, whereas the located clean A/B/C
maps are annotation-derived. The two fixed perturbation families also differ in
deletion/intensity definitions. Table S2's unique input/mode/evaluator binding
is therefore **unconfirmed**; neither matching a historical number nor passing
representative migration establishes it. No source document numbers were edited.

PWB follows map extraction using an explicit JSON scale, Tx RoomIDs and powers.
The Room-8 display is not a Part C validation target. Units and unresolved
interface limitations are in [MATLAB interface](matlab_interface.md).

Commands and required inputs are in the root README, [Part B](part_b.md), and
[Part C](part_c.md); the scope of the available checks is described in
[known limitations](known_limitations.md).
