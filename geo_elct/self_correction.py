"""Reference-free preprocessing for recoverable semantic-map artifacts.

The correction API deliberately accepts only the perturbed wall/opening maps,
an output directory, and an ablation mode.  It has no clean-reference,
perturbation-level, random-seed, or manifest input.
"""

from __future__ import annotations

import json
from collections import Counter, deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import cv2
import numpy as np
from PIL import Image

from .extract_rooms import ROOM_EXCLUDE_LABELS, extract_rooms, merge_spurious_room_fragments


CORRECTION_MODES = (
    "baseline",
    "fragment_only",
    "fragment_plus_wall",
    "fragment_plus_wall_plus_opening",
)

# One fixed configuration is used for every level and seed.
REFERENCE_FREE_CONFIG: Dict[str, Any] = {
    "wall_code": 2,
    "opening_labels": [1, 2],
    "fragment": {
        "min_fragment_area_px": 160,
        "fragment_area_ratio": 0.002,
        "dominant_neighbor_fraction": 0.80,
        "touch_ring_radius_px": 1,
        "dominance_ring_radius_px": 2,
        "connectivity": 8,
    },
    "wall_gap": {
        "max_length_px": 6,
        "max_area_px": 512,
        "min_endpoint_alignment_fraction": 0.90,
        "max_endpoint_thickness_difference_px": 2,
        "support_extension_px": 6,
        "min_support_fraction": 0.95,
        "opening_clearance_px": 1,
        "min_room_side_dominance": 0.90,
    },
    "wall_boundary": {
        "max_bulge_span_px": 20,
        "support_extension_px": 6,
        "body_depth_px": 3,
        "min_body_fraction": 0.98,
        "min_host_fraction": 0.95,
    },
    "opening": {
        "snap_max_distance_px": 3,
        "min_wall_overlap_fraction": 0.995,
        "partial_gap_max_length_px": 4,
        "min_component_fill_fraction": 0.75,
        "spurious_component_area_px": 8,
        "domain_search_radius_px": 2,
    },
    "validation": {
        "max_wall_thickness_px": 64,
        "tiny_room_area_px": 160,
    },
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def write_json(path: str | Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(_json_safe(payload), handle, ensure_ascii=False, indent=2)


def load_palette_map(path: str | Path) -> Tuple[np.ndarray, Optional[List[int]]]:
    with Image.open(path) as image:
        palette_image = image.convert("P")
        return np.asarray(palette_image, dtype=np.uint8).copy(), palette_image.getpalette()


def save_palette_map(array: np.ndarray, palette: Optional[List[int]], path: str | Path) -> None:
    image = Image.fromarray(array.astype(np.uint8), mode="P")
    if palette is not None:
        image.putpalette(palette)
    image.save(path)


def _components(mask: np.ndarray, connectivity: int = 8) -> List[np.ndarray]:
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=connectivity)
    return [np.argwhere(labels == label) for label in range(1, count)]


def _bbox(coords: np.ndarray) -> Tuple[int, int, int, int]:
    return (
        int(coords[:, 0].min()),
        int(coords[:, 1].min()),
        int(coords[:, 0].max()),
        int(coords[:, 1].max()),
    )


def _room_values(values: np.ndarray) -> List[int]:
    return [int(value) for value in values.ravel() if int(value) not in ROOM_EXCLUDE_LABELS]


def _dominant_room(values: np.ndarray) -> Tuple[Optional[int], float, Dict[int, int]]:
    counts = Counter(_room_values(values))
    if not counts:
        return None, 0.0, {}
    label, count = counts.most_common(1)[0]
    total = sum(counts.values())
    return int(label), float(count / total), {int(key): int(value) for key, value in counts.items()}


def repair_enclosed_fragments(
    wall_array: np.ndarray,
    icon_array: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, Any], List[Dict[str, Any]]]:
    cfg = dict(REFERENCE_FREE_CONFIG["fragment"])
    cfg.update({
        "wall_code": REFERENCE_FREE_CONFIG["wall_code"],
        "opening_labels": list(REFERENCE_FREE_CONFIG["opening_labels"]),
    })
    return merge_spurious_room_fragments(wall_array, icon_array, params=cfg)


def _endpoint_alignment(wall: np.ndarray, coords: np.ndarray, orientation: str) -> Tuple[float, int, int]:
    y0, x0, y1, x1 = _bbox(coords)
    if orientation == "horizontal" and x0 > 0 and x1 + 1 < wall.shape[1]:
        left = wall[y0:y1 + 1, x0 - 1]
        right = wall[y0:y1 + 1, x1 + 1]
    elif orientation == "vertical" and y0 > 0 and y1 + 1 < wall.shape[0]:
        left = wall[y0 - 1, x0:x1 + 1]
        right = wall[y1 + 1, x0:x1 + 1]
    else:
        return 0.0, 0, 0
    aligned = float(np.logical_and(left, right).mean()) if left.size else 0.0
    return aligned, int(left.sum()), int(right.sum())


