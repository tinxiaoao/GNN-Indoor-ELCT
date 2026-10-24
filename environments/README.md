# Environments

Run the documented commands from the repository root. Python 3.11 is the tested
version. Create a separate environment rather than modifying an existing
research environment:

```powershell
python -m venv .venv-translator
.\.venv-translator\Scripts\Activate.ps1
python -m pip install -r environments/translator-requirements.txt
python -m pip install -e . --no-deps
python -m geo_elct --help
```

On macOS or Linux, activate with `source .venv-translator/bin/activate`.
Running `python -m geo_elct` directly from the source tree also works after
installing its requirements. Root configurations and benchmark inputs are
provided in the source tree; use that tree or its editable installation.

| Module | Requirements |
| --- | --- |
| Geo-ELCT | `translator-requirements.txt`: NumPy 1.26.4, OpenCV 4.11.0.86, pandas 2.2.3, openpyxl 3.1.5, Pillow 9.4.0, Matplotlib 3.9.2 |
| MWM benchmark | `mwm-requirements.txt`: NumPy 1.26.4, SciPy 1.13.1, Shapely 2.0.6 |
| MATLAB PWB | Licensed MATLAB; the adapter and core were tested with R2025b |
| GNN adapter | Standard library for source preparation; Pillow for map handoff. Full inference needs a separate upstream environment; see [gnn.md](gnn.md). |

Install MWM requirements before using `benchmarks/mwm/run.py`:

```powershell
python -m pip install -r environments/mwm-requirements.txt
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/verified-C4-inputs" --output "path/outside/repository/new-mwm-run"
python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"
```

The MWM commands require the actual C-4 Room-8 Tx location, WI receiver/power
exports and matching Proposed references described in the
[input schema](../benchmarks/mwm/input_schema.md). The supplied template is
incomplete and cannot produce numerical results. Earlier Rooms 1,2,4,18
replay commands are in the [archive](../archives/mwm_rooms_1_2_4_18/README.md).

Numerical limitations and MATLAB's preserved singleton-frequency failure are
documented in [known issues](../docs/known_issues.md).
