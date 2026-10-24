# Configuration fields that are actually consumed

`geo_elct.api.load_case` resolves paths relative to the JSON file, checks `schema_version=1`, validates map hashes and dimensions, reads `extraction.mode` and `outputs.directory`, and rejects unsupported extraction overrides or `lightweight=true`. `geo_elct.__main__` accepts explicit command-line mode/output overrides. Modes are never inferred from identifiers or reference paths.

| Field | Runtime use |
|---|---|
| `maps.wall.path`, `maps.icon.path`, `maps.rough.path` | Input loading and copied run-local maps; rough is plotting only |
| Each map's `sha256`, `width`, `height` | Checked against the supplied local files before extraction; no resampling or recoloring |
| `extraction.mode` | Exact explicit selection of `none`, `legacy_revised`, `reference_faithful` or `correction_v2`; default remains `none` |
| `extraction.opening_aggregation` | Independent dimension aggregation identity: `by_thickness_v1` (default) groups internal door/window components by room pair, type and thickness, sums lengths and retains that thickness; `legacy_width_sum` explicitly reproduces the historical width sum. The CLI override is `--opening-aggregation`. |
| `extraction.lightweight` | Must be false; both real Excel tables are always exported |
| `outputs.directory` | New output path unless `--out` explicitly overrides it |
| `input_source_type` | Recorded as declared provenance; the extractor does not run or authenticate a GNN |
| `building`, `sample_id` | Run metadata only; do not alter computation |
| `dataset_split` | Provenance documentation only, not a training/validation switch |
| `reference_results` | Documentation of separate expected reference locations; extraction never reads these fields |
| `matlab_documentation_only` | Evidence notes only; no MATLAB parameter is configured by Python extraction |

Threshold dictionaries remain source constants. `run_manifest.json.parameters_read_from_implementation` records the selected source dictionary. Historical `reference_faithful` includes `min_component_fill_fraction=0.75`, which is configured but **unused**; its presence does not make it an acceptance condition. V2 omits that unused key. Fragment 160 px² is an absolute area cap, not a lower bound or an unconditional deletion criterion; the effective cap is `min(160,0.002*A_ref)` with the unchanged neighborhood protections. See [v2 rules](correction_v2.md) for the complete interpretation. Other fixed extraction rules and their source hashes are recorded; per-input search limits remain derived from the original room perimeter rule. A copy of a threshold into JSON is not exposed as a new configurable function.

The MATLAB adapter has its own JSON contract documented in `matlab_interface.md`. Its table/output paths and numerical fields are actually read. Current examples use two distinct frequencies or an explicitly labeled singleton known failure. No frequency is duplicated by the wrapper.

Neither the Python extractor nor the MATLAB adapter supports concurrent use of its in-process API with shared global library state. Use separate command processes and new run directories. The Python wrapper assigns a run-local temporary directory; plotting uses a noninteractive backend by default.

Room `Perimeter` is the pixel count of the 3×3 morphological gradient
(dilation minus erosion), rather than a Euclidean contour length. Internal
wall rays use `round(min(Perimeter)/10)` as their wall-pixel count limit.
Exterior wall/opening rays use `Perimeter/10` from the last enumerated room,
without rounding. Rays are rejected when their wall-pixel count reaches the
corresponding limit; reaching an excluded exterior label or leaving the image
after traversing wall supplies exterior evidence. A search limit alone does
not classify a wall as exterior.

The topology workbook groups dimension records into rows by room pair and
interface type. `Count` is the number of exported `Length_k`/`Width_k` pairs.
For doors and windows, the raw `edges.json` field `num` separately counts
4-connected raster components in each thickness group; it is not multiplied
into the exported length and is not a count of verified physical door leaves.
Lengths and thicknesses are pixels and areas are pixels squared. Convert
lengths using `px2m` and areas using `px2m**2`; calibration values are unchanged.