def _wall_support_fraction(
    wall: np.ndarray,
    coords: np.ndarray,
    orientation: str,
    extension: int,
) -> float:
    y0, x0, y1, x1 = _bbox(coords)
    if orientation == "horizontal":
        if x0 < extension or x1 + extension >= wall.shape[1]:
            return 0.0
        left = wall[y0:y1 + 1, x0 - extension:x0]
        right = wall[y0:y1 + 1, x1 + 1:x1 + 1 + extension]
    else:
        if y0 < extension or y1 + extension >= wall.shape[0]:
            return 0.0
        left = wall[y0 - extension:y0, x0:x1 + 1]
        right = wall[y1 + 1:y1 + 1 + extension, x0:x1 + 1]
    if left.size == 0 or right.size == 0:
        return 0.0
    return float(min(left.mean(), right.mean()))


def _wall_support_fractions(
    wall: np.ndarray,
    coords: np.ndarray,
    orientation: str,
    extension: int,
) -> Tuple[float, float]:
    """Return independent support fractions at the two longitudinal ends."""
    y0, x0, y1, x1 = _bbox(coords)
    if orientation == "horizontal":
        if x0 < extension or x1 + extension >= wall.shape[1]:
            return 0.0, 0.0
        first = wall[y0:y1 + 1, x0 - extension:x0]
        second = wall[y0:y1 + 1, x1 + 1:x1 + 1 + extension]
    else:
        if y0 < extension or y1 + extension >= wall.shape[0]:
            return 0.0, 0.0
        first = wall[y0 - extension:y0, x0:x1 + 1]
        second = wall[y1 + 1:y1 + 1 + extension, x0:x1 + 1]
    return (
        float(first.mean()) if first.size else 0.0,
        float(second.mean()) if second.size else 0.0,
    )


