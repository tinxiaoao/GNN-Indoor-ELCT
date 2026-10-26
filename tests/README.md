# Regression tests

Run the test suite from the repository root:

```powershell
python -B -m unittest discover -s tests -v
```

The tests cover command-line and configuration contracts, source identities,
opening correction mechanisms, dimension aggregation and topology-matching
metrics. Fixtures exercise single and multiple opening components, retained
thickness groups, room/type separation, dimension-record counts and the
morphological perimeter/search conventions. Synthetic fixtures keep these
software checks independent of external simulation datasets.

See [the program guide](../docs/reproduction.md) for module workflows and
[implementation notes](../docs/implementation_notes.md) for field interpretation.
