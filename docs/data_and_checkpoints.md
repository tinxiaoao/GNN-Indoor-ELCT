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

Part B uses all 20 cases in `experiments/part_b_inputs.json`, prepared from local
files using `scripts/prepare_fixed_inputs.py`. The ranges, seeds and correction
modes are in `experiments/part_b_protocol.json`. These annotation-derived inputs
and the synthetic example are not model predictions.

Part C uses C-1 = [1], C-2 = [1,2], C-3 = [1,2,4] and C-4 = [1,2,4,8] at
2.4, 5 and 28 GHz. Follow the [input schema](../benchmarks/mwm/input_schema.md)
to provide the source SVG, verified WI Tx coordinates and coordinate transform,
actual per-room receiver coordinates and per-Tx received powers, matching WI
and Proposed room ARPs, and a source/hash manifest. The fourth transmitter must
be verified inside Room 8. The supplied template still lacks these verified
Room-8/WI/Rx inputs, so the formal runner stops before calculating results.

The earlier Room-18 numerical files and the
`R1Q6_WI_Confirmed_Reproducible.zip` preparation interface are retained only in
[the Rooms 1,2,4,18 archive](../archives/mwm_rooms_1_2_4_18/README.md). They do
not supply the formal C-4 reference data.

Public provenance paths are project-relative. Private local manifests, absolute
paths and newly computed runs are excluded from the repository.