def _expand_terminal_gap_candidate(
    wall_array: np.ndarray,
    wall: np.ndarray,
    coords: np.ndarray,
    orientation: str,
    max_gap: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    """Expand a one-sided morphology seed across a short, room-bounded void.

    An even-sized closing kernel can expose only the first pixel of a retracted
    wall endpoint.  The entire missing rectangle is nevertheless inferable when
    the void is short, has the stable wall cross-section, and terminates at one
    dominant non-wall room label.
    """
    y0, x0, y1, x1 = _bbox(coords)
    _, thickness_a, thickness_b = _endpoint_alignment(wall, coords, orientation)
    if (thickness_a > 0) == (thickness_b > 0):
        return coords, {"is_terminal_candidate": False}
    boundary = np.asarray([], dtype=wall_array.dtype)

    if orientation == "horizontal":
        direction = 1 if thickness_a > 0 else -1
        start = x0 if direction > 0 else x1
        positions: List[int] = []
        for offset in range(max_gap):
            position = start + direction * offset
            if position < 0 or position >= wall.shape[1]:
                break
            cross_section = wall_array[y0:y1 + 1, position]
            if np.all(cross_section == 0):
                positions.append(position)
                continue
            boundary = cross_section
            break
        else:
            boundary = np.asarray([], dtype=wall_array.dtype)
        if not positions:
            return coords, {"is_terminal_candidate": False}
        axis_min, axis_max = min(positions), max(positions)
        yy, xx = np.mgrid[y0:y1 + 1, axis_min:axis_max + 1]
    else:
        direction = 1 if thickness_a > 0 else -1
        start = y0 if direction > 0 else y1
        positions = []
        for offset in range(max_gap):
            position = start + direction * offset
            if position < 0 or position >= wall.shape[0]:
                break
            cross_section = wall_array[position, x0:x1 + 1]
            if np.all(cross_section == 0):
                positions.append(position)
                continue
            boundary = cross_section
            break
        else:
            boundary = np.asarray([], dtype=wall_array.dtype)
        if not positions:
            return coords, {"is_terminal_candidate": False}
        axis_min, axis_max = min(positions), max(positions)
        yy, xx = np.mgrid[axis_min:axis_max + 1, x0:x1 + 1]

    boundary_label, boundary_fraction, _ = _dominant_room(boundary)
    boundary_is_room = bool(
        boundary.size
        and boundary_label is not None
        and boundary_fraction >= 0.90
        and np.all(boundary != 0)
        and np.all(boundary != int(REFERENCE_FREE_CONFIG["wall_code"]))
    )
    expanded = np.column_stack((yy.ravel(), xx.ravel())).astype(np.int32)
    return expanded, {
        "is_terminal_candidate": True,
        "supported_end": "first" if thickness_a > 0 else "second",
        "terminal_boundary_label": boundary_label,
        "terminal_boundary_fraction": boundary_fraction,
        "terminal_boundary_is_room": boundary_is_room,
    }


def _wall_side_rooms(
    wall_array: np.ndarray,
    coords: np.ndarray,
    orientation: str,
    search_px: int = 4,
) -> Tuple[Tuple[Optional[int], float], Tuple[Optional[int], float]]:
    y0, x0, y1, x1 = _bbox(coords)
    if orientation == "horizontal":
        first = wall_array[max(0, y0 - search_px):y0, x0:x1 + 1]
        second = wall_array[y1 + 1:min(wall_array.shape[0], y1 + 1 + search_px), x0:x1 + 1]
    else:
        first = wall_array[y0:y1 + 1, max(0, x0 - search_px):x0]
        second = wall_array[y0:y1 + 1, x1 + 1:min(wall_array.shape[1], x1 + 1 + search_px)]
    label_a, frac_a, _ = _dominant_room(first)
    label_b, frac_b, _ = _dominant_room(second)
    return (label_a, frac_a), (label_b, frac_b)


def _dominant_positive_region(values: np.ndarray) -> Tuple[Optional[int], float]:
    """Return the dominant connected-room ID, treating zero as non-room."""
    counts = Counter(int(value) for value in values.ravel() if int(value) > 0)
    if not counts:
        return None, 0.0
    region_id, count = counts.most_common(1)[0]
    return int(region_id), float(count / sum(counts.values()))


def _wall_side_region_ids(
    region_id_map: np.ndarray,
    coords: np.ndarray,
    orientation: str,
    search_px: int = 4,
) -> Tuple[Tuple[Optional[int], float], Tuple[Optional[int], float]]:
    """Sample connected rooms on both sides of a candidate using only the input map.

    Palette room labels are semantic classes rather than room instances: two rooms
    separated by a wall can legitimately share the same label.  Connected-component
    IDs from the perturbed map distinguish those instances without a clean reference.
    """
    y0, x0, y1, x1 = _bbox(coords)
    if orientation == "horizontal":
        first = region_id_map[max(0, y0 - search_px):y0, x0:x1 + 1]
        second = region_id_map[
            y1 + 1:min(region_id_map.shape[0], y1 + 1 + search_px), x0:x1 + 1
        ]
    else:
        first = region_id_map[y0:y1 + 1, max(0, x0 - search_px):x0]
        second = region_id_map[
            y0:y1 + 1, x1 + 1:min(region_id_map.shape[1], x1 + 1 + search_px)
        ]
    return _dominant_positive_region(first), _dominant_positive_region(second)


def _opening_near(icon_array: np.ndarray, coords: np.ndarray, clearance: int) -> bool:
    y0, x0, y1, x1 = _bbox(coords)
    return bool(np.any(icon_array[
        max(0, y0 - clearance):min(icon_array.shape[0], y1 + clearance + 1),
        max(0, x0 - clearance):min(icon_array.shape[1], x1 + clearance + 1),
    ] != 0))


def reconstruct_short_wall_gaps(
    wall_array: np.ndarray,
    icon_array: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, Any], List[Dict[str, Any]]]:
    cfg = REFERENCE_FREE_CONFIG["wall_gap"]
    wall_code = int(REFERENCE_FREE_CONFIG["wall_code"])
    repaired = wall_array.copy()
    wall = repaired == wall_code
    region_id_map, _, _, _ = extract_rooms(repaired)
    max_gap = int(cfg["max_length_px"])
    candidates = {
        "horizontal": cv2.morphologyEx(
            wall.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((1, max_gap + 2), np.uint8)
        ).astype(bool) & ~wall & (repaired == 0),
        "vertical": cv2.morphologyEx(
            wall.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((max_gap + 2, 1), np.uint8)
        ).astype(bool) & ~wall & (repaired == 0),
    }
    records: List[Dict[str, Any]] = []
    accepted = np.zeros(wall.shape, dtype=bool)
    seen: Set[Tuple[int, int, int, int]] = set()

    for orientation, mask in candidates.items():
        for coords in _components(mask, connectivity=8):
            if len(coords) == 0:
                continue
            coords, terminal = _expand_terminal_gap_candidate(
                repaired, wall, coords, orientation, max_gap
            )
            box = _bbox(coords)
            if box in seen:
                continue
            seen.add(box)
            y0, x0, y1, x1 = box
            gap_length = x1 - x0 + 1 if orientation == "horizontal" else y1 - y0 + 1
            cross_thickness = y1 - y0 + 1 if orientation == "horizontal" else x1 - x0 + 1
            alignment, thickness_a, thickness_b = _endpoint_alignment(wall, coords, orientation)
            support = _wall_support_fraction(
                wall, coords, orientation, int(cfg["support_extension_px"])
            )
            support_a, support_b = _wall_support_fractions(
                wall, coords, orientation, int(cfg["support_extension_px"])
            )
            side_label_a, side_label_b = _wall_side_rooms(repaired, coords, orientation)
            side_a, side_b = _wall_side_region_ids(region_id_map, coords, orientation)
            opening_near = _opening_near(icon_array, coords, int(cfg["opening_clearance_px"]))
            reasons: List[str] = []
            if gap_length > int(cfg["max_length_px"]) or len(coords) > int(cfg["max_area_px"]):
                reasons.append("gap exceeds fixed local size limit")
            if terminal.get("is_terminal_candidate"):
                if max(thickness_a, thickness_b) < max(1, cross_thickness - 1):
                    reasons.append("terminal candidate lacks a full-thickness wall endpoint")
                if max(support_a, support_b) < float(cfg["min_support_fraction"]):
                    reasons.append("terminal candidate lacks a stable one-sided wall run")
                if not terminal.get("terminal_boundary_is_room"):
                    reasons.append("short endpoint void is not bounded by one dominant room")
            else:
                if alignment < float(cfg["min_endpoint_alignment_fraction"]):
                    reasons.append("wall endpoints are not sufficiently aligned")
                if abs(thickness_a - thickness_b) > int(cfg["max_endpoint_thickness_difference_px"]):
                    reasons.append("endpoint wall thicknesses are incompatible")
                if min(thickness_a, thickness_b) < max(1, cross_thickness - 1):
                    reasons.append("candidate cross-section is not supported by both endpoints")
                if support < float(cfg["min_support_fraction"]):
                    reasons.append("adjacent stable wall runs are insufficient")
            if opening_near:
                reasons.append("valid opening pixels occupy or border the candidate gap")
            if (
                side_a[0] is None
                or side_b[0] is None
                or side_a[0] == side_b[0]
                or side_a[1] < float(cfg["min_room_side_dominance"])
                or side_b[1] < float(cfg["min_room_side_dominance"])
            ):
                reasons.append("cross-wall room support is not two distinct dominant rooms")
            accepted_candidate = not reasons
            if accepted_candidate:
                accepted[coords[:, 0], coords[:, 1]] = True
            records.append({
                "mechanism": "short_wall_gap_reconstruction",
                "bbox_ymin_xmin_ymax_xmax": list(box),
                "orientation": orientation,
                "candidate_kind": (
                    "terminal_retraction" if terminal.get("is_terminal_candidate")
                    else "two_sided_bridge"
                ),
                "gap_length_px": int(gap_length),
                "estimated_thickness_px": int(round((thickness_a + thickness_b) / 2)),
                "endpoint_thickness_px": [int(thickness_a), int(thickness_b)],
                "endpoint_alignment_fraction": alignment,
                "stable_wall_support_fraction": support,
                "endpoint_support_fractions": [support_a, support_b],
                "terminal_boundary_label": terminal.get("terminal_boundary_label"),
                "terminal_boundary_fraction": terminal.get("terminal_boundary_fraction"),
                "side_room_labels": [side_label_a[0], side_label_b[0]],
                "side_connected_room_ids": [side_a[0], side_b[0]],
                "side_connected_room_dominance": [side_a[1], side_b[1]],
                "pixels_reconstructed": int(len(coords)) if accepted_candidate else 0,
                "accepted": accepted_candidate,
                "validation_result": "accepted" if accepted_candidate else "; ".join(reasons),
            })

    repaired[accepted] = wall_code
    summary = {
        "candidates_checked": len(records),
        "components_reconstructed": sum(bool(record["accepted"]) for record in records),
        "pixels_reconstructed": int(accepted.sum()),
        "components_rejected": sum(not bool(record["accepted"]) for record in records),
    }
    return repaired, summary, records


