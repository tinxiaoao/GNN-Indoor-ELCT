# Third-party and asset notices

The project authors publish the code, numerical references and Supplementary
Material in this repository. No project-wide license is assigned here;
third-party materials retain their own terms.

| Material | Provenance and treatment | License status |
| --- | --- | --- |
| Geo-ELCT, IndoorEMT, preserved perturbation/MWM scripts and release wrappers | Project source; source identities retained in the module provenance files | Author code; no project-wide license assigned |
| Part C WI/Proposed room references, parameters and frozen predictions | Designated confirmed benchmark archive; only selected numerical files included | Author-provided numerical data |
| Synthetic maps and regression tables | Generated for interface testing; no third-party geometry | Author-provided fixtures |
| Supplementary Material | Exact supplied document; author/paper attribution retained | Author-provided document |
| VecFloorSeg and embedded modified PyG/GraphGym | Identified upstream `DrZiji/VecFloorSeg` commit `c3f51b39a4649c6b978898589a71df2e9c8159ba`; no nonempty license found in inspected snapshot | Not redistributed; authorized local-source preparation only |
| CubiCasa5K-derived room attributes, topology tables and ELCT graphs | Full available extraction outputs in `output/`; see [source attribution](third_party/README.md) | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/); original [license notice](third_party/CubiCasa5K-LICENSE) retained |
| GNN/backbone weights and Part C external SVG/geometry arrays | Required external assets with hashes/acquisition instructions where known | Not bundled; redistribution not established |
| Python/MATLAB dependencies | Installed separately, not vendored | Retain their own licenses |

Official sources and CubiCasa5K author attribution are given in
[third_party/README.md](third_party/README.md). Frozen reference results are
saved evaluation targets; they are not current calculations or WI reruns.
