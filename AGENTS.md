# Working on this candidate

Preserve the numerical baseline unless a task explicitly authorizes a separate numerical change. The default mode is `none`. `legacy_revised` and `reference_faithful` name different algorithms; never apply both to one input or choose a mode from a building ID, clean map or reference result.

Keep source provenance current. Imports must resolve within the package, without links to an author's development tree. Outputs must use new run directories. Never overwrite reference results, local inputs or existing user changes.

`correction_v2` is a separately versioned opening repair, not a replacement for the frozen modes. Do not modify shared historical functions to change v2. Keep its source hash identity current and test preservation, restoration and misrepair independently. Unresolved components and anomalies must remain visible; an export or internal graph pass does not imply EM readiness.

Report migration equivalence separately from geometric correctness, runtime diagnostics and each evaluation definition. Known exterior-window losses must remain visible in tests and documentation. Do not change thresholds, inputs, seeds, references or pass criteria to hide them.

Read `docs/known_issues.md` before changing geometry or the MATLAB interface. Numerical fixes require a separate change and before/after validation. Do not add absent experimental implementations under the name of historical source code.

Do not commit restricted assets, private paths, correspondence, credentials, model weights or generated runs. Dataset/asset rights and project licensing require explicit clearance before public distribution. Do not publish, push or assign a license without authorization.
