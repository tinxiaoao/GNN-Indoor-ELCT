# Release preparation changes

No numerical Geo-ELCT, PWB or MWM algorithm was changed. Relative to the existing
working package, the preparation added or changed these interfaces:

| Area | Change | Numerical scope |
| --- | --- | --- |
| Python packaging | Include `gnn*`; select the cv2 dependency distribution matching available metadata; retain existing development version | Package metadata only; loaded cv2 version recorded separately |
| GNN | New hash-bound local source acquisition/inspection and byte-preserving semantic-map export | No model/inference replacement; external predictions remain unverified |
| Part B | Preserve two existing generators; package imports, remove path bootstrap, reject existing CLI output | Numerical ASTs/constants unchanged; no new seeds/intensities |
| Fixed inputs | New whitelist/hash-bound acquisition script; 43 original identities | Copies authorized local data only; no source module import |
| Synthetic example | New deterministic two-room semantic-map generator and saved migration target | New interface fixture; not a paper result |
| MATLAB | Preserve eight core functions/material table exactly; wrapper explanatory known-issue text updated | No formula, direction-field or singleton fix; example configurations explicit |
| MWM | Preserve three original numerical scripts; external-input preparation and fresh-work-copy runner | Existing fits/objective/constraints/starts/tolerance retained |
| Configurations/docs | Replace stale duplicate-frequency demonstration with distinct-frequency and singleton examples; separate Room8 display from C-4v; update paths/help/provenance/limits | No change to confirmed references; Supplementary document copied byte-for-byte |

Source identities remain in `geo_elct/source_provenance.json`,
`geo_elct/correction_v2_provenance.json` and `matlab/source_identity.json`.
Private preparation logs and newly computed runs are excluded from the repository.
