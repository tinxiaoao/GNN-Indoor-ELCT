# GNN environment status

The GNN environment is **not validated**. The source README recommends PyG 2.0.4, references an absent `requirements.txt`, and requires modified `graphgym` / `torch_geometric` directories. The embedded `torch_geometric/__init__.py` declares version 2.0.5. Neither statement establishes a complete reproducible installation. No successful torch/PyG/GNN imports or inference are claimed.

Keep GNN separate from the tested Geo-ELCT/MWM environment. Do not update the author's existing conda or site-packages. Recover the original Python, PyTorch, torchvision, CUDA and PyG build combination, create a new environment, retain modified upstream modules, and record actual import paths/versions. Complete GNN weights, eagerly loaded backbone weights and processed data are also missing.

The new `python -m gnn` source commands use Python's standard library. `export-maps` also uses Pillow already required by Geo-ELCT. Adapter execution does not establish the network environment.
