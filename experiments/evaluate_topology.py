"""Evaluate room count and typed room connectivity against Clean maps.

Dimension-record Count and complete table equality are reported separately.
The existing mask-IoU matching and strict table evaluator are unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from geo_elct.evaluation.evaluate_reference_faithful_tables import evaluate_tables


def typed_connectivity(clean_rooms, candidate_rooms, clean_edges, candidate_edges):
    """Compare already spatially mapped canonical records without geometry/Count."""
    clean_ids = {row["RoomID"] for row in clean_rooms}
    candidate_ids = {row["RoomID"] for row in candidate_rooms}
    clean_relations = {(row["RoomA"], row["RoomB"], row["ConnectionType"]) for row in clean_edges}
    candidate_relations = {(row["RoomA"], row["RoomB"], row["ConnectionType"]) for row in candidate_edges}
    return {
        "room_count_equal": len(clean_rooms) == len(candidate_rooms),
        "spatially_matched_room_set_equal": clean_ids == candidate_ids,
        "typed_room_connectivity_equal": clean_relations == candidate_relations,
    }


def evaluate_topology(reference: Path, candidate: Path, out: Path):
    out = Path(out)
    if out.exists():
        raise FileExistsError("Choose a new evaluation output directory")
    strict = evaluate_tables(reference, candidate, out / "tables", room_iou_threshold=0.5)
    if strict["room_matching_method"] != "mask_iou":
        raise ValueError("This topology definition requires both exported room ID rasters")
    records = {}
    for side in ("clean", "candidate"):
        for kind in ("room", "edge"):
            records[f"{side}_{kind}s"] = json.loads(
                (out / "tables" / f"canonical_{side}_{kind}_table.json").read_text(encoding="utf-8")
            )
    result = typed_connectivity(**records)
    result.update({
        "topology_matching": all(result.values()),
        "room_iou_threshold": 0.5,
        "room_matching_method": strict["room_matching_method"],
        "definition": "Equal room count, a complete spatial room correspondence, and identical unordered room-pair/connection-type sets; no Count or geometry condition.",
        "strict_topology_with_room_types_and_count": strict["topology_exact_match"],
        "room_table_exact": strict["room_table_exact_match"],
        "edge_table_exact": strict["edge_table_exact_match"],
        "both_tables_exact": strict["original_tables_recovered"],
        "room_table_difference_count": strict["room_table_difference_count"],
        "edge_table_difference_count": strict["edge_table_difference_count"],
    })
    (out / "topology_matching.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate_topology(args.reference, args.candidate, args.out), indent=2))


if __name__ == "__main__":
    main()
