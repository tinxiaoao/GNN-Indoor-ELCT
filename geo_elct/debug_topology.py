import argparse
import json
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
from PIL import Image


_HERE = Path(__file__).resolve().parent

try:
    import matplotlib

    matplotlib.rcParams["font.sans-serif"] = ["SimHei"]
    matplotlib.rcParams["axes.unicode_minus"] = False
except Exception:
    matplotlib = None


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    return value


def _write_json(path: str | Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_json_safe(payload), f, ensure_ascii=False, indent=2)


_REPAIR_EXCLUDE_LABELS = {0, 1, 2, 8, 50}
CORRECTION_MODES = (
    "baseline",
    "fragment_only",
    "fragment_plus_wall",
    "fragment_plus_wall_plus_opening",
)
_CONSERVATIVE_REPAIR_PARAMS = {
    "wall_gap_max_length_px": 4,
    "wall_gap_max_component_area_px": 512,
    "wall_gap_endpoint_alignment_fraction": 0.8,
    "wall_gap_opening_clearance_px": 2,
    "wall_regularization_max_artifact_area_px": 1,
    "opening_snap_max_distance_px": 3,
    "opening_min_wall_overlap_fraction": 0.90,
    "opening_already_snapped_overlap_fraction": 0.98,
    "opening_spurious_component_area_px": 8,
    "validation_max_wall_thickness_px": 64.0,
}


def _component_coords(mask: np.ndarray, connectivity: int = 8) -> List[np.ndarray]:
    import cv2

    n_labels, label_map = cv2.connectedComponents(mask.astype(np.uint8), connectivity=connectivity)
    return [np.argwhere(label_map == label) for label in range(1, n_labels)]


def _dominant_neighbor_label(
    label_array: np.ndarray,
    coords: np.ndarray,
    *,
    source_label: int,
    radius: int = 1,
) -> Optional[int]:
    counts: Dict[int, int] = {}
    height, width = label_array.shape
    for y, x in coords:
        y0, y1 = max(0, int(y) - radius), min(height, int(y) + radius + 1)
        x0, x1 = max(0, int(x) - radius), min(width, int(x) + radius + 1)
        for value in label_array[y0:y1, x0:x1].ravel():
            value_int = int(value)
            if value_int == source_label or value_int in _REPAIR_EXCLUDE_LABELS:
                continue
            counts[value_int] = counts.get(value_int, 0) + 1
    if not counts:
        return None
    label, count = max(counts.items(), key=lambda item: item[1])
    if count < max(2, int(0.4 * len(coords))):
        return None
    return label


def _remove_tiny_room_components(wall_label_array: np.ndarray) -> Tuple[np.ndarray, Dict[str, int]]:
    repaired = wall_label_array.copy()
    stats = {"tiny_room_components_removed": 0, "tiny_room_pixels_reassigned": 0}
    threshold = int(_CONSERVATIVE_REPAIR_PARAMS["tiny_room_component_area_px"])
    room_labels = [
        int(value)
        for value in np.unique(repaired)
        if int(value) not in _REPAIR_EXCLUDE_LABELS
    ]
    for label in room_labels:
        for coords in _component_coords(repaired == label, connectivity=8):
            if len(coords) == 0 or len(coords) > threshold:
                continue
            replacement = _dominant_neighbor_label(repaired, coords, source_label=label)
            if replacement is None:
                continue
            repaired[coords[:, 0], coords[:, 1]] = replacement
            stats["tiny_room_components_removed"] += 1
            stats["tiny_room_pixels_reassigned"] += int(len(coords))
    return repaired, stats


def _room_values(values: np.ndarray) -> Set[int]:
    return {int(value) for value in values.ravel() if int(value) not in _REPAIR_EXCLUDE_LABELS}


def _gap_cross_section_has_rooms(
    wall_label_array: np.ndarray,
    coords: np.ndarray,
    orientation: str,
    *,
    search_px: int = 6,
) -> bool:
    """Require an internal wall: room pixels must lie on both cross-wall sides."""
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    height, width = wall_label_array.shape
    if orientation == "horizontal":
        above = wall_label_array[max(0, int(y0) - search_px):int(y0), int(x0):int(x1) + 1]
        below = wall_label_array[int(y1) + 1:min(height, int(y1) + 1 + search_px), int(x0):int(x1) + 1]
        return bool(_room_values(above)) and bool(_room_values(below))
    left = wall_label_array[int(y0):int(y1) + 1, max(0, int(x0) - search_px):int(x0)]
    right = wall_label_array[int(y0):int(y1) + 1, int(x1) + 1:min(width, int(x1) + 1 + search_px)]
    return bool(_room_values(left)) and bool(_room_values(right))


