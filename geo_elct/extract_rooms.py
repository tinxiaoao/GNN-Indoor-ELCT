from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np


ROOM_EXCLUDE_LABELS = {0, 1, 2, 8, 50}
ROOM_CATEGORY_TO_NAME = {
    3: "Kitchen",
    4: "Living Room",
    5: "Bedroom",
    6: "Bath",
    7: "Hallway",
    9: "Storage",
    10: "Garage",
}

DEFAULT_INTERIOR_NOISE_PARAMS = {
    "min_fragment_area_px": 160,
    "fragment_area_ratio": 0.002,
    "dominant_neighbor_fraction": 0.8,
    "touch_ring_radius_px": 1,
    "dominance_ring_radius_px": 2,
    "wall_code": 2,
    "opening_labels": [1, 2],
    "connectivity": 8,
}


def _component_coords(mask: np.ndarray, connectivity: int = 8) -> List[np.ndarray]:
    n_labels, label_map = cv2.connectedComponents(mask.astype(np.uint8), connectivity=connectivity)
    return [np.argwhere(label_map == label) for label in range(1, n_labels)]


def _room_labels(label_array: np.ndarray) -> List[int]:
    return sorted(int(v) for v in np.unique(label_array) if int(v) not in ROOM_EXCLUDE_LABELS)


def _component_areas(label_array: np.ndarray, connectivity: int = 8) -> List[int]:
    areas: List[int] = []
    for label in _room_labels(label_array):
        areas.extend(int(len(coords)) for coords in _component_coords(label_array == label, connectivity))
    return areas


def _component_mask(shape: Tuple[int, int], coords: np.ndarray) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    if len(coords):
        mask[coords[:, 0], coords[:, 1]] = 1
    return mask


def _ring_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return np.zeros_like(mask, dtype=bool)
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), np.uint8)
    dilated = cv2.dilate(mask.astype(np.uint8), kernel, iterations=1).astype(bool)
    return dilated & ~mask.astype(bool)


def _bbox(coords: np.ndarray) -> List[int]:
    return [
        int(coords[:, 0].min()),
        int(coords[:, 1].min()),
        int(coords[:, 0].max()),
        int(coords[:, 1].max()),
    ]


def _values_on_mask(array: np.ndarray, mask: np.ndarray) -> Counter:
    if mask.sum() == 0:
        return Counter()
    return Counter(int(v) for v in array[mask])


def _opening_touch_count(icon_array: Optional[np.ndarray], ring: np.ndarray, opening_labels: List[int]) -> int:
    if icon_array is None:
        return 0
    return int(np.isin(icon_array[ring], opening_labels).sum())


