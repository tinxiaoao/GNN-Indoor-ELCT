"""Versioned conservative opening correction from supplied maps only.

Frozen fragment/boundary/gap routines are reused without mutation. The new
opening rules never consume case identities, seeds, references or target tables.
"""
from __future__ import annotations

from collections import Counter
import copy
import hashlib
from pathlib import Path
import cv2
import numpy as np

from . import self_correction as frozen
from .extract_rooms import extract_rooms

VERSION = "correction_v2.0"
CONFIG = {key: copy.deepcopy(frozen.REFERENCE_FREE_CONFIG[key])
          for key in ("wall_code", "opening_labels", "fragment", "wall_boundary", "wall_gap", "validation")}
CONFIG["opening"] = {
    "snap_max_distance_px": 3,
    "min_wall_overlap_fraction": 0.995,
    "partial_gap_max_length_px": 4,
    "completion_pass_limit_per_label": 8,
    "spurious_component_area_px": 8,
    "normal_probe_radius_px": 2,
    "lateral_domain_radius_px": 2,
    "inplace_exterior_lip_max_px": 1,
    "outside_labels": [0, 1, 8, 50],
    "outside_connectivity": 4,
    "opening_connectivity": 8,
    "collision_clearance_px": 1,
}


def exterior_background(wall):
    """Only excluded nonwall components connected to the image border qualify."""
    allowed = np.isin(wall, CONFIG["opening"]["outside_labels"])
    _, labels = cv2.connectedComponents(allowed.astype(np.uint8),
                                      connectivity=CONFIG["opening"]["outside_connectivity"])
    border = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    return allowed & np.isin(labels, border[border > 0])


def _nearby_mask(coords, shape, radius):
    y0, x0, y1, x1 = frozen._bbox(coords)
    y0, x0 = max(0, y0-radius), max(0, x0-radius)
    y1, x1 = min(shape[0]-1, y1+radius), min(shape[1]-1, x1+radius)
    mask = np.zeros((y1-y0+1, x1-x0+1), np.uint8)
    mask[coords[:, 0]-y0, coords[:, 1]-x0] = 1
    if radius:
        mask = cv2.dilate(mask, np.ones((2*radius+1, 2*radius+1), np.uint8))
    return (slice(y0, y1+1), slice(x0, x1+1)), mask.astype(bool)


def _normal_end(wall, regions, outside, position, step):
    y, x = position
    for _ in range(int(CONFIG["opening"]["normal_probe_radius_px"])+1):
        if not (0 <= y < wall.shape[0] and 0 <= x < wall.shape[1]):
            return "outside", "image_exit"
        if wall[y, x] != CONFIG["wall_code"]:
            if regions[y, x] > 0:
                return f"room:{int(regions[y, x])}", "room_instance"
            if outside[y, x]:
                return "outside", "border_connected_background"
            return "unknown", "unqualified_nonwall"
        y, x = y+step[0], x+step[1]
    return "unknown", "wall_probe_limit"


