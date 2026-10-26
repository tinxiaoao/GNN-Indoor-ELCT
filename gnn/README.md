# GNN source and semantic-map interface

This module prepares a separately obtained VecFloorSeg source archive and
passes existing semantic maps to Geo-ELCT. It does not include trained GNN
weights or perform full inference. The supplied A/B/C map identities are
annotation-derived; see [provenance](../docs/gnn_provenance.md).

Run from the repository root after installing the translator requirements:

```powershell
python -B -m gnn --help
python -B -m gnn inspect-source --archive <VecFloorSeg-master.zip>
python -B -m gnn prepare-source --archive <VecFloorSeg-master.zip> --out <new-source-directory>
```

`prepare-source` accepts the source SHA256 recorded in the adapter and copies
its bytes into a new directory. Obtain the archive from its original source
under its applicable terms; third-party source and checkpoints are not bundled.

The upstream entry is `graphgym/main.py`. Its inference command has the
following structure, but has not been verified as a complete inference run:

```powershell
# Run inside the prepared source and its separate upstream environment.
python -B graphgym/main.py --cfg graphgym/configs/CUBI.yaml --eval train.epoch_resume 1 train.ckpt_prefix best val.extra_infos True seed 0
```

That step needs compatible PyTorch/PyG dependencies, complete GNN and backbone
weights, processed inputs, and the corresponding original configuration. Update
the upstream YAML's dataset and output paths for your machine. See
[environment requirements](../environments/gnn.md). A verified exporter from
the upstream graph predictions to Geo-ELCT's two label maps is also required;
the SVG annotation loader does not provide that prediction conversion.

For existing integer-label PNG maps:

```powershell
python -B -m gnn export-maps --wall <wall-map.png> --icon <opening-map.png> --source-type annotation_derived --out <new-map-directory>
python -B -m geo_elct extract --wall <new-map-directory>/wall_svg.png --icon <new-map-directory>/icon_svg.png --source-type annotation_derived --mode none --out <new-translator-run>
```

The adapter checks image modes and dimensions, records hashes in
`map_handoff.json`, and copies bytes without resizing or remapping. Add `--rough`
to copy an equal-size background. For independently obtained model predictions,
use `--source-type model_prediction --evidence <inference-evidence.json>`;
the evidence requires `checkpoint_sha256`, `config_sha256` and
`inference_command`. Evidence is recorded as externally supplied and unverified.
Keep credentials and personal paths out of evidence intended for publication.
