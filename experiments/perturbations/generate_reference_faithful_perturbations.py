"""Targeted and compound recoverable perturbations for reference-faithful R1-Q4 tests."""

from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[2]

from geo_elct.extract_rooms import extract_rooms
from .perturb_segmentation_maps import (
    DEFAULT_SEEDS,
    displace_local_wall_boundary,
    find_local_wall_segments,
    insert_enclosed_fragment,
    insert_local_wall_gap,
    load_palette_image,
    save_palette_image,
    shift_opening_component,
)


LEVEL_SETTINGS: Dict[str, Dict[str, Any]] = {
    "clean": {
        "fragment_count": (0, 0), "fragment_area_px": (0, 0),
        "wall_gap_count": (0, 0), "wall_gap_length_px": (0, 0),
        "boundary_count": (0, 0), "boundary_span_px": (0, 0), "boundary_displacement_px": (0, 0),
        "door_shift_count": (0, 0), "window_shift_count": (0, 0), "opening_shift_px": (0, 0),
        "partial_delete_count": (0, 0), "partial_delete_gap_px": (0, 0),
        "interpretation": "Unmodified clean maps.",
        "strict_target": "Exact clean reproduction.",
    },
    "mild": {
        "fragment_count": (1, 1), "fragment_area_px": (3, 5),
        "wall_gap_count": (1, 1), "wall_gap_length_px": (2, 2),
        "boundary_count": (1, 1), "boundary_span_px": (6, 8), "boundary_displacement_px": (1, 1),
        "door_shift_count": (1, 1), "window_shift_count": (0, 1), "opening_shift_px": (1, 1),
        "partial_delete_count": (1, 1), "partial_delete_gap_px": (1, 1),
        "interpretation": "Light, uniquely inferable local artifacts.",
        "strict_target": "Reference-free recovery to the clean room and edge tables.",
    },
    "moderate": {
        "fragment_count": (2, 3), "fragment_area_px": (4, 9),
        "wall_gap_count": (2, 2), "wall_gap_length_px": (3, 4),
        "boundary_count": (2, 2), "boundary_span_px": (8, 12), "boundary_displacement_px": (1, 1),
        "door_shift_count": (1, 1), "window_shift_count": (1, 1), "opening_shift_px": (2, 2),
        "partial_delete_count": (2, 2), "partial_delete_gap_px": (2, 3),
        "interpretation": "Moderate, still locally inferable artifacts.",
        "strict_target": "Reference-free recovery to the clean room and edge tables.",
    },
    "severe": {
        "fragment_count": (4, 6), "fragment_area_px": (6, 16),
        "wall_gap_count": (3, 3), "wall_gap_length_px": (5, 6),
        "boundary_count": (3, 3), "boundary_span_px": (12, 18), "boundary_displacement_px": (1, 1),
        "door_shift_count": (1, 2), "window_shift_count": (1, 2), "opening_shift_px": (3, 3),
        "partial_delete_count": (2, 3), "partial_delete_gap_px": (3, 4),
        "interpretation": "Strong local artifacts; no complete wall or opening deletion and no forced room merge.",
        "strict_target": "Topology recovery is primary; any non-exact geometric fields are reported honestly.",
    },
}


UNIT_CASES = (
    "room_fragment_only",
    "wall_gap_only",
    "wall_boundary_displacement_only",
    "door_shift_only",
    "window_shift_only",
    "opening_partial_delete_only",
    "compound_recoverable",
)


def _randint(rng: random.Random, bounds: Sequence[int]) -> int:
    return rng.randint(int(bounds[0]), int(bounds[1]))


def _components(array: np.ndarray, label: int) -> List[np.ndarray]:
    count, labels = cv2.connectedComponents((array == label).astype(np.uint8), connectivity=8)
    return [np.argwhere(labels == index) for index in range(1, count)]


def _bbox(coords: np.ndarray) -> List[int]:
    return [
        int(coords[:, 0].min()), int(coords[:, 1].min()),
        int(coords[:, 0].max()), int(coords[:, 1].max()),
    ]


def _room_neighbors(region_map: np.ndarray, coords: np.ndarray, radius: int = 2) -> set[int]:
    rooms: set[int] = set()
    height, width = region_map.shape
    for y, x in coords:
        y0, y1 = max(0, int(y) - radius), min(height, int(y) + radius + 1)
        x0, x1 = max(0, int(x) - radius), min(width, int(x) + radius + 1)
        rooms.update(int(value) for value in region_map[y0:y1, x0:x1].ravel() if int(value) > 0)
    return rooms