def host_evidence(wall, regions, outside, coords, *, orientation=None):
    """Require a supported wall ribbon separating opposite, consistent domains.

    This is an opening-host probe, not a change to any extractor ray bound.
    Every occupied longitudinal scanline must have one continuous wall interval
    and the same ordered two-domain pair along its normal. Nearby third rooms
    are ambiguous. An image exit alone, without wall and room support, fails.
    """
    item = frozen._component_record(coords)
    y0, x0, y1, x1 = item["bbox"]
    selected_orientation = orientation or item["orientation"]
    horizontal = selected_orientation == "horizontal"
    pairs, reasons, supported = Counter(), Counter(), 0
    core_bands = []
    axis_values = range(x0, x1+1) if horizontal else range(y0, y1+1)
    for t in axis_values:
        line = coords[coords[:, 1 if horizontal else 0] == t]
        wall_coords = line[wall[line[:, 0], line[:, 1]] == CONFIG["wall_code"]]
        if not len(wall_coords):
            reasons["no_wall_support"] += 1
            continue
        normal = np.sort(wall_coords[:, 0 if horizontal else 1])
        if len(normal) != int(normal[-1]-normal[0]+1):
            reasons["discontinuous_wall_support"] += 1
            continue
        low, high = int(normal[0]), int(normal[-1])
        core_bands.append((low, high))
        a = _normal_end(wall, regions, outside, (low-1, t) if horizontal else (t, low-1), (-1, 0) if horizontal else (0, -1))
        b = _normal_end(wall, regions, outside, (high+1, t) if horizontal else (t, high+1), (1, 0) if horizontal else (0, 1))
        reasons[a[1]] += 1; reasons[b[1]] += 1
        if "unknown" in (a[0], b[0]) or a[0] == b[0] or not any(v.startswith("room:") for v in (a[0], b[0])):
            reasons["unsupported_domain_pair"] += 1
            continue
        pairs[(a[0], b[0])] += 1
        supported += 1
    signature = sorted({v for pair in pairs for v in pair})
    roi, mask = _nearby_mask(coords, wall.shape, int(CONFIG["opening"]["lateral_domain_radius_px"]))
    nearby_rooms = {f"room:{int(v)}" for v in np.unique(regions[roi][mask]) if v > 0}
    extra_rooms = sorted(nearby_rooms-set(signature))
    line_count = len(axis_values)
    square_ambiguous = item["width"] == item["height"] and orientation is None
    valid = (not square_ambiguous and supported == line_count
             and len(pairs) == 1 and len(signature) == 2 and not extra_rooms)
    return {"valid_host": bool(valid), "orientation": selected_orientation,
            "orientation_source": "aligned_completion_pair" if orientation else "component_bbox",
            "signature": signature, "ordered_domain_pairs": [{"domains": list(k), "lines": v} for k, v in sorted(pairs.items())],
            "supported_lines": supported, "total_lines": line_count, "evidence_counts": dict(reasons),
            "additional_nearby_rooms": extra_rooms, "uniform_wall_band": list(core_bands[0]) if core_bands and len(set(core_bands)) == 1 else None,
            "square_orientation_ambiguous": square_ambiguous}


def inplace_exterior_lip(wall, outside, coords, host):
    """Separate structural rule: one whole exterior face row/column overhang.

    No overlap threshold is lowered. A fully rectangular component may have
    exactly one outside face layer, with the remaining rectangle entirely wall,
    an unambiguous room/outside pair across every normal, and no internal hole.
    This rule can keep the original footprint; it never authorizes a move.
    """
    item = frozen._component_record(coords)
    band = host["uniform_wall_band"]
    if not host["valid_host"] or "outside" not in host["signature"] or band is None or item["fill_fraction"] != 1.0:
        return False
    normal0, normal1 = (item["bbox"][0], item["bbox"][2]) if item["orientation"] == "horizontal" else (item["bbox"][1], item["bbox"][3])
    excess = (band[0]-normal0, normal1-band[1])
    limit = int(CONFIG["opening"]["inplace_exterior_lip_max_px"])
    if not ((excess[0] == 0 and 0 < excess[1] <= limit) or (excess[1] == 0 and 0 < excess[0] <= limit)):
        return False
    # A raster overhang covers the WHOLE wall thickness. A displaced opening
    # can instead leave an uncovered wall layer on the opposite face; that is
    # not valid-in-place evidence and must go through the strict shift search.
    y0, x0, y1, x1 = item["bbox"]
    for face in (band[0]-1, band[1]+1):
        if item["orientation"] == "horizontal":
            if 0 <= face < wall.shape[0] and np.any(wall[face, x0:x1+1] == CONFIG["wall_code"]):
                return False
        elif 0 <= face < wall.shape[1] and np.any(wall[y0:y1+1, face] == CONFIG["wall_code"]):
            return False
    nonwall = coords[wall[coords[:, 0], coords[:, 1]] != CONFIG["wall_code"]]
    return bool(len(nonwall) and np.all(outside[nonwall[:, 0], nonwall[:, 1]]))


def component_record(coords):
    """Exact original/after footprint in row-run encoding, plus size and hash."""
    if not len(coords):
        return {"area_px": 0, "bbox_yxyx": None, "height_px": 0, "width_px": 0, "row_runs_y_x0_x1": []}
    coords = np.asarray(sorted(map(tuple, coords)), dtype=np.int32)
    runs = []
    for y in np.unique(coords[:, 0]):
        xs = coords[coords[:, 0] == y, 1]
        for part in np.split(xs, np.flatnonzero(np.diff(xs) != 1)+1):
            runs.append([int(y), int(part[0]), int(part[-1])])
    y0, x0, y1, x1 = frozen._bbox(coords)
    return {"area_px": len(coords), "bbox_yxyx": [y0, x0, y1, x1], "height_px": y1-y0+1, "width_px": x1-x0+1,
            "coordinate_sha256": hashlib.sha256(coords.astype('<i4').tobytes()).hexdigest(), "row_runs_y_x0_x1": runs}