def _runs(mask: np.ndarray) -> Iterable[Tuple[int, int]]:
    indices = np.flatnonzero(mask)
    if indices.size == 0:
        return
    start = previous = int(indices[0])
    for value in indices[1:]:
        value = int(value)
        if value != previous + 1:
            yield start, previous
            start = value
        previous = value
    yield start, previous


def regularize_wall_boundaries(
    wall_array: np.ndarray,
    icon_array: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, Any], List[Dict[str, Any]]]:
    """Remove short one-pixel wall bulges supported by a stable straight wall."""
    cfg = REFERENCE_FREE_CONFIG["wall_boundary"]
    wall_code = int(REFERENCE_FREE_CONFIG["wall_code"])
    wall = wall_array == wall_code
    height, width = wall.shape
    candidates: List[Dict[str, Any]] = []

    directions = (
        ("horizontal", "top", -1, 0),
        ("horizontal", "bottom", 1, 0),
        ("vertical", "left", 0, -1),
        ("vertical", "right", 0, 1),
    )
    for orientation, side, outward_y, outward_x in directions:
        if orientation == "horizontal":
            for y in range(1, height - 1):
                inward_y = y - outward_y
                boundary = wall[y] & wall[inward_y] & ~wall[y + outward_y]
                for x0, x1 in _runs(boundary):
                    span = x1 - x0 + 1
                    candidates.append({"orientation": orientation, "side": side, "y0": y, "y1": y, "x0": x0, "x1": x1, "span": span, "outward_y": outward_y, "outward_x": 0})
        else:
            for x in range(1, width - 1):
                inward_x = x - outward_x
                boundary = wall[:, x] & wall[:, inward_x] & ~wall[:, x + outward_x]
                for y0, y1 in _runs(boundary):
                    span = y1 - y0 + 1
                    candidates.append({"orientation": orientation, "side": side, "y0": y0, "y1": y1, "x0": x, "x1": x, "span": span, "outward_y": 0, "outward_x": outward_x})

    records: List[Dict[str, Any]] = []
    remove_mask = np.zeros(wall.shape, dtype=bool)
    replacement_labels = np.zeros(wall.shape, dtype=np.uint8)
    extension = int(cfg["support_extension_px"])
    depth = int(cfg["body_depth_px"])
    max_span = int(cfg["max_bulge_span_px"])

    for candidate in candidates:
        y0, x0, y1, x1 = (candidate[key] for key in ("y0", "x0", "y1", "x1"))
        span = int(candidate["span"])
        if span > max_span:
            continue
        orientation = str(candidate["orientation"])
        outward_y = int(candidate["outward_y"])
        outward_x = int(candidate["outward_x"])
        reasons: List[str] = []
        if orientation == "horizontal":
            if x0 < extension or x1 + extension >= width:
                continue
            inward_y = y0 - outward_y
            body_rows = [inward_y - outward_y * offset for offset in range(depth)]
            if any(row < 0 or row >= height for row in body_rows):
                continue
            body = wall[np.asarray(body_rows)[:, None], np.arange(x0, x1 + 1)[None, :]]
            continuation = wall[inward_y, x0 - extension:x0].mean() if extension else 1.0
            continuation = min(continuation, wall[inward_y, x1 + 1:x1 + 1 + extension].mean())
            endpoint_clear = not wall[y0, x0 - 1] and not wall[y0, x1 + 1]
            outside_y = y0 + outward_y
            host_values = np.concatenate((
                wall_array[outside_y, x0:x1 + 1].ravel(),
                wall_array[y0, x0 - 1:x0].ravel(),
                wall_array[y0, x1 + 1:x1 + 2].ravel(),
            ))
            coords = np.column_stack((np.full(span, y0, dtype=np.int32), np.arange(x0, x1 + 1, dtype=np.int32)))
        else:
            if y0 < extension or y1 + extension >= height:
                continue
            inward_x = x0 - outward_x
            body_cols = [inward_x - outward_x * offset for offset in range(depth)]
            if any(col < 0 or col >= width for col in body_cols):
                continue
            body = wall[np.arange(y0, y1 + 1)[:, None], np.asarray(body_cols)[None, :]]
            continuation = wall[y0 - extension:y0, inward_x].mean() if extension else 1.0
            continuation = min(continuation, wall[y1 + 1:y1 + 1 + extension, inward_x].mean())
            endpoint_clear = not wall[y0 - 1, x0] and not wall[y1 + 1, x0]
            outside_x = x0 + outward_x
            host_values = np.concatenate((
                wall_array[y0:y1 + 1, outside_x].ravel(),
                wall_array[y0 - 1:y0, x0].ravel(),
                wall_array[y1 + 1:y1 + 2, x0].ravel(),
            ))
            coords = np.column_stack((np.arange(y0, y1 + 1, dtype=np.int32), np.full(span, x0, dtype=np.int32)))

        body_fraction = float(body.mean()) if body.size else 0.0
        host_label, host_fraction, host_counts = _dominant_room(host_values)
        if body_fraction < float(cfg["min_body_fraction"]):
            reasons.append("insufficient inward wall body")
        if continuation < float(cfg["min_body_fraction"]):
            reasons.append("stable wall does not continue beyond both bulge ends")
        if not endpoint_clear:
            reasons.append("candidate is part of a longer boundary rather than a local bulge")
        if host_label is None or host_fraction < float(cfg["min_host_fraction"]):
            reasons.append("outside side does not identify one dominant room label")
        if np.any(icon_array[coords[:, 0], coords[:, 1]] != 0):
            reasons.append("candidate overlaps an opening component")
        accepted = not reasons
        if accepted:
            remove_mask[coords[:, 0], coords[:, 1]] = True
            replacement_labels[coords[:, 0], coords[:, 1]] = int(host_label)
        records.append({
            "mechanism": "wall_boundary_regularization",
            "bbox_ymin_xmin_ymax_xmax": [int(y0), int(x0), int(y1), int(x1)],
            "orientation": orientation,
            "side": candidate["side"],
            "span_length_px": span,
            "dominant_host_label": host_label,
            "host_fraction": host_fraction,
            "host_label_counts": host_counts,
            "body_support_fraction": body_fraction,
            "continuation_fraction": float(continuation),
            "pixels_removed": span if accepted else 0,
            "accepted": accepted,
            "validation_result": "accepted" if accepted else "; ".join(reasons),
        })

    repaired = wall_array.copy()
    repaired[remove_mask] = replacement_labels[remove_mask]

    # Exact one-pixel holes are safe to fill when every orthogonal neighbor is wall.
    current_wall = repaired == wall_code
    padded = np.pad(current_wall, 1, mode="constant")
    orthogonal = (
        padded[:-2, 1:-1].astype(np.uint8)
        + padded[2:, 1:-1].astype(np.uint8)
        + padded[1:-1, :-2].astype(np.uint8)
        + padded[1:-1, 2:].astype(np.uint8)
    )
    holes = (repaired == 0) & (orthogonal == 4) & (icon_array == 0)
    repaired[holes] = wall_code
    summary = {
        "candidates_checked": len(records),
        "bulges_removed": sum(bool(record["accepted"]) for record in records),
        "bulge_pixels_removed": int(remove_mask.sum()),
        "one_pixel_holes_filled": int(holes.sum()),
    }
    return repaired, summary, records


