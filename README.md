# GNN-Indoor-ELCT

Code and automatically extracted CubiCasa5K results for indoor electrically large cavity topology (ELCT) modelling and broadband power balance calculations.

## Code modules

| Module | Location | Purpose |
| --- | --- | --- |
| GNN interface | `gnn/` | Integrate the external VecFloorSeg source and hand off semantic label maps using upstream checkpoints and configuration. |
| Geo-ELCT | `geo_elct/` | Extract room attributes, topology tables and ELCT graphs from room/opening label maps. |
| IndoorEMT / PWB | `matlab/` | Calculate room power levels from the extracted tables and an explicit physical configuration. |

`experiments/` provides perturbation generation and topology evaluation programs. `benchmarks/mwm/` provides Multi-Wall Model forward calculation, coefficient fitting and input processing. See the [program map](docs/reproduction.md).

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

For your own maps, use `python -m geo_elct extract --help`. Label definitions, units and configuration fields are in [configuration](docs/configuration.md) and the [MATLAB interface](docs/matlab_interface.md). The [MWM instructions](benchmarks/mwm/README.md) describe the calculation workflow and its external input format.

The [topology workflow](docs/part_b.md) describes perturbation generation, extraction and evaluation metrics. The [MWM module](benchmarks/mwm/README.md) is distributed as calculation code and methods; simulation inputs and numerical comparison datasets are supplied separately by the user. Prepare an input directory according to the [MWM input schema](benchmarks/mwm/input_schema.md), then run:

```powershell
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --output "path/outside/repository/new-mwm-run"
```

The Python MWM workflow processes existing simulation exports offline. Generating new Wireless InSite exports requires a valid license for that software.

## Public dataset

[Browse all extraction results](https://github.com/tinxiaoao/GNN-Indoor-ELCT/tree/main/output) or [download the repository with the full output dataset](https://github.com/tinxiaoao/GNN-Indoor-ELCT/archive/refs/heads/main.zip).

The `output/` directory contains every file from the supplied extraction output (about 240 MiB), retaining the original filenames and structure:

| Directory | Contents |
| --- | --- |
| `output/roomself_excel/` | 3,829 room attribute workbooks |
| `output/topology_excel/` | 3,829 topology workbooks |
| `output/topology/` | 3,823 ELCT graph images |

Match files across directories by their building ID filename. This includes all available extraction results, beyond Buildings A, B and C.

The dataset contains automatically extracted room attributes, topology tables and ELCT graphs from CubiCasa5K, retaining the original building identifiers for downstream use.

Source: [CubiCasa5K](https://github.com/CubiCasa/CubiCasa5k), [original dataset](https://zenodo.org/records/2613548), by Ahti Kalervo, Juha Ylioinas, Markus Häikiö, Antti Karhu and Juho Kannala (2019), [CubiCasa5K paper](https://arxiv.org/abs/1904.01920). The extracted data are derived from CubiCasa5K; retain attribution and its [CC BY-NC 4.0 license](third_party/CubiCasa5K-LICENSE), including the noncommercial condition. See [third-party notices](THIRD_PARTY_NOTICES.md).