def _action(label, action, reason, before, after, host_before, host_after=None, **extra):
    a, b = component_record(before), component_record(after)
    return {"module": "opening_v2", "opening_label": int(label), "action": action, "reason": reason,
            "before": a, "after": b, "domains_before": host_before, "domains_after": host_after or host_before,
            "area_change_px": b["area_px"]-a["area_px"], "height_change_px": b["height_px"]-a["height_px"],
            "width_change_px": b["width_px"]-a["width_px"],
            "pixels_modified": len(set(map(tuple, before)) ^ set(map(tuple, after))), **extra}


def _collision(icon, own_coords, target):
    roi, mask = _nearby_mask(target, icon.shape, int(CONFIG["opening"]["collision_clearance_px"]))
    local = icon[roi].copy()
    valid = ((own_coords[:, 0] >= roi[0].start) & (own_coords[:, 0] < roi[0].stop)
             & (own_coords[:, 1] >= roi[1].start) & (own_coords[:, 1] < roi[1].stop))
    own = own_coords[valid]
    local[own[:, 0]-roi[0].start, own[:, 1]-roi[1].start] = 0
    return bool(np.any(local[mask] != 0))


def _completion_gap(a, b):
    ca, cb = frozen._component_record(a), frozen._component_record(b)
    ya, xa, yA, xA = ca["bbox"];yb, xb, yB, xB = cb["bbox"]
    # A full-thickness deletion can invert each fragment's aspect ratio.
    # Infer the proposed axis from the observed shared extents, then validate
    # both pieces AND their union against the wall's opposite domains.
    if (ya, yA) == (yb, yB):
        left, right = sorted([(xa, xA), (xb, xB)])
        bounds = (ya, left[1]+1, yA, right[0]-1)
        gap = right[0]-left[1]-1
        orientation = "horizontal"
    elif (xa, xA) == (xb, xB):
        top, bottom = sorted([(ya, yA), (yb, yB)])
        bounds = (top[1]+1, xa, bottom[0]-1, xA)
        gap = bottom[0]-top[1]-1
        orientation = "vertical"
    else:
        return None
    if not 1 <= gap <= CONFIG["opening"]["partial_gap_max_length_px"]:
        return None
    y0, x0, y1, x1 = bounds
    yy, xx = np.mgrid[y0:y1+1, x0:x1+1]
    return np.column_stack((yy.ravel(), xx.ravel())), orientation


def complete_internal_bands(icon, wall, regions, outside):
    repaired, records = icon.copy(), []
    for label in CONFIG["opening_labels"]:
        for _ in range(CONFIG["opening"]["completion_pass_limit_per_label"]):
            components = frozen._components(repaired == label, CONFIG["opening"]["opening_connectivity"])
            candidates = []
            for i, a in enumerate(components):
                for j in range(i+1, len(components)):
                    b = components[j]; proposed = _completion_gap(a, b)
                    if proposed is None:continue
                    fill, orientation = proposed
                    before = np.vstack((a, b)); after = np.vstack((before, fill))
                    ha = host_evidence(wall, regions, outside, a, orientation=orientation)
                    hb = host_evidence(wall, regions, outside, b, orientation=orientation)
                    merged = host_evidence(wall, regions, outside, after, orientation=orientation)
                    good = (ha["valid_host"] and hb["valid_host"] and merged["valid_host"]
                            and ha["signature"] == hb["signature"] == merged["signature"]
                            and np.all(wall[fill[:, 0], fill[:, 1]] == CONFIG["wall_code"])
                            and np.all(repaired[fill[:, 0], fill[:, 1]] == 0)
                            and not _collision(repaired, before, after))
                    if good:candidates.append((i, j, before, after, fill, ha, merged))
                    else:records.append(_action(label, "keep_unresolved", "band_completion_host_or_collision_ambiguous", before, before, ha,
                                                event_scope="completion_proposal", second_domains=hb, proposed_domains=merged))
            degree = Counter(k for c in candidates for k in c[:2])
            unique = [c for c in candidates if degree[c[0]] == degree[c[1]] == 1]
            if not unique:
                for _, _, before, _, _, ha, _ in candidates:
                    records.append(_action(label, "keep_unresolved", "multiple_completion_partners", before, before, ha, event_scope="completion_proposal"))
                break
            _, _, before, after, fill, ha, merged = unique[0]
            repaired[fill[:, 0], fill[:, 1]] = label
            records.append(_action(label, "complete", "unique_collinear_full_thickness_internal_band", before, after, ha, merged,
                                   event_scope="completion", pixels_added=len(fill), merged_component_count=2))
    return repaired, records


