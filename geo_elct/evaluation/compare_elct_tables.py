import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np

from .parse_elct_tables import parse_edge_table, parse_room_table


OPEN_SPACE_TYPE = "open_space"
CONNECTION_TYPES = ("wall", "door", "window", OPEN_SPACE_TYPE)
OPENING_COUPLING_TYPES = {"door", "window", OPEN_SPACE_TYPE}


def number_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def room_id_as_int(value: Any) -> Optional[int]:
    number = number_or_none(value)
    if number is None or not float(number).is_integer():
        return None
    return int(number)


def room_sort_key(value: Any) -> Tuple[int, Any]:
    number = number_or_none(value)
    if number is not None:
        return (0, float(number))
    return (1, str(value))


def finite(values: Iterable[Optional[float]]) -> List[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = finite(values)
    if not nums:
        return None
    return float(sum(nums) / len(nums))


def mae(pairs: Iterable[Tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    errors = []
    for ref, cand in pairs:
        if ref is None or cand is None:
            continue
        errors.append(abs(float(cand) - float(ref)))
    return mean(errors)


def mape(pairs: Iterable[Tuple[Optional[float], Optional[float]]]) -> Optional[float]:
    errors = []
    for ref, cand in pairs:
        if ref is None or cand is None:
            continue
        ref_value = float(ref)
        if ref_value == 0:
            continue
        errors.append(abs(float(cand) - ref_value) / abs(ref_value))
    return mean(errors)


def safe_div(numerator: float, denominator: float) -> Optional[float]:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def f1_score(precision: Optional[float], recall: Optional[float]) -> Optional[float]:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return float(2 * precision * recall / (precision + recall))


def canonical_connection_type(conn_type: Any) -> str:
    text = str(conn_type or "").strip().lower()
    if text in {"opening", "open", "open_space", "open-space", "open passage", "open_passage"}:
        return OPEN_SPACE_TYPE
    return text


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def write_json(path: str | Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json_safe(payload), f, ensure_ascii=False, indent=2)


def write_csv(path: str | Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(json_safe(v), ensure_ascii=False) if isinstance(v, (list, dict)) else v
                             for k, v in row.items()})


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_room_geometry(directory: Path) -> Dict[Any, Dict[str, Any]]:
    rooms_raw = directory / "rooms_raw.json"
    if not rooms_raw.exists():
        return {}
    geometry: Dict[Any, Dict[str, Any]] = {}
    for room in load_json(rooms_raw):
        rid = room.get("id", room.get("room_id"))
        if rid is None:
            continue
        geometry[rid] = room
    return geometry


def enrich_rooms_with_geometry(rooms: List[Dict[str, Any]], directory: Path) -> None:
    geometry = load_room_geometry(directory)
    if not geometry:
        return
    for room in rooms:
        rid = room["room_id"]
        geom = geometry.get(rid)
        if geom is None:
            rid_int = room_id_as_int(rid)
            geom = geometry.get(rid_int)
        if not geom:
            continue
        for key in ("centroid_y", "centroid_x", "bbox_ymin", "bbox_xmin", "bbox_ymax", "bbox_xmax"):
            if key in geom:
                room[key] = geom[key]


def load_tables(directory: str | Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    directory = Path(directory)
    room_json = directory / "room_table_canonical.json"
    edge_json = directory / "edge_table_canonical.json"
    if room_json.exists() and edge_json.exists():
        rooms = load_json(room_json)
        edges = load_json(edge_json)
        enrich_rooms_with_geometry(rooms, directory)
        return rooms, edges
    room_xlsx = directory / "debug_roomself.xlsx"
    edge_xlsx = directory / "debug_topology_edges.xlsx"
    if not room_xlsx.exists():
        raise FileNotFoundError(room_xlsx)
    if not edge_xlsx.exists():
        raise FileNotFoundError(edge_xlsx)
    rooms = parse_room_table(room_xlsx)
    edges = parse_edge_table(edge_xlsx)
    enrich_rooms_with_geometry(rooms, directory)
    return rooms, edges


def room_index(rooms: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    return {room["room_id"]: room for room in rooms}


def load_region_map(directory: Path) -> Optional[np.ndarray]:
    npy_path = directory / "region_id_map.npy"
    if not npy_path.exists():
        return None
    return np.load(npy_path)


def mask_iou(ref_map: np.ndarray, cand_map: np.ndarray, ref_id: int, cand_id: int) -> float:
    ref_mask = ref_map == ref_id
    cand_mask = cand_map == cand_id
    ref_area = int(ref_mask.sum())
    cand_area = int(cand_mask.sum())
    if ref_area == 0 or cand_area == 0:
        return 0.0
    h = min(ref_map.shape[0], cand_map.shape[0])
    w = min(ref_map.shape[1], cand_map.shape[1])
    intersection = int(np.logical_and(ref_mask[:h, :w], cand_mask[:h, :w]).sum())
    union = ref_area + cand_area - intersection
    if union <= 0:
        return 0.0
    return float(intersection / union)


def greedy_room_iou_match(
    ref_rooms: List[Dict[str, Any]],
    cand_rooms: List[Dict[str, Any]],
    ref_map: np.ndarray,
    cand_map: np.ndarray,
    threshold: float,
) -> Tuple[Dict[Any, Any], Dict[Any, float]]:
    candidates: List[Tuple[float, Any, Any]] = []
    for ref in ref_rooms:
        ref_id_int = room_id_as_int(ref["room_id"])
        if ref_id_int is None:
            continue
        for cand in cand_rooms:
            cand_id_int = room_id_as_int(cand["room_id"])
            if cand_id_int is None:
                continue
            iou = mask_iou(ref_map, cand_map, ref_id_int, cand_id_int)
            if iou >= threshold:
                candidates.append((iou, ref["room_id"], cand["room_id"]))

    candidates.sort(reverse=True, key=lambda item: item[0])
    used_ref: Set[Any] = set()
    used_cand: Set[Any] = set()
    cand_to_ref: Dict[Any, Any] = {}
    scores: Dict[Any, float] = {}
    for iou, ref_id, cand_id in candidates:
        if ref_id in used_ref or cand_id in used_cand:
            continue
        used_ref.add(ref_id)
        used_cand.add(cand_id)
        cand_to_ref[cand_id] = ref_id
        scores[cand_id] = float(iou)
    return cand_to_ref, scores


def rooms_have_centroids(rooms: List[Dict[str, Any]]) -> bool:
    return all("centroid_y" in room and "centroid_x" in room for room in rooms)


def centroid_distance(room_a: Dict[str, Any], room_b: Dict[str, Any]) -> float:
    ay = float(room_a["centroid_y"])
    ax = float(room_a["centroid_x"])
    by = float(room_b["centroid_y"])
    bx = float(room_b["centroid_x"])
    return math.hypot(ay - by, ax - bx)


def greedy_centroid_area_match(
    ref_rooms: List[Dict[str, Any]],
    cand_rooms: List[Dict[str, Any]],
    threshold: float,
) -> Tuple[Dict[Any, Any], Dict[Any, float]]:
    pairs: List[Tuple[float, float, Any, Any]] = []
    for ref in ref_rooms:
        ref_area = number_or_none(ref.get("area"))
        for cand in cand_rooms:
            cand_area = number_or_none(cand.get("area"))
            if ref_area is None or cand_area is None or ref_area <= 0 or cand_area <= 0:
                continue
            area_similarity = min(ref_area, cand_area) / max(ref_area, cand_area)
            if area_similarity < threshold:
                continue
            dist = centroid_distance(ref, cand)
            scale = max(math.sqrt(max(ref_area, cand_area)), 1.0)
            normalized_dist = dist / scale
            cost = normalized_dist + (1.0 - area_similarity)
            pairs.append((cost, area_similarity, ref["room_id"], cand["room_id"]))

    pairs.sort(key=lambda item: item[0])
    used_ref: Set[Any] = set()
    used_cand: Set[Any] = set()
    cand_to_ref: Dict[Any, Any] = {}
    scores: Dict[Any, float] = {}
    for cost, area_similarity, ref_id, cand_id in pairs:
        if ref_id in used_ref or cand_id in used_cand:
            continue
        used_ref.add(ref_id)
        used_cand.add(cand_id)
        cand_to_ref[cand_id] = ref_id
        scores[cand_id] = float(area_similarity)
    return cand_to_ref, scores


def exact_identity_match(
    ref_rooms: List[Dict[str, Any]],
    cand_rooms: List[Dict[str, Any]],
) -> Tuple[Dict[Any, Any], Dict[Any, float]]:
    ref_by_id = room_index(ref_rooms)
    cand_by_id = room_index(cand_rooms)
    if set(ref_by_id) != set(cand_by_id):
        return {}, {}
    return {rid: rid for rid in cand_by_id}, {rid: 1.0 for rid in cand_by_id}


def match_rooms(
    ref_dir: Path,
    cand_dir: Path,
    ref_rooms: List[Dict[str, Any]],
    cand_rooms: List[Dict[str, Any]],
    threshold: float,
) -> Tuple[Dict[Any, Any], Dict[Any, float], str]:
    ref_map = load_region_map(ref_dir)
    cand_map = load_region_map(cand_dir)
    if ref_map is not None and cand_map is not None:
        mapping, scores = greedy_room_iou_match(ref_rooms, cand_rooms, ref_map, cand_map, threshold)
        return mapping, scores, "mask_iou"

    if rooms_have_centroids(ref_rooms) and rooms_have_centroids(cand_rooms):
        mapping, scores = greedy_centroid_area_match(ref_rooms, cand_rooms, threshold)
        return mapping, scores, "centroid_area"

    mapping, scores = exact_identity_match(ref_rooms, cand_rooms)
    if mapping:
        return mapping, scores, "exact_identity"

    return {}, {}, "failed"


def validate_segment(length: Any, width: Any) -> bool:
    length_value = number_or_none(length)
    width_value = number_or_none(width)
    if length_value is None or width_value is None:
        return False
    return length_value > 0 and width_value > 0 and width_value <= length_value


def validate_topology(rooms: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> Dict[str, Any]:
    room_ids = {room["room_id"] for room in rooms}
    edge_room_ids: Set[Any] = set()
    invalid_edge_count = 0
    invalid_opening_count = 0
    invalid_room_segment_count = 0

    for room in rooms:
        for wall in room.get("exterior_walls", []):
            if not validate_segment(wall.get("length"), wall.get("width")):
                invalid_room_segment_count += 1
        for opening in room.get("exterior_openings", []):
            if not validate_segment(opening.get("length"), opening.get("width")):
                invalid_room_segment_count += 1
                invalid_opening_count += 1

    for edge in edges:
        a = edge.get("roomA")
        b = edge.get("roomB")
        edge_room_ids.update([a, b])
        edge_invalid = a not in room_ids or b not in room_ids
        segments = edge.get("segments", [])
        if not segments:
            edge_invalid = True
        for segment in segments:
            if not validate_segment(segment.get("length"), segment.get("width")):
                edge_invalid = True
        if edge_invalid:
            invalid_edge_count += 1

        conn_type = canonical_connection_type(edge.get("connection_type"))
        if conn_type in OPENING_COUPLING_TYPES:
            if edge.get("segment_count", 0) <= 0 or number_or_none(edge.get("total_length")) in (None, 0):
                invalid_opening_count += 1

    isolated_room_count = len(room_ids - edge_room_ids)
    valid_topology = (
        len(room_ids) > 0
        and invalid_edge_count == 0
        and invalid_opening_count == 0
        and invalid_room_segment_count == 0
    )
    return {
        "valid_topology": bool(valid_topology),
        "isolated_room_count": int(isolated_room_count),
        "invalid_edge_count": int(invalid_edge_count),
        "invalid_opening_count": int(invalid_opening_count),
        "invalid_room_segment_count": int(invalid_room_segment_count),
    }


def edge_key(edge: Dict[str, Any], mapping: Optional[Dict[Any, Any]] = None) -> Tuple[Any, Any, str]:
    a = edge["roomA"]
    b = edge["roomB"]
    conn_type = canonical_connection_type(edge["connection_type"])
    if mapping is not None:
        if a not in mapping or b not in mapping:
            mapped = sorted((f"__unmatched_candidate_room_{a}", f"__unmatched_candidate_room_{b}"))
            return mapped[0], mapped[1], conn_type
        a = mapping[a]
        b = mapping[b]
    a, b = sorted((a, b), key=room_sort_key)
    return a, b, conn_type


def pair_key_from_edge_key(key: Tuple[Any, Any, str]) -> Tuple[Any, Any]:
    return tuple(sorted((key[0], key[1]), key=room_sort_key))


def aggregate_edge_records(edges: List[Dict[str, Any]], mapping: Optional[Dict[Any, Any]] = None) -> Dict[Tuple[Any, Any, str], Dict[str, Any]]:
    aggregated: Dict[Tuple[Any, Any, str], Dict[str, Any]] = {}
    for edge in edges:
        key = edge_key(edge, mapping)
        record = aggregated.setdefault(key, {
            "roomA": key[0],
            "roomB": key[1],
            "connection_type": key[2],
            "segments": [],
        })
        record["segments"].extend(edge.get("segments", []))

    for record in aggregated.values():
        lengths = finite(seg.get("length") for seg in record["segments"])
        widths = finite(seg.get("width") for seg in record["segments"])
        record["segment_count"] = len(record["segments"])
        record["total_length"] = float(sum(lengths))
        record["mean_width"] = float(sum(widths) / len(widths)) if widths else None
        record["max_width"] = max(widths) if widths else None
        record["min_width"] = min(widths) if widths else None
    return aggregated


def set_metrics(ref_keys: Set[Tuple[Any, Any, str]], cand_keys: Set[Tuple[Any, Any, str]]) -> Dict[str, Optional[float]]:
    if not ref_keys and not cand_keys:
        return {"precision": 1.0, "recall": 1.0, "F1": 1.0}
    true_positive = len(ref_keys & cand_keys)
    precision = safe_div(true_positive, len(cand_keys)) if cand_keys else None
    recall = safe_div(true_positive, len(ref_keys)) if ref_keys else None
    if precision is None and recall is not None:
        f1 = 0.0
    elif recall is None and precision is not None:
        f1 = 0.0
    else:
        f1 = f1_score(precision, recall)
    return {
        "precision": precision,
        "recall": recall,
        "F1": f1,
    }


def is_one(value: Optional[float], tolerance: float = 1e-12) -> bool:
    return value is not None and abs(float(value) - 1.0) <= tolerance


def within_tolerance(value: Optional[float], threshold: float, *, required: bool = True) -> bool:
    if value is None:
        return not required
    return float(value) <= threshold


def geometric_tolerance_pass(summary: Dict[str, Any]) -> bool:
    checks = [
        within_tolerance(summary.get("area_MAPE"), 0.01),
        within_tolerance(summary.get("perimeter_MAPE"), 0.01),
        within_tolerance(summary.get("wall_length_MAPE"), 0.02),
        within_tolerance(summary.get("exterior_wall_length_MAPE"), 0.02),
    ]
    if summary.get("wall_width_MAPE") is not None:
        checks.append(within_tolerance(summary.get("wall_width_MAPE"), 0.05))
    return all(checks)


def room_comparison_rows(
    ref_rooms: List[Dict[str, Any]],
    cand_rooms: List[Dict[str, Any]],
    cand_to_ref: Dict[Any, Any],
    scores: Dict[Any, float],
) -> List[Dict[str, Any]]:
    ref_by_id = room_index(ref_rooms)
    cand_by_id = room_index(cand_rooms)
    ref_to_cand = {ref_id: cand_id for cand_id, ref_id in cand_to_ref.items()}
    rows: List[Dict[str, Any]] = []

    for ref_id, ref in ref_by_id.items():
        cand_id = ref_to_cand.get(ref_id)
        cand = cand_by_id.get(cand_id) if cand_id is not None else None
        row: Dict[str, Any] = {
            "reference_room_id": ref_id,
            "candidate_room_id": cand_id,
            "match_score": scores.get(cand_id) if cand_id is not None else None,
            "matched": cand is not None,
            "room_type_ref": ref.get("room_type"),
            "room_type_candidate": cand.get("room_type") if cand else None,
            "room_type_match": (
                str(ref.get("room_type", "")).lower() == str(cand.get("room_type", "")).lower()
                if cand else None
            ),
        }
        for key in (
            "area",
            "perimeter",
            "exterior_wall_count",
            "exterior_wall_total_length",
            "exterior_wall_mean_width",
            "exterior_opening_count",
            "exterior_opening_total_length",
            "exterior_opening_mean_width",
        ):
            ref_value = ref.get(key)
            cand_value = cand.get(key) if cand else None
            row[f"{key}_ref"] = ref_value
            row[f"{key}_candidate"] = cand_value
            row[f"{key}_error"] = (
                float(cand_value) - float(ref_value)
                if number_or_none(ref_value) is not None and number_or_none(cand_value) is not None
                else None
            )
        rows.append(row)

    for cand_id, cand in cand_by_id.items():
        if cand_id in cand_to_ref:
            continue
        rows.append({
            "reference_room_id": None,
            "candidate_room_id": cand_id,
            "match_score": None,
            "matched": False,
            "room_type_ref": None,
            "room_type_candidate": cand.get("room_type"),
        })
    return rows


def edge_comparison_rows(
    ref_indexed_edges: Dict[Tuple[Any, Any, str], Dict[str, Any]],
    cand_indexed_edges: Dict[Tuple[Any, Any, str], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key in sorted(set(ref_indexed_edges) | set(cand_indexed_edges), key=lambda item: (str(item[2]), str(item[0]), str(item[1]))):
        ref = ref_indexed_edges.get(key)
        cand = cand_indexed_edges.get(key)
        row = {
            "roomA": key[0],
            "roomB": key[1],
            "connection_type": key[2],
            "present_ref": ref is not None,
            "present_candidate": cand is not None,
        }
        for metric in ("segment_count", "total_length", "mean_width", "max_width", "min_width"):
            ref_value = ref.get(metric) if ref else None
            cand_value = cand.get(metric) if cand else None
            row[f"{metric}_ref"] = ref_value
            row[f"{metric}_candidate"] = cand_value
            row[f"{metric}_error"] = (
                float(cand_value) - float(ref_value)
                if number_or_none(ref_value) is not None and number_or_none(cand_value) is not None
                else None
            )
        rows.append(row)
    return rows


def summarize_room_metrics(
    ref_rooms: List[Dict[str, Any]],
    cand_rooms: List[Dict[str, Any]],
    cand_to_ref: Dict[Any, Any],
) -> Dict[str, Any]:
    ref_by_id = room_index(ref_rooms)
    cand_by_id = room_index(cand_rooms)
    matched_pairs = [(ref_by_id[ref_id], cand_by_id[cand_id]) for cand_id, ref_id in cand_to_ref.items()
                     if ref_id in ref_by_id and cand_id in cand_by_id]

    room_count_ref = len(ref_rooms)
    room_count_candidate = len(cand_rooms)
    matched_count = len(matched_pairs)

    type_matches = [
        str(ref.get("room_type", "")).lower() == str(cand.get("room_type", "")).lower()
        for ref, cand in matched_pairs
    ]

    def pairs(key: str) -> List[Tuple[Optional[float], Optional[float]]]:
        return [(number_or_none(ref.get(key)), number_or_none(cand.get(key))) for ref, cand in matched_pairs]

    return {
        "room_count_ref": room_count_ref,
        "room_count_candidate": room_count_candidate,
        "room_count_error": room_count_candidate - room_count_ref,
        "room_match_rate": safe_div(matched_count, room_count_ref),
        "room_type_accuracy": safe_div(sum(1 for match in type_matches if match), len(type_matches)),
        "area_MAE": mae(pairs("area")),
        "area_MAPE": mape(pairs("area")),
        "room_area_MAPE": mape(pairs("area")),
        "perimeter_MAE": mae(pairs("perimeter")),
        "perimeter_MAPE": mape(pairs("perimeter")),
        "room_perimeter_MAPE": mape(pairs("perimeter")),
        "exterior_wall_count_error": mae(pairs("exterior_wall_count")),
        "exterior_wall_total_length_MAE": mae(pairs("exterior_wall_total_length")),
        "exterior_wall_total_length_MAPE": mape(pairs("exterior_wall_total_length")),
        "exterior_wall_length_MAPE": mape(pairs("exterior_wall_total_length")),
        "exterior_wall_mean_width_MAE": mae(pairs("exterior_wall_mean_width")),
        "exterior_wall_width_MAE": mae(pairs("exterior_wall_mean_width")),
        "exterior_wall_width_MAPE": mape(pairs("exterior_wall_mean_width")),
        "exterior_opening_count_error": mae(pairs("exterior_opening_count")),
        "exterior_opening_total_length_MAE": mae(pairs("exterior_opening_total_length")),
        "exterior_opening_total_length_MAPE": mape(pairs("exterior_opening_total_length")),
        "exterior_opening_mean_width_MAE": mae(pairs("exterior_opening_mean_width")),
        "exterior_opening_width_MAPE": mape(pairs("exterior_opening_mean_width")),
    }


def summarize_edge_metrics(
    ref_edges: List[Dict[str, Any]],
    cand_edges: List[Dict[str, Any]],
    cand_to_ref: Dict[Any, Any],
    room_matching_failed: bool,
) -> Tuple[Dict[str, Any], Dict[Tuple[Any, Any, str], Dict[str, Any]], Dict[Tuple[Any, Any, str], Dict[str, Any]]]:
    ref_indexed = aggregate_edge_records(ref_edges)
    if room_matching_failed:
        cand_raw_indexed = aggregate_edge_records(cand_edges, {})
        ref_pair_keys = {pair_key_from_edge_key(key) for key in ref_indexed}
        cand_pair_keys = {pair_key_from_edge_key(key) for key in cand_raw_indexed}
        summary = {
            "edge_count_ref": len(ref_indexed),
            "edge_count_candidate": len(cand_raw_indexed),
            "edge_count_error": len(cand_raw_indexed) - len(ref_indexed),
            "untyped_pair_F1": None,
            "edge_precision": None,
            "edge_recall": None,
            "edge_F1": None,
            "typed_edge_F1": None,
            "edge_precision_by_type": {},
            "edge_recall_by_type": {},
            "edge_F1_by_type": {},
        }
        opening_count_ref = sum(1 for key in ref_indexed if key[2] in OPENING_COUPLING_TYPES)
        opening_count_candidate = sum(1 for key in cand_raw_indexed if key[2] in OPENING_COUPLING_TYPES)
        summary["opening_count_ref"] = opening_count_ref
        summary["opening_count_candidate"] = opening_count_candidate
        summary["opening_count_error"] = opening_count_candidate - opening_count_ref
        summary["opening_count_relative_error"] = (
            abs(opening_count_candidate - opening_count_ref) / opening_count_ref
            if opening_count_ref else None
        )
        for conn_type in CONNECTION_TYPES:
            ref_type_count = sum(1 for k in ref_indexed if k[2] == conn_type)
            cand_type_count = sum(1 for k in cand_raw_indexed if k[2] == conn_type)
            summary[f"{conn_type}_edge_count_error"] = cand_type_count - ref_type_count
            summary[f"{conn_type}_edge_precision"] = None
            summary[f"{conn_type}_edge_recall"] = None
            summary[f"{conn_type}_edge_F1"] = None
        summary["door_edge_precision"] = None
        summary["door_edge_recall"] = None
        summary["open_space_edge_count_error"] = summary.get(f"{OPEN_SPACE_TYPE}_edge_count_error")
        summary["open_space_edge_F1"] = summary.get(f"{OPEN_SPACE_TYPE}_edge_F1")
        summary["open_passage_edge_F1"] = summary.get(f"{OPEN_SPACE_TYPE}_edge_F1")
        return summary, ref_indexed, cand_raw_indexed

    cand_indexed = aggregate_edge_records(cand_edges, cand_to_ref)
    ref_keys = set(ref_indexed)
    cand_keys = set(cand_indexed)
    overall = set_metrics(ref_keys, cand_keys)
    untyped = set_metrics({pair_key_from_edge_key(key) for key in ref_keys}, {pair_key_from_edge_key(key) for key in cand_keys})

    precision_by_type: Dict[str, Optional[float]] = {}
    recall_by_type: Dict[str, Optional[float]] = {}
    f1_by_type: Dict[str, Optional[float]] = {}
    summary: Dict[str, Any] = {
        "edge_count_ref": len(ref_keys),
        "edge_count_candidate": len(cand_keys),
        "edge_count_error": len(cand_keys) - len(ref_keys),
        "untyped_pair_precision": untyped["precision"],
        "untyped_pair_recall": untyped["recall"],
        "untyped_pair_F1": untyped["F1"],
        "edge_precision": overall["precision"],
        "edge_recall": overall["recall"],
        "edge_F1": overall["F1"],
        "typed_edge_F1": overall["F1"],
    }

    matched_keys = ref_keys & cand_keys
    opening_matched_keys = [key for key in matched_keys if key[2] in OPENING_COUPLING_TYPES]
    opening_length_pairs = [(ref_indexed[key].get("total_length"), cand_indexed[key].get("total_length"))
                            for key in opening_matched_keys]
    opening_width_pairs = [(ref_indexed[key].get("mean_width"), cand_indexed[key].get("mean_width"))
                           for key in opening_matched_keys]
    for conn_type in CONNECTION_TYPES:
        ref_type_keys = {key for key in ref_keys if key[2] == conn_type}
        cand_type_keys = {key for key in cand_keys if key[2] == conn_type}
        typed = set_metrics(ref_type_keys, cand_type_keys)
        precision_by_type[conn_type] = typed["precision"]
        recall_by_type[conn_type] = typed["recall"]
        f1_by_type[conn_type] = typed["F1"]
        summary[f"{conn_type}_edge_count_error"] = len(cand_type_keys) - len(ref_type_keys)
        summary[f"{conn_type}_edge_precision"] = typed["precision"]
        summary[f"{conn_type}_edge_recall"] = typed["recall"]
        summary[f"{conn_type}_edge_F1"] = typed["F1"]

        matched_type = [key for key in matched_keys if key[2] == conn_type]
        count_pairs = [(ref_indexed[key].get("segment_count"), cand_indexed[key].get("segment_count"))
                       for key in matched_type]
        length_pairs = [(ref_indexed[key].get("total_length"), cand_indexed[key].get("total_length"))
                        for key in matched_type]
        width_pairs = [(ref_indexed[key].get("mean_width"), cand_indexed[key].get("mean_width"))
                       for key in matched_type]

        if conn_type == "wall":
            summary["wall_total_length_MAE"] = mae(length_pairs)
            summary["wall_total_length_MAPE"] = mape(length_pairs)
            summary["wall_length_MAE"] = mae(length_pairs)
            summary["wall_length_MAPE"] = mape(length_pairs)
            summary["wall_width_MAE"] = mae(width_pairs)
            summary["wall_width_MAPE"] = mape(width_pairs)
        else:
            summary[f"{conn_type}_count_error"] = mae(count_pairs)
            summary[f"{conn_type}_length_MAE"] = mae(length_pairs)
            summary[f"{conn_type}_length_MAPE"] = mape(length_pairs)
            summary[f"{conn_type}_width_MAE"] = mae(width_pairs)
            summary[f"{conn_type}_width_MAPE"] = mape(width_pairs)

    summary["edge_precision_by_type"] = precision_by_type
    summary["edge_recall_by_type"] = recall_by_type
    summary["edge_F1_by_type"] = f1_by_type
    summary["door_edge_precision"] = precision_by_type.get("door")
    summary["door_edge_recall"] = recall_by_type.get("door")
    summary["open_space_edge_count_error"] = summary.get(f"{OPEN_SPACE_TYPE}_edge_count_error")
    summary["open_space_edge_F1"] = summary.get(f"{OPEN_SPACE_TYPE}_edge_F1")
    summary["open_passage_edge_F1"] = summary.get(f"{OPEN_SPACE_TYPE}_edge_F1")
    opening_count_ref = sum(1 for key in ref_keys if key[2] in OPENING_COUPLING_TYPES)
    opening_count_candidate = sum(1 for key in cand_keys if key[2] in OPENING_COUPLING_TYPES)
    summary["opening_count_ref"] = opening_count_ref
    summary["opening_count_candidate"] = opening_count_candidate
    summary["opening_count_error"] = opening_count_candidate - opening_count_ref
    summary["opening_count_relative_error"] = (
        abs(opening_count_candidate - opening_count_ref) / opening_count_ref
        if opening_count_ref else None
    )
    summary["opening_length_MAPE"] = mape(opening_length_pairs)
    summary["opening_width_MAPE"] = mape(opening_width_pairs)
    summary["opening_width_MAE"] = mae(opening_width_pairs)

    for metric in (
        "wall_total_length_MAE",
        "wall_total_length_MAPE",
        "wall_length_MAE",
        "wall_length_MAPE",
        "wall_width_MAE",
        "wall_width_MAPE",
        "door_count_error",
        "door_length_MAE",
        "door_length_MAPE",
        "door_width_MAE",
        "door_width_MAPE",
        "window_count_error",
        "window_length_MAE",
        "window_length_MAPE",
        "window_width_MAE",
        "window_width_MAPE",
        "open_space_count_error",
        "open_space_length_MAE",
        "open_space_length_MAPE",
        "open_space_width_MAE",
        "open_space_width_MAPE",
        "opening_length_MAPE",
        "opening_width_MAPE",
        "opening_width_MAE",
    ):
        summary.setdefault(metric, None)

    return summary, ref_indexed, cand_indexed


def run_comparison(
    reference_dir: str | Path,
    candidate_dir: str | Path,
    out_dir: str | Path,
    *,
    room_iou_threshold: float = 0.5,
) -> Dict[str, Any]:
    reference_path = Path(reference_dir)
    candidate_path = Path(candidate_dir)
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    ref_rooms, ref_edges = load_tables(reference_path)
    cand_rooms, cand_edges = load_tables(candidate_path)

    cand_to_ref, match_scores, match_method = match_rooms(
        reference_path,
        candidate_path,
        ref_rooms,
        cand_rooms,
        room_iou_threshold,
    )
    room_matching_failed = len(ref_rooms) > 0 and len(cand_to_ref) == 0

    unmatched_reference_rooms = sorted(set(room_index(ref_rooms)) - set(cand_to_ref.values()), key=str)
    unmatched_candidate_rooms = sorted(set(room_index(cand_rooms)) - set(cand_to_ref), key=str)

    room_summary = summarize_room_metrics(ref_rooms, cand_rooms, cand_to_ref)
    edge_summary, ref_indexed_edges, cand_indexed_edges = summarize_edge_metrics(
        ref_edges,
        cand_edges,
        cand_to_ref,
        room_matching_failed,
    )
    ref_validity = validate_topology(ref_rooms, ref_edges)
    cand_validity = validate_topology(cand_rooms, cand_edges)

    summary: Dict[str, Any] = {}
    summary.update(room_summary)
    summary.update(edge_summary)
    summary.update({
        "reference_dir": str(reference_path),
        "candidate_dir": str(candidate_path),
        "room_matching_method": match_method,
        "room_matching_failed": bool(room_matching_failed),
        "room_iou_threshold": room_iou_threshold,
        "unmatched_reference_rooms": unmatched_reference_rooms,
        "unmatched_candidate_rooms": unmatched_candidate_rooms,
        "reference_valid_topology": ref_validity["valid_topology"],
        "candidate_valid_topology": cand_validity["valid_topology"],
        "valid_topology": cand_validity["valid_topology"],
        "reference_isolated_room_count": ref_validity["isolated_room_count"],
        "isolated_room_count": cand_validity["isolated_room_count"],
        "reference_invalid_edge_count": ref_validity["invalid_edge_count"],
        "invalid_edge_count": cand_validity["invalid_edge_count"],
        "reference_invalid_opening_count": ref_validity["invalid_opening_count"],
        "invalid_opening_count": cand_validity["invalid_opening_count"],
        "reference_invalid_room_segment_count": ref_validity["invalid_room_segment_count"],
        "invalid_room_segment_count": cand_validity["invalid_room_segment_count"],
    })
    summary["topology_relation_preserved"] = (
        summary.get("room_count_error") == 0
        and summary.get("isolated_room_count") == 0
        and is_one(summary.get("untyped_pair_F1"))
        and is_one(summary.get("wall_edge_F1"))
    )
    summary["geometric_parameter_consistency"] = {
        "wall_length_MAPE": summary.get("wall_length_MAPE"),
        "wall_width_MAPE": summary.get("wall_width_MAPE"),
        "exterior_wall_length_MAPE": summary.get("exterior_wall_length_MAPE"),
        "exterior_wall_width_MAPE": summary.get("exterior_wall_width_MAPE"),
        "opening_length_MAPE": summary.get("opening_length_MAPE"),
        "opening_width_MAPE": summary.get("opening_width_MAPE"),
        "room_area_MAPE": summary.get("room_area_MAPE"),
        "room_perimeter_MAPE": summary.get("room_perimeter_MAPE"),
    }
    summary["coupling_type_consistency"] = {
        "door_edge_precision": summary.get("door_edge_precision"),
        "door_edge_recall": summary.get("door_edge_recall"),
        "door_edge_F1": summary.get("door_edge_F1"),
        "window_edge_F1": summary.get("window_edge_F1"),
        "open_space_edge_F1": summary.get("open_space_edge_F1"),
    }
    summary["geometric_tolerance_pass"] = geometric_tolerance_pass(summary)

    write_csv(out_path / "roomself_comparison.csv", room_comparison_rows(ref_rooms, cand_rooms, cand_to_ref, match_scores))
    write_csv(out_path / "edge_comparison.csv", edge_comparison_rows(ref_indexed_edges, cand_indexed_edges))
    write_json(out_path / "comparison_summary.json", summary)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare Geo-ELCT Excel tables under perturbation.")
    parser.add_argument("--reference-dir", required=True, help="Directory containing reference debug_roomself.xlsx and debug_topology_edges.xlsx.")
    parser.add_argument("--candidate-dir", required=True, help="Directory containing candidate debug_roomself.xlsx and debug_topology_edges.xlsx.")
    parser.add_argument("--out-dir", required=True, help="Output directory for comparison CSV/JSON files.")
    parser.add_argument("--room-iou-threshold", type=float, default=0.5, help="Minimum mask IoU or centroid-area similarity for room matching.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = run_comparison(
        reference_dir=args.reference_dir,
        candidate_dir=args.candidate_dir,
        out_dir=args.out_dir,
        room_iou_threshold=args.room_iou_threshold,
    )
    print(json.dumps(json_safe(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
