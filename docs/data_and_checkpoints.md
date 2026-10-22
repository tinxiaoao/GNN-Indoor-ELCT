# Data and checkpoints

The dataset contains automatically extracted room attributes, topology tables, and ELCT graphs from CubiCasa5K. The results have not all been manually verified and may require further screening.

`output/roomself_excel/`, `output/topology_excel/` and `output/topology/`
contain the full available extraction outputs, with their original filenames
and directory structure. See [source attribution and CC BY-NC 4.0 terms](../third_party/README.md)
and [known limitations](known_limitations.md) for existing incomplete records.

The bundled `examples/synthetic_two_rooms/` maps were generated for interface
testing by `scripts/make_synthetic_example.py`. No external dataset geometry or
trained prediction was used. This synthetic example does not validate a paper
benchmark or raw-image GNN inference.

Real semantic maps for 193, 11184 and 7795 are annotation-derived CubiCasa5K
assets. `configs/building_A/B/C.json` binds their hashes/dimensions and records
their source type. `python -m geo_elct prepare-examples` copies only the nine
hash-verified maps/backgrounds from a locally authorized processed dataset.
The default prepared mode remains `none`; explicitly add `--mode correction_v2`
for Part A. Raw floor-plan images, SVG files, LMDB and training caches are not
bundled; `output/` contains the extracted results.

GNN source was identified as VecFloorSeg commit
`c3f51b39a4649c6b978898589a71df2e9c8159ba`, with no substantive changes in the
located source archive after newline normalization. Redistribution permission
was not established, so source is external. The actual source-preparation,
preprocessing/graph/evaluation chain and missing items are documented in
[GNN provenance](gnn_provenance.md). No complete trained GNN checkpoint was
found. Backbone weights or a separate CubiCasa CNN checkpoint are not complete
VecFloorSeg checkpoints and are not substitutes. Full inference is NOT RUN.

Part B inputs are bound in `experiments/fixed_inputs.json` and acquired only
from authorized local files using `scripts/prepare_fixed_inputs.py`. Neither
annotation-derived nor synthetic inputs should be relabeled `model_prediction`.

Part C requires the exact external `R1Q6_WI_Confirmed_Reproducible.zip` whose
SHA256 is recorded in `benchmarks/mwm/external_inputs.json`. The preparation
script extracts nine whitelisted, hash-bound input files into a new local
directory. The external SVG and geometry arrays are not bundled.
Author-provided numerical room references, parameters and predictions are
included as frozen references. The original archive contains other material;
it is not redistributed wholesale.

Public provenance paths are project-relative. Private local manifests, absolute
paths and newly computed runs are excluded from the repository.
