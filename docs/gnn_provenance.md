# GNN source, assets and handoff provenance

`code/VecFloorSeg-master.zip`, SHA256 `b52bb52c693d2ce52cd11354a87ffc1250708b7ba5b1dc4ee83829daa0547667`, contains 330 files, no Git history, no full trained checkpoint, no `requirements.txt` and no nonempty LICENSE file. Its nested `torch_geometric/graphgym/utils/LICENSE` is empty. Redistribution permission is unconfirmed; the archive, its source, dataset and checkpoints are absent from this candidate.

A clean, independent local VecFloorSeg checkout identifies [DrZiji/VecFloorSeg](https://github.com/DrZiji/VecFloorSeg) as its configured upstream. HEAD and locally stored `upstream/master` are both `c3f51b39a4649c6b978898589a71df2e9c8159ba`. All 330 archive files match all 330 tracked files at that commit after CRLF/LF normalization; no substantive differences or missing tracked files were found. Of these, 329 differ in byte representation solely because of newlines. This determines local provenance, not current remote HEAD. No author-specific GNN algorithm modification was detected. The modified PyG/GraphGym modules are already part of this upstream snapshot.

| Stage | Original implementation / contract | Status |
|---|---|---|
| Roughcast | `Replace_with_CubiCasa/roughcast_data_generation.py`, then `ImgRasterization.py` in compatible CubiCasa source | Located; not executed; source scripts write into dataset paths |
| Annotation maps | `svg_loader.py::FloorplanSVG.get_txt` → `House(model_roughcast.svg).get_segmentation_tensor()` channels 0/1 → `wall_svg.png` / `icon_svg.png` | Ground truth, not network predictions |
| Graph preparation | `DataPreparation/ImageProcessing_CubiCasa.py`, `SvgProcessing_CubiCasa.py` | Located, preserved externally; not rewritten |
| Model config | `graphgym/configs/CUBI.yaml`: loader `CUBICASA_Merge_DUALIMG_1`, network `CUBICASA_DUAL`, encoder `merge_node_resnet_1`, 6 message-passing layers, `dim_inner=256`, image encoder `resnet50` | No bound full trained checkpoint |
| Data/scale | `CUBIMergeDualImgDataset_1.py`: `merge_{train,val,test}_phase_V10.pkl` and split lists; `ToTensor` → `Resize(size=256)` → ImageNet mean/std; graph mapping shape 256 | Complete bound processed data not located |
| Inference | `graphgym/main.py --cfg ... --eval ...`; modified `torch_geometric/graphgym/train.py` | Not run: missing environment, weights and data |
| Graph → native map export | Both room and opening prediction maps | Verified exporter not located; no replacement rasterizer or annotation substitution |
| Existing-map handoff | New `gnn export-maps` → existing `geo_elct extract` | Copies existing maps; no inference |

The registered loader's ordered room classes are `background`, `Outdoor`, `Wall`, `Kitchen`, `Dining`, `Bedroom`, `Bath`, `Entrance`, `Railing`, `Closet`, `Garage`, `Corridor` (indices 0–11). The actual translator annotation interface uses wall 2, excludes room labels `{0,1,2,8,50}`, and reads opening 1 as window and 2 as door. These are separate class domains. Auxiliary graph output has not been bound to both opening classes at native map scale; no new remapping is asserted.

The README asks for a ResNet-101 backbone, but `custom_graphgym/encoder/node_edge_encoder.py` constructs an eager encoder dictionary loading `resnet34-torch.pth`, `resnet50-torch.pth`, `resnet101-torch.pth` and `vgg16_bn-torch.pth` at import. These initialization backbones are not complete trained segmentation checkpoints. None was found in the task's `code/` tree or archive. A separate historical CubiCasa checkout contains `floortrans/models/model_1427.pth` (69,744,847 bytes, SHA256 `10d3992fcb43c64bd5773a71410283e50476ba21c506702d736a071cb5acf6a0`), a different model family that is neither accepted as VecFloorSeg weights nor redistributed.

The earlier pixelwise SVG reconstruction classified all six maps for A/193, B/11184 and C/7795 as annotation-derived. The current candidate retains their known hashes and provenance; no saved artifact is relabeled as new GNN output. The task's CubiCasa directory contains sample folders/split files rather than the GNN implementation. A separate CubiCasa source checkout declares CC BY-NC 4.0; this alone does not independently clear modified SVGs, derived images or checkpoints.

New adapters only inspect/copy an exact source archive and validate/copy existing maps with manifests. They do not import or change the network, graph construction, labels or scale. Exact private paths/hashes remain in the private audit inventory. Full inference needs the original trained checkpoint/configuration, compatible data/environment, verified prediction-to-map exporter and rights confirmation.
