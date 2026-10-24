# MATLAB PWB interface

`matlab/run_pwb_case.m` reads exported Geo-ELCT tables and an explicit JSON configuration. The solver functions and material table in `matlab/core/` retain their source identities, checked by `verify_core_identity` against `matlab/source_identity.json` before computation. The adapter preserves material formulas, layers and boundary conventions.

## Run from a semantic-map example

Run these commands from the repository root with the Python environment described in `environments/` and a licensed MATLAB installation on PATH:

```powershell
python -m geo_elct extract --config examples/synthetic_two_rooms/case.json --mode none --out runs/synthetic_two_rooms_none
matlab -batch "restoredefaultpath; addpath('matlab'); run_pwb_case('configs/pwb_synthetic_multifrequency.json')"
```

The packaged example contains synthetic semantic maps, not a GNN prediction or a paper-building input. They can also be regenerated with `python scripts/make_synthetic_example.py --out local/synthetic_two_rooms`, then extracted using `local/synthetic_two_rooms/case.json`. The MATLAB configuration reads `runs/synthetic_two_rooms_none/debug_roomself.xlsx` and `debug_topology_edges.xlsx`, and writes `runs/pwb_synthetic_multifrequency`. It uses two distinct frequencies, 2.4 and 5 GHz, an explicitly chosen synthetic scale of 0.02 m/px and a 15 dBm transmitter in Room 1. These example settings are not a claim about the manuscript scenarios. Every JSON path is relative to its JSON file. Each output directory must be new; reruns require an explicitly new `output_dir`.

`configs/pwb_C4_room8_display.json` uses the C-4 transmitter room set `{1,2,4,8}`, with the existing source scale/heights and two distinct frequencies. Prepare Building C tables at its configured path first. This PWB interface example does not read WI reference arrays or verify physical Tx coordinates. Formal Part C calculations at 2.4, 5 and 28 GHz require the separate [verified WI input bundle](../benchmarks/mwm/input_schema.md).

## Schema, units and calls

| Input | Actual consumer and units |
|---|---|
| Room workbook | `readtable(..., 'Sheet', 'Rooms', 'VariableNamingRule', 'preserve')`; RoomID, Type, Area (px²), Perimeter (px), paired ExtWallLength_k / ExtWallWidth_k and opening slots |
| Topology workbook | First worksheet; RoomA, RoomB, ConnectionType and paired Length_k / Width_k; lengths and wall thicknesses are pixels |
| Exported directions | Python emits WallDir_k, but the preserved MATLAB core reads ExtWallDir_k or ExtWallDirection_k. OpenDir_k is read for exterior openings. The wall-direction mismatch remains visible and is not repaired by this adapter. |
| `frequency_hz` | Explicit vector in Hz, passed unchanged to both loss/coupling functions and the received-power function |
| `px2m` | Metres per pixel; lengths/thicknesses become metres and room areas become m² inside the original functions |
| `heights_m` | Wall, door and window heights in metres; internal Opening uses wall height |
| `door_is_open` | JSON boolean; open-door air coupling or the original closed wood-door stack. There is no window-open switch. |
| `tx_room_ids`, `tx_power_dbm` | Explicit RoomID-to-row mapping in unchanged room-table order; dBm converted to watts by the original solver |
| `case_id`, `sample_id`, `notes` | Descriptive metadata only; they select no mode, building geometry or physical parameter |

The chain is `roomWallSegments` → `computeRoomSelfLoss` / `computeRoomCouplings` → `assemblePropagationMatrix` → `calculateRoomPowerLevels` → `calculateReceivedPower`. RoomA/RoomB are mapped to actual RoomIDs; Outside is a boundary contribution to the diagonal and is not a transmitting or solved room. The original solver uses absorption and transmission areas, preserves its one-half angular factor, and returns fields in V/m and room-average received powers in dBm. Exported `Count` does not multiply MATLAB segment slots. Preserve paired length/width column ordering.

Only `matlab/core` is added, and every resolved solver path is checked. No recursive `genpath`, source-tree path injection or fixed author-drive input path is used. `compute_coverage_loss_from_list` runs after the solver as a separate coverage diagnostic; it does not produce or replace the PWB result.

## Preserved physical settings

The core keeps ceiling/floor absorption and vertical Outside coupling disabled, 0.12 m inactive ceiling/floor middle thickness, 1000 angular samples and default zero diagonal regularization. Exterior layers use material rows `[15,19,15]`, interior `[15,16,15]`, with the original 5 mm outer layers and table-derived middle thickness. Window stacks use `[13,21,13]` with a 1 mm air gap; closed doors use `[21,5,21]` and the original air layers. Original callers pass `Wm/4` for window/door middle-thickness conventions. Material parameters remain in `matlab/core/epsilon_paper_tabel.txt`. Use the actual scenario's configuration when interpreting these settings.

## Actual checks and limitations

The release check ran licensed MATLAB R2025b, version 25.2.0.2998904. `matlab.codetools.requiredFilesAndProducts` identified MATLAB only for the explicitly resolved adapter/core chain; no extra toolbox was identified.

| Fresh check | Observed status |
|---|---|
| Synthetic two-room input, `[2.4e9,5e9]` Hz | Completed in the candidate and a private isolated copy of the original core. RoomIDs, frequency vector, full wide table, transmitter vector, loss, internal and external/diagonal coupling, propagation matrices, field and ARP arrays were exactly equal (`isequaln`, zero absolute/relative tolerance). |
| Building C/7795 correction_v2 input, C-4 room set `{1,2,4,8}`, `[2.4e9,5e9]` Hz | Completed on 18 rooms; all ten full numerical/table fields exactly matched an isolated original-core evaluation with zero tolerance. This checks solver equivalence for these inputs, without WI validation. |
| Same synthetic input, one frequency `[2.4e9]` Hz | Failed in both versions with `assemblePropagationMatrix:SizeMismatch`; the preassembly arrays were exactly equal. This is an observed failure, not single-frequency support. |

To observe the real singleton failure directly after creating the two Geo-ELCT tables:

```powershell
matlab -batch "restoredefaultpath; addpath('matlab'); run_pwb_case('configs/pwb_synthetic_singleton_known_failure.json')"
```

MATLAB collapses the trailing singleton dimension, and the original assembler requires a three-dimensional coupling array. No frequency is silently repeated and the core is not patched. Two distinct frequencies exercise a true frequency axis; duplicate equal-frequency columns are not used in these checks.

`preassembly.mat` contains the fresh wide table, RoomIDs, input source vector and loss/coupling arrays, including when assembly fails. On success, `results.mat` also contains M, field and ARP arrays, and `room_power.csv` has RoomID, frequency-column index, Hz, V/m and dBm. `room_wall_segments.csv` exposes the consumer's actual segment/direction interpretation. `run_report.json` records version, configuration, input and core hashes, transmitter mapping, limitations and completion/failure. These are newly computed outputs, never copied saved reference results.

Exact agreement establishes migration equivalence for the checked input/configuration. It does not establish physical correctness, restore missing exterior directions, bind all manuscript scenarios or rerun WI. The release makes no full GNN-to-PWB reproduction claim while segmentation weights are missing.
