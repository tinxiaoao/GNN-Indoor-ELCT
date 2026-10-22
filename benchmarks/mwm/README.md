# Part C MWM benchmark

See [the Part C reproduction guide](../../docs/part_c.md) for scope, validation,
and limitations. The three files under `code/` are unchanged from the confirmed
handoff package. `manifest.json` records that package's historical source hashes
and environment, rather than the environment used for this release check.

The `inputs/` and `results/` files are **frozen references**, not outputs of a new
run. Full precision is retained. The SVG and derived geometry arrays are omitted
because their redistribution permission is not established by the handoff.
Obtain authorized local access to the exact source package; its SHA256 is fixed
in `external_inputs.json`. This candidate supplies no download URL or WI software.

From the release root, using a separate MWM Python environment:

```text
python benchmarks/mwm/verify_results.py
python benchmarks/mwm/prepare_inputs.py --source-package "path/to/R1Q6_WI_Confirmed_Reproducible.zip" --output "runs/part-c-inputs"
python benchmarks/mwm/run.py --inputs "runs/part-c-inputs" --output "runs/part-c-calculation"
python benchmarks/mwm/verify_results.py --results "runs/part-c-calculation/replayed/results.npz"
```

Choose new directories for every preparation and calculation. `run.py` copies
the local inputs, reference results and original code into a new working root.
The original calculation rebuilds SVG-derived inputs inside that disposable
root, writes new predictions to `replayed/`, and compares with frozen references.
It preserves the three C-1 parameter sets and recalibrates the other nine sets.

Running `code/recalculate.py --root benchmarks/mwm` directly is unsuitable for
this curated candidate: the geometry asset is deliberately external, and that
original entry rewrites derived inputs. Use the wrapper above.

`verify_results.py` without `--results` only checks arithmetic of saved
references. Passing the new `replayed/results.npz` checks a fresh calculation.
No command here runs Wireless InSite or recomputes the saved Proposed model.

Code and author-generated numerical data require the author's release-license
confirmation. No license is granted to third-party geometry by this package.
