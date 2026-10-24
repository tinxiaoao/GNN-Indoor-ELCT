# Supplementary material and executable correspondence

Run all commands from the release root in the environment for that module.
Every output directory must be new. Frozen results are evaluation targets only.

| Document section | Program | Configuration/input | Command | Output |
| --- | --- | --- | --- | --- |
| Part A, Algorithm S1 | `geo_elct/api.py`, `correction_v2.py`, baseline extraction modules | `examples/synthetic_two_rooms/case.json`; real `configs/building_A/B/C.json` after local preparation | `python -m geo_elct extract --config examples/synthetic_two_rooms/case.json --mode correction_v2 --out runs/part-a` | Two XLSX tables, mask, raw/canonical records and separate diagnostics |
| Part B, perturbation construction | `experiments/perturbations/generate_reference_faithful_perturbations.py` | `experiments/part_b_protocol.json`, seeds 0–4 and clean sample 7795 maps | `python -m experiments.perturbations.generate_reference_faithful_perturbations --help` | Perturbed maps, settings and operation manifests |
| Part B, fixed-input extraction | `scripts/prepare_fixed_inputs.py`, `experiments/run_existing_cases.py` | `experiments/part_b_inputs.json`: all 20 cases, each under `none` and `correction_v2` | `python -m experiments.run_existing_cases --manifest local/part-b-inputs/cases.json --opening-aggregation by_thickness_v1 --out runs/part-b` | All 40 individual extractions |
| Part B, independent evaluation | `experiments/evaluate_topology.py` | Clean output and each perturbed output | `python -m experiments.evaluate_topology --reference runs/part-b/runs/reference_faithful_clean_0/none --candidate runs/part-b/runs/reference_faithful_severe_2/correction_v2 --out runs/part-b-evaluation` | Room count and typed connectivity; Count and complete table equality separately |
| Part C, input validation | `benchmarks/mwm/run.py`, `input_contract.py` | Verified C-4 Room-8 WI Tx/Rx data and matching Proposed references | `python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --validate-only` | Source, coordinate and reference checks; no fitting |
| Part C, calculation | `benchmarks/mwm/run.py`, `code/build_features.py`, `code/mwm_core.py` | Verified bundle described in `benchmarks/mwm/input_schema.md` | `python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --output "path/outside/repository/new-mwm-run"` | Parameters, 864 room predictions and three 4×4 MAE matrices |
| Part C, result verification | `benchmarks/mwm/verify_results.py` | New result directory | `python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"` | Full-precision AE/18-room MAE and minimum-selection checks |

Use explicit `--mode correction_v2` for Part A. The CLI default is `none`;
the correction implementation is versioned independently of packaging.

Opening aggregation defaults to `by_thickness_v1`: internal interfaces group
by room pair, type and thickness, accumulate length and retain thickness.
Use explicit `--opening-aggregation legacy_width_sum` to reproduce the earlier
sum-of-widths behavior. Correction modes and thresholds are independent of
this aggregation choice. MATLAB core identities are recorded separately.

Part B uses the reference-faithful generation protocol and annotation-derived
maps for Building C, sample 7795. All four levels and seeds 0–4 are evaluated
with the same correction parameters and `by_thickness_v1` aggregation. The
five Clean slots repeat the same map pair. The separate legacy generator's
endpoint deletion and intensity ranges are not substituted for this protocol.

PWB follows map extraction using an explicit JSON scale, Tx RoomIDs and powers.
The C-4 room set is [1,2,4,8]. Multifrequency PWB examples exercise the solver
interface and do not supply WI validation. Units and interface limitations
are in [MATLAB interface](matlab_interface.md).

Formal Part C calculation requires the verified Room-8 input bundle; the
distributed template is incomplete. Earlier Rooms 1,2,4,18 references and ZIP
replay commands are retained in
[the numerical archive](../archives/mwm_rooms_1_2_4_18/README.md), separately
from the formal C-4 path.

Commands and required inputs are in the root README, [Part B](part_b.md), and
[Part C](part_c.md); the scope of the available checks is described in
[known limitations](known_limitations.md).
