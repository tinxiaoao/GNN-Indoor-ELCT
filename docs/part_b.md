# Part B perturbations and topology matching

Part B uses Building C, CubiCasa5K sample 7795, with the
`generate_reference_faithful_perturbations` protocol. The input maps are
annotation-derived. All four levels use seeds 0, 1, 2, 3 and 4; Clean repeats
the same unperturbed maps. Seed 2 provides the existing illustrated examples.
[The protocol](../experiments/part_b_protocol.json) and
[all 20 fixed inputs](../experiments/part_b_inputs.json) specify the settings
and original input hashes.

The table gives inclusive sampling ranges. Counts are per map; fragment area
is in px² and all other dimensions are in px.

| Perturbation | Mild | Moderate | Severe |
| --- | --- | --- | --- |
| Enclosed fragments: count; area each | 1; 3–5 | 2–3; 4–9 | 4–6; 6–16 |
| Wall gaps: count; length each | 1; 2 | 2; 3–4 | 3; 5–6 |
| Boundary displacements: count; span; displacement | 1; 6–8; 1 | 2; 8–12; 1 | 3; 12–18; 1 |
| Shifted doors: count; displacement | 1; 1 | 1; 2 | 1–2; 3 |
| Shifted windows: count; displacement | 0–1; 1 | 1; 2 | 1–2; 3 |
| Partially deleted openings: count; strip length | 1; 1 | 2; 2–3 | 2–3; 3–4 |

Partial deletion removes an internal strip through the opening thickness,
leaving both ends visible. The generator selects geometrically eligible
candidates. All requested injections succeeded for the five fixed seeds.
The sampled values need not reach every endpoint of a range.

Use a new output directory for every command. To prepare the saved inputs
from an existing local source tree containing the manifest-listed `code/`
paths, then execute all 40 cases:

```powershell
python scripts/prepare_fixed_inputs.py --source-root "path/to/local-source-tree" --manifest experiments/part_b_inputs.json --out local/part-b-inputs
python -m experiments.run_existing_cases --manifest local/part-b-inputs/cases.json --opening-aggregation by_thickness_v1 --out runs/part-b
```

To generate maps from a clean pair using the same protocol instead:

```powershell
python -B -m experiments.perturbations.generate_reference_faithful_perturbations --wall "path/to/wall_svg.png" --icon "path/to/icon_svg.png" --out local/part-b-generated --seeds 0 1 2 3 4
```

Extract each generated pair with explicit `--mode none` or
`--mode correction_v2` and `--opening-aggregation by_thickness_v1`. Correction
uses only its input maps and fixed implementation parameters; it does not read
the Clean maps, generation manifests, defect locations or reference results.

Topology matching requires equal room count, complete spatial room matching
with mask IoU ≥ 0.5, and identical unordered room-pair/connection-type sets.
The evaluator reports Count, room types and complete table equality separately.
For example:

```powershell
python -m experiments.evaluate_topology --reference runs/part-b/runs/reference_faithful_clean_0/none --candidate runs/part-b/runs/reference_faithful_severe_2/correction_v2 --out runs/part-b-severe-2-evaluation
```

| Condition | Without correction | With `correction_v2` |
| --- | --- | --- |
| Clean | 5/5 | 5/5 |
| Mild | 0/5 | 5/5 |
| Moderate | 0/5 | 5/5 |
| Severe | 0/5 | 5/5 |

These results use all 40 executions with `by_thickness_v1`. Complete canonical
room and interface tables also equal Clean for every corrected case in this
batch. The five Clean trials repeat one map pair and are not five buildings.

The separate `perturb_segmentation_maps` generator is retained for other
experiments. Its endpoint pixel deletion and intensity ranges differ from
this Part B protocol; do not substitute its maps or combine their results.
