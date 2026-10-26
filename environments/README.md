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
installing its requirements. Use the source tree or its editable installation
for the supplied configurations and command-line tools.

| Module | Requirements |
| --- | --- |
| Geo-ELCT | `translator-requirements.txt`: NumPy 1.26.4, OpenCV 4.11.0.86, pandas 2.2.3, openpyxl 3.1.5, Pillow 9.4.0, Matplotlib 3.9.2 |
| MWM calculation | `mwm-requirements.txt`: NumPy 1.26.4, SciPy 1.13.1, Shapely 2.0.6 |
| MATLAB PWB | Licensed MATLAB; the adapter and core were tested with R2025b |
| GNN adapter | Standard library for source preparation; Pillow for map handoff. Full inference needs a separate upstream environment; see [gnn.md](gnn.md). |

Install MWM requirements before using `benchmarks/mwm/run.py`:

```powershell
python -m pip install -r environments/mwm-requirements.txt
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --validate-only
python benchmarks/mwm/run.py --inputs "path/to/mwm-inputs" --output "path/outside/repository/new-mwm-run"
python benchmarks/mwm/verify_results.py --results "path/outside/repository/new-mwm-run"
```

The MWM commands process an external input directory containing geometry,
simulation exports and corresponding room references, as described in
[the input schema](../benchmarks/mwm/input_schema.md). Input datasets are
supplied separately from the calculation code. Existing Wireless InSite exports
are processed offline; generating new exports requires a valid Wireless InSite
license.

See [the MATLAB interface](../docs/matlab_interface.md) for its units and software
requirements, and [implementation notes](../docs/implementation_notes.md) for
field conventions.