def _domain_signature(
    region_map: np.ndarray,
    wall_array: np.ndarray,
    coords: np.ndarray,
    radius: int,
) -> Tuple[str, ...]:
    rooms: Set[int] = set()
    outside = False
    height, width = region_map.shape
    for y, x in coords:
        y0, y1 = max(0, int(y) - radius), min(height, int(y) + radius + 1)
        x0, x1 = max(0, int(x) - radius), min(width, int(x) + radius + 1)
        rooms.update(int(value) for value in region_map[y0:y1, x0:x1].ravel() if int(value) > 0)
        if np.isin(wall_array[y0:y1, x0:x1], [0, 1, 8, 50]).any():
            outside = True
    signature = [f"room:{room}" for room in sorted(rooms)]
    if outside:
        signature.append("outside")
    return tuple(signature)


def _component_record(coords: np.ndarray) -> Dict[str, Any]:
    y0, x0, y1, x1 = _bbox(coords)
    height = y1 - y0 + 1
    width = x1 - x0 + 1
    return {
        "coords": coords,
        "bbox": (y0, x0, y1, x1),
        "height": height,
        "width": width,
        "orientation": "horizontal" if width >= height else "vertical",
        "area": int(len(coords)),
        "fill_fraction": float(len(coords) / (height * width)),
    }


