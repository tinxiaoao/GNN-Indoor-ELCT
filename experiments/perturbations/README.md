# Preserved perturbation generators

These are two existing source families, not newly designed perturbations. Their numerical functions, settings, seeds and random-number formulas are unchanged. The migration only removes development-tree path injection, uses package imports and adds CLI rejection of existing output directories. `settings.json` records the source constants without changing them. Historical source docstrings saying “post-GNN” describe intended use; the identified A/B/C maps themselves are annotation-derived.

| Family | Original source | Randomness / definition |
|---|---|---|
| Legacy local | `code/R1-Q4/indoor_topology/scripts/perturb_segmentation_maps.py` | Seeds 0–4 by default, `random.Random(int(seed))`; opening shift or boundary-pixel deletion are alternative edits |
| Reference-faithful | `code/R1-Q4/indoor_topology/scripts/generate_reference_faithful_perturbations.py` | Main cases use `random.Random(41000 + seed + 1000 * level_index)`; unit cases use `93000 + case_index`; partial deletion removes an internal full-thickness strip |

The two families have different intensity definitions and output trees. A shared level/seed label does not make their images interchangeable. Part B uses the reference-faithful protocol and all five fixed seeds with the explicit `correction_v2` mode and `by_thickness_v1` opening aggregation. See [Part B settings and commands](../../docs/part_b.md).

Run from the repository root with authorized clean input maps and a new output root:

```powershell
python -B -m experiments.perturbations.perturb_segmentation_maps --help
python -B -m experiments.perturbations.generate_reference_faithful_perturbations --help
python -B -m experiments.perturbations.perturb_segmentation_maps --wall <clean-wall.png> --icon <clean-icon.png> --output-dir <new-legacy-inputs> --seeds 0 1 2 3 4
python -B -m experiments.perturbations.generate_reference_faithful_perturbations --wall <clean-wall.png> --icon <clean-icon.png> --out <new-reference-faithful-inputs> --seeds 0 1 2 3 4
```

The second generator retains its original optional input defaults, now relative to this repository; the maps are not bundled, so supply both input paths explicitly. Source CLI flags differ: legacy uses `--output-dir`, reference-faithful uses `--out`. Clean maps are used to construct perturbations and local geometry pools, not provided as a hidden answer to correction. The generators write perturbation settings/manifests, never repaired Geo-ELCT tables or success rates. Correction must not read their manifests. Keep these generated manifests private when they contain local absolute paths. Extract each perturbed input with an explicitly selected mode; evaluate against clean references independently and report topology, complete two-table equality and pixel differences separately.

The Part B protocol is recorded in [part_b_protocol.json](../part_b_protocol.json), with all 20 fixed input identities in [part_b_inputs.json](../part_b_inputs.json). Its extraction and evaluation commands report typed connectivity separately from dimension-record Count and complete table equality.
