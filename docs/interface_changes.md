# Interfaces and numerical versions

Segmentation correction modes and opening-size aggregation are selected
independently. The default opening aggregation is an explicit numerical change;
MATLAB formulas, material values and correction thresholds are preserved.

| Area | Change | Numerical scope |
| --- | --- | --- |
| Python packaging | Install the Geo-ELCT and GNN adapters with pinned environment files | Packaging and dependencies |
| GNN | New hash-bound local source acquisition/inspection and byte-preserving semantic-map export | No model/inference replacement; external predictions remain unverified |
| Opening aggregation | Default `by_thickness_v1` groups internal doors/windows by room pair, type and thickness; sums lengths and retains thickness | Changes groups containing multiple components; `legacy_width_sum` explicitly reproduces the earlier aggregation |
| Part B | Reference-faithful protocol, all seeds 0–4, `none` and `correction_v2`, explicit `by_thickness_v1` | All 40 cases computed; typed connectivity and complete table equality evaluated separately |
| Fixed inputs | Hash-bound preparation; Part B selects all 20 inputs in `part_b_inputs.json` | Copies input files without changing labels |
| Synthetic example | New deterministic two-room semantic-map generator and saved migration target | New interface fixture; not a paper result |
| MATLAB | Existing core and material table with an explicit JSON adapter | Direction-field mismatch and singleton-frequency failure remain; multifrequency examples test the interface |
| MWM | Formal C-4 uses Rooms 1,2,4,8 and actual verified WI Tx/Rx inputs | Existing fitting rules retained; incomplete inputs produce no numerical results |
| Saved MWM baseline | Earlier Rooms 1,2,4,18 code and results retained under `archives/` | Original values preserved; separate from formal C-4 |

Source identities remain in `geo_elct/source_provenance.json`,
`geo_elct/correction_v2_provenance.json` and `matlab/source_identity.json`.
Private preparation files and newly computed runs are excluded from the repository.
