# Explicit correction_v2 rules

`correction_v2` is a new behavior version (`correction_v2.0`). It calls the unchanged independent fragment → wall-boundary → wall-gap routines, applies its own opening logic, then invokes the unchanged B baseline extractor once. `none` remains the default. The source of all three historical modes and both evaluators is unchanged. V2 has no case-ID, filename, seed, manifest, reference-map, reference-table or target-length argument.

```powershell
python -m geo_elct extract --config <local-config>/building_A.json --mode correction_v2 --out <new-v2-run>
python -m geo_elct extract --wall <wall.png> --icon <icon.png> --rough <background.png> --source-type annotation_derived --mode correction_v2 --out <new-v2-run>
```

The opening implementation reads `geo_elct/correction_v2.py::CONFIG`; inherited preprocessing/validation routines still read their frozen `self_correction.REFERENCE_FREE_CONFIG` values. The corresponding groups in V2's dictionary are identity snapshots, not separate overrides. `correction_v2_effective_config.json` is generated documentation, **not** a new user parameter override interface. Each actual run records the effective dictionary and the versioned module hash. The frozen numerical dependencies retain their old hashes. No MATLAB code or setting is changed.

## Exterior evidence and orientation

The qualified background mask consists only of labels `{0,1,8,50}` connected to an image border by **four-neighbor** nonwall paths. Enclosed zero-label holes are not exterior evidence. A normal probe leaving the image also yields outside, consistently with the extractor's image-exit interpretation. Proximity to the border alone is insufficient.

For every occupied longitudinal scanline of a candidate opening, require a nonempty contiguous wall interval under that opening. Probe in opposite normal directions, through at most two additional wall pixels on each side, to a room instance, qualified background, or image exit. Every scanline must yield the same ordered pair of distinct domains, with at least one indoor room. Reject a locally observed third room in the 2 px neighborhood as ambiguous. Isolated components use their bounding-box long axis; square components remain unresolved. Completion proposals derive their axis from the two fragments' identical cross-wall extents and gap location, then validate both pieces and their union along that axis. This avoids the aspect-ratio inversion failure when deletion makes each fragment shorter than the wall thickness.

This changes opening-host validation only. The original extractor still treats its excluded nonwall labels as outside in its rays and retains its original bounds and table aggregation. The new qualification does not silently rewrite that baseline behavior; questionable retained components appear in diagnostics. Border-connected background can still reflect incorrect input annotation connectivity, so the local rule is not a proof of physical exterior geometry.

## Explicit actions

| Action | Required evidence and behavior |
|---|---|
| `keep_valid` | Supported opposite-domain host, no contact with another icon component, and original overlap ≥0.995; alternatively the separately defined original-footprint exterior-face rule below |
| `move` | Candidate is fully inside the image, overlap ≥0.995, supported opposite domains, no other icon within 1 px; unique best candidate under original ordering (maximum overlap, then minimum Manhattan shift) |
| `complete` | Same-label pieces have equal cross-wall extents and a 1–4 px gap; the entire fill is empty icon on wall; both pieces and their union have the same qualified host; no other icon contact and only one admissible partner per piece |
| `erase` | Area ≤8 px², isolated from other icons, and no wall anywhere in the entire square 3 px dilation envelope, which contains all allowed shifts. This is independent small-unsupported-speck evidence, not simply a failed candidate search |
| `keep_unresolved` | No legal shift, tied best shifts, existing icon contact, ambiguous completion partners or failed completion host/collision evidence. Retain the original pixels and request review |

Search offsets satisfy `dy²+dx²≤3²`. The shift overlap threshold remains **0.995**. Different-type collision and implicit same-type merging are prohibited; only an explicit recorded completion may merge components. Existing component contact is unresolved rather than a reason to slide otherwise supported openings away from each other. At most eight accepted completion passes per class use the fixed original budget.

The **original-footprint exterior-face rule** requires a completely filled rectangular component; exactly one normal face layer, at most 1 px thick, lies in qualified exterior background; the remaining rectangle covers a uniform **complete wall thickness**, with no further wall pixels immediately beyond either normal face; every longitudinal scanline has the same unambiguous room/outside pair. An outward shift that leaves an uncovered wall layer on the opposite face fails this rule and must use the strict candidate search. The rule changes no pixel and never accepts a shifted candidate. Thus it is not a lowered overlap threshold. It preserves raster face overhangs such as the identified ~0.967742 clean case under explicit structural evidence.

Action records contain the exact original/after footprint (lossless row-run encoding), bounding boxes, areas, dimensions and changes, original/after host evidence, disposition and reason. Completion records identify the two-parent merge; erase has an empty after-component/domain. Failed proposals and final unresolved components are reported separately. These records are in `correction/correction_log.json`.

## Two parameter corrections

The historical `min_component_fill_fraction=0.75` key is configured but **unused**. Its only occurrence in the frozen independent source is the dictionary entry. V2 omits it. The new exterior-face predicate checks exact rectangular occupancy as a separately defined structural rule, not 0.75.

Fragment 160 px² is the **absolute maximum candidate area**. The effective cap is `min(160, 0.002*A_ref)`, where `A_ref` is the median area of eligible 8-connected room-semantic components larger than 160; if none exist, use the median of all eligible components. With no components A_ref=0 and the relative term is infinity. The area cap alone never erases a component. The unchanged routine additionally requires no wall/excluded-background/opening contact in the 1 px ring, one other host **semantic label** in that ring, and that same host's share ≥0.80 among other room labels in the 2 px dominance ring. Accepted fragments are relabeled to the host. Runtime's separate instance-area ≤160 warning is a diagnostic, not this merge rule.

## Diagnostics and interpretation

`runtime_validation.json` preserves the existing independent internal-graph report. `correction_v2_diagnostics.json` separately reports exported exterior wall/opening counts and dimensional anomalies, exterior/unclassified opening-host anomalies, deletions, merges, unresolved components/events, and manual-review status. Deletion events require review even when the small-speck rule accepts them. Any unresolved component/event, exterior anomaly or failed original graph check prevents `all_implemented_checks_passed`.

`em_ready` is always false: these diagnostics do not validate downstream material, direction-field or matrix conventions. Even when every implemented check passes, completeness and correctness of the supplied map have not been proved. Clean-reference comparisons are performed by separate evaluators after extraction, never by correction. The observed limits and full fixed-case results are in [known_limitations.md](known_limitations.md).
