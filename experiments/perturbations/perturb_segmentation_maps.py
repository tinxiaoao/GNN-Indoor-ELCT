"""Deterministic, local post-GNN segmentation-map perturbations for R1-Q4.

The main levels deliberately avoid room-merging wall destruction.  Every edit
is recorded in a per-case manifest and the complete parameter set is exported
at the experiment root.  ``extreme_failure_mode`` is retained only as an
optional stress test and is never included by the default CLI or table runner.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from collections import deque
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image


ROOM_EXCLUDE_LABELS = {0, 1, 2, 8, 50}
MAIN_LEVELS = ("clean", "mild", "moderate", "severe")
DEFAULT_SEEDS = (0, 1, 2, 3, 4)

# Pixel ranges are inclusive.  Values are explicit so the same configuration
# can be cited verbatim in the response letter and reconstructed from JSON.
LEVEL_PARAMS: Dict[str, Dict[str, Any]] = {
    "clean": {
        "affected_wall_segments_max": 0,
        "wall_gap_count": (0, 0),
        "wall_gap_length_px": (0, 0),
        "boundary_displacement_count": (0, 0),
        "boundary_displacement_px": (0, 0),
        "boundary_span_length_px": (0, 0),
        "fragment_count": (0, 0),
        "fragment_area_px": (0, 0),
        "opening_component_count": (0, 0),
        "opening_shift_px": (0, 0),
        "opening_delete_fraction": (0.0, 0.0),
        "interpretation": "Unmodified post-GNN segmentation maps.",
    },
    "mild": {
        "affected_wall_segments_max": 1,
        "wall_gap_count": (1, 1),
        "wall_gap_length_px": (1, 3),
        "boundary_displacement_count": (0, 1),
        "boundary_displacement_px": (1, 1),
        "boundary_span_length_px": (4, 8),
        "fragment_count": (0, 0),
        "fragment_area_px": (0, 0),
        "opening_component_count": (1, 1),
        "opening_shift_px": (1, 1),
        "opening_delete_fraction": (0.03, 0.05),
        "interpretation": "Light local segmentation artifacts.",
    },
    "moderate": {
        "affected_wall_segments_max": 2,
        "wall_gap_count": (1, 2),
        "wall_gap_length_px": (2, 5),
        "boundary_displacement_count": (1, 2),
        "boundary_displacement_px": (1, 1),
        "boundary_span_length_px": (6, 12),
        "fragment_count": (2, 4),
        "fragment_area_px": (2, 9),
        "opening_component_count": (1, 2),
        "opening_shift_px": (1, 2),
        "opening_delete_fraction": (0.05, 0.10),
        "interpretation": "Moderate but realistic local artifacts.",
    },
    "severe": {
        "affected_wall_segments_max": 3,
        "wall_gap_count": (2, 4),
        "wall_gap_length_px": (4, 8),
        "boundary_displacement_count": (2, 4),
        "boundary_displacement_px": (1, 2),
        "boundary_span_length_px": (10, 20),
        "fragment_count": (4, 8),
        "fragment_area_px": (4, 16),
        "opening_component_count": (1, 3),
        "opening_shift_px": (2, 3),
        "opening_delete_fraction": (0.15, 0.20),
        "interpretation": "Strong but still realistic local artifacts.",
    },
    "extreme_failure_mode": {
        "affected_wall_segments_max": 5,
        "wall_gap_count": (5, 8),
        "wall_gap_length_px": (8, 18),
        "boundary_displacement_count": (6, 10),
        "boundary_displacement_px": (3, 6),
        "boundary_span_length_px": (24, 60),
        "fragment_count": (18, 18),
        "fragment_area_px": (50, 250),
        "opening_component_count": (8, 16),
        "opening_shift_px": (4, 10),
        "opening_delete_fraction": (0.20, 0.50),
        "interpretation": "Optional extreme failure-mode stress test; excluded from main tables.",
    },
}

HUMAN_READABLE_SETTINGS = {
    "clean": {
        "Affected wall segments": "None",
        "Local wall-gap setting": "None",
        "Local wall-boundary displacement": "None",
        "Room-fragment setting": "None",
        "Opening shift": "None",
        "Opening deletion": "None",
        "Intended interpretation": "Unmodified post-GNN segmentation maps",
    },
    "mild": {
        "Affected wall segments": "1",
        "Local wall-gap setting": "1 gap on 1 wall, 1-3 px long",
        "Local wall-boundary displacement": "Optional 1 px displacement over one 4-8 px span",
        "Room-fragment setting": "None",
        "Opening shift": "1 component by 1 px (alternative action)",
        "Opening deletion": "3-5% of 1 component (alternative action; never >5%)",
        "Intended interpretation": "Light local segmentation artifacts",
    },
    "moderate": {
        "Affected wall segments": "Up to 2",
        "Local wall-gap setting": "1-2 gaps on up to 2 walls, each 2-5 px long",
        "Local wall-boundary displacement": "1 px over 1-2 spans, each 6-12 px long",
        "Room-fragment setting": "2-4 enclosed fragments, each 2-9 px",
        "Opening shift": "1-2 components by 1-2 px (alternative action)",
        "Opening deletion": "5-10% per selected component (alternative action; never >10%)",
        "Intended interpretation": "Moderate but realistic local artifacts",
    },
    "severe": {
        "Affected wall segments": "Up to 3",
        "Local wall-gap setting": "2-4 gaps on up to 3 walls, each 4-8 px long",
        "Local wall-boundary displacement": "1-2 px over 2-4 spans, each 10-20 px long",
        "Room-fragment setting": "4-8 enclosed fragments, each 4-16 px",
        "Opening shift": "1-3 components by 2-3 px (alternative action)",
        "Opening deletion": "15-20% per selected component (alternative action; never >20%)",
        "Intended interpretation": "Strong but still realistic local artifacts",
    },
}


def parse_modes(raw: str | Iterable[str]) -> List[str]:
    if isinstance(raw, str):
        parts = raw.split(",")
    else:
        parts = []
        for item in raw:
            parts.extend(str(item).split(","))
    aliases = {
        "icon_shift": "opening",
        "icon_drop": "opening",
        "wall_erode": "wall_boundary",
        "wall_dilate": "wall_boundary",
    }
    parsed: List[str] = []
    for part in parts:
        mode = aliases.get(part.strip(), part.strip())
        if mode and mode not in parsed:
            parsed.append(mode)
    return parsed


def load_palette_image(path: str | Path) -> Tuple[Image.Image, np.ndarray, Optional[List[int]]]:
    image = Image.open(path).convert("P")
    return image, np.array(image, dtype=np.uint8), image.getpalette()


def save_palette_image(array: np.ndarray, palette: Optional[List[int]], path: str | Path) -> None:
    image = Image.fromarray(array.astype(np.uint8), mode="P")
    if palette is not None:
        image.putpalette(palette)
    image.save(path)


def connected_components(mask: np.ndarray, connectivity: int = 4) -> List[np.ndarray]:
    mask = mask.astype(bool)
    visited = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    neighbors = (
        [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
        if connectivity == 8
        else [(-1, 0), (1, 0), (0, -1), (0, 1)]
    )
    components: List[np.ndarray] = []
    ys, xs = np.where(mask)
    for sy, sx in zip(ys, xs):
        if visited[sy, sx]:
            continue
        queue: deque[Tuple[int, int]] = deque([(int(sy), int(sx))])
        visited[sy, sx] = True
        coords: List[Tuple[int, int]] = []
        while queue:
            y, x = queue.popleft()
            coords.append((y, x))
            for dy, dx in neighbors:
                ny, nx = y + dy, x + dx
                if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        components.append(np.asarray(coords, dtype=np.int32))
    return components


def _randint(rng: random.Random, bounds: Sequence[int]) -> int:
    return rng.randint(int(bounds[0]), int(bounds[1]))


def _room_labels(array: np.ndarray) -> List[int]:
    return sorted(int(v) for v in np.unique(array) if int(v) not in ROOM_EXCLUDE_LABELS)


def _run_bounds(line: np.ndarray, index: int, value: int) -> Tuple[int, int]:
    lo = hi = int(index)
    while lo > 0 and int(line[lo - 1]) == value:
        lo -= 1
    while hi + 1 < len(line) and int(line[hi + 1]) == value:
        hi += 1
    return lo, hi


def _nearest_nonwall_label(line: np.ndarray, start: int, step: int, wall_code: int, max_distance: int = 8) -> int:
    index = start
    for _ in range(max_distance):
        if not 0 <= index < len(line):
            return -1
        value = int(line[index])
        if value != wall_code:
            return value
        index += step
    return -1


def find_local_wall_segments(
    wall_array: np.ndarray,
    icon_array: np.ndarray,
    *,
    wall_code: int = 2,
    scan_step: int = 7,
    min_length_px: int = 48,
    max_thickness_px: int = 64,
) -> List[Dict[str, Any]]:
    """Return safe interior positions on long, axis-aligned wall segments."""
    height, width = wall_array.shape
    candidates: List[Dict[str, Any]] = []
    valid_room_labels = set(_room_labels(wall_array))
    for y in range(20, height - 20, scan_step):
        for x in range(20, width - 20, scan_step):
            if int(wall_array[y, x]) != wall_code:
                continue

            vy0, vy1 = _run_bounds(wall_array[:, x], y, wall_code)
            hx0, hx1 = _run_bounds(wall_array[y, :], x, wall_code)
            v_thickness = vy1 - vy0 + 1
            h_thickness = hx1 - hx0 + 1

            # Horizontal wall: short vertical thickness, sustained support in x.
            if 3 <= v_thickness <= max_thickness_px and h_thickness >= min_length_px:
                above = _nearest_nonwall_label(wall_array[:, x], vy0 - 1, -1, wall_code)
                below = _nearest_nonwall_label(wall_array[:, x], vy1 + 1, 1, wall_code)
                if above in valid_room_labels and below in valid_room_labels:
                    if not np.any(icon_array[max(0, vy0 - 6):min(height, vy1 + 7), max(0, x - 16):min(width, x + 17)]):
                        candidates.append({
                            "orientation": "horizontal",
                            "center": [y, x],
                            "cross_bounds": [vy0, vy1],
                            "axis_bounds": [hx0, hx1],
                            "adjacent_labels": [above, below],
                            "segment_id": f"H_{round((vy0 + vy1) / 14)}_{above}_{below}",
                        })

            # Vertical wall: short horizontal thickness, sustained support in y.
            if 3 <= h_thickness <= max_thickness_px and v_thickness >= min_length_px:
                left = _nearest_nonwall_label(wall_array[y, :], hx0 - 1, -1, wall_code)
                right = _nearest_nonwall_label(wall_array[y, :], hx1 + 1, 1, wall_code)
                if left in valid_room_labels and right in valid_room_labels:
                    if not np.any(icon_array[max(0, y - 16):min(height, y + 17), max(0, hx0 - 6):min(width, hx1 + 7)]):
                        candidates.append({
                            "orientation": "vertical",
                            "center": [y, x],
                            "cross_bounds": [hx0, hx1],
                            "axis_bounds": [vy0, vy1],
                            "adjacent_labels": [left, right],
                            "segment_id": f"V_{round((hx0 + hx1) / 14)}_{left}_{right}",
                        })
    return candidates


def _far_from(selected: List[Dict[str, Any]], candidate: Dict[str, Any], distance: int = 36) -> bool:
    y, x = candidate["center"]
    return all((y - other["center"][0]) ** 2 + (x - other["center"][1]) ** 2 >= distance ** 2 for other in selected)


def choose_wall_positions(
    rng: random.Random,
    candidates: List[Dict[str, Any]],
    count: int,
    max_segments: int,
) -> List[Dict[str, Any]]:
    if count <= 0 or not candidates:
        return []
    shuffled = list(candidates)
    rng.shuffle(shuffled)
    selected: List[Dict[str, Any]] = []
    segments: set[str] = set()
    # First cover distinct segments, then allow separated positions on them.
    for distinct_only in (True, False):
        for candidate in shuffled:
            sid = str(candidate["segment_id"])
            if distinct_only and sid in segments:
                continue
            if sid not in segments and len(segments) >= max_segments:
                continue
            if not _far_from(selected, candidate):
                continue
            selected.append(candidate)
            segments.add(sid)
            if len(selected) >= count:
                return selected
    return selected


def insert_local_wall_gap(
    wall_array: np.ndarray,
    candidate: Dict[str, Any],
    length_px: int,
    *,
    wall_code: int = 2,
) -> Dict[str, Any]:
    y, x = candidate["center"]
    start_offset = length_px // 2
    if candidate["orientation"] == "horizontal":
        y0, y1 = candidate["cross_bounds"]
        x0 = x - start_offset
        x1 = x0 + length_px - 1
    else:
        x0, x1 = candidate["cross_bounds"]
        y0 = y - start_offset
        y1 = y0 + length_px - 1
    view = wall_array[y0:y1 + 1, x0:x1 + 1]
    changed = view == wall_code
    view[changed] = 0
    return {
        "operation": "short_wall_gap",
        "orientation": candidate["orientation"],
        "segment_id": candidate["segment_id"],
        "length_px": int(length_px),
        "bbox_ymin_xmin_ymax_xmax": [int(y0), int(x0), int(y1), int(x1)],
        "changed_pixels": int(changed.sum()),
    }


def displace_local_wall_boundary(
    wall_array: np.ndarray,
    candidate: Dict[str, Any],
    span_px: int,
    displacement_px: int,
    rng: random.Random,
    *,
    wall_code: int = 2,
) -> Dict[str, Any]:
    """Move one local wall boundary outward; the opposite boundary is unchanged."""
    y, x = candidate["center"]
    side = -1 if rng.random() < 0.5 else 1
    half = span_px // 2
    if candidate["orientation"] == "horizontal":
        cross0, cross1 = candidate["cross_bounds"]
        x0, x1 = x - half, x - half + span_px - 1
        if side < 0:
            y0, y1 = cross0 - displacement_px, cross0 - 1
        else:
            y0, y1 = cross1 + 1, cross1 + displacement_px
    else:
        cross0, cross1 = candidate["cross_bounds"]
        y0, y1 = y - half, y - half + span_px - 1
        if side < 0:
            x0, x1 = cross0 - displacement_px, cross0 - 1
        else:
            x0, x1 = cross1 + 1, cross1 + displacement_px
    y0, x0 = max(0, y0), max(0, x0)
    y1, x1 = min(wall_array.shape[0] - 1, y1), min(wall_array.shape[1] - 1, x1)
    view = wall_array[y0:y1 + 1, x0:x1 + 1]
    changed = ~np.isin(view, list(ROOM_EXCLUDE_LABELS))
    view[changed] = wall_code
    return {
        "operation": "wall_boundary_displacement",
        "orientation": candidate["orientation"],
        "segment_id": candidate["segment_id"],
        "span_length_px": int(span_px),
        "displacement_px": int(displacement_px),
        "side": int(side),
        "bbox_ymin_xmin_ymax_xmax": [int(y0), int(x0), int(y1), int(x1)],
        "changed_pixels": int(changed.sum()),
    }


def insert_enclosed_fragment(
    wall_array: np.ndarray,
    icon_array: np.ndarray,
    rng: random.Random,
    area_px: int,
) -> Optional[Dict[str, Any]]:
    labels = _room_labels(wall_array)
    if len(labels) < 2 or area_px <= 0:
        return None
    height, width = wall_array.shape
    for _ in range(400):
        host = rng.choice(labels)
        ys, xs = np.where(wall_array == host)
        if len(ys) == 0:
            continue
        idx = rng.randrange(len(ys))
        y, x = int(ys[idx]), int(xs[idx])
        radius = max(3, int(np.ceil(np.sqrt(area_px))) + 2)
        if y - radius < 0 or x - radius < 0 or y + radius >= height or x + radius >= width:
            continue
        local = wall_array[y - radius:y + radius + 1, x - radius:x + radius + 1]
        local_icon = icon_array[y - radius:y + radius + 1, x - radius:x + radius + 1]
        if not np.all(local == host) or np.any(local_icon):
            continue
        offsets = [(dy, dx) for dy in range(-radius + 2, radius - 1) for dx in range(-radius + 2, radius - 1)]
        offsets.sort(key=lambda item: (item[0] * item[0] + item[1] * item[1], abs(item[0]) + abs(item[1]), item))
        coords = offsets[:area_px]
        target = rng.choice([label for label in labels if label != host])
        yy = np.asarray([y + dy for dy, _ in coords], dtype=np.int32)
        xx = np.asarray([x + dx for _, dx in coords], dtype=np.int32)
        wall_array[yy, xx] = target
        return {
            "operation": "enclosed_room_fragment",
            "host_label": int(host),
            "fragment_label": int(target),
            "area_px": int(area_px),
            "bbox_ymin_xmin_ymax_xmax": [int(yy.min()), int(xx.min()), int(yy.max()), int(xx.max())],
            "changed_pixels": int(area_px),
        }
    return None


def _component_bbox(component: np.ndarray) -> List[int]:
    return [
        int(component[:, 0].min()), int(component[:, 1].min()),
        int(component[:, 0].max()), int(component[:, 1].max()),
    ]


def shift_opening_component(
    icon_array: np.ndarray,
    component: np.ndarray,
    distance_px: int,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    if len(component) == 0:
        return None
    label = int(icon_array[component[0, 0], component[0, 1]])
    y0, x0, y1, x1 = _component_bbox(component)
    # Shift normal to the component's long axis, which models a small wall-
    # association error and gives the snapping module a meaningful test.
    if (x1 - x0) >= (y1 - y0):
        directions = [(-distance_px, 0), (distance_px, 0)]
    else:
        directions = [(0, -distance_px), (0, distance_px)]
    rng.shuffle(directions)
    for dy, dx in directions:
        shifted = component + np.asarray([dy, dx], dtype=np.int32)
        if shifted[:, 0].min() < 0 or shifted[:, 1].min() < 0:
            continue
        if shifted[:, 0].max() >= icon_array.shape[0] or shifted[:, 1].max() >= icon_array.shape[1]:
            continue
        occupied = icon_array[shifted[:, 0], shifted[:, 1]]
        if np.any((occupied != 0) & (occupied != label)):
            continue
        before = _component_bbox(component)
        old_linear = set((component[:, 0] * icon_array.shape[1] + component[:, 1]).tolist())
        new_linear = set((shifted[:, 0] * icon_array.shape[1] + shifted[:, 1]).tolist())
        icon_array[component[:, 0], component[:, 1]] = 0
        icon_array[shifted[:, 0], shifted[:, 1]] = label
        return {
            "operation": "opening_shift",
            "opening_label": label,
            "distance_px": int(distance_px),
            "shift_dy_dx": [int(dy), int(dx)],
            "bbox_before_ymin_xmin_ymax_xmax": before,
            "bbox_after_ymin_xmin_ymax_xmax": _component_bbox(shifted),
            "component_area_px": int(len(component)),
            "changed_pixels": int(len(old_linear.symmetric_difference(new_linear))),
        }
    return None


def delete_opening_boundary_pixels(
    icon_array: np.ndarray,
    component: np.ndarray,
    fraction: float,
    rng: random.Random,
) -> Optional[Dict[str, Any]]:
    if len(component) == 0:
        return None
    delete_count = max(1, min(len(component) - 1, int(np.floor(len(component) * fraction))))
    y0, x0, y1, x1 = _component_bbox(component)
    horizontal = (x1 - x0) >= (y1 - y0)
    reverse = rng.random() < 0.5
    # Shorten one end of the component.  This achieves the exact deletion cap
    # without peppering the component or splitting off tiny islands.
    if horizontal:
        order = np.lexsort((component[:, 0], component[:, 1]))
    else:
        order = np.lexsort((component[:, 1], component[:, 0]))
    if reverse:
        order = order[::-1]
    coords = component[order[:delete_count]]
    label = int(icon_array[component[0, 0], component[0, 1]])
    icon_array[coords[:, 0], coords[:, 1]] = 0
    return {
        "operation": "opening_pixel_deletion",
        "opening_label": label,
        "requested_fraction": float(fraction),
        "actual_fraction": float(delete_count / len(component)),
        "deleted_pixels": int(delete_count),
        "component_area_px": int(len(component)),
        "bbox_ymin_xmin_ymax_xmax": _component_bbox(component),
        "changed_pixels": int(delete_count),
    }


def output_case_root(output_dir: Path, case_id: Optional[str]) -> Path:
    if not case_id:
        return output_dir
    return output_dir if output_dir.name == case_id else output_dir / case_id


def export_settings_manifest(out_root: Path, seeds: Sequence[int], modes: Sequence[str]) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "workflow": "R1-Q4 revised local post-GNN segmentation perturbations",
        "main_levels": list(MAIN_LEVELS),
        "default_seeds": list(DEFAULT_SEEDS),
        "seeds_used": [int(seed) for seed in seeds],
        "selected_modes": list(modes),
        "extreme_failure_mode_excluded_from_main": True,
        "machine_readable_parameters": LEVEL_PARAMS,
        "human_readable_settings": HUMAN_READABLE_SETTINGS,
        "restrictions": [
            "No long wall spans are removed in the main experiment.",
            "Wall gaps are local and written as non-room background, so the generator never relabels a gap as an adjacent room.",
            "Opening shifts are at most 3 px in the main experiment.",
            "No main-level operation intentionally merges rooms.",
        ],
    }
    with open(out_root / "perturbation_settings_manifest.json", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def perturb_maps(
    wall_path: str | Path,
    icon_path: str | Path,
    output_dir: str | Path,
    levels: List[str],
    seeds: List[int],
    modes: List[str],
    *,
    wall_code: int = 2,
    case_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    wall_img, wall_base, wall_palette = load_palette_image(wall_path)
    icon_img, icon_base, icon_palette = load_palette_image(icon_path)
    if wall_base.shape != icon_base.shape:
        raise ValueError("Wall and opening maps must have identical dimensions.")
    out_root = output_case_root(Path(output_dir), case_id)
    export_settings_manifest(out_root, seeds, modes)
    safe_wall_candidates = find_local_wall_segments(wall_base, icon_base, wall_code=wall_code)
    if not safe_wall_candidates:
        raise RuntimeError("No safe local internal wall segments were found.")

    manifests: List[Dict[str, Any]] = []
    for level in levels:
        if level not in LEVEL_PARAMS:
            raise ValueError(f"Unsupported level: {level}")
        for seed in seeds:
            rng = random.Random(int(seed))
            case_dir = out_root / level / f"seed_{seed}"
            case_dir.mkdir(parents=True, exist_ok=True)
            out_wall = case_dir / "wall_svg_perturbed.png"
            out_icon = case_dir / "icon_svg_perturbed.png"
            params = LEVEL_PARAMS[level]
            events: List[Dict[str, Any]] = []
            warnings: List[str] = []

            if level == "clean":
                shutil.copyfile(wall_path, out_wall)
                shutil.copyfile(icon_path, out_icon)
            else:
                wall_array = wall_base.copy()
                icon_array = icon_base.copy()
                max_segments = int(params["affected_wall_segments_max"])
                segment_ids = sorted({str(candidate["segment_id"]) for candidate in safe_wall_candidates})
                rng.shuffle(segment_ids)
                allowed_segment_ids = set(segment_ids[:max_segments])
                level_wall_candidates = [
                    candidate for candidate in safe_wall_candidates
                    if str(candidate["segment_id"]) in allowed_segment_ids
                ]

                if "wall_gap" in modes:
                    gap_count = _randint(rng, params["wall_gap_count"])
                    selected = choose_wall_positions(
                        rng, level_wall_candidates, gap_count, max_segments
                    )
                    for candidate in selected:
                        events.append(insert_local_wall_gap(
                            wall_array, candidate, _randint(rng, params["wall_gap_length_px"]), wall_code=wall_code
                        ))
                    if len(selected) < gap_count:
                        warnings.append(f"Requested {gap_count} wall gaps but safely placed {len(selected)}.")

                if "wall_boundary" in modes:
                    count = _randint(rng, params["boundary_displacement_count"])
                    selected = choose_wall_positions(
                        rng, level_wall_candidates, count, max_segments
                    )
                    for candidate in selected:
                        event = displace_local_wall_boundary(
                            wall_array,
                            candidate,
                            _randint(rng, params["boundary_span_length_px"]),
                            _randint(rng, params["boundary_displacement_px"]),
                            rng,
                            wall_code=wall_code,
                        )
                        if event["changed_pixels"]:
                            events.append(event)

                if "room_fragment" in modes:
                    count = _randint(rng, params["fragment_count"])
                    for _ in range(count):
                        event = insert_enclosed_fragment(
                            wall_array, icon_array, rng, _randint(rng, params["fragment_area_px"])
                        )
                        if event is None:
                            warnings.append("A requested enclosed fragment could not be safely placed.")
                        else:
                            events.append(event)

                if "opening" in modes:
                    components: List[np.ndarray] = []
                    for label in (1, 2):
                        components.extend(connected_components(icon_array == label, connectivity=8))
                    rng.shuffle(components)
                    count = min(_randint(rng, params["opening_component_count"]), len(components))
                    for index, component in enumerate(components[:count]):
                        # Alternating actions ensure both shift and partial-deletion
                        # behavior appear across the fixed five-seed experiment.
                        use_shift = (int(seed) + index) % 2 == 0
                        if use_shift:
                            event = shift_opening_component(
                                icon_array, component, _randint(rng, params["opening_shift_px"]), rng
                            )
                        else:
                            fraction = rng.uniform(*params["opening_delete_fraction"])
                            event = delete_opening_boundary_pixels(icon_array, component, fraction, rng)
                        if event is None:
                            warnings.append("A requested opening edit could not be safely applied.")
                        else:
                            events.append(event)

                save_palette_image(wall_array, wall_palette, out_wall)
                save_palette_image(icon_array, icon_palette, out_icon)

            changed_wall = int(np.count_nonzero(np.array(Image.open(out_wall).convert("P")) != wall_base))
            changed_icon = int(np.count_nonzero(np.array(Image.open(out_icon).convert("P")) != icon_base))
            manifest: Dict[str, Any] = {
                "schema_version": 2,
                "wall_input_path": str(Path(wall_path).resolve()),
                "icon_input_path": str(Path(icon_path).resolve()),
                "wall_output_path": str(out_wall.resolve()),
                "icon_output_path": str(out_icon.resolve()),
                "seed": int(seed),
                "level": level,
                "is_main_experiment_level": level in MAIN_LEVELS,
                "selected_perturbation_modes": [] if level == "clean" else modes,
                "wall_code": int(wall_code),
                "parameter_values_used": params,
                "events": events,
                "event_counts": {
                    operation: sum(1 for event in events if event["operation"] == operation)
                    for operation in sorted({event["operation"] for event in events})
                },
                "changed_wall_pixels_vs_clean": changed_wall,
                "changed_opening_pixels_vs_clean": changed_icon,
                "warnings": warnings,
            }
            with open(case_dir / "perturbation_manifest.json", "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)
            manifests.append(manifest)

    wall_img.close()
    icon_img.close()
    return manifests


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create deterministic local post-GNN segmentation-map perturbations.")
    parser.add_argument("--wall", required=True, help="Input wall_svg.png palette map.")
    parser.add_argument("--icon", required=True, help="Input icon_svg.png palette map.")
    parser.add_argument("--output-dir", required=True, help="Output root for level/seed map folders.")
    parser.add_argument("--case-id", help="Optional case-id folder name.")
    parser.add_argument("--levels", nargs="+", default=list(MAIN_LEVELS), help="Perturbation levels.")
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS), help="Fixed random seeds.")
    parser.add_argument(
        "--modes",
        default="wall_gap,wall_boundary,room_fragment,opening",
        help="Comma-separated modes: wall_gap, wall_boundary, room_fragment, opening.",
    )
    parser.add_argument("--wall-code", type=int, default=2, help="Wall label in wall_svg.png.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    if Path(args.output_dir).exists():
        raise FileExistsError("Choose a new output directory; existing results are never overwritten")
    manifests = perturb_maps(
        wall_path=args.wall,
        icon_path=args.icon,
        output_dir=args.output_dir,
        levels=args.levels,
        seeds=args.seeds,
        modes=parse_modes(args.modes),
        wall_code=args.wall_code,
        case_id=args.case_id,
    )
    print(json.dumps({"generated": len(manifests), "output_dir": args.output_dir}, indent=2))


if __name__ == "__main__":
    main()
