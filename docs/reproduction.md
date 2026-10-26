# Program and workflow guide

Run commands from the repository root in the environment for each module.
Choose a new output directory for every calculation.

| Workflow | Program | Inputs | Example command |
| --- | --- | --- | --- |
| Room and topology extraction | `geo_elct/api.py`, `correction_v2.py` | Semantic maps and an extraction configuration | `python -m geo_elct extract --config examples/synthetic_two_rooms/case.json --mode correction_v2 --out runs/part-a` |
| Perturbation generation | `experiments/perturbations/generate_reference_faithful_perturbations.py` | Clean semantic maps and the selected perturbation settings | `python -m experiments.perturbations.generate_reference_faithful_perturbations --help` |
| Batch extraction | `scripts/prepare_fixed_inputs.py`, `experiments/run_existing_cases.py` | An explicit input manifest and correction modes | `python -m experiments.run_existing_cases --manifest local/part-b-inputs/cases.json --opening-aggregation by_thickness_v1 --out runs/part-b` |
| Topology evaluation | `experiments/evaluate_topology.py` | Reference and candidate extraction directories | `python -m experiments.evaluate_topology --reference "path/to/reference" --candidate "path/to/candidate" --out runs/topology-evaluation` |
| MWM input processing | `benchmarks/mwm/run.py`, `input_contract.py` | The user's external geometry, simulation exports and room references | `python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --validate-only` |
| MWM calculation | `benchmarks/mwm/code/build_features.py`, `code/mwm_core.py` | The same external MWM input directory | `python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --output "path/outside/repository/new-mwm-run"` |
| Local MWM result check | `benchmarks/mwm/verify_results.py` | A newly calculated result directory | `python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"` |

The extraction CLI defaults to `none`; use explicit `--mode correction_v2` to
select the separately versioned correction implementation. Opening aggregation
defaults to `by_thickness_v1`: internal interfaces are grouped by room pair,
type and thickness, with accumulated length and retained thickness. Select
`--opening-aggregation legacy_width_sum` for the earlier sum-of-widths convention.
Correction modes and thresholds are independent of the aggregation selection.

The [topology workflow](part_b.md) describes the perturbation programs and
spatial room-matching metrics. Perturbation settings and input manifests record
the generator, seeds and correction modes used for a local run.

PWB reads the extracted tables together with an explicit JSON scale,
transmitter room IDs and powers. The synthetic multifrequency example gives a
starting point; units, fields and software requirements are described in
[the MATLAB interface](matlab_interface.md).

The [MWM method guide](part_c.md) and [input schema](../benchmarks/mwm/input_schema.md)
describe the computation and external input format. The module is distributed
as calculation code; simulation inputs and numerical comparison datasets are
supplied separately. Existing WI exports can be processed offline, while
creating new exports requires a valid Wireless InSite license.

[Implementation notes](implementation_notes.md) describe interface conventions
and diagnostic fields. Module installation commands are in
[the environment guide](../environments/README.md).