def _complete_split_openings(
    icon_array: np.ndarray,
    wall_array: np.ndarray,
    region_map: np.ndarray,
    label: int,
) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    cfg = REFERENCE_FREE_CONFIG["opening"]
    repaired = icon_array.copy()
    records: List[Dict[str, Any]] = []
    radius = int(cfg["domain_search_radius_px"])
    components = [_component_record(coords) for coords in _components(repaired == label, connectivity=8)]
    components.sort(key=lambda item: item["bbox"])

    for first_index, first in enumerate(components):
        for second in components[first_index + 1:]:
            if first["orientation"] != second["orientation"]:
                continue
            y0a, x0a, y1a, x1a = first["bbox"]
            y0b, x0b, y1b, x1b = second["bbox"]
            if first["orientation"] == "horizontal":
                if (y0a, y1a) != (y0b, y1b):
                    continue
                left, right = (first, second) if x0a <= x0b else (second, first)
                ly0, lx0, ly1, lx1 = left["bbox"]
                ry0, rx0, ry1, rx1 = right["bbox"]
                gap = rx0 - lx1 - 1
                if not 1 <= gap <= int(cfg["partial_gap_max_length_px"]):
                    continue
                fill_coords = np.argwhere(np.ones((ly1 - ly0 + 1, gap), dtype=bool))
                fill_coords[:, 0] += ly0
                fill_coords[:, 1] += lx1 + 1
            else:
                if (x0a, x1a) != (x0b, x1b):
                    continue
                top, bottom = (first, second) if y0a <= y0b else (second, first)
                ty0, tx0, ty1, tx1 = top["bbox"]
                by0, bx0, by1, bx1 = bottom["bbox"]
                gap = by0 - ty1 - 1
                if not 1 <= gap <= int(cfg["partial_gap_max_length_px"]):
                    continue
                fill_coords = np.argwhere(np.ones((gap, tx1 - tx0 + 1), dtype=bool))
                fill_coords[:, 0] += ty1 + 1
                fill_coords[:, 1] += tx0
            signature_a = _domain_signature(region_map, wall_array, first["coords"], radius)
            signature_b = _domain_signature(region_map, wall_array, second["coords"], radius)
            all_wall = bool(np.all(wall_array[fill_coords[:, 0], fill_coords[:, 1]] == REFERENCE_FREE_CONFIG["wall_code"]))
            empty = bool(np.all(repaired[fill_coords[:, 0], fill_coords[:, 1]] == 0))
            accepted = signature_a == signature_b and len(signature_a) == 2 and all_wall and empty
            if accepted:
                repaired[fill_coords[:, 0], fill_coords[:, 1]] = label
            records.append({
                "mechanism": "opening_partial_delete_completion",
                "opening_label": int(label),
                "first_bbox": list(first["bbox"]),
                "second_bbox": list(second["bbox"]),
                "gap_length_px": int(gap),
                "domain_signature": list(signature_a),
                "pixels_completed": int(len(fill_coords)) if accepted else 0,
                "accepted": accepted,
                "validation_result": "accepted" if accepted else "component alignment, host domain, or wall support was ambiguous",
            })
            if accepted:
                return repaired, records
    return repaired, records


