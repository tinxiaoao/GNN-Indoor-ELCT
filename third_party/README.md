# Third-party sources and assets

The local source archive corresponds after newline normalization to [DrZiji/VecFloorSeg](https://github.com/DrZiji/VecFloorSeg), commit `c3f51b39a4649c6b978898589a71df2e9c8159ba`. No nonempty redistribution license was present. This release includes preparation/handoff adapters and instructions; VecFloorSeg source, modified PyG code and weights remain external. See [GNN provenance](../docs/gnn_provenance.md).

CubiCasa5K was created by Ahti Kalervo, Juha Ylioinas, Markus Häikiö, Antti Karhu and Juho Kannala (2019). Its sources are [CubiCasa/CubiCasa5k](https://github.com/CubiCasa/CubiCasa5k), the [original dataset record](https://zenodo.org/records/2613548), and the paper [CubiCasa5K: A Dataset and an Improved Multi-Task Model for Floorplan Image Analysis](https://arxiv.org/abs/1904.01920). The upstream [license notice](CubiCasa5K-LICENSE) is preserved unchanged: [Creative Commons Attribution-NonCommercial 4.0 International](https://creativecommons.org/licenses/by-nc/4.0/). CubiCasa5K-derived outputs retain these attribution and noncommercial terms.

The dataset contains automatically extracted room attributes, topology tables, and ELCT graphs from CubiCasa5K. The results have not all been manually verified and may require further screening.

The full available extraction outputs are included in `output/`; original floor-plan images, SVG files and model weights are not bundled. The A/193, B/11184 and C/7795 semantic maps are annotation-derived. `geo_elct prepare-examples` copies hash-verified maps from an existing local processed dataset, while `gnn prepare-source` copies an exact locally held source archive. Dependencies retain their own licenses. No project-wide license is assigned here.