def _aligned_endpoint_fraction(wall_mask: np.ndarray, coords: np.ndarray, orientation: str) -> float:
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    height, width = wall_mask.shape
    aligned = 0
    total = 0
    if orientation == "horizontal" and x0 > 0 and x1 + 1 < width:
        for y in range(int(y0), int(y1) + 1):
            total += 1
            aligned += int(bool(wall_mask[y, int(x0) - 1] and wall_mask[y, int(x1) + 1]))
    elif orientation == "vertical" and y0 > 0 and y1 + 1 < height:
        for x in range(int(x0), int(x1) + 1):
            total += 1
            aligned += int(bool(wall_mask[int(y0) - 1, x] and wall_mask[int(y1) + 1, x]))
    return float(aligned / total) if total else 0.0


def _opening_near_coords(icon_label_array: np.ndarray, coords: np.ndarray, clearance: int) -> bool:
    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0)
    return bool(np.any(icon_label_array[
        max(0, int(y0) - clearance):min(icon_label_array.shape[0], int(y1) + clearance + 1),
        max(0, int(x0) - clearance):min(icon_label_array.shape[1], int(x1) + clearance + 1),
    ]))


def _close_short_wall_gaps(
    wall_label_array: np.ndarray,
    icon_label_array: np.ndarray,
    wall_code: int = 2,
) -> Tuple[np.ndarray, Dict[str, int]]:
    """Bridge only aligned, opening-free, internal wall gaps up to 4 px."""
    import cv2

    repaired = wall_label_array.copy()
    wall_mask = repaired == wall_code
    max_gap = int(_CONSERVATIVE_REPAIR_PARAMS["wall_gap_max_length_px"])
    max_area = int(_CONSERVATIVE_REPAIR_PARAMS["wall_gap_max_component_area_px"])
    alignment_min = float(_CONSERVATIVE_REPAIR_PARAMS["wall_gap_endpoint_alignment_fraction"])
    clearance = int(_CONSERVATIVE_REPAIR_PARAMS["wall_gap_opening_clearance_px"])

    horizontal_closed = cv2.morphologyEx(
        wall_mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((1, max_gap + 2), np.uint8)
    ).astype(bool)
    vertical_closed = cv2.morphologyEx(
        wall_mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((max_gap + 2, 1), np.uint8)
    ).astype(bool)
    candidate_masks = {
        "horizontal": horizontal_closed & ~wall_mask & (repaired == 0),
        "vertical": vertical_closed & ~wall_mask & (repaired == 0),
    }
    stats = {
        "short_wall_gap_candidates_before": 0,
        "short_wall_gap_components_closed": 0,
        "short_wall_gap_pixels_filled": 0,
        "short_wall_gap_rejected_opening": 0,
        "short_wall_gap_rejected_alignment": 0,
        "short_wall_gap_rejected_geometry": 0,
        "short_wall_gap_candidates_remaining_after": 0,
    }
    accepted_mask = np.zeros(wall_mask.shape, dtype=bool)
    seen_boxes: Set[Tuple[int, int, int, int]] = set()

    for orientation, candidate_mask in candidate_masks.items():
        for coords in _component_coords(candidate_mask, connectivity=8):
            if len(coords) == 0:
                continue
            y0, x0 = coords.min(axis=0)
            y1, x1 = coords.max(axis=0)
            box = (int(y0), int(x0), int(y1), int(x1))
            if box in seen_boxes:
                continue
            seen_boxes.add(box)
            stats["short_wall_gap_candidates_before"] += 1
            gap_length = int(x1 - x0 + 1) if orientation == "horizontal" else int(y1 - y0 + 1)
            if len(coords) > max_area or gap_length > max_gap or not _gap_cross_section_has_rooms(
                repaired, coords, orientation
            ):
                stats["short_wall_gap_rejected_geometry"] += 1
                continue
            if _opening_near_coords(icon_label_array, coords, clearance):
                stats["short_wall_gap_rejected_opening"] += 1
                continue
            if _aligned_endpoint_fraction(wall_mask, coords, orientation) < alignment_min:
                stats["short_wall_gap_rejected_alignment"] += 1
                continue
            accepted_mask[coords[:, 0], coords[:, 1]] = True
            stats["short_wall_gap_components_closed"] += 1
            stats["short_wall_gap_pixels_filled"] += int(len(coords))

    repaired[accepted_mask] = wall_code
    stats["short_wall_gap_candidates_remaining_after"] = (
        stats["short_wall_gap_candidates_before"] - stats["short_wall_gap_components_closed"]
    )
    return repaired, stats


