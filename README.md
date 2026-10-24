# GNN-Indoor-ELCT

Code and automatically extracted CubiCasa5K results for indoor electrically large cavity topology (ELCT) modelling and broadband power balance calculations.

## Code modules

| Module | Location | Purpose |
| --- | --- | --- |
| GNN interface | `gnn/` | Prepare the external VecFloorSeg source and hand off existing semantic label maps. Full GNN inference requires external checkpoints, configuration and a prediction exporter; these are not bundled. |
| Geo-ELCT | `geo_elct/` | Extract room attributes, topology tables and ELCT graphs from room/opening label maps. |
| IndoorEMT / PWB | `matlab/` | Calculate room power levels from the extracted tables and an explicit physical configuration. |

`experiments/` contains perturbation and comparison tools; `benchmarks/mwm/` contains the independent Multi-Wall Model benchmark. See the [program map](docs/reproduction.md) and [known limitations](docs/known_limitations.md).

## Installation and running

Use Python 3.11 for the pinned Python environment. Run commands from the repository root:

```powershell
git clone https://github.com/tinxiaoao/GNN-Indoor-ELCT.git
cd GNN-Indoor-ELCT
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r environments/translator-requirements.txt
python -m pip install --no-deps -e .
python -m geo_elct --help
```

On Linux/macOS, activate with `source .venv/bin/activate`. Use a separate environment for the external GNN source; see [GNN instructions](gnn/README.md).

Run the supplied synthetic example, then the MATLAB power balance solver (tested with MATLAB R2025b):

```powershell
python -B -m geo_elct extract --config examples/synthetic_two_rooms/case.json --mode none --out runs/synthetic_two_rooms_none
matlab -batch "addpath('matlab'); run_pwb_case('configs/pwb_synthetic_multifrequency.json');"
python -B -m unittest discover -s tests -v
```

Each run needs a new output directory. The default correction mode is `none`; `legacy_revised`, `reference_faithful` and `correction_v2` are separate, explicitly selected modes. Internal door/window components with the same room pair, type and thickness have their lengths summed while retaining that thickness. Use `--opening-aggregation legacy_width_sum` to reproduce the earlier dimension aggregation. `Count` gives the exported dimension entries; component counts are stored separately. Lengths use `px2m` and areas use its square when converting to physical units.

For your own maps, use `python -m geo_elct extract --help`. Label definitions, units and configuration fields are in [configuration](docs/configuration.md) and the [MATLAB interface](docs/matlab_interface.md). The [MWM instructions](benchmarks/mwm/README.md) explain the separate benchmark and its required external geometry inputs.

The [Part B protocol](docs/part_b.md) gives the fixed five-seed perturbation settings and topology-matching results. MWM uses C-1 = [1], C-2 = [1,2], C-3 = [1,2,4], and C-4 = [1,2,4,8]. Supply the verified WI transmitter coordinates, actual receiver samples, received-power exports and matching Proposed room data described by the [MWM input schema](benchmarks/mwm/input_schema.md), then run:

```powershell
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --output "path/outside/repository/new-mwm-run"
```

The supplied C-4 template requires verified Room 8 inputs before calculation. Earlier Rooms 1, 2, 4 and 18 benchmark data and their replay commands are in the [archive](archives/mwm_rooms_1_2_4_18/README.md).

## Public dataset

[Browse all extraction results](https://github.com/tinxiaoao/GNN-Indoor-ELCT/tree/main/output) or [download the repository with the full output dataset](https://github.com/tinxiaoao/GNN-Indoor-ELCT/archive/refs/heads/main.zip).

The `output/` directory contains every file from the supplied extraction output (about 240 MiB), retaining the original filenames and structure:

| Directory | Contents |
| --- | --- |
| `output/roomself_excel/` | 3,829 room attribute workbooks |
| `output/topology_excel/` | 3,829 topology workbooks |
| `output/topology/` | 3,823 ELCT graph images |

Match files across directories by their building ID filename. This includes all available extraction results, beyond Buildings A, B and C.

The dataset contains automatically extracted room attributes, topology tables, and ELCT graphs from CubiCasa5K. The results have not all been manually verified and may require further screening.

Source: [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k), [original dataset](https://zenodo.org/records/2613548), by Ahti Kalervo, Juha Ylioinas, Markus Häikiö, Antti Karhu and Juho Kannala (2019), [CubiCasa5K paper](https://arxiv.org/abs/1904.01920). The extracted data are derived from CubiCasa5K; retain attribution and its [CC BY-NC 4.0 license](third_party/CubiCasa5K-LICENSE), including the noncommercial condition. See [third-party notices](THIRD_PARTY_NOTICES.md).
