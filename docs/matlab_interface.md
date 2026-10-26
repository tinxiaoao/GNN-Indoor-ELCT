# MATLAB PWB interface

`matlab/run_pwb_case.m` reads Geo-ELCT room/topology workbooks and an explicit
physical configuration, then runs the broadband power balance solver. The
functions and material table in `matlab/core/` are checked against
`matlab/source_identity.json` before computation.

## Run the synthetic example

Use the Python environment in [environments](../environments/README.md) and a
licensed MATLAB installation on PATH. Run from the repository root:

```powershell
python -m geo_elct extract --config examples/synthetic_two_rooms/case.json --mode none --out runs/synthetic_two_rooms_none
matlab -batch "restoredefaultpath; addpath('matlab'); run_pwb_case('configs/pwb_synthetic_multifrequency.json')"
```

The synthetic maps demonstrate the table-to-solver interface. The configuration
uses 2.4 and 5 GHz, a 0.02 m/px scale and a 15 dBm transmitter in Room 1.
Adapt table paths, scale, heights, frequencies, transmitter rooms and powers
for other inputs. Paths resolve relative to the JSON file. Choose a new
`output_dir` for every run.

## Configuration and units

| Field/input | Use |
| --- | --- |
| Room workbook | `Rooms` sheet; RoomID, Type, Area, Perimeter, exterior wall dimensions and opening slots |
| Topology workbook | First sheet; RoomA, RoomB, ConnectionType and paired Length_k/Width_k |
| Direction columns | Exterior walls: `ExtWallDir_k` or `ExtWallDirection_k`; exterior openings: `OpenDir_k`. Python exports `WallDir_k`; prepare the names expected by the core for directional area accounting. |
| `frequency_hz` | Frequency vector in Hz; use at least two distinct entries with the current assembler |
| `px2m` | Converts pixel lengths/thicknesses to metres and pixel areas to square metres |
| `heights_m` | Wall, door and window heights in metres; internal Opening uses wall height |
| `door_is_open` | Selects open-door air coupling or the closed-door layer stack |
| `tx_room_ids`, `tx_power_dbm` | Map transmitter powers in dBm to RoomIDs; powers convert to watts in the solver |
| `case_id`, `sample_id`, `notes` | Run metadata |

The computation proceeds through `roomWallSegments`, `computeRoomSelfLoss`,
`computeRoomCouplings`, `assemblePropagationMatrix`, `calculateRoomPowerLevels`
and `calculateReceivedPower`. Outside contributes to the boundary terms.
Workbook `Count` denotes dimension records; the core reads the paired segment
slots directly.

The current assembler expects a three-dimensional coupling array. A single
frequency collapses its trailing dimension in MATLAB and raises
`assemblePropagationMatrix:SizeMismatch`; the supplied multi-frequency example
provides the supported array shape. See [implementation notes](implementation_notes.md)
for the extraction and interface conventions.

## Physical settings

The core uses its existing absorption/transmission formulas and one-half
angular factor. Ceiling/floor absorption and vertical Outside coupling are
disabled in the source configuration; the inactive ceiling/floor middle
thickness is 0.12 m. The angular integration uses 1000 samples and the default
diagonal regularization is zero.

Exterior layers use material rows `[15,19,15]`, interior layers `[15,16,15]`,
with 5 mm outer layers and table-derived middle thicknesses. Window stacks use
`[13,21,13]` with a 1 mm air gap; closed-door stacks use `[21,5,21]` and the
source air layers. Existing calls use `Wm/4` for window/door middle thickness.
Material parameters are in `matlab/core/epsilon_paper_tabel.txt`.

## Outputs

`preassembly.mat` records the input wide table, RoomIDs, source vector, losses
and coupling arrays. A completed calculation writes `results.mat` with the
propagation matrix, field and ARP arrays, plus `room_power.csv` with frequency,
V/m and dBm values. `room_wall_segments.csv` records segment/direction
interpretation; `run_report.json` records the configuration, source hashes and
execution status. `compute_coverage_loss_from_list` provides a separate
coverage diagnostic.
