# Current limitations

* **GNN NOT RUN:** full checkpoint/configuration/input binding, compatible
  dependency lock and verified prediction-to-map conversion are absent. Source
  and export-map interfaces do not establish end-to-end inference.
* **Part B scope:** all five fixed seeds at each of four levels were executed
  under `none` and `correction_v2` with `by_thickness_v1`. The results in
  [Part B](part_b.md) apply to the reference-faithful protocol on sample 7795;
  they do not establish recovery for other defect distributions or buildings.
  Clean repeats one map pair, and the inputs are annotation-derived.
* **Preserved geometry issues:** old modes can erase clean exterior windows.
  V2 retains an unresolved A corner window and historical legacy-family failures.
  Runtime success does not establish full geometric or physical validity.
* **Observed MATLAB singleton failure:** a true one-column `[2.4e9]` input fails
  in both original and candidate at `assemblePropagationMatrix:SizeMismatch`.
  Real `[2.4e9,5e9]` checks pass. No duplicated-frequency workaround is included.
* **Preserved direction mismatch:** Python emits `WallDir_k`; the unchanged PWB
  consumer reads `ExtWallDir_k`/`ExtWallDirection_k`. Exact original-core
  agreement does not validate that area accounting. This needs a separate
  numerical correction and before/after validation, outside release preparation.
* **Physical scenario binding:** material layers/thickness, ceiling/floor
  switches and door state are preserved. Multifrequency PWB examples check
  the solver interface; they do not validate WI reference powers or Tx locations.
* **Part C inputs:** formal C-4 uses Rooms 1,2,4,8. The verified Room-8 Tx
  location, its WI projects/power exports, exact receiver coordinates and
  matching Proposed references are still missing. The runner stops without
  numerical results until the [input contract](../benchmarks/mwm/input_schema.md)
  is satisfied. Earlier Rooms 1,2,4,18 numerical files remain in
  [the archive](../archives/mwm_rooms_1_2_4_18/README.md); they do not validate C-4.
* **Environment installation:** a fresh Python 3.11 virtual environment passed
  the standard online installation of the pinned translator requirements and
  editable package.
* **Third-party materials:** CubiCasa5K-derived extraction outputs are included
  under the original CC BY-NC 4.0 terms; attribution is retained in
  [third_party/README.md](../third_party/README.md). VecFloorSeg source, model
  weights and the Part C source geometry/WI inputs remain external.

Historical source-specific issues and parameter conventions remain available in
[known_issues.md](known_issues.md). Those prior finite checks are historical
evidence, not this preparation's execution log. New interfaces/docs are English;
existing core comments are preserved with the frozen source identity.

The published `output/` preserves the supplied files unchanged. All three
original files for IDs `158` and `9018` are zero-filled and unreadable. IDs
`1657`, `4520`, `6443`, `6683`, `8426` and `9451` have empty room/topology tables
and no ELCT graph image; nine additional topology tables are empty. Five
topology `RoomB` references lack a matching room attribute record:
`12712:4100`, `14963:4099/4098`, `3099:4096` and `3252:4101` (file ID:RoomID).
