# Examples

`synthetic_two_rooms/` contains newly generated palette-index maps and a
portable hash-bound case configuration. It contains no dataset geometry or
GNN output. Regenerate a private copy with:

```powershell
python scripts/make_synthetic_example.py --out local/synthetic_two_rooms
```

For real examples use `python -m geo_elct prepare-examples --help` with authorized
processed CubiCasa5K assets. This checks the three existing building hashes and
copies only nine files; it neither downloads data nor grants redistribution
rights. Part B has its own hash-bound preparation script.
