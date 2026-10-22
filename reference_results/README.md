# Saved comparison targets

`synthetic_two_rooms/` preserves the baseline output computed during this
preparation as a future migration target. It is not independent physical ground
truth or a fresh result from a later user's execution. The selected XLSX/NPY/JSON
files support full cell/mask/exterior comparison; run logs/caches and absolute
local path metadata are not distributed. Run extraction to a new directory first,
then evaluate explicitly against this target.

`baseline_manifest.json` and `frozen_A_manifest.json` are hash-only historical
identities of real building outputs and the separate A source variant. Their
binary data is external pending rights review. Newly written XLSX ZIP bytes may
differ from frozen bytes while cell values match; comparisons check every cell.

Part C's saved numerical references remain under `benchmarks/mwm/results/` and
are used for explicit evaluation only. `run.py` performs new model computation
in a fresh working directory, never copies predictions into computed outputs as
a substitute for calculating them.
