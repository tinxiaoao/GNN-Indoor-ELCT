# Modules and interface conventions

Segmentation correction modes and opening-size aggregation are selected
independently. Each run records its configuration and source identities.

| Module | Interface | Calculation convention |
| --- | --- | --- |
| Python packaging | Geo-ELCT and GNN adapters with pinned environment files | Explicit module dependencies and command-line entry points |
| GNN | Source preparation and semantic-map handoff | Upstream source, configuration and checkpoints supplied externally |
| Opening aggregation | `by_thickness_v1` groups internal doors/windows by room pair, type and thickness | Sum component lengths while retaining thickness; `legacy_width_sum` selects the earlier convention |
| Topology workflow | Perturbation generation, batch extraction and topology evaluation programs | Room count, spatial room matching, typed connectivity and complete tables are evaluated separately |
| Fixed inputs | Hash-bound input preparation | Copy source files without changing labels |
| Synthetic example | Deterministic two-room semantic-map generator and regression fixture | An executable interface example |
| MATLAB | JSON adapter for the existing core and material table | Explicit physical units, frequencies, layer settings and room-ID mapping |
| MWM | Forward calculation, coefficient fitting and processing of external exports | External case labels and deployment configuration; fixed multistart fitting rules |

Source identities are recorded in `geo_elct/source_provenance.json`,
`geo_elct/correction_v2_provenance.json` and `matlab/source_identity.json`.
See [implementation notes](implementation_notes.md) for field interpretation
and [the program guide](reproduction.md) for commands.
