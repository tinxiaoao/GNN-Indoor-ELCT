# Experiment interfaces

`run_existing_cases.py` reads an explicit manifest of hash-bound input maps,
source types and modes. It does not generate perturbations or choose seeds.
`compare_outputs.py` independently compares full table cells, room masks/IDs,
Tx mappings when supplied, raw/exterior records and legacy/strict metrics.
`evaluate_topology.py` evaluates equal room count and typed room connectivity
with spatial room matching; Count and complete table equality are separate.

Use [Part B](../docs/part_b.md) for preparation and actual commands. The two
preserved generators and fixed settings are in `perturbations/`.
`fixed_inputs.json` binds all located historical identities without redistributing
their maps. `part_b_inputs.json` selects all 20 cases of the adopted Part B
protocol; `part_b_protocol.json` records its ranges, seeds, correction modes and
opening aggregation. `fixed_cases.example.json` is the earlier five-case schema example;
it is not a shipped runnable dataset. For Part C see `benchmarks/mwm/`.
