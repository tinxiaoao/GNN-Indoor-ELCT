# Part B perturbations and recovery evaluation

Two existing generation families are packaged under `experiments/perturbations/`.
Their numerical functions/settings/randomness are preserved; only package
imports, development-path removal and rejection of existing output roots were
added. `settings.json` records the original fixed intensity ranges and seed
rules; [generator instructions](../experiments/perturbations/README.md) give the
actual distinct CLI flags.

The legacy family uses boundary-pixel deletion (3–5%, 5–10%, 15–20% by level).
The reference-faithful family deletes an internal full-thickness strip (1,
2–3, 3–4 px by level), with different seed transformation and local defect
settings. Both use seeds 0–4. They must not share a result label merely because
level and seed strings match. No alternate seed or favorable input was selected
to establish a five-trial rate here.

`experiments/fixed_inputs.json` binds all 43 located historical identities to
exact local project-relative input files and SHA256: three clean buildings and
20 slots per family. Each family's five clean slots are explicit repeated
inputs, not five independent clean buildings. The clean maps are annotation-
derived. Images/backgrounds are excluded pending redistribution permission.

```powershell
python scripts/prepare_fixed_inputs.py --source-root "path/to/authorized-original-tree" --out local/fixed
python -m experiments.run_existing_cases --manifest local/fixed/cases.json --out runs/fixed-batch
python -m experiments.compare_outputs --reference "path/to/clean-computed-output" --candidate "path/to/new-perturbed-output" --out runs/fixed-evaluation
```

The preparation script verifies every file before copying. Its source root is
used only to acquire input data, never to import original modules. The extractor
uses copied run-local maps and accepts no reference result. Clean maps may be
used to construct perturbations and independently evaluate them; no repair
function reads a clean map, perturbation manifest or saved answer.

Report legacy relation, strict room/type/internal pair/type/Count topology,
full room-table equality, full edge-table equality and pixel restoration
separately. Full comparison uses mask-IoU room correspondence and checks raw
IDs, complete workbook cells and exterior walls/openings. Integer/category
fields and preserved Geo float values are compared exactly (absolute tolerance
0), not relaxed after failures. A successful command is not topology recovery.

This preparation reran clean A/B/C and the fixed legacy Mild seed 0 and
reference-faithful Severe seed 4 under both `none` and `correction_v2` (10 new
extractions). All ten match historical algorithm-specific reference outputs
exactly. Comparisons against clean geometry remain separate: the v2 examples
preserve/restore both tables; `none` on perturbed inputs may not. Neither full
generator family nor the complete five-seed aggregate was recomputed. Saved
v2 history includes failures in the legacy family; it is not relabeled as a
fresh 5/5 result.

Supplementary B.2/Table S1 calls its inputs GNN segmentation outputs; the
located maps have annotation provenance. Table S2 gives 5/5 mild and 0/5
moderate/severe without correction and 5/5 with correction, but a unique
source/run/mode/evaluator binding is not established by the located records.
These claims are **not newly reproduced**. Preserve the supplied document and
resolve the binding with the author rather than substituting metrics or data.
