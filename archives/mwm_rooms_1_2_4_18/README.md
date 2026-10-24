# Rooms 1, 2, 4, 18 numerical baseline

This archive preserves the earlier MWM code, references and results at 2.4,
5 and 28 GHz. Its fourth deployment uses Room 18. It is separate from the
current C-4 deployment with Room 8. Files retain their original numerical
values and labels.

The [previous Supplementary document](Supplementary%20Material.docx) is retained
with this baseline. Its numerical tables are not results for the current
Room 8 deployment.

From the repository root, in the MWM environment:

```text
python archives/mwm_rooms_1_2_4_18/verify_results.py
python archives/mwm_rooms_1_2_4_18/prepare_inputs.py --source-package "path/to/R1Q6_WI_Confirmed_Reproducible.zip" --output "path/outside/repository/new-archive-inputs"
python archives/mwm_rooms_1_2_4_18/run.py --inputs "path/outside/repository/new-archive-inputs" --output "path/outside/repository/new-archive-run"
python archives/mwm_rooms_1_2_4_18/verify_results.py --results "path/outside/repository/new-archive-run/replayed/results.npz"
```

The source package SHA256 and whitelisted hashes are in `external_inputs.json`.
Obtain an authorized local copy. The source SVG and derived geometry arrays are
external to this archive. Preparation and replay use new directories and
preserve existing inputs and reference results.

The original SVG reconstruction uses 11,480 receiver points. It does not read
the current WI project's receiver-coordinate export. Saved Proposed room ARPs
are inputs to this replay; neither Wireless InSite nor the Proposed model runs
through these commands.
