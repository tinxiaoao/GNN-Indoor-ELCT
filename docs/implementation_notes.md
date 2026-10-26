# Implementation notes

These notes describe the input and output conventions used by the computation
programs. See [configuration](configuration.md), [the MATLAB interface](matlab_interface.md)
and [topology evaluation](part_b.md) for commands and parameters.

## Extraction and correction modes

`none` exports geometry from the supplied semantic maps. `legacy_revised` and
`reference_faithful` retain their respective source rules; `correction_v2`
provides the versioned opening-repair workflow. Select a mode explicitly to
match the intended processing method.

Correction can move, merge or remove opening components. Historical modes can
remove exterior-window components, including on otherwise clean maps. Use
`none` to preserve the input opening map, or inspect the action records and
exported exterior-opening tables when applying correction. V2 retains
unresolved components and writes their review status in its diagnostic output.

The correction neighborhood and exterior ray routines use their own image
boundary rules. The v2 opening rules are described in
[correction_v2.md](correction_v2.md). Run logs record the selected implementation,
parameters and input identities.

## Dimensions and aggregation

Lengths and wall thicknesses are in pixels; areas are in pixels squared.
The MATLAB conversion uses `px2m` for lengths and its square for areas.
Room perimeter is the pixel count of the 3×3 morphological gradient. Internal
wall searches use the rounded minimum room perimeter divided by ten; exterior
searches use the last enumerated room's perimeter divided by ten.

`by_thickness_v1` groups internal doors/windows by room pair, interface type
and thickness, sums lengths and retains each thickness. `legacy_width_sum`
selects the earlier aggregation. Workbook `Count` denotes exported dimension
records; the raw edge `num` field records connected raster components.

## MATLAB input conventions

The PWB core reads exterior-wall directions from `ExtWallDir_k` or
`ExtWallDirection_k`, and opening directions from `OpenDir_k`. The Python
exporter writes wall directions as `WallDir_k`; the adapter does not rename
that column automatically. Directional area accounting therefore requires
preparing the column names expected by the core.

Use the provided two-frequency example for the PWB workflow. The current
assembler requires a three-dimensional coupling array; a one-frequency input
collapses the trailing dimension in MATLAB and raises
`assemblePropagationMatrix:SizeMismatch`. Frequencies are passed through as
specified in the configuration. Material layers, opening state and the
ceiling/floor settings are described in [the MATLAB interface](matlab_interface.md).

## Evaluation fields

The programs report complementary quantities:

- Runtime diagnostics describe the extracted internal graph and processing events.
- Topology matching compares room count, spatial room correspondence and typed
  room-pair connections.
- Dimension-record `Count`, room types, complete table equality and pixel
  correspondence are reported separately by the evaluation programs.

Use the metric corresponding to the intended comparison. The correction
program reads its input maps; clean-reference comparisons are a separate step.
