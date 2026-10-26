# Multi-Wall Model calculation code

This module provides forward calculation, coefficient fitting and processing
of user-supplied input exports. Simulation inputs and numerical comparison
datasets are not distributed with this code release.

The implementation supports three frequencies (2.4, 5 and 28 GHz), four
cumulative transmitter configurations and eighteen rooms. Case labels,
transmitter rooms, coordinates and geometry are defined in the user's external
configuration. See [the input schema](input_schema.md).

Install `environments/mwm-requirements.txt` in a separate Python environment.
Run these commands from the repository root with a prepared input directory:

```text
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --output "path/outside/repository/new-mwm-run"
python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"
```

`--validate-only` checks input sources, coordinates, room mapping and power
aggregation. Calculation writes a new directory containing model parameters,
room predictions, fitting records and a source receipt. The result checker
checks the arithmetic and file identities of that local run.

The model sums transmitter powers in linear units, averages samples within
each room and converts the room average to dBm. Calibration uses the room
averages of the selected training configuration. The fixed multistart fitting
rule is implemented in `code/mwm_core.py`; [the method guide](../../docs/part_c.md)
explains the calculation sequence.

The Python programs process existing Wireless InSite exports offline.
Generating new simulation exports requires a valid Wireless InSite license.
The user supplies the source geometry, simulation exports and corresponding
room-reference files described by the input schema.
