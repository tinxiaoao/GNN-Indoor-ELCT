# MWM input bundle

Use one directory containing these files. Coordinates are in metres, powers in
dBm, frequencies in GHz and room order is 1 through 18. The configurations are
C-1 = [1], C-2 = [1,2], C-3 = [1,2,4] and C-4 = [1,2,4,8].

| File | Required contents |
| --- | --- |
| `recovery_config.json` | Complete the supplied configuration template with the actual Room-8 WI Tx xyz; the verified metre-preserving 3×3 `wi_to_svg_m` affine transform; and `validation_status: "verified_wi_inputs"`. `tx_xyz_m` uses the WI local coordinate frame, in Tx order [1,2,4,8]. `wi_to_svg_m` maps WI xy metres to SVG xy metres after `scale_units_per_m` conversion. The z coordinate is unchanged. The Building C SVG hash, scale and room-to-SVG mapping remain fixed. |
| `source.svg` | The source floor plan named by `svg_sha256`; the `rooms` records map room numbers to SVG polygon IDs. |
| `wi_samples.npz` | `frequency_GHz`: (3,), `tx_room_ids`: (4,), `tx_xyz_m`: (4,3), `room_ids`: (18,). For each room r, `room{r}_xyz_m`: (Nr,3), its **actual WI receiver coordinates**; `room{r}_WI_dBm`: (3,4,Nr), individual Tx received powers in that receiver order. No receiver is added, removed or moved to match a nominal count. No-signal powers may be −infinity; NaN and +infinity are invalid. |
| `reference_and_proposed.npz` | `WI_ARP_dBm` and `Proposed_ARP_dBm`, each (3,4,18), plus `frequency_GHz`, `case_labels`, `tx_room_ids`, `tx_xyz_m` and `room_ids`. The WI array must equal the cumulative linear-power sum followed by the arithmetic mean over actual receivers, converted to dBm. The Proposed array must use the same four deployments and room order. |
| `input_manifest.json` | SHA256 hashes and source records described below. Retain the source WI XML projects, power exports and Proposed exports in the bundle. |

Provide one actual C-4 WI XML project per frequency with all four transmitters
and the complete receiver sets. The validator reads Tx coordinates, power and
frequency from XML and compares every explicit/grid Rx position with the NPZ
lists. It also checks each transformed Tx against its room polygon. Verify the
transformation and the power-export-to-NPZ mapping against the engineering files
before marking them verified.

The supplied Building C geometry, first three WI transmitter positions,
15 dBm transmitter power and 1 m model-distance floor are fixed benchmark
settings. Receiver positions and counts come from the actual WI export.

The files listed in `wi_power_exports` are CSV exports with columns
`frequency_GHz,tx_room,room,rx_index,power_dBm`; `rx_index` is one-based within
the exact `room{r}_xyz_m` order. They must uniquely cover every frequency, Tx
and receiver, and every value is compared with the NPZ array. Files listed in
`proposed_exports` use `frequency_GHz,case,room,Proposed_ARP_dBm` and must
uniquely cover all 216 room references. Preserve the export's precision. When
normalizing a WI or spreadsheet export to these columns, retain the original
export files in the hashed `files` mapping and verify the identifier/order
mapping against those originals.

`input_manifest.json` has this structure. Replace the placeholders with hashes
of the actual files. Paths are relative to the input directory.

```json
{
  "files": {
    "recovery_config.json": "SHA256",
    "source.svg": "SHA256",
    "wi_samples.npz": "SHA256",
    "reference_and_proposed.npz": "SHA256",
    "sources/C4_2p4GHz.xml": "SHA256",
    "sources/C4_5GHz.xml": "SHA256",
    "sources/C4_28GHz.xml": "SHA256",
    "sources/received_power.csv": "SHA256",
    "sources/proposed_room_power.csv": "SHA256"
  },
  "input_fingerprint_sha256": "SHA256_OF_CANONICAL_FILES_MAPPING",
  "wi_projects": [
    {"frequency_GHz": 2.4, "path": "sources/C4_2p4GHz.xml"},
    {"frequency_GHz": 5.0, "path": "sources/C4_5GHz.xml"},
    {"frequency_GHz": 28.0, "path": "sources/C4_28GHz.xml"}
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
All source artifacts, including multiple power-export files when needed, must
appear in `files`. The manifest itself is excluded from that mapping.

The runner fits all twelve parameter sets with the fixed eight starts and
training-SSE selection rule. To retain prior C-1 parameters, optionally include
`C1_parameter_archive.npz` in the hashed bundle. Its `frequency_GHz` (3,),
`parameters` (3,4), `C1_ARP_dBm` (3,18) and `c1_input_fingerprint_sha256` must
come from a prior run with identical C-1 geometry, actual Tx/Rx features, power,
frequencies and WI targets. A mismatch is rejected; omit it to refit C-1.

The distributed template still requires a verified Room-8 Tx location, its
three-frequency WI projects/exports, exact Rx coordinates and matching Proposed
references. Incomplete inputs produce no numerical results.
