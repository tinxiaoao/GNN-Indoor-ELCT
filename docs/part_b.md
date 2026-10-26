# Perturbation generation and topology evaluation

The experiment programs provide a reproducible workflow for generating local
semantic-map perturbations, extracting ELCT tables and evaluating the resulting
room connections. [The protocol](../experiments/part_b_protocol.json) defines
four intensity levels and seeds 0–4; the Clean condition uses the unperturbed
input pair. The supplied fixed-input manifest records annotation-derived
CubiCasa5K inputs and their hashes.

The ranges below are generation parameters. Counts are per map; fragment area
is in px² and other dimensions are in px.

| Perturbation | Mild | Moderate | Severe |
| --- | --- | --- | --- |
| Enclosed fragments: count; area each | 1; 3–5 | 2–3; 4–9 | 4–6; 6–16 |
| Wall gaps: count; length each | 1; 2 | 2; 3–4 | 3; 5–6 |
| Boundary displacements: count; span; displacement | 1; 6–8; 1 | 2; 8–12; 1 | 3; 12–18; 1 |
| Shifted doors: count; displacement | 1; 1 | 1; 2 | 1–2; 3 |
| Shifted windows: count; displacement | 0–1; 1 | 1; 2 | 1–2; 3 |
| Partially deleted openings: count; strip length | 1; 1 | 2; 2–3 | 2–3; 3–4 |

Partial deletion removes an internal strip through the opening thickness,
leaving both ends visible. The generator chooses geometrically eligible
candidates and writes the sampled edits to a manifest.

## Generate and process inputs

Run commands from the repository root and use a new output directory:

```powershell
python -B -m experiments.perturbations.generate_reference_faithful_perturbations --wall "path/to/clean-wall.png" --icon "path/to/clean-icon.png" --out local/part-b-generated --seeds 0 1 2 3 4
python -m geo_elct extract --wall "path/to/generated-wall.png" --icon "path/to/generated-icon.png" --mode correction_v2 --opening-aggregation by_thickness_v1 --out runs/perturbed
```

For batch processing of the [fixed-input manifest](../experiments/part_b_inputs.json)
from an authorized local source tree:

```powershell
python scripts/prepare_fixed_inputs.py --source-root "path/to/local-source-tree" --manifest experiments/part_b_inputs.json --out local/part-b-inputs
python -m experiments.run_existing_cases --manifest local/part-b-inputs/cases.json --opening-aggregation by_thickness_v1 --out runs/part-b
```

`none` and `correction_v2` select the baseline and repair workflows. Correction
reads only its input maps and implementation parameters. Generation manifests
and clean-reference maps are reserved for the separate evaluation step.

## Evaluate topology

Topology matching requires equal room count, one-to-one spatial room matching
with mask IoU ≥ 0.5, and identical unordered room-pair/connection-type sets.
The evaluator also reports dimension-record Count, room types and complete
table equality as separate fields.

```powershell
python -m experiments.evaluate_topology --reference "path/to/clean-extraction" --candidate "path/to/perturbed-extraction" --out runs/topology-evaluation
```

This release provides the generation, extraction and evaluation programs and
their parameter definitions. Numerical recovery-rate tables are outside the
code distribution; the commands write results for the supplied local inputs.

The separate `perturb_segmentation_maps` generator provides another local
perturbation protocol. Select the generator and its settings consistently
within an experiment; see [generator interfaces](../experiments/perturbations/README.md).
