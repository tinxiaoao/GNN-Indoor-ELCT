# Synthetic regression fixtures

`synthetic_two_rooms/` stores expected outputs for the bundled two-room
interface example. Its XLSX, NPY and JSON files support regression checks of
workbook cells, room masks, room records and interface records. Run extraction
to a new directory before comparing it with this fixture.

For spreadsheet regression checks, compare workbook cells rather than XLSX ZIP bytes.

MWM is distributed as calculation code in [the MWM module](../benchmarks/mwm/README.md).
Its input datasets are provided by the user according to
[the external input format](../benchmarks/mwm/input_schema.md).
