# External MWM input format

Prepare one external directory containing the files below. Coordinates are in
metres, powers in dBm and frequencies in GHz. The implementation uses frequencies
[2.4, 5, 28], four cumulative transmitter configurations and room order 1 through
18. The user defines the case labels, transmitter rooms, coordinates and source
geometry. Input datasets are supplied separately from the calculation code.

| File | Required contents |
| --- | --- |
| `recovery_config.json` | The configuration fields described below, using actual source coordinates and room identities. |
| `source.svg` | The source floor plan identified by `svg_sha256`; each `rooms` entry maps a room number to its SVG polygon ID. |
| `wi_samples.npz` | `frequency_GHz`: (3,), `tx_room_ids`: (4,), `tx_xyz_m`: (4,3), `room_ids`: (18,). For each room r, `room{r}_xyz_m`: (Nr,3), its actual receiver coordinates, and `room{r}_WI_dBm`: (3,4,Nr), individual transmitter powers in the same receiver order. No-signal powers may be negative infinity; NaN and positive infinity are invalid. |
| `reference_and_proposed.npz` | `WI_ARP_dBm` and `Proposed_ARP_dBm`, each (3,4,18), plus `frequency_GHz`, `case_labels`, `tx_room_ids`, `tx_xyz_m` and `room_ids`. The WI array equals cumulative linear-power summation followed by the arithmetic mean over actual receivers, converted to dBm. Both arrays use the configured cases and room order. |
| `input_manifest.json` | Source records and SHA256 hashes as described below. Include the source WI XML projects, received-power exports and matching room-reference exports. |

## Configuration

| Field | Value and interpretation |
| --- | --- |
| `case_labels` | Four unique, nonempty strings in the order of the cumulative configurations. |
| `tx_room_ids` | Four unique integer room IDs from 1 through 18, in transmitter order. |
| `case_tx_room_ids` | Four lists containing the first one, two, three and four entries of `tx_room_ids`, respectively. |
| `frequency_GHz` | `[2.4, 5.0, 28.0]`. |
| `tx_xyz_m` | Four finite xyz coordinates, shape (4,3), in the declared transmitter order. |
| `coordinate_frame` | `"wireless_insite_local_m"`; transmitter and receiver coordinates use the WI local metre frame. |
| `wi_to_svg_m` | A finite, metre-preserving 3x3 affine transform from WI xy metres to SVG xy metres after scale conversion. Its last row is `[0,0,1]`; z is unchanged. |
| `svg` | `"source.svg"`. |
| `svg_sha256` | The SHA256 of the supplied source SVG. |
| `scale_units_per_m` | A finite positive number giving SVG coordinate units per metre. |
| `P_tx_dBm` | A finite common transmitter power in dBm, matching the source projects. |
| `distance_min_m` | A finite positive lower bound for model distances, in metres. |
| `rooms` | Eighteen records in room order 1 through 18, each with `room_id` and a unique, nonempty `svg_id` for its source space polygon. |
| `validation_status` | `"verified_wi_inputs"` after the supplied coordinates, source records and export mapping have been checked against the engineering files. |

Use the exact receiver positions and ordering from the source exports. Receiver
counts follow those exports; no receiver is added, removed or moved to match a
nominal count.

Provide one source WI XML project per frequency, containing all configured
transmitters and complete receiver sets. The validator reads transmitter
coordinates, power and frequency from XML and compares every explicit/grid
receiver position with the NPZ lists. The feature builder checks each transformed
transmitter against its configured room polygon. The Python workflow consumes
these existing files; generating new exports uses a licensed WI installation.

## Export columns and source manifest

Files listed in `wi_power_exports` use columns
`frequency_GHz,tx_room,room,rx_index,power_dBm`; `rx_index` is one-based within
the exact `room{r}_xyz_m` order. The records uniquely cover every frequency,
transmitter and receiver. Each value is checked against the NPZ array.

Files listed in `proposed_exports` use
`frequency_GHz,case,room,Proposed_ARP_dBm` and uniquely cover all 216 room
references. Preserve the export's precision. When normalizing a WI or spreadsheet
export to these columns, retain the original files in the hashed `files` mapping
and check the identifier and ordering correspondence against those originals.

`input_manifest.json` has the following structure. Replace each hash placeholder
with the SHA256 of the actual file. Paths are relative to the input directory.
Set the `verification` fields after completing the corresponding source checks.

```json
{
  "files": {
    "recovery_config.json": "SHA256",
    "source.svg": "SHA256",
    "wi_samples.npz": "SHA256",
    "reference_and_proposed.npz": "SHA256",
    "sources/project_2p4GHz.xml": "SHA256",
    "sources/project_5GHz.xml": "SHA256",
    "sources/project_28GHz.xml": "SHA256",
    "sources/received_power.csv": "SHA256",
    "sources/proposed_room_power.csv": "SHA256"
  },
  "input_fingerprint_sha256": "SHA256_OF_CANONICAL_FILES_MAPPING",
  "wi_projects": [
    {"frequency_GHz": 2.4, "path": "sources/project_2p4GHz.xml"},
    {"frequency_GHz": 5.0, "path": "sources/project_5GHz.xml"},
    {"frequency_GHz": 28.0, "path": "sources/project_28GHz.xml"}
  ],
  "wi_power_exports": ["sources/received_power.csv"],
  "proposed_exports": ["sources/proposed_room_power.csv"],
  "verification": {
    "tx_room_membership": true,
    "coordinate_transform": true,
    "rx_coordinates": true,
    "linear_power_aggregation": true,
    "proposed_same_configuration": true
  }
}
```

The input fingerprint is the SHA256 of
`json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")).encode()`.
All source artifacts, including multiple power-export files when needed, appear
in `files`. The manifest itself is excluded from that mapping.

## Optional first-configuration parameter reuse

The runner fits twelve parameter sets using eight fixed starts and minimum
training SSE among converged starts. To reuse first-configuration parameters,
include `C1_parameter_archive.npz` in the hashed input bundle. Its fields are
`frequency_GHz` (3,), `parameters` (3,4), `C1_ARP_dBm` (3,18) and
`c1_input_fingerprint_sha256`. They identify a prior run with the same
first-configuration geometry, transmitter/receiver features, power, frequencies
and reference targets. The runner checks the fingerprint and independent forward
calculation before reuse; omitting this file fits the first configuration anew.