def _independent_invalid_evidence(wall, icon, coords):
    if len(coords) > CONFIG["opening"]["spurious_component_area_px"]:
        return False
    roi, search = _nearby_mask(coords, wall.shape, CONFIG["opening"]["snap_max_distance_px"])
    # A square envelope conservatively includes every permitted Euclidean shift.
    return bool(not np.any(wall[roi][search] == CONFIG["wall_code"])
                and not _collision(icon, coords, coords))


def repair_opening_components(icon, wall):
    regions, *_ = extract_rooms(wall)
    outside = exterior_background(wall)
    repaired, records = complete_internal_bands(icon, wall, regions, outside)
    after_completion = repaired.copy()
    distance = CONFIG["opening"]["snap_max_distance_px"]
    shifts = [(dy, dx) for dy in range(-distance, distance+1) for dx in range(-distance, distance+1)
              if dy*dy+dx*dx <= distance*distance]
    threshold = CONFIG["opening"]["min_wall_overlap_fraction"]
    for label in CONFIG["opening_labels"]:
        for coords in frozen._components(after_completion == label, CONFIG["opening"]["opening_connectivity"]):
            host = host_evidence(wall, regions, outside, coords)
            overlap = float(np.mean(wall[coords[:, 0], coords[:, 1]] == CONFIG["wall_code"]))
            collision = _collision(repaired, coords, coords)
            if host["valid_host"] and not collision and (overlap >= threshold or inplace_exterior_lip(wall, outside, coords, host)):
                reason = "strict_overlap_and_opposed_domains" if overlap >= threshold else "inplace_rectangular_exterior_face_lip"
                records.append(_action(label, "keep_valid", reason, coords, coords, host, wall_overlap_before=overlap, event_scope="component"))
                continue
            if collision:
                records.append(_action(label, "keep_unresolved", "existing_component_contact_requires_review", coords, coords, host,
                                       wall_overlap_before=overlap, current_collision=True, event_scope="component"))
                continue
            if _independent_invalid_evidence(wall, repaired, coords):
                repaired[coords[:, 0], coords[:, 1]] = 0
                records.append(_action(label, "erase", "tiny_isolated_component_with_no_wall_in_entire_shift_envelope", coords,
                                       np.empty((0, 2), dtype=int), host,
                                       {"valid_host": False, "signature": [], "status": "component_erased"},
                                       wall_overlap_before=overlap, event_scope="component"))
                continue
            candidates = []
            for dy, dx in shifts:
                shifted = coords + (dy, dx)
                if np.any(shifted < 0) or np.any(shifted[:, 0] >= wall.shape[0]) or np.any(shifted[:, 1] >= wall.shape[1]):continue
                score = float(np.mean(wall[shifted[:, 0], shifted[:, 1]] == CONFIG["wall_code"]))
                if score < threshold or _collision(repaired, coords, shifted):continue
                candidate_host = host_evidence(wall, regions, outside, shifted)
                if candidate_host["valid_host"]:
                    candidates.append((score, -(abs(dy)+abs(dx)), dy, dx, shifted, candidate_host))
            candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
            tied = [c for c in candidates if c[:2] == candidates[0][:2]] if candidates else []
            if len(tied) != 1:
                reason = "no_legal_shift" if not tied else "tied_best_shifts"
                records.append(_action(label, "keep_unresolved", reason, coords, coords, host, event_scope="component",
                    wall_overlap_before=overlap, current_collision=collision, candidate_count=len(candidates),
                    tied_best_shifts=[[c[2], c[3]] for c in tied]))
                continue
            score, _, dy, dx, shifted, candidate_host = tied[0]
            repaired[coords[:, 0], coords[:, 1]] = 0
            repaired[shifted[:, 0], shifted[:, 1]] = label
            records.append(_action(label, "move", "unique_best_strict_overlap_and_opposed_domains", coords, shifted, host, candidate_host,
                                   event_scope="component", shift_dy_dx=[dy, dx], wall_overlap_before=overlap, wall_overlap_after=score))
    final = []
    for label in CONFIG["opening_labels"]:
        for coords in frozen._components(repaired == label, CONFIG["opening"]["opening_connectivity"]):
            host = host_evidence(wall, regions, outside, coords)
            overlap = float(np.mean(wall[coords[:, 0], coords[:, 1]] == CONFIG["wall_code"]))
            verified = (host["valid_host"] and not _collision(repaired, coords, coords)
                        and (overlap >= threshold or inplace_exterior_lip(wall, outside, coords, host)))
            final.append({"opening_label": int(label), "component": component_record(coords), "host": host,
                          "wall_overlap": overlap, "verified_by_v2_rules": bool(verified)})
    counts = Counter(r["action"] for r in records)
    summary = {"action_counts": dict(counts), "final_component_count": len(final),
               "unresolved_component_count": sum(not c["verified_by_v2_rules"] for c in final),
               "unresolved_event_count": counts["keep_unresolved"],
               "erased_component_count": counts["erase"], "merged_pairs": counts["complete"],
               "opening_pixels_modified": int(np.count_nonzero(repaired != icon)), "final_components": final}
    return repaired, summary, records


