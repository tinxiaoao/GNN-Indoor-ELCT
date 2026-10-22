"""Strict canonical evaluation of Geo-ELCT room and edge workbooks."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


from .compare_elct_tables import match_rooms
from .parse_elct_tables import parse_edge_table, parse_room_table


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(json_safe(payload), handle, ensure_ascii=False, indent=2)


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[Sequence[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fields: List[str] = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
        fieldnames = fields
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(json_safe(value), ensure_ascii=False) if isinstance(value, (list, dict, tuple)) else value
                for key, value in row.items()
            })


def normalized_type(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"opening": "open_space", "open": "open_space", "open_passage": "open_space"}
    return aliases.get(text, text)


def canonical_room(
    room: Dict[str, Any],
    canonical_id: Any,
) -> Dict[str, Any]:
    walls = sorted(
        (
            str(item.get("direction") or "").strip().lower(),
            item.get("length"),
            item.get("width"),
        )
        for item in room.get("exterior_walls", [])
    )
    openings = sorted(
        (
            normalized_type(item.get("type")),
            str(item.get("direction") or "").strip().lower(),
            item.get("length"),
            item.get("width"),
        )
        for item in room.get("exterior_openings", [])
    )
    return {
        "RoomID": canonical_id,
        "Type": str(room.get("room_type") or "").strip(),
        "Area": room.get("area"),
        "Perimeter": room.get("perimeter"),
        "walls": walls,
        "openings": openings,
    }


def canonical_rooms(
    rooms: List[Dict[str, Any]],
    mapping: Optional[Dict[Any, Any]] = None,
) -> List[Dict[str, Any]]:
    records = []
    for room in rooms:
        source_id = room["room_id"]
        canonical_id = mapping.get(source_id, f"unmatched_candidate:{source_id}") if mapping is not None else source_id
        records.append(canonical_room(room, canonical_id))
    records.sort(key=lambda item: (isinstance(item["RoomID"], str), str(item["RoomID"]).zfill(12)))
    return records


def canonical_edges(
    edges: List[Dict[str, Any]],
    mapping: Optional[Dict[Any, Any]] = None,
) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Any, Any, str], Dict[str, Any]] = {}
    for edge in edges:
        a, b = edge["roomA"], edge["roomB"]
        if mapping is not None:
            a = mapping.get(a, f"unmatched_candidate:{a}")
            b = mapping.get(b, f"unmatched_candidate:{b}")
        a, b = sorted((a, b), key=lambda value: (isinstance(value, str), str(value).zfill(12)))
        edge_type = normalized_type(edge.get("connection_type")) or ""
        record = grouped.setdefault((a, b, edge_type), {
            "RoomA": a,
            "RoomB": b,
            "ConnectionType": edge_type,
            "Count": 0,
            "segments": [],
        })
        source_count = edge.get("source_count")
        record["Count"] += int(source_count) if source_count is not None else len(edge.get("segments", []))
        record["segments"].extend(
            (segment.get("length"), segment.get("width"))
            for segment in edge.get("segments", [])
        )
    records = list(grouped.values())
    for record in records:
        record["segments"] = sorted(record["segments"])
    records.sort(key=lambda item: (
        isinstance(item["RoomA"], str), str(item["RoomA"]).zfill(12),
        isinstance(item["RoomB"], str), str(item["RoomB"]).zfill(12),
        item["ConnectionType"],
    ))
    return records


def _flatten_room(record: Dict[str, Any]) -> Dict[str, Any]:
    flat = {key: record[key] for key in ("RoomID", "Type", "Area", "Perimeter")}
    for index, (direction, length, width) in enumerate(record["walls"], start=1):
        flat[f"WallDir_{index}"] = direction
        flat[f"ExtWallLength_{index}"] = length
        flat[f"ExtWallWidth_{index}"] = width
    for index, (opening_type, direction, length, width) in enumerate(record["openings"], start=1):
        flat[f"OpenType_{index}"] = opening_type
        flat[f"OpenDir_{index}"] = direction
        flat[f"OpenLength_{index}"] = length
        flat[f"OpenWidth_{index}"] = width
    return flat


def _flatten_edge(record: Dict[str, Any]) -> Dict[str, Any]:
    flat = {key: record[key] for key in ("RoomA", "RoomB", "ConnectionType", "Count")}
    for index, (length, width) in enumerate(record["segments"], start=1):
        flat[f"Length_{index}"] = length
        flat[f"Width_{index}"] = width
    return flat


def _diff_records(
    reference: List[Dict[str, Any]],
    candidate: List[Dict[str, Any]],
    *,
    kind: str,
) -> List[Dict[str, Any]]:
    if kind == "room":
        key_fields = ("RoomID",)
        flatten = _flatten_room
    else:
        key_fields = ("RoomA", "RoomB", "ConnectionType")
        flatten = _flatten_edge
    ref_index = {tuple(record[field] for field in key_fields): flatten(record) for record in reference}
    cand_index = {tuple(record[field] for field in key_fields): flatten(record) for record in candidate}
    keys = sorted(set(ref_index) | set(cand_index), key=str)
    diffs: List[Dict[str, Any]] = []
    for key in keys:
        ref = ref_index.get(key, {})
        cand = cand_index.get(key, {})
        fields = sorted(set(ref) | set(cand))
        for field in fields:
            ref_value = ref.get(field)
            cand_value = cand.get(field)
            if ref_value != cand_value:
                numeric = isinstance(ref_value, (int, float)) and isinstance(cand_value, (int, float))
                absolute_error = abs(float(cand_value) - float(ref_value)) if numeric else None
                percentage_error = (
                    absolute_error / abs(float(ref_value))
                    if numeric and float(ref_value) != 0
                    else None
                )
                diffs.append({
                    "record_kind": kind,
                    "record_key": json.dumps(key, ensure_ascii=False),
                    "field": field,
                    "clean_value": ref_value,
                    "candidate_value": cand_value,
                    "absolute_error": absolute_error,
                    "absolute_percentage_error": percentage_error,
                })
    return diffs


def _numeric_summary(diffs: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    grouped: Dict[str, List[Tuple[float, Optional[float]]]] = defaultdict(list)
    for diff in diffs:
        absolute_error = diff.get("absolute_error")
        if absolute_error is None:
            continue
        grouped[str(diff["field"])].append((float(absolute_error), diff.get("absolute_percentage_error")))
    per_field = {}
    for field, values in sorted(grouped.items()):
        absolute_values = [value[0] for value in values]
        percentage_values = [float(value[1]) for value in values if value[1] is not None]
        per_field[field] = {
            "count": len(values),
            "MAE": sum(absolute_values) / len(absolute_values),
            "MAPE": sum(percentage_values) / len(percentage_values) if percentage_values else None,
        }
    return per_field


def evaluate_tables(
    clean_dir: str | Path,
    candidate_dir: str | Path,
    output_dir: str | Path,
    *,
    room_iou_threshold: float = 0.5,
) -> Dict[str, Any]:
    clean_dir = Path(clean_dir)
    candidate_dir = Path(candidate_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    clean_rooms_raw = parse_room_table(clean_dir / "debug_roomself.xlsx")
    candidate_rooms_raw = parse_room_table(candidate_dir / "debug_roomself.xlsx")
    clean_edges_raw = parse_edge_table(clean_dir / "debug_topology_edges.xlsx")
    candidate_edges_raw = parse_edge_table(candidate_dir / "debug_topology_edges.xlsx")
    mapping, scores, match_method = match_rooms(
        clean_dir,
        candidate_dir,
        clean_rooms_raw,
        candidate_rooms_raw,
        room_iou_threshold,
    )

    clean_rooms = canonical_rooms(clean_rooms_raw)
    candidate_rooms = canonical_rooms(candidate_rooms_raw, mapping)
    clean_edges = canonical_edges(clean_edges_raw)
    candidate_edges = canonical_edges(candidate_edges_raw, mapping)
    room_diffs = _diff_records(clean_rooms, candidate_rooms, kind="room")
    edge_diffs = _diff_records(clean_edges, candidate_edges, kind="edge")

    clean_room_types = {record["RoomID"]: record["Type"] for record in clean_rooms}
    candidate_room_types = {record["RoomID"]: record["Type"] for record in candidate_rooms}
    clean_topology = {
        (record["RoomA"], record["RoomB"], record["ConnectionType"]): record["Count"]
        for record in clean_edges
    }
    candidate_topology = {
        (record["RoomA"], record["RoomB"], record["ConnectionType"]): record["Count"]
        for record in candidate_edges
    }
    topology_exact = (
        set(clean_room_types) == set(candidate_room_types)
        and clean_room_types == candidate_room_types
        and clean_topology == candidate_topology
    )
    room_exact = clean_rooms == candidate_rooms
    edge_exact = clean_edges == candidate_edges
    all_diffs = room_diffs + edge_diffs
    summary = {
        "schema_version": 1,
        "clean_dir": str(clean_dir.resolve()),
        "candidate_dir": str(candidate_dir.resolve()),
        "room_matching_method": match_method,
        "room_iou_threshold": room_iou_threshold,
        "candidate_to_clean_room_mapping": {str(key): value for key, value in mapping.items()},
        "room_match_scores": {str(key): value for key, value in scores.items()},
        "unmatched_clean_room_ids": sorted(set(record["room_id"] for record in clean_rooms_raw) - set(mapping.values())),
        "unmatched_candidate_room_ids": sorted(set(record["room_id"] for record in candidate_rooms_raw) - set(mapping)),
        "topology_exact_match": topology_exact,
        "room_table_exact_match": room_exact,
        "edge_table_exact_match": edge_exact,
        "original_tables_recovered": room_exact and edge_exact,
        "room_table_difference_count": len(room_diffs),
        "edge_table_difference_count": len(edge_diffs),
        "numeric_differences": _numeric_summary(all_diffs),
        "topology_definition": "Identical spatially matched room set and types, plus identical unordered room-pair, normalized connection type, and Count records.",
        "room_table_definition": "All required canonical room fields exactly equal after spatial matching and repeated-field sorting.",
        "edge_table_definition": "All required canonical edge fields exactly equal after endpoint remapping and segment-tuple sorting.",
    }
    write_csv(output_dir / "room_table_cell_diff.csv", room_diffs, fieldnames=(
        "record_kind", "record_key", "field", "clean_value", "candidate_value", "absolute_error", "absolute_percentage_error"
    ))
    write_csv(output_dir / "edge_table_cell_diff.csv", edge_diffs, fieldnames=(
        "record_kind", "record_key", "field", "clean_value", "candidate_value", "absolute_error", "absolute_percentage_error"
    ))
    write_json(output_dir / "comparison_summary.json", summary)
    write_json(output_dir / "canonical_clean_room_table.json", clean_rooms)
    write_json(output_dir / "canonical_candidate_room_table.json", candidate_rooms)
    write_json(output_dir / "canonical_clean_edge_table.json", clean_edges)
    write_json(output_dir / "canonical_candidate_edge_table.json", candidate_edges)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Strict reference-faithful Geo-ELCT table evaluator.")
    parser.add_argument("--clean-dir", required=True, type=Path)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--room-iou-threshold", type=float, default=0.5)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    summary = evaluate_tables(
        args.clean_dir,
        args.candidate_dir,
        args.out,
        room_iou_threshold=args.room_iou_threshold,
    )
    print(json.dumps(json_safe(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