def repair_opening_components(
    icon_array: np.ndarray,
    wall_array: np.ndarray,
) -> Tuple[np.ndarray, Dict[str, Any], List[Dict[str, Any]]]:
    cfg = REFERENCE_FREE_CONFIG["opening"]
    repaired = icon_array.copy()
    region_map, _, _, _ = extract_rooms(wall_array)
    records: List[Dict[str, Any]] = []

    # Reconnect small full-thickness internal deletions. Repeat because each
    # accepted completion changes the component list.
    for label in REFERENCE_FREE_CONFIG["opening_labels"]:
        for _ in range(8):
            before = repaired.copy()
            repaired, completion_records = _complete_split_openings(repaired, wall_array, region_map, int(label))
            records.extend(completion_records)
            if np.array_equal(before, repaired):
                break

    original_after_completion = repaired.copy()
    height, width = repaired.shape
    max_distance = int(cfg["snap_max_distance_px"])
    shifts = [(dy, dx) for dy in range(-max_distance, max_distance + 1) for dx in range(-max_distance, max_distance + 1) if dy * dy + dx * dx <= max_distance * max_distance]
    shifts.sort(key=lambda item: (abs(item[0]) + abs(item[1]), item[0] * item[0] + item[1] * item[1], item))
    radius = int(cfg["domain_search_radius_px"])

    for label in REFERENCE_FREE_CONFIG["opening_labels"]:
        for coords in _components(original_after_completion == int(label), connectivity=8):
            component = _component_record(coords)
            current_overlap = float((wall_array[coords[:, 0], coords[:, 1]] == REFERENCE_FREE_CONFIG["wall_code"]).mean())
            current_domain = _domain_signature(region_map, wall_array, coords, radius)
            if component["area"] <= int(cfg["spurious_component_area_px"]) and (current_overlap == 0 or len(current_domain) != 2):
                repaired[coords[:, 0], coords[:, 1]] = 0
                records.append({
                    "mechanism": "opening_snapping_and_validation",
                    "opening_label": int(label),
                    "bbox_before": list(component["bbox"]),
                    "action": "removed_spurious",
                    "accepted": True,
                    "pixels_modified": int(len(coords)),
                })
                continue
            if current_overlap >= float(cfg["min_wall_overlap_fraction"]) and len(current_domain) == 2:
                records.append({
                    "mechanism": "opening_snapping_and_validation",
                    "opening_label": int(label),
                    "bbox_before": list(component["bbox"]),
                    "action": "already_valid",
                    "accepted": True,
                    "pixels_modified": 0,
                    "domain_signature": list(current_domain),
                })
                continue

            candidates: List[Tuple[float, int, int, int, np.ndarray, Tuple[str, ...]]] = []
            for dy, dx in shifts:
                shifted = coords + np.asarray([dy, dx], dtype=np.int32)
                if shifted[:, 0].min() < 0 or shifted[:, 1].min() < 0 or shifted[:, 0].max() >= height or shifted[:, 1].max() >= width:
                    continue
                occupied = repaired[shifted[:, 0], shifted[:, 1]]
                if np.any((occupied != 0) & (occupied != int(label))):
                    continue
                overlap = float((wall_array[shifted[:, 0], shifted[:, 1]] == REFERENCE_FREE_CONFIG["wall_code"]).mean())
                if overlap < float(cfg["min_wall_overlap_fraction"]):
                    continue
                domain = _domain_signature(region_map, wall_array, shifted, radius)
                if len(domain) != 2:
                    continue
                distance = abs(dy) + abs(dx)
                candidates.append((overlap, -distance, int(dy), int(dx), shifted, domain))

            if not candidates:
                repaired[coords[:, 0], coords[:, 1]] = 0
                records.append({
                    "mechanism": "opening_snapping_and_validation",
                    "opening_label": int(label),
                    "bbox_before": list(component["bbox"]),
                    "action": "rejected_unsnappable",
                    "accepted": False,
                    "pixels_modified": int(len(coords)),
                    "validation_result": "no small shift reached one unambiguous two-domain host wall",
                })
                continue
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            best = candidates[0]
            tied = [candidate for candidate in candidates if candidate[0] == best[0] and candidate[1] == best[1]]
            if len(tied) != 1:
                repaired[coords[:, 0], coords[:, 1]] = 0
                records.append({
                    "mechanism": "opening_snapping_and_validation",
                    "opening_label": int(label),
                    "bbox_before": list(component["bbox"]),
                    "action": "rejected_ambiguous",
                    "accepted": False,
                    "pixels_modified": int(len(coords)),
                    "validation_result": f"{len(tied)} equally plausible host-wall positions",
                })
                continue
            _, _, dy, dx, shifted, domain = best
            repaired[coords[:, 0], coords[:, 1]] = 0
            repaired[shifted[:, 0], shifted[:, 1]] = int(label)
            records.append({
                "mechanism": "opening_snapping_and_validation",
                "opening_label": int(label),
                "bbox_before": list(component["bbox"]),
                "bbox_after": list(_bbox(shifted)),
                "action": "snapped",
                "accepted": True,
                "shift_dy_dx": [dy, dx],
                "wall_overlap_before": current_overlap,
                "wall_overlap_after": best[0],
                "domain_signature": list(domain),
                "pixels_modified": int(len(set(map(tuple, coords)).symmetric_difference(set(map(tuple, shifted))))),
            })

    summary = {
        "components_checked": sum(record.get("mechanism") == "opening_snapping_and_validation" for record in records),
        "components_already_valid": sum(record.get("action") == "already_valid" for record in records),
        "components_snapped": sum(record.get("action") == "snapped" for record in records),
        "partial_deletions_completed": sum(record.get("mechanism") == "opening_partial_delete_completion" and record.get("accepted") for record in records),
        "completion_pixels": sum(int(record.get("pixels_completed", 0)) for record in records),
        "components_removed_spurious": sum(record.get("action") == "removed_spurious" for record in records),
        "components_rejected": sum(str(record.get("action", "")).startswith("rejected") for record in records),
    }
    return repaired, summary, records