def _regularize_wall_boundary(
    wall_label_array: np.ndarray,
    icon_label_array: np.ndarray,
    wall_code: int = 2,
) -> Tuple[np.ndarray, Dict[str, int]]:
    """Fill isolated one-pixel holes and remove unambiguous one-pixel spurs."""
    repaired = wall_label_array.copy()
    wall = repaired == wall_code
    padded = np.pad(wall, 1, mode="constant")
    orthogonal = (
        padded[:-2, 1:-1].astype(np.uint8)
        + padded[2:, 1:-1].astype(np.uint8)
        + padded[1:-1, :-2].astype(np.uint8)
        + padded[1:-1, 2:].astype(np.uint8)
    )
    holes = (repaired == 0) & (orthogonal == 4) & (icon_label_array == 0)
    repaired[holes] = wall_code

    wall = repaired == wall_code
    padded = np.pad(wall, 1, mode="constant")
    neighbors = np.zeros(wall.shape, dtype=np.uint8)
    for dy in range(3):
        for dx in range(3):
            if dy == 1 and dx == 1:
                continue
            neighbors += padded[dy:dy + wall.shape[0], dx:dx + wall.shape[1]]
    spur_candidates = wall & (neighbors <= 1) & (icon_label_array == 0)
    removed = 0
    for coords in _component_coords(spur_candidates, connectivity=8):
        if len(coords) != 1:
            continue
        y, x = (int(coords[0, 0]), int(coords[0, 1]))
        y0, y1 = max(0, y - 1), min(repaired.shape[0], y + 2)
        x0, x1 = max(0, x - 1), min(repaired.shape[1], x + 2)
        values = [int(v) for v in repaired[y0:y1, x0:x1].ravel() if int(v) != wall_code]
        if not values or len(set(values)) != 1:
            continue
        repaired[y, x] = values[0]
        removed += 1
    return repaired, {
        "wall_one_pixel_holes_filled": int(holes.sum()),
        "wall_one_pixel_spurs_removed": int(removed),
    }


def _room_neighbors_for_coords(
    region_id_map: np.ndarray,
    coords: np.ndarray,
    *,
    radius: int = 1,
) -> Set[int]:
    neighbors: Set[int] = set()
    height, width = region_id_map.shape
    for y, x in coords:
        y0, y1 = max(0, int(y) - radius), min(height, int(y) + radius + 1)
        x0, x1 = max(0, int(x) - radius), min(width, int(x) + radius + 1)
        for rid in region_id_map[y0:y1, x0:x1].ravel():
            rid_int = int(rid)
            if rid_int > 0:
                neighbors.add(rid_int)
    return neighbors


def _shift_candidates(max_distance: int) -> List[Tuple[int, int]]:
    shifts: List[Tuple[int, int]] = [(0, 0)]
    for dy in range(-max_distance, max_distance + 1):
        for dx in range(-max_distance, max_distance + 1):
            if dy == 0 and dx == 0:
                continue
            if dy * dy + dx * dx <= max_distance * max_distance:
                shifts.append((dy, dx))
    shifts.sort(key=lambda item: (abs(item[0]) + abs(item[1]), item[0] * item[0] + item[1] * item[1]))
    return shifts


def _opening_domain_count(
    region_id_map: np.ndarray,
    wall_label_array: np.ndarray,
    coords: np.ndarray,
) -> Tuple[int, Set[int], bool]:
    rooms = _room_neighbors_for_coords(region_id_map, coords, radius=2)
    outside_seen = False
    height, width = wall_label_array.shape
    for y, x in coords:
        y0, y1 = max(0, int(y) - 2), min(height, int(y) + 3)
        x0, x1 = max(0, int(x) - 2), min(width, int(x) + 3)
        if np.isin(wall_label_array[y0:y1, x0:x1], [0, 1, 8, 50]).any():
            outside_seen = True
            break
    return len(rooms) + int(outside_seen), rooms, outside_seen