def merge_spurious_room_fragments(
    wall_array: np.ndarray,
    icon_array: Optional[np.ndarray] = None,
    *,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[np.ndarray, Dict[str, Any], List[Dict[str, Any]]]:
    """Merge tiny fully enclosed room-color islands into their dominant room.

    The rule is intentionally narrow: a component is merged only when it is
    small, does not touch walls/exterior/openings, and its dilated boundary is
    dominated by one surrounding room label. Ambiguous small components are
    preserved and reported.
    """
    cfg = dict(DEFAULT_INTERIOR_NOISE_PARAMS)
    if params:
        cfg.update(params)

    corrected = wall_array.copy()
    connectivity = int(cfg["connectivity"])
    wall_code = int(cfg["wall_code"])
    touch_radius = int(cfg["touch_ring_radius_px"])
    dominance_radius = int(cfg["dominance_ring_radius_px"])
    dominant_threshold = float(cfg["dominant_neighbor_fraction"])
    opening_labels = [int(v) for v in cfg["opening_labels"]]

    component_areas = _component_areas(corrected, connectivity)
    min_fragment_area = float(cfg["min_fragment_area_px"])
    plausible_room_areas = [area for area in component_areas if area > min_fragment_area]
    median_area = float(np.median(component_areas)) if component_areas else 0.0
    reference_area = (
        float(np.median(plausible_room_areas))
        if plausible_room_areas
        else median_area
    )
    relative_limit = float(cfg["fragment_area_ratio"]) * reference_area if reference_area > 0 else float("inf")
    effective_limit = min(min_fragment_area, relative_limit)

    summary: Dict[str, Any] = {
        "room_fragment_correction": "interior_noise",
        "parameters": cfg,
        "median_component_area_px": median_area,
        "reference_component_area_px": reference_area,
        "plausible_room_component_count": len(plausible_room_areas),
        "effective_fragment_area_threshold_px": effective_limit,
        "components_checked": 0,
        "small_components": 0,
        "interior_noise_components": 0,
        "components_merged": 0,
        "components_preserved": 0,
        "suspicious_components": 0,
        "touching_wall_components": 0,
        "touching_exterior_components": 0,
        "touching_opening_components": 0,
        "not_fully_enclosed_components": 0,
        "ambiguous_neighbor_components": 0,
        "large_components": 0,
        "pixels_reassigned": 0,
    }
    records: List[Dict[str, Any]] = []

    height, width = corrected.shape
    exterior_labels = set(ROOM_EXCLUDE_LABELS) - {wall_code}

    for label in _room_labels(wall_array):
        # Components are evaluated on the original input so one merge cannot
        # cause a neighboring component to be reconsidered in the same pass.
        for coords in _component_coords(wall_array == label, connectivity):
            if len(coords) == 0:
                continue
            area = int(len(coords))
            summary["components_checked"] += 1

            record: Dict[str, Any] = {
                "source_label": int(label),
                "area_px": area,
                "bbox_ymin_xmin_ymax_xmax": _bbox(coords),
            }
            if area > effective_limit:
                summary["large_components"] += 1
                summary["components_preserved"] += 1
                record.update({"action": "preserved", "reason": "component is above tiny-fragment threshold"})
                records.append(record)
                continue

            summary["small_components"] += 1
            comp_mask = _component_mask((height, width), coords).astype(bool)
            touch_ring = _ring_mask(comp_mask, touch_radius)
            dominance_ring = _ring_mask(comp_mask, dominance_radius)

            touch_counts = _values_on_mask(wall_array, touch_ring)
            wall_touch = touch_counts.get(wall_code, 0)
            exterior_touch = sum(touch_counts.get(v, 0) for v in exterior_labels)
            opening_touch = _opening_touch_count(icon_array, touch_ring, opening_labels)

            if wall_touch > 0:
                summary["touching_wall_components"] += 1
                summary["suspicious_components"] += 1
                summary["components_preserved"] += 1
                record.update({"action": "preserved", "reason": "tiny component touches wall pixels"})
                records.append(record)
                continue
            if exterior_touch > 0:
                summary["touching_exterior_components"] += 1
                summary["suspicious_components"] += 1
                summary["components_preserved"] += 1
                record.update({"action": "preserved", "reason": "tiny component touches exterior/background labels"})
                records.append(record)
                continue
            if opening_touch > 0:
                summary["touching_opening_components"] += 1
                summary["suspicious_components"] += 1
                summary["components_preserved"] += 1
                record.update({"action": "preserved", "reason": "tiny component touches a door/window/opening component"})
                records.append(record)
                continue

            # "Fully enclosed" is stricter than merely avoiding a wall: every
            # immediate room-valued neighbor must be the same host label.
            enclosing_labels = {
                int(v)
                for v in touch_counts
                if int(v) not in ROOM_EXCLUDE_LABELS and int(v) != int(label)
            }
            if len(enclosing_labels) != 1:
                summary["not_fully_enclosed_components"] += 1
                summary["suspicious_components"] += 1
                summary["components_preserved"] += 1
                record.update({
                    "action": "preserved",
                    "reason": "tiny component is not fully enclosed by exactly one host room",
                    "immediate_neighbor_room_labels": sorted(enclosing_labels),
                })
                records.append(record)
                continue

            dominance_counts = _values_on_mask(wall_array, dominance_ring)
            neighbor_counts = {
                int(v): int(c)
                for v, c in dominance_counts.items()
                if int(v) not in ROOM_EXCLUDE_LABELS and int(v) != int(label)
            }
            total_neighbor = sum(neighbor_counts.values())
            if total_neighbor <= 0:
                summary["ambiguous_neighbor_components"] += 1
                summary["suspicious_components"] += 1
                summary["components_preserved"] += 1
                record.update({"action": "preserved", "reason": "no dominant surrounding room label"})
                records.append(record)
                continue

            dominant_label, dominant_count = max(neighbor_counts.items(), key=lambda item: item[1])
            dominant_fraction = dominant_count / total_neighbor
            record.update({
                "dominant_neighbor_label": int(dominant_label),
                "dominant_neighbor_fraction": float(dominant_fraction),
                "neighbor_label_counts": neighbor_counts,
            })
            if dominant_fraction < dominant_threshold or dominant_label not in enclosing_labels:
                summary["ambiguous_neighbor_components"] += 1
                summary["suspicious_components"] += 1
                summary["components_preserved"] += 1
                record.update({"action": "preserved", "reason": "neighbor labels are not dominated by one room"})
                records.append(record)
                continue

            corrected[coords[:, 0], coords[:, 1]] = int(dominant_label)
            summary["interior_noise_components"] += 1
            summary["components_merged"] += 1
            summary["pixels_reassigned"] += area
            record.update({"action": "merged", "reason": "tiny fully interior fragment dominated by one room"})
            records.append(record)

    return corrected, summary, records


def extract_rooms(wall_array: np.ndarray):
    """
    Input:
        wall_array: palette-index room/wall map.
    Output:
        region_id_map: integer room-ID map, with 0 for non-room pixels.
        rooms: List[Dict] with id, area, perimeter, and room_type.
        min_avg_room_length: minimum perimeter-derived room scale.
        wall_outside_width: exterior wall scale used by downstream extraction.
    """
    unique_room_indices = np.unique(wall_array)
    room_indices = [idx for idx in unique_room_indices if int(idx) not in ROOM_EXCLUDE_LABELS]

    region_id_map = np.zeros_like(wall_array, dtype=np.int32)
    current_label = 1

    rooms = []
    min_avg_room_length = float("inf")
    wall_outside_width = float("inf")
    kernel = np.ones((3, 3), np.uint8)

    for room_idx in room_indices:
        mask = (wall_array == room_idx).astype(np.uint8)
        num_labels, labels = cv2.connectedComponents(mask, connectivity=8)

        for lbl in range(1, num_labels):
            region_mask = labels == lbl
            area = int(region_mask.sum())

            vals, counts = np.unique(wall_array[region_mask], return_counts=True)
            filtered = [(int(v), int(c)) for v, c in zip(vals, counts) if int(v) not in ROOM_EXCLUDE_LABELS]
            main_category = max(filtered, key=lambda x: x[1])[0] if filtered else None
            room_type = ROOM_CATEGORY_TO_NAME.get(main_category, "Other")

            boundary = cv2.morphologyEx(region_mask.astype(np.uint8), cv2.MORPH_GRADIENT, kernel)
            perimeter = int(boundary.sum())
            avg_len = perimeter / 10
            min_avg_room_length = min(min_avg_room_length, avg_len)
            wall_outside_width = perimeter / 10

            rooms.append({
                "id": current_label,
                "area": area,
                "perimeter": perimeter,
                "room_type": room_type,
            })

            region_id_map[region_mask] = current_label
            current_label += 1

    if min_avg_room_length == float("inf"):
        min_avg_room_length = 0.0
        wall_outside_width = 0.0

    return region_id_map, rooms, float(min_avg_room_length), float(wall_outside_width)
