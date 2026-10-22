# Existing tests

```powershell
python -B -m unittest discover -s tests -v
```

The 29 preserved tests check entry/configuration/source contracts and v2 opening
mechanisms. They do not establish GNN inference, building generalization or the
five-seed recovery rate. Reproduction commands and numerical limitations are
described in [the reproduction guide](../docs/reproduction.md) and
[known limitations](../docs/known_limitations.md).