def _snap_opening_components(
    icon_label_array: np.ndarray,
    region_id_map: np.ndarray,
    wall_label_array: np.ndarray,
    *,
    wall_code: int = 2,
) -> Tuple[np.ndarray, Dict[str, int]]:
    repaired = icon_label_array.copy()
    original = icon_label_array.copy()
    max_distance = int(_CONSERVATIVE_REPAIR_PARAMS["opening_snap_max_distance_px"])
    min_overlap = float(_CONSERVATIVE_REPAIR_PARAMS["opening_min_wall_overlap_fraction"])
    snapped_overlap = float(_CONSERVATIVE_REPAIR_PARAMS["opening_already_snapped_overlap_fraction"])
    spurious_area = int(_CONSERVATIVE_REPAIR_PARAMS["opening_spurious_component_area_px"])
    shifts = _shift_candidates(max_distance)
    stats = {
        "opening_components_checked": 0,
        "opening_components_already_valid": 0,
        "opening_components_snapped": 0,
        "opening_components_removed_spurious": 0,
        "opening_components_rejected": 0,
        "opening_components_left_ambiguous": 0,
    }
    height, width = icon_label_array.shape

    for icon_label in (1, 2):
        for coords in _component_coords(original == icon_label, connectivity=8):
            if len(coords) == 0:
                continue
            stats["opening_components_checked"] += 1
            domain_count, _, _ = _opening_domain_count(region_id_map, wall_label_array, coords)
            current_overlap = float((wall_label_array[coords[:, 0], coords[:, 1]] == wall_code).mean())
            if len(coords) <= spurious_area and (domain_count != 2 or current_overlap == 0.0):
                repaired[coords[:, 0], coords[:, 1]] = 0
                stats["opening_components_removed_spurious"] += 1
                continue
            if domain_count == 2 and current_overlap >= snapped_overlap:
                stats["opening_components_already_valid"] += 1
                continue

            best_coords: Optional[np.ndarray] = None
            best_score: Optional[Tuple[float, int]] = None
            for dy, dx in shifts:
                shifted = coords + np.array([dy, dx], dtype=np.int64)
                if (
                    shifted[:, 0].min() < 0
                    or shifted[:, 1].min() < 0
                    or shifted[:, 0].max() >= height
                    or shifted[:, 1].max() >= width
                ):
                    continue
                shifted_domain_count, _, _ = _opening_domain_count(region_id_map, wall_label_array, shifted)
                if shifted_domain_count != 2:
                    continue
                wall_overlap = float((wall_label_array[shifted[:, 0], shifted[:, 1]] == wall_code).mean())
                if wall_overlap < min_overlap:
                    continue
                distance = abs(dy) + abs(dx)
                score = (wall_overlap, -distance)
                if best_score is None or score > best_score:
                    best_score = score
                    best_coords = shifted

            if best_coords is None:
                # An invalid, unsnappable opening is rejected instead of being
                # translated into a false coupling edge.
                if domain_count != 2 or current_overlap < min_overlap:
                    repaired[coords[:, 0], coords[:, 1]] = 0
                    stats["opening_components_rejected"] += 1
                else:
                    stats["opening_components_left_ambiguous"] += 1
                continue
            if np.array_equal(best_coords, coords):
                stats["opening_components_already_valid"] += 1
                continue
            repaired[coords[:, 0], coords[:, 1]] = 0
            repaired[best_coords[:, 0], best_coords[:, 1]] = icon_label
            stats["opening_components_snapped"] += 1
    return repaired, stats


def _save_palette_array(array: np.ndarray, palette: Optional[List[int]], path: Path) -> None:
    image = Image.fromarray(array.astype(np.uint8), mode="P")
    if palette is not None:
        image.putpalette(palette)
    image.save(path)


def _room_centroids(region_id_map: np.ndarray) -> Dict[int, Dict[str, float]]:
    centroids: Dict[int, Dict[str, float]] = {}
    for rid in np.unique(region_id_map):
        rid_int = int(rid)
        if rid_int <= 0:
            continue
        ys, xs = np.where(region_id_map == rid_int)
        if ys.size == 0:
            continue
        centroids[rid_int] = {
            "centroid_y": float(ys.mean()),
            "centroid_x": float(xs.mean()),
            "bbox_ymin": int(ys.min()),
            "bbox_xmin": int(xs.min()),
            "bbox_ymax": int(ys.max()),
            "bbox_xmax": int(xs.max()),
        }
    return centroids


def _augment_rooms_with_geometry(rooms: List[Dict[str, Any]], region_id_map: np.ndarray) -> List[Dict[str, Any]]:
    centroids = _room_centroids(region_id_map)
    augmented: List[Dict[str, Any]] = []
    for room in rooms:
        room_copy = dict(room)
        geom = centroids.get(int(room_copy["id"]), {})
        room_copy.update(geom)
        augmented.append(room_copy)
    return augmented


