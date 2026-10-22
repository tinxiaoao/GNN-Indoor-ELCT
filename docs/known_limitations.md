# Current limitations

* **GNN NOT RUN:** full checkpoint/configuration/input binding, compatible
  dependency lock and verified prediction-to-map conversion are absent. Source
  and export-map interfaces do not establish end-to-end inference.
* **Part B aggregate NOT REPRODUCED:** two different fixed input families were
  found. A unique Supplementary S2 source/mode/evaluator binding is unconfirmed;
  B's GNN-output description conflicts with annotation-derived located maps.
  Ten finite new extractions establish migration, not five-seed recovery rates.
* **Preserved geometry issues:** old modes can erase clean exterior windows.
  V2 retains an unresolved A corner window and historical legacy-family failures.
  Runtime success is not full geometric or EM validity. V2 diagnostics always
  keep `em_ready=false`.
* **Observed MATLAB singleton failure:** a true one-column `[2.4e9]` input fails
  in both original and candidate at `assemblePropagationMatrix:SizeMismatch`.
  Real `[2.4e9,5e9]` checks pass. No duplicated-frequency workaround is included.
* **Preserved direction mismatch:** Python emits `WallDir_k`; the unchanged PWB
  consumer reads `ExtWallDir_k`/`ExtWallDirection_k`. Exact original-core
  agreement does not validate that area accounting. This needs a separate
  numerical correction and before/after validation, outside release preparation.
* **Physical scenario binding:** material layers/thickness, ceiling/floor
  switches and door state are preserved. Their correspondence to every paper
  scenario is not confirmed. Room-8 display and C-4v validation are different.
* **Part C scope:** fresh recovered MWM calculation passed the original
  tolerance and S3–S5 checks, but fixed Proposed values were not regenerated.
  WI software was not run. Room-18 geometric-center and receiver-grid coordinates
  are not independently matched to WI coordinate export.
* **Environment installation:** isolated local dependency copies passed;
  a fresh online installation remains unverified after a download hash failure.
* **Third-party materials:** CubiCasa5K-derived extraction outputs are included
  under the original CC BY-NC 4.0 terms; attribution is retained in
  [third_party/README.md](../third_party/README.md). VecFloorSeg source, model
  weights and external Part C SVG/geometry inputs remain external. The
  Supplementary document is copied unchanged; no manuscript text or numerical
  table was edited.

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
