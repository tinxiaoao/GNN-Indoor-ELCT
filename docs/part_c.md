# Multi-Wall Model computation

The MWM module provides forward calculation, coefficient fitting and processing
of user-supplied input exports. This release distributes calculation code and
methods; simulation inputs and numerical comparison datasets are supplied
separately by the user. See [the module instructions](../benchmarks/mwm/README.md)
and [the external input format](../benchmarks/mwm/input_schema.md).

The implementation processes three frequencies, four cumulative transmitter
configurations and eighteen rooms. Case labels and physical deployment settings
are read from the external configuration.

The calculation proceeds as follows:

1. Check source-file hashes and align the geometry, coordinates and exported
   received powers with the input metadata.
2. Build link features from transmitter-to-receiver distance and intersections
   with wall and opening polygons.
3. Sum transmitter powers in linear units, average the receiver samples in each
   room and convert the room average to dBm.
4. Fit the intercept, distance slope, wall loss and opening loss to the selected
   configuration's room averages. Use eight fixed starts, nonnegative slope and
   loss constraints, and training SSE to select a converged fit.
5. Write parameters, room predictions, fitting records and source receipts to a
   new local directory. The result checker checks that directory's arithmetic
   and file identities.

`benchmarks/mwm/code/mwm_core.py` contains the forward equations and fitting
rule. MAE averages all eighteen rooms. ARP uses dBm; AE and MAE use dB.
Numerical calculations retain full precision.

From the repository root, after preparing the external inputs:

```text
python -m pip install -r environments/mwm-requirements.txt
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --output "path/outside/repository/new-mwm-run"
python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"
```

The Python workflow consumes existing Wireless InSite exports offline.
Generating new simulation exports requires a valid Wireless InSite license.
