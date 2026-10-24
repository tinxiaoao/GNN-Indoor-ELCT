# Saved comparison targets

`synthetic_two_rooms/` preserves the baseline output computed during this
preparation as a future migration target. It is not independent physical ground
truth or a fresh result from a later user's execution. The selected XLSX/NPY/JSON
files support full cell/mask/exterior comparison; run logs/caches and absolute
local path metadata are not distributed. Run extraction to a new directory first,
then evaluate explicitly against this target.

`baseline_manifest.json` and `frozen_A_manifest.json` retain hash-only identities
of earlier building outputs and the separate A source variant. Their original
binary comparison files are external. Newly written XLSX ZIP bytes may differ
while cell values match; compare workbook cells rather than ZIP bytes.

Earlier MWM references and results are preserved under
[archives/mwm_rooms_1_2_4_18](../archives/mwm_rooms_1_2_4_18/README.md). Their
fourth deployment uses Room 18. Formal C-4 uses Rooms 1,2,4,8 and requires the
verified inputs in [the MWM schema](../benchmarks/mwm/input_schema.md); no
verified C-4 numerical results are bundled.
