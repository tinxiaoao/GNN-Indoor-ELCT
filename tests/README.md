# Existing tests

```powershell
python -B -m unittest discover -s tests -v
```

The 29 preserved tests check entry/configuration/source contracts and v2 opening
mechanisms. Seven additional geometry tests cover single and multiple opening
components, retained thickness groups, room/type separation, dimension-record
counts and the unchanged morphological perimeter/search scales.
These tests do not establish GNN inference, building generalization or the
five-seed recovery rate. Reproduction commands and numerical limitations are
described in [the reproduction guide](../docs/reproduction.md) and
[known limitations](../docs/known_limitations.md).