def correct_maps(
    wall_path: str | Path,
    icon_path: str | Path,
    output_dir: str | Path,
    *,
    mode: str,
) -> Dict[str, Any]:
    """Apply one fixed reference-free correction configuration."""
    if mode not in CORRECTION_MODES:
        raise ValueError(f"Unsupported correction mode: {mode}")
    wall_input, wall_palette = load_palette_map(wall_path)
    icon_input, icon_palette = load_palette_map(icon_path)
    if wall_input.shape != icon_input.shape:
        raise ValueError("Wall and opening maps must have identical dimensions.")
    wall = wall_input.copy()
    icon = icon_input.copy()
    actions: List[Dict[str, Any]] = []
    module_summaries: Dict[str, Any] = {}

    if mode != "baseline":
        wall, fragment_summary, fragment_records = repair_enclosed_fragments(wall, icon)
        module_summaries["enclosed_room_fragment_repair"] = fragment_summary
        actions.extend({"module": "enclosed_room_fragment_repair", **record} for record in fragment_records)

    if mode in {"fragment_plus_wall", "fragment_plus_wall_plus_opening"}:
        # Stabilize a one-pixel boundary displacement before detecting a gap.  This
        # prevents a local bulge from masquerading as one endpoint of a nearby gap.
        wall, boundary_summary, boundary_records = regularize_wall_boundaries(wall, icon)
        module_summaries["wall_boundary_regularization"] = boundary_summary
        actions.extend({"module": "wall_boundary_regularization", **record} for record in boundary_records)
        wall, gap_summary, gap_records = reconstruct_short_wall_gaps(wall, icon)
        module_summaries["short_wall_gap_reconstruction"] = gap_summary
        actions.extend({"module": "short_wall_gap_reconstruction", **record} for record in gap_records)

    if mode == "fragment_plus_wall_plus_opening":
        icon, opening_summary, opening_records = repair_opening_components(icon, wall)
        module_summaries["door_window_component_repair"] = opening_summary
        actions.extend({"module": "door_window_component_repair", **record} for record in opening_records)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    corrected_wall = output_dir / "corrected_wall_svg.png"
    corrected_icon = output_dir / "corrected_icon_svg.png"
    save_palette_map(wall, wall_palette, corrected_wall)
    save_palette_map(icon, icon_palette, corrected_icon)
    changed_wall = int(np.count_nonzero(wall != wall_input))
    changed_icon = int(np.count_nonzero(icon != icon_input))
    log = {
        "schema_version": 1,
        "reference_free": True,
        "mode": mode,
        "configuration": REFERENCE_FREE_CONFIG,
        "prohibited_inputs_absent": {
            "clean_wall_map": True,
            "clean_opening_map": True,
            "clean_room_workbook": True,
            "clean_edge_workbook": True,
            "perturbation_level": True,
            "random_seed": True,
            "perturbation_manifest": True,
            "perturbation_coordinates_or_parameters": True,
        },
        "input_wall_path": str(Path(wall_path).resolve()),
        "input_icon_path": str(Path(icon_path).resolve()),
        "corrected_wall_path": str(corrected_wall.resolve()),
        "corrected_icon_path": str(corrected_icon.resolve()),
        "wall_pixels_modified": changed_wall,
        "opening_pixels_modified": changed_icon,
        "module_summaries": module_summaries,
        "actions": actions,
    }
    write_json(output_dir / "correction_log.json", log)
    return log


def reference_free_runtime_validation(topology_dir: str | Path) -> Dict[str, Any]:
    """Validate a corrected topology without any clean-reference data."""
    topology_dir = Path(topology_dir)
    with open(topology_dir / "rooms.json", "r", encoding="utf-8") as handle:
        rooms = json.load(handle)
    with open(topology_dir / "edges.json", "r", encoding="utf-8") as handle:
        edges = json.load(handle)
    room_ids = {int(room["id"]) for room in rooms}
    adjacency: Dict[int, Set[int]] = {room_id: set() for room_id in room_ids}
    invalid_edges: List[Dict[str, Any]] = []
    invalid_openings: List[Dict[str, Any]] = []
    suspicious_wall_thicknesses: List[Dict[str, Any]] = []
    for edge in edges:
        a, b = int(edge["roomA"]), int(edge["roomB"])
        length = float(edge.get("length", 0) or 0)
        width = float(edge.get("width", 0) or 0)
        if a not in room_ids or b not in room_ids or a == b or length <= 0 or width <= 0 or width > length:
            invalid_edges.append(edge)
        else:
            adjacency[a].add(b)
            adjacency[b].add(a)
        if edge.get("type") in {"door", "window", "opening"} and (a not in room_ids or b not in room_ids or width > length):
            invalid_openings.append(edge)
        if edge.get("type") == "wall" and width > float(REFERENCE_FREE_CONFIG["validation"]["max_wall_thickness_px"]):
            suspicious_wall_thicknesses.append(edge)

    isolated = sorted(room_id for room_id, neighbors in adjacency.items() if not neighbors)
    unseen = set(room_ids)
    component_count = 0
    while unseen:
        component_count += 1
        queue: deque[int] = deque([unseen.pop()])
        while queue:
            current = queue.popleft()
            for neighbor in adjacency[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
    areas = [int(room.get("area", 0)) for room in rooms]
    suspicious_rooms = [room for room in rooms if int(room.get("area", 0)) <= int(REFERENCE_FREE_CONFIG["validation"]["tiny_room_area_px"])]
    result = {
        "reference_free": True,
        "room_count": len(rooms),
        "edge_count": len(edges),
        "isolated_room_count": len(isolated),
        "isolated_room_ids": isolated,
        "invalid_edge_count": len(invalid_edges),
        "invalid_opening_count": len(invalid_openings),
        "disconnected_topology": component_count > 1,
        "connected_component_count": component_count,
        "suspicious_room_count": len(suspicious_rooms),
        "minimum_room_area_px": min(areas) if areas else None,
        "suspicious_wall_thickness_count": len(suspicious_wall_thicknesses),
        "invalid_edges": invalid_edges,
        "invalid_openings": invalid_openings,
        "suspicious_rooms": suspicious_rooms,
        "suspicious_wall_thicknesses": suspicious_wall_thicknesses,
        "passed": not isolated and not invalid_edges and not invalid_openings and component_count == 1 and not suspicious_rooms and not suspicious_wall_thicknesses,
    }
    write_json(topology_dir / "runtime_validation.json", result)
    return result