def _summarize_topology(
    rooms: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    region_id_map: np.ndarray,
    room_stats: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    room_ids = {int(r["id"]) for r in rooms}
    edge_room_ids = set()
    invalid_edge_count = 0
    invalid_opening_count = 0
    invalid_wall_thickness_count = 0
    max_wall_thickness_violation_count = 0
    geometric_plausibility_violation_count = 0
    invalid_records = []
    wall_thicknesses: List[float] = []
    max_wall_thickness = float(_CONSERVATIVE_REPAIR_PARAMS["validation_max_wall_thickness_px"])

    for edge in edges:
        a = int(edge.get("roomA", 0))
        b = int(edge.get("roomB", 0))
        edge_room_ids.update([a, b])

        length = float(edge.get("length", 0) or 0)
        width = float(edge.get("width", 0) or 0)
        count = int(edge.get("num", 1) or 0)
        conn_type = str(edge.get("type", "")).lower()

        bad_dimension = length <= 0 or width <= 0
        bad_reference = a not in room_ids or b not in room_ids
        bad_opening_adjacency = conn_type in {"door", "window", "opening"} and (
            a == b or bad_reference or count <= 0 or length <= 0
        )
        if conn_type == "wall":
            wall_thicknesses.append(width)
            if width > length:
                invalid_wall_thickness_count += 1
                geometric_plausibility_violation_count += 1
                bad_dimension = True
            if width > max_wall_thickness:
                invalid_wall_thickness_count += 1
                max_wall_thickness_violation_count += 1
                bad_dimension = True
        elif conn_type in {"door", "window", "opening"} and width > length:
            invalid_opening_count += 1
            geometric_plausibility_violation_count += 1
            bad_dimension = True
        if bad_dimension or bad_reference:
            invalid_edge_count += 1
            invalid_records.append({
                "type": "edge",
                "roomA": a,
                "roomB": b,
                "connection_type": conn_type,
                "length": length,
                "width": width,
                "reason": "bad dimension or nonexistent room reference",
            })
        if bad_opening_adjacency:
            invalid_opening_count += 1
            invalid_records.append({
                "type": "opening",
                "roomA": a,
                "roomB": b,
                "connection_type": conn_type,
                "length": length,
                "count": count,
                "reason": "opening is not adjacent to exactly two valid rooms",
            })

    for rid, stats in room_stats.items():
        for wall_dir, length, thickness in stats.get("walls", []):
            length_value = float(length or 0)
            thickness_value = float(thickness or 0)
            if thickness_value > 0:
                wall_thicknesses.append(thickness_value)
            if length_value <= 0 or thickness_value <= 0 or thickness_value > length_value:
                invalid_wall_thickness_count += 1
                geometric_plausibility_violation_count += 1
                invalid_records.append({
                    "type": "exterior_wall",
                    "room_id": int(rid),
                    "direction": wall_dir,
                    "length": length_value,
                    "width": thickness_value,
                    "reason": "wall thickness is nonpositive or larger than wall length",
                })
            if thickness_value > max_wall_thickness:
                invalid_wall_thickness_count += 1
                max_wall_thickness_violation_count += 1
                invalid_records.append({
                    "type": "exterior_wall",
                    "room_id": int(rid),
                    "direction": wall_dir,
                    "length": length_value,
                    "width": thickness_value,
                    "reason": f"wall thickness exceeds validation limit ({max_wall_thickness:g} px)",
                })
        for opening_type, opening_dir, length, thickness in stats.get("openings", []):
            length_value = float(length or 0)
            thickness_value = float(thickness or 0)
            if length_value <= 0 or thickness_value <= 0 or thickness_value > length_value:
                invalid_opening_count += 1
                geometric_plausibility_violation_count += 1
                invalid_records.append({
                    "type": "exterior_opening",
                    "room_id": int(rid),
                    "opening_type": opening_type,
                    "direction": opening_dir,
                    "length": length_value,
                    "width": thickness_value,
                    "reason": "opening has nonpositive dimensions or thickness exceeds length",
                })

    isolated_room_count = len(room_ids - edge_room_ids)
    edge_type_counts = {
        "wall": sum(1 for edge in edges if str(edge.get("type", "")).lower() == "wall"),
        "door": sum(1 for edge in edges if str(edge.get("type", "")).lower() == "door"),
        "window": sum(1 for edge in edges if str(edge.get("type", "")).lower() == "window"),
        "opening": sum(1 for edge in edges if str(edge.get("type", "")).lower() == "opening"),
    }
    thickness_stats = {
        "mean": float(mean(wall_thicknesses)) if wall_thicknesses else None,
        "median": float(median(wall_thicknesses)) if wall_thicknesses else None,
        "max": float(max(wall_thicknesses)) if wall_thicknesses else None,
        "min": float(min(wall_thicknesses)) if wall_thicknesses else None,
    }
    valid_topology = (
        len(room_ids) > 0
        and invalid_edge_count == 0
        and invalid_opening_count == 0
        and invalid_wall_thickness_count == 0
    )

    return {
        "number_of_rooms": len(room_ids),
        "number_of_edges": len(edges),
        "number_of_wall_edges": edge_type_counts["wall"],
        "number_of_door_edges": edge_type_counts["door"],
        "number_of_window_edges": edge_type_counts["window"],
        "number_of_opening_edges": edge_type_counts["opening"],
        "number_of_isolated_rooms": int(isolated_room_count),
        "number_of_invalid_openings": int(invalid_opening_count),
        "wall_thickness_statistics": thickness_stats,
        "room_count": len(room_ids),
        "edge_count": len(edges),
        "wall_edge_count": edge_type_counts["wall"],
        "door_edge_count": edge_type_counts["door"],
        "window_edge_count": edge_type_counts["window"],
        "opening_edge_count": edge_type_counts["opening"],
        "region_id_map_shape": list(region_id_map.shape),
        "valid_topology": bool(valid_topology),
        "isolated_room_count": int(isolated_room_count),
        "invalid_edge_count": int(invalid_edge_count),
        "invalid_opening_count": int(invalid_opening_count),
        "invalid_wall_thickness_count": int(invalid_wall_thickness_count),
        "max_wall_thickness_violation_count": int(max_wall_thickness_violation_count),
        "geometric_plausibility_violation_count": int(geometric_plausibility_violation_count),
        "validation_checks": {
            "isolated_room_detection": {"count": int(isolated_room_count), "passed": isolated_room_count == 0},
            "invalid_edge_detection": {"count": int(invalid_edge_count), "passed": invalid_edge_count == 0},
            "maximum_wall_thickness_px": max_wall_thickness,
            "maximum_wall_thickness_constraint": {
                "count": int(max_wall_thickness_violation_count),
                "passed": max_wall_thickness_violation_count == 0,
            },
            "geometric_plausibility": {
                "count": int(geometric_plausibility_violation_count),
                "passed": geometric_plausibility_violation_count == 0,
            },
        },
        "invalid_records": invalid_records,
    }


def _export_canonical_tables(output_dir: str | Path) -> None:
    from .evaluation.parse_elct_tables import write_canonical_tables

    output_dir = Path(output_dir)
    write_canonical_tables(
        room_xlsx=output_dir / "debug_roomself.xlsx",
        edge_xlsx=output_dir / "debug_topology_edges.xlsx",
        out_dir=output_dir,
        write_csv=False,
    )


def _export_canonical_json_direct(
    output_dir: Path,
    rooms: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    room_stats: Dict[int, Dict[str, Any]],
) -> None:
    canonical_rooms: List[Dict[str, Any]] = []
    for room in rooms:
        rid = int(room["id"])
        stats = room_stats.get(rid, {})
        exterior_walls = [
            {"direction": direction, "length": float(length), "width": float(width)}
            for direction, length, width in stats.get("walls", [])
        ]
        exterior_openings = [
            {"type": opening_type, "direction": direction, "length": float(length), "width": float(width)}
            for opening_type, direction, length, width in stats.get("openings", [])
        ]
        widths = [item["width"] for item in exterior_walls]
        opening_widths = [item["width"] for item in exterior_openings]
        record = {
            "room_id": rid,
            "room_type": room.get("room_type"),
            "area": float(room.get("area", 0)),
            "perimeter": float(room.get("perimeter", 0)),
            "exterior_walls": exterior_walls,
            "exterior_openings": exterior_openings,
            "exterior_wall_count": len(exterior_walls),
            "exterior_wall_total_length": float(sum(item["length"] for item in exterior_walls)),
            "exterior_wall_mean_width": float(mean(widths)) if widths else None,
            "exterior_opening_count": len(exterior_openings),
            "exterior_opening_total_length": float(sum(item["length"] for item in exterior_openings)),
            "exterior_opening_mean_width": float(mean(opening_widths)) if opening_widths else None,
        }
        record.update({key: value for key, value in room.items() if key.startswith("centroid_") or key.startswith("bbox_")})
        canonical_rooms.append(record)

    grouped: Dict[Tuple[int, int, str], List[Dict[str, float]]] = {}
    for edge in edges:
        a, b = sorted((int(edge["roomA"]), int(edge["roomB"])))
        conn_type = str(edge.get("type", "")).lower()
        grouped.setdefault((a, b, conn_type), []).append({
            "length": float(edge.get("length", 0) or 0),
            "width": float(edge.get("width", 0) or 0),
        })
    canonical_edges: List[Dict[str, Any]] = []
    for (a, b, conn_type), segments in grouped.items():
        lengths = [item["length"] for item in segments]
        widths = [item["width"] for item in segments]
        canonical_edges.append({
            "roomA": a,
            "roomB": b,
            "connection_type": conn_type,
            "source_count": len(segments),
            "segments": segments,
            "segment_count": len(segments),
            "total_length": float(sum(lengths)),
            "mean_width": float(mean(widths)) if widths else None,
            "max_width": float(max(widths)) if widths else None,
            "min_width": float(min(widths)) if widths else None,
        })
    _write_json(output_dir / "room_table_canonical.json", canonical_rooms)
    _write_json(output_dir / "edge_table_canonical.json", canonical_edges)


def _resolve_correction_mode(
    correction_mode: Optional[str],
    repair_mode: str,
    room_fragment_correction: str,
) -> str:
    if correction_mode is not None:
        mode = str(correction_mode).lower()
        if mode not in CORRECTION_MODES:
            raise ValueError(f"Unsupported correction_mode: {correction_mode}")
        return mode
    # Backward-compatible translation for the pre-revision CLI/API.
    if str(repair_mode or "none").lower() == "conservative":
        return "fragment_plus_wall_plus_opening"
    if str(room_fragment_correction or "none").lower() == "interior_noise":
        return "fragment_only"
    return "baseline"


def run_topology(
    wall_svg_path: str,
    icon_svg_path: str,
    rough_img_path: str,
    output_dir: str,
    repair_mode: str = "none",
    room_fragment_correction: str = "none",
    correction_mode: Optional[str] = None,
    lightweight: bool = False,
) -> dict:
    """Run the Geo-ELCT topology translator and save Excel plus canonical debug artifacts."""
    from .detect_adjacency import detect_adjacency
    from .exterior_wall import exterior_wall_segments, exterior_opening_segments
    from .extract_rooms import extract_rooms, merge_spurious_room_fragments
    from .save_topology_image import (
        save_topology_image, save_to_excel, save_rooms_excel, compose_room_stats
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    repair_mode = str(repair_mode or "none").lower()
    room_fragment_correction = str(room_fragment_correction or "none").lower()
    correction_mode = _resolve_correction_mode(correction_mode, repair_mode, room_fragment_correction)
    do_fragment = correction_mode in {
        "fragment_only", "fragment_plus_wall", "fragment_plus_wall_plus_opening"
    }
    do_wall = correction_mode in {"fragment_plus_wall", "fragment_plus_wall_plus_opening"}
    do_opening = correction_mode == "fragment_plus_wall_plus_opening"
    active_modules = [
        name for name, active in (
            ("enclosed_room_fragment_correction", do_fragment),
            ("short_wall_gap_bridging", do_wall),
            ("wall_boundary_regularization", do_wall),
            ("opening_snapping_and_validation", do_opening),
        ) if active
    ]

    wall_label_img = Image.open(wall_svg_path).convert("P")
    wall_label_array = np.array(wall_label_img)
    wall_palette = wall_label_img.getpalette()

    icon_label_img = Image.open(icon_svg_path).convert("P")
    icon_label_array = np.array(icon_label_img)
    icon_palette = icon_label_img.getpalette()

    repair_summary: Dict[str, Any] = {
        "correction_mode": correction_mode,
        "active_modules": active_modules,
        "repair_mode": repair_mode,
        "room_fragment_correction": "interior_noise" if do_fragment else "none",
        "parameters": dict(_CONSERVATIVE_REPAIR_PARAMS) if correction_mode != "baseline" else {},
        "tiny_room_components_removed": 0,
        "tiny_room_pixels_reassigned": 0,
        "interior_noise_components": 0,
        "room_fragment_components_checked": 0,
        "room_fragment_small_components": 0,
        "room_fragment_components_merged": 0,
        "room_fragment_components_preserved": 0,
        "room_fragment_suspicious_components": 0,
        "room_fragment_pixels_reassigned": 0,
        "short_wall_gap_components_closed": 0,
        "short_wall_gap_pixels_filled": 0,
        "short_wall_gap_candidates_before": 0,
        "short_wall_gap_candidates_remaining_after": 0,
        "wall_one_pixel_holes_filled": 0,
        "wall_one_pixel_spurs_removed": 0,
        "opening_components_checked": 0,
        "opening_components_already_valid": 0,
        "opening_components_snapped": 0,
        "opening_components_removed_spurious": 0,
        "opening_components_rejected": 0,
        "opening_components_left_ambiguous": 0,
    }

    room_fragment_summary: Dict[str, Any] = {
        "room_fragment_correction": "interior_noise" if do_fragment else "none",
        "components_checked": 0,
        "small_components": 0,
        "interior_noise_components": 0,
        "components_merged": 0,
        "components_preserved": 0,
        "suspicious_components": 0,
        "pixels_reassigned": 0,
    }
    room_fragment_records: List[Dict[str, Any]] = []
    if do_fragment:
        wall_label_array, room_fragment_summary, room_fragment_records = merge_spurious_room_fragments(
            wall_label_array,
            icon_label_array,
        )
        repair_summary.update({
            "interior_noise_components": room_fragment_summary.get("interior_noise_components", 0),
            "room_fragment_components_checked": room_fragment_summary.get("components_checked", 0),
            "room_fragment_small_components": room_fragment_summary.get("small_components", 0),
            "room_fragment_components_merged": room_fragment_summary.get("components_merged", 0),
            "room_fragment_components_preserved": room_fragment_summary.get("components_preserved", 0),
            "room_fragment_suspicious_components": room_fragment_summary.get("suspicious_components", 0),
            "room_fragment_pixels_reassigned": room_fragment_summary.get("pixels_reassigned", 0),
        })
        _save_palette_array(wall_label_array, wall_palette, output_path / "wall_svg_room_fragment_corrected.png")
    _write_json(output_path / "room_fragment_correction_summary.json", room_fragment_summary)
    _write_json(output_path / "room_fragment_correction_records.json", room_fragment_records)

    if do_wall:
        wall_label_array, stats = _close_short_wall_gaps(wall_label_array, icon_label_array)
        repair_summary.update({key: repair_summary.get(key, 0) + value for key, value in stats.items()})
        wall_label_array, stats = _regularize_wall_boundary(wall_label_array, icon_label_array)
        repair_summary.update({key: repair_summary.get(key, 0) + value for key, value in stats.items()})

    region_id_map, rooms, min_len, wall_outside_width = extract_rooms(wall_label_array)

    if do_opening:
        icon_label_array, stats = _snap_opening_components(icon_label_array, region_id_map, wall_label_array)
        repair_summary.update(stats)
    if correction_mode != "baseline":
        _save_palette_array(wall_label_array, wall_palette, output_path / "wall_svg_corrected.png")
        _save_palette_array(icon_label_array, icon_palette, output_path / "icon_svg_corrected.png")
        _save_palette_array(wall_label_array, wall_palette, output_path / "wall_svg_repaired.png")
        _save_palette_array(icon_label_array, icon_palette, output_path / "icon_svg_repaired.png")
    _write_json(output_path / "repair_summary.json", repair_summary)

    wall_array = (wall_label_array == 2).astype(np.uint8)
    icon_array = np.zeros_like(icon_label_array, dtype=np.uint8)
    icon_array[icon_label_array == 1] = 2
    icon_array[icon_label_array == 2] = 1

    edges = detect_adjacency(
        region_id_map,
        wall_array,
        icon_array,
        wall_label_array,
        max_wall_thickness=min_len,
    )

    room_ext_stats = exterior_wall_segments(region_id_map, wall_label_array, wall_outside_width)
    room_opening_stats = exterior_opening_segments(
        region_id_map,
        wall_label_array,
        icon_label_array,
        wall_outside_width,
    )
    room_stats = compose_room_stats(room_ext_stats, room_opening_stats)

    img_save = output_path / "debug_topology_result.png"
    xlsx_save = output_path / "debug_topology_edges.xlsx"
    room_save = output_path / "debug_roomself.xlsx"

    if not lightweight:
        save_topology_image(
            region_id_map,
            rooms,
            edges,
            rough_img_path,
            str(img_save),
            edge_width_px=12,
            node_margin_px=3,
        )
        save_to_excel(edges, str(xlsx_save))
        save_rooms_excel(rooms, room_stats, str(room_save))

    np.save(output_path / "region_id_map.npy", region_id_map.astype(np.int32))
    rooms_with_geometry = _augment_rooms_with_geometry(rooms, region_id_map)
    _write_json(output_path / "rooms.json", rooms_with_geometry)
    _write_json(output_path / "edges.json", edges)
    _write_json(output_path / "room_stats.json", room_stats)
    _write_json(output_path / "rooms_raw.json", rooms_with_geometry)
    _write_json(output_path / "edges_raw.json", edges)

    _export_canonical_json_direct(output_path, rooms_with_geometry, edges, room_stats)
    if not lightweight:
        _export_canonical_tables(output_path)

    summary = _summarize_topology(rooms, edges, region_id_map, room_stats)
    summary.update({
        "wall_svg_path": str(wall_svg_path),
        "icon_svg_path": str(icon_svg_path),
        "rough_img_path": str(rough_img_path),
        "output_dir": str(output_path),
        "correction_mode": correction_mode,
        "active_correction_modules": active_modules,
        "lightweight_artifacts": bool(lightweight),
        "repair_mode": repair_mode,
        "room_fragment_correction": "interior_noise" if do_fragment else "none",
        "repair_summary": repair_summary,
        "room_fragment_correction_summary": room_fragment_summary,
    })
    _write_json(output_path / "topology_summary.json", summary)
    return summary


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Geo-ELCT topology extraction.")
    parser.add_argument("--wall", "--wall-svg", dest="wall", default="wall_svg.png", help="Path to wall_svg.png or wall_svg_perturbed.png.")
    parser.add_argument("--icon", "--icon-svg", dest="icon", default="icon_svg.png", help="Path to icon_svg.png or icon_svg_perturbed.png.")
    parser.add_argument("--rough", "--rough-img", dest="rough", default="svgImg_roughcast.png", help="Path to rough background image.")
    parser.add_argument("--out", "--output-dir", dest="out", default="debug_output", help="Directory for debug outputs.")
    parser.add_argument("--repair-mode", choices=["none", "conservative"], default="none", help="Optional conservative segmentation-map repair mode.")
    parser.add_argument("--room-fragment-correction", choices=["none", "interior_noise"], default="none", help="Optional conservative correction for tiny interior room-color islands.")
    parser.add_argument(
        "--correction-mode",
        choices=list(CORRECTION_MODES),
        default=None,
        help="Ablation mode. Recommended main mode: fragment_plus_wall_plus_opening.",
    )
    parser.add_argument("--lightweight", action="store_true", help="Skip debug PNG/XLSX files and write canonical JSON directly.")
    return parser


def main() -> None:
    args = _build_arg_parser().parse_args()
    summary = run_topology(
        wall_svg_path=args.wall,
        icon_svg_path=args.icon,
        rough_img_path=args.rough,
        output_dir=args.out,
        repair_mode=args.repair_mode,
        room_fragment_correction=args.room_fragment_correction,
        correction_mode=args.correction_mode,
        lightweight=args.lightweight,
    )
    print(json.dumps(_json_safe(summary), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