def _opening_pools(icon_array: np.ndarray, region_map: np.ndarray) -> Dict[str, List[np.ndarray]]:
    doors = _components(icon_array, 2)
    windows = _components(icon_array, 1)
    internal_doors = [coords for coords in doors if len(_room_neighbors(region_map, coords)) == 2]
    return {
        "internal_doors": internal_doors,
        "doors": doors,
        "windows": windows,
    }


def delete_internal_opening_strip(
    icon_array: np.ndarray,
    component: np.ndarray,
    gap_px: int,
) -> Optional[Dict[str, Any]]:
    """Delete an internal full-thickness strip so both ends reveal the original extent."""
    if len(component) == 0 or gap_px <= 0:
        return None
    y0, x0, y1, x1 = _bbox(component)
    horizontal = (x1 - x0) >= (y1 - y0)
    long_length = (x1 - x0 + 1) if horizontal else (y1 - y0 + 1)
    if long_length < 2 * gap_px + 8:
        return None
    if horizontal:
        start = x0 + (long_length - gap_px) // 2
        mask = (
            (component[:, 1] >= start)
            & (component[:, 1] < start + gap_px)
        )
    else:
        start = y0 + (long_length - gap_px) // 2
        mask = (
            (component[:, 0] >= start)
            & (component[:, 0] < start + gap_px)
        )
    deleted = component[mask]
    if len(deleted) == 0:
        return None
    label = int(icon_array[component[0, 0], component[0, 1]])
    icon_array[deleted[:, 0], deleted[:, 1]] = 0
    return {
        "operation": "opening_partial_delete_internal_strip",
        "opening_label": label,
        "orientation": "horizontal" if horizontal else "vertical",
        "gap_length_px": int(gap_px),
        "component_bbox_before": [y0, x0, y1, x1],
        "deleted_bbox": _bbox(deleted),
        "component_area_px": int(len(component)),
        "deleted_pixels": int(len(deleted)),
        "actual_fraction": float(len(deleted) / len(component)),
        "changed_pixels": int(len(deleted)),
    }


def _choose_wall_candidates(
    rng: random.Random,
    candidates: List[Dict[str, Any]],
    count: int,
    used_segments: set[str],
) -> List[Dict[str, Any]]:
    pool = [candidate for candidate in candidates if str(candidate["segment_id"]) not in used_segments]
    rng.shuffle(pool)
    chosen: List[Dict[str, Any]] = []
    for candidate in pool:
        segment_id = str(candidate["segment_id"])
        if segment_id in used_segments:
            continue
        chosen.append(candidate)
        used_segments.add(segment_id)
        if len(chosen) == count:
            break
    return chosen


def _copy_clean_case(
    wall_path: Path,
    icon_path: Path,
    case_dir: Path,
) -> Dict[str, Path]:
    case_dir.mkdir(parents=True, exist_ok=True)
    wall_out = case_dir / "perturbed_wall_svg.png"
    icon_out = case_dir / "perturbed_icon_svg.png"
    shutil.copyfile(wall_path, wall_out)
    shutil.copyfile(icon_path, icon_out)
    return {"wall": wall_out, "icon": icon_out}


