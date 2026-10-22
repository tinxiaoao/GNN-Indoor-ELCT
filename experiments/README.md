# Experiment interfaces

`run_existing_cases.py` reads an explicit manifest of hash-bound input maps,
source types and modes. It does not generate perturbations or choose seeds.
`compare_outputs.py` independently compares full table cells, room masks/IDs,
Tx mappings when supplied, raw/exterior records and legacy/strict metrics.

Use [Part B](../docs/part_b.md) for preparation and actual commands. The two
preserved generators and fixed settings are in `perturbations/`.
`fixed_inputs.json` binds all located historical identities without redistributing
their maps. `fixed_cases.example.json` is the earlier five-case schema example;
it is not a shipped runnable dataset. For Part C see `benchmarks/mwm/`.
