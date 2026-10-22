# Known issues preserved in this candidate

Version note: the historical modes below remain byte-for-byte in their numerical implementations. The separately selected `correction_v2` addresses the opening changes described in [v2 rules](correction_v2.md); its actual preservation, unresolved cases and failures are in [v2 results](known_limitations.md). The original issues and earlier results below are retained, not silently relabeled as repaired historical results. MATLAB is unchanged.

This candidate preserves the selected source behavior. Migration equivalence means that the packaged implementation reproduces its source implementation on the same input. It does **not** establish that correction preserves correct geometry, that runtime validation detects every defect, or that all publication results have been reproduced. No numerical fix below is included in this release candidate.

## K01 — Correction deletes exterior windows on clean inputs

The pre-migration audit used Buildings A/193, B/11184 and C/7795. The `none` mode preserves their original baseline tables. `reference_faithful` deletes three exterior-window records from A and three from B; `legacy_revised` deletes two from A and three from B. Neither changes the clean C tables. Room masks, IDs, areas, perimeters, exterior-wall geometry and internal-edge tables remain unchanged in these clean cases. Both original runtime validators can still report success.

| Clean input | Mode | Missing exterior-window records | Expected correctness status |
|---|---|---:|---|
| A/193 | `reference_faithful` | 3 | Known failure: clean geometry preservation |
| A/193 | `legacy_revised` | 2 | Known failure: clean geometry preservation |
| B/11184 | `reference_faithful` | 3 | Known failure: clean geometry preservation |
| B/11184 | `legacy_revised` | 3 | Known failure: clean geometry preservation |
| C/7795 | Either correction mode | 0 | Preserved on this input only |

The affected reference-faithful records are A: Room 1 horizontal 129×30 px, Room 2 vertical 61×30 px, Room 3 vertical 64×30 px; B: Rooms 1 and 4 horizontal 99×34 px, Room 5 horizontal 59×34 px. Legacy correction preserves the first A record and deletes the others. A regression that reproduces these deletions is a migration pass **and a geometry-preservation known failure**. Do not report an aggregate “all passed” by hiding these failures. The default is `none`; neither correction mode is selected from a building ID or a reference result.

## K02 — Exterior-domain definitions disagree

`geo_elct/self_correction.py::_domain_signature` searches a clipped image neighborhood for room IDs and in-image outside labels `{0,1,8,50}`. It does not add outside merely because that neighborhood crosses the image boundary. The legacy `_opening_domain_count` has the same relevant limitation. `geo_elct/exterior_wall.py::_shoot_ray_to_outside_openings` treats leaving the image as reaching outside. Five of the six reference-faithful missing clean windows touch an image boundary, so their validation neighborhoods fail to identify the second domain even though exterior extraction recognizes outside there.

The remaining A window has maximum candidate wall overlap approximately 0.967742, below the independent correction threshold 0.995. This is a distinct acceptance issue; changing outside alone would not resolve every case. No overlap threshold has been lowered.

## K03 — Rejected openings can be erased

In `geo_elct/self_correction.py::repair_opening_components`, no admissible shift (`rejected_unsnappable`) or tied best shifts (`rejected_ambiguous`) clear the original component. An action with `accepted=false` therefore does not mean “leave the input unchanged.” Small spurious-component removal is another explicit deletion action. The legacy `_snap_opening_components` also has a deletion branch for invalid unsnappable components, with different acceptance and ambiguity rules. Its behavior must not be described using the independent module's rule set.

A correctness check must examine corrected pixels, exterior-opening records and the full room table. A check of retained edges alone cannot find a removed opening.

## K04 — MATLAB does not consume the emitted exterior-wall direction field

The Python room-table writer emits `WallDir_k`. The frozen MATLAB `matlab/core/roomWallSegments.m` reads `ExtWallDir_k` or `ExtWallDirection_k`. All 9/14/23 exterior-wall segments in the A/B/C reference tables therefore enter the unknown-direction bucket in the existing consumer, while `OpenDir_k` is read normally for exterior openings. Direction-and-thickness matching in both self-loss and coupling calculations consequently does not subtract these openings from the corresponding wall bucket.

This field mismatch is preserved. Matching the original MATLAB result is not proof that this area accounting is correct. The numerical effect of a future correction must be measured separately; it is not inferred from the Python table differences.

## K05 — Scenario and material correspondence remains incomplete

The preserved active MATLAB settings use C's pixel scale, C-4 transmitter rows, disabled ceiling/floor absorption and disabled vertical outside coupling. Wall widths are used as middle-layer thicknesses with additional outer layers; door/window stacks use their existing width conventions. The active driver has an open-door setting and no corresponding window-open switch. The relation of these settings to every reported scenario, layer-thickness convention and sensitivity result remains unconfirmed. Packaging them does not validate all those results.

## K06 — Runtime and recovery metrics have different scopes

- Extractor `valid_topology`: checks retained topology/geometric records, but does not require the isolation condition and does not detect a correct opening that has already been deleted.
- Independent `reference_free_runtime_validation`: reads rooms and internal edges, including connectivity/small-room checks; it does not compare the two spreadsheets or validate all exterior attributes.
- Legacy `topology_relation_preserved`: requires room-count equality, no isolated rooms, untyped pair F1=1 and wall-edge F1=1. It does not require every door/window/open-space type or exported `Count` to match.
- Strict `topology_exact`: compares spatially matched room sets/types and internal `(RoomA, RoomB, ConnectionType) -> Count`. Exterior geometry remains outside this metric.
- Strict `room_table_exact` and `edge_table_exact`: separately compare full normalized records. Both are needed for “two tables exact”; runtime validity or topology exact cannot replace either result.

These names and outputs remain separate. The two retained representative perturbations are fixed existing inputs; they are not a fresh estimate of five-seed recovery rates.

## K07 — Extraction/export conventions remain frozen

Internal wall search uses the minimum extracted morphological perimeter divided by ten. Exterior search uses the perimeter divided by ten of the **last** traversed room. The 64 px diagnostic bound is not a common extraction bound. Opening aggregation and export `Count` retain their original meaning: exported segment slots, not an independently verified count of physical door/window leaves. These conventions must not be silently normalized during later cleanup.

## K08 — MATLAB singleton frequency dimension fails in the original and candidate

The finite MATLAB R2025b check at 2.4 GHz fails in both original and packaged `assemblePropagationMatrix` with `SizeMismatch`: the original array-shape check does not accommodate the collapsed singleton frequency dimension. This is a preserved executable failure, not a successful single-frequency run. The wrapper does not repeat frequencies automatically or patch the core.

A separate explicit configuration with two entries `[2.4e9, 2.4e9]` evaluates the same physical frequency twice and preserves a non-singleton frequency dimension. Under that configuration, original and packaged C-4 wide tables, RoomIDs, self-loss, internal/external coupling, propagation matrices, field and received-power arrays match exactly (`isequaln=true`, maximum difference 0). This establishes a limited migration equivalence check, not support for a singleton input or validation of all reported scenarios. Any later shape fix needs an independently recorded behavior change and tests for one and multiple frequencies.

See [known_limitations.md](known_limitations.md) for proposed future work and [reproduction.md](reproduction.md) for the supported claims.