def correct_maps(wall_path, icon_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    wall, wp = frozen.load_palette_map(wall_path); icon, ip = frozen.load_palette_map(icon_path)
    if wall.shape != icon.shape:raise ValueError("Wall and icon dimensions differ")
    original_wall, original_icon = wall.copy(), icon.copy()
    actions, modules = [], {}
    for name, function in [("enclosed_room_fragment_repair", frozen.repair_enclosed_fragments),
                           ("wall_boundary_regularization", frozen.regularize_wall_boundaries),
                           ("short_wall_gap_reconstruction", frozen.reconstruct_short_wall_gaps)]:
        wall, summary, records = function(wall, icon)
        modules[name] = summary
        actions.extend({"module": name, **r} for r in records)
    icon, summary, records = repair_opening_components(icon, wall)
    modules["door_window_component_repair_v2"] = summary
    actions.extend(records)
    frozen.save_palette_map(wall, wp, output_dir/"corrected_wall_svg.png")
    frozen.save_palette_map(icon, ip, output_dir/"corrected_icon_svg.png")
    log = {"schema_version": 2, "algorithm_version": VERSION, "reference_free": True,
           "configuration": CONFIG, "wall_pixels_modified": int(np.count_nonzero(wall != original_wall)),
           "opening_pixels_modified": int(np.count_nonzero(icon != original_icon)),
           "module_summaries": modules, "actions": actions}
    frozen.write_json(output_dir/"correction_log.json", log)
    return log


def runtime_diagnostics(topology_dir, correction, internal_report):
    """Reference-free disposition report, distinct from historical validators."""
    import json
    folder = Path(topology_dir)
    opening = correction["module_summaries"]["door_window_component_repair_v2"]
    stats = json.loads((folder/"room_stats.json").read_text(encoding="utf-8"))
    abnormal = []
    for room, data in stats.items():
        for kind in ("walls", "openings"):
            for segment in data.get(kind, []):
                length, width = segment[-2:]
                if length <= 0 or width <= 0 or width > length:
                    abnormal.append({"room_id": room, "kind": kind, "segment": segment})
    unresolved = [c for c in opening["final_components"] if not c["verified_by_v2_rules"]]
    external_unresolved = [c for c in unresolved if "outside" in c["host"]["signature"]
                           or c["host"]["evidence_counts"].get("image_exit", 0)
                           or c["host"]["evidence_counts"].get("border_connected_background", 0)]
    review = bool(unresolved or abnormal or opening["unresolved_event_count"] or opening["erased_component_count"])
    return {"schema_version": 1, "algorithm_version": VERSION, "reference_free": True,
            "internal_graph_existing_report_passed": internal_report["passed"],
            "external_export_anomalies": abnormal, "opening_action_counts": opening["action_counts"],
            "exported_external_wall_segment_count": sum(len(d.get("walls", [])) for d in stats.values()),
            "exported_external_opening_segment_count": sum(len(d.get("openings", [])) for d in stats.values()),
            "external_opening_host_anomalies": external_unresolved,
            "other_unresolved_opening_count": len(unresolved)-len(external_unresolved),
            "unresolved_component_count": len(unresolved), "unresolved_components": unresolved,
            "unresolved_event_count": opening["unresolved_event_count"],
            "deleted_components": opening["erased_component_count"], "merged_component_pairs": opening["merged_pairs"],
            "manual_review_required": review or not internal_report["passed"],
            "all_implemented_checks_passed": bool(internal_report["passed"] and not review),
            "em_ready": False,
            "scope": "Local opening-host rules and exported geometry diagnostics only. Not a proof that all openings are present; unresolved/deletion events require review. EM readiness also requires independent downstream validation."}