def generate_main_cases(
    wall_path: Path,
    icon_path: Path,
    output_root: Path,
    seeds: Sequence[int],
) -> List[Dict[str, Any]]:
    wall_image, clean_wall, wall_palette = load_palette_image(wall_path)
    icon_image, clean_icon, icon_palette = load_palette_image(icon_path)
    region_map, _, _, _ = extract_rooms(clean_wall)
    base_candidates = find_local_wall_segments(clean_wall, clean_icon, wall_code=2)
    opening_pools = _opening_pools(clean_icon, region_map)
    manifests: List[Dict[str, Any]] = []

    for level, settings in LEVEL_SETTINGS.items():
        for seed in seeds:
            case_dir = output_root / level / f"seed_{seed}"
            case_dir.mkdir(parents=True, exist_ok=True)
            wall_out = case_dir / "perturbed_wall_svg.png"
            icon_out = case_dir / "perturbed_icon_svg.png"
            events: List[Dict[str, Any]] = []
            warnings: List[str] = []
            if level == "clean":
                shutil.copyfile(wall_path, wall_out)
                shutil.copyfile(icon_path, icon_out)
            else:
                rng = random.Random(41000 + int(seed) + 1000 * list(LEVEL_SETTINGS).index(level))
                wall = clean_wall.copy()
                icon = clean_icon.copy()
                used_segments: set[str] = set()

                gap_count = _randint(rng, settings["wall_gap_count"])
                for candidate in _choose_wall_candidates(rng, base_candidates, gap_count, used_segments):
                    events.append(insert_local_wall_gap(
                        wall, candidate, _randint(rng, settings["wall_gap_length_px"]), wall_code=2
                    ))

                boundary_count = _randint(rng, settings["boundary_count"])
                for candidate in _choose_wall_candidates(rng, base_candidates, boundary_count, used_segments):
                    event = displace_local_wall_boundary(
                        wall,
                        candidate,
                        _randint(rng, settings["boundary_span_px"]),
                        _randint(rng, settings["boundary_displacement_px"]),
                        rng,
                        wall_code=2,
                    )
                    if event.get("changed_pixels", 0):
                        events.append(event)

                for _ in range(_randint(rng, settings["fragment_count"])):
                    event = insert_enclosed_fragment(
                        wall, icon, rng, _randint(rng, settings["fragment_area_px"])
                    )
                    if event:
                        events.append(event)
                    else:
                        warnings.append("An enclosed fragment could not be placed safely.")

                doors = list(opening_pools["internal_doors"])
                windows = list(opening_pools["windows"])
                rng.shuffle(doors)
                rng.shuffle(windows)
                used_components: set[Tuple[int, int, int, int, int]] = set()

                for pool, count_bounds in (
                    (doors, settings["door_shift_count"]),
                    (windows, settings["window_shift_count"]),
                ):
                    count = min(_randint(rng, count_bounds), len(pool))
                    for component in pool[:count]:
                        label = int(clean_icon[component[0, 0], component[0, 1]])
                        key = (label, *_bbox(component))
                        event = shift_opening_component(
                            icon, component, _randint(rng, settings["opening_shift_px"]), rng
                        )
                        if event:
                            used_components.add(key)
                            events.append(event)

                partial_pool = list(doors) + list(windows)
                rng.shuffle(partial_pool)
                partial_needed = _randint(rng, settings["partial_delete_count"])
                partial_done = 0
                for component in partial_pool:
                    label = int(clean_icon[component[0, 0], component[0, 1]])
                    key = (label, *_bbox(component))
                    if key in used_components:
                        continue
                    event = delete_internal_opening_strip(
                        icon, component, _randint(rng, settings["partial_delete_gap_px"])
                    )
                    if event:
                        events.append(event)
                        used_components.add(key)
                        partial_done += 1
                    if partial_done == partial_needed:
                        break
                if partial_done < partial_needed:
                    warnings.append(f"Requested {partial_needed} partial opening deletions, placed {partial_done}.")

                save_palette_image(wall, wall_palette, wall_out)
                save_palette_image(icon, icon_palette, icon_out)

            with Image.open(wall_out) as image:
                saved_wall = np.asarray(image.convert("P"))
            with Image.open(icon_out) as image:
                saved_icon = np.asarray(image.convert("P"))
            manifest = {
                "schema_version": 1,
                "level": level,
                "seed": int(seed),
                "correction_must_not_read_this_manifest": True,
                "settings": settings,
                "events": events,
                "event_counts": {
                    operation: sum(event["operation"] == operation for event in events)
                    for operation in sorted({event["operation"] for event in events})
                },
                "changed_wall_pixels_vs_clean": int(np.count_nonzero(saved_wall != clean_wall)),
                "changed_opening_pixels_vs_clean": int(np.count_nonzero(saved_icon != clean_icon)),
                "wall_output_path": str(wall_out.resolve()),
                "icon_output_path": str(icon_out.resolve()),
                "warnings": warnings,
            }
            with open(case_dir / "perturbation_manifest.json", "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2)
            manifests.append(manifest)
    wall_image.close()
    icon_image.close()
    return manifests


def generate_unit_cases(
    wall_path: Path,
    icon_path: Path,
    output_root: Path,
) -> List[Dict[str, Any]]:
    wall_image, clean_wall, wall_palette = load_palette_image(wall_path)
    icon_image, clean_icon, icon_palette = load_palette_image(icon_path)
    region_map, _, _, _ = extract_rooms(clean_wall)
    wall_candidates = find_local_wall_segments(clean_wall, clean_icon, wall_code=2)
    pools = _opening_pools(clean_icon, region_map)
    manifests: List[Dict[str, Any]] = []

    for case_index, case_name in enumerate(UNIT_CASES):
        rng = random.Random(93000 + case_index)
        wall = clean_wall.copy()
        icon = clean_icon.copy()
        events: List[Dict[str, Any]] = []
        used_segments: set[str] = set()
        doors = list(pools["internal_doors"])
        windows = list(pools["windows"])
        rng.shuffle(doors)
        rng.shuffle(windows)

        if case_name in {"room_fragment_only", "compound_recoverable"}:
            event = insert_enclosed_fragment(wall, icon, rng, 5)
            if event:
                events.append(event)
        if case_name in {"wall_gap_only", "compound_recoverable"}:
            selected = _choose_wall_candidates(rng, wall_candidates, 1, used_segments)
            if selected:
                events.append(insert_local_wall_gap(wall, selected[0], 3, wall_code=2))
        if case_name in {"wall_boundary_displacement_only", "compound_recoverable"}:
            selected = _choose_wall_candidates(rng, wall_candidates, 1, used_segments)
            if selected:
                event = displace_local_wall_boundary(wall, selected[0], 9, 1, rng, wall_code=2)
                if event.get("changed_pixels", 0):
                    events.append(event)
        used_opening_keys: set[Tuple[int, int, int, int, int]] = set()
        if case_name in {"door_shift_only", "compound_recoverable"} and doors:
            component = doors[0]
            event = shift_opening_component(icon, component, 2, rng)
            if event:
                events.append(event)
                used_opening_keys.add((2, *_bbox(component)))
        if case_name in {"window_shift_only", "compound_recoverable"} and windows:
            component = windows[0]
            event = shift_opening_component(icon, component, 2, rng)
            if event:
                events.append(event)
                used_opening_keys.add((1, *_bbox(component)))
        if case_name in {"opening_partial_delete_only", "compound_recoverable"}:
            pool = doors + windows
            for component in pool:
                label = int(clean_icon[component[0, 0], component[0, 1]])
                if (label, *_bbox(component)) in used_opening_keys:
                    continue
                event = delete_internal_opening_strip(icon, component, 3)
                if event:
                    events.append(event)
                    break

        case_dir = output_root / case_name
        case_dir.mkdir(parents=True, exist_ok=True)
        wall_out = case_dir / "perturbed_wall_svg.png"
        icon_out = case_dir / "perturbed_icon_svg.png"
        save_palette_image(wall, wall_palette, wall_out)
        save_palette_image(icon, icon_palette, icon_out)
        manifest = {
            "schema_version": 1,
            "unit_case": case_name,
            "correction_must_not_read_this_manifest": True,
            "events": events,
            "changed_wall_pixels_vs_clean": int(np.count_nonzero(wall != clean_wall)),
            "changed_opening_pixels_vs_clean": int(np.count_nonzero(icon != clean_icon)),
            "wall_output_path": str(wall_out.resolve()),
            "icon_output_path": str(icon_out.resolve()),
        }
        with open(case_dir / "perturbation_manifest.json", "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
        manifests.append(manifest)
    wall_image.close()
    icon_image.close()
    return manifests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate reference-faithful R1-Q4 perturbations.")
    parser.add_argument("--wall", type=Path, default=REPO_ROOT / "wall_svg.png")
    parser.add_argument("--icon", type=Path, default=REPO_ROOT / "icon_svg.png")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "experiments" / "r1q4_reference_faithful_7795")
    parser.add_argument("--seeds", nargs="+", type=int, default=list(DEFAULT_SEEDS))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.out.exists():
        raise FileExistsError("Choose a new output directory; existing results are never overwritten")
    args.wall = args.wall.resolve()
    args.icon = args.icon.resolve()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    main_manifests = generate_main_cases(args.wall, args.icon, args.out / "maps", args.seeds)
    unit_manifests = generate_unit_cases(args.wall, args.icon, args.out / "unit_perturbations")
    settings = {
        "schema_version": 1,
        "main_levels": LEVEL_SETTINGS,
        "unit_cases": list(UNIT_CASES),
        "seeds": list(args.seeds),
        "restrictions": [
            "No complete wall or room boundary is deleted.",
            "No complete opening component is deleted.",
            "No perturbation intentionally merges adjacent rooms.",
            "Opening shifts remain within 3 pixels and preserve local host-wall evidence.",
            "Severe remains local; exact recovery is not assumed when local evidence is insufficient.",
        ],
        "correction_input_prohibition": "Correction must not read this file or any per-case manifest.",
    }
    with open(args.out / "perturbation_settings.json", "w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)
    print(json.dumps({
        "main_cases": len(main_manifests),
        "unit_cases": len(unit_manifests),
        "output_root": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
