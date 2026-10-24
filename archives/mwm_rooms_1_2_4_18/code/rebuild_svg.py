#!/usr/bin/env python3
"""Rebuild SVG link inputs and check original fixed-parameter outputs.

No propagation-parameter fitting, no reference-value editing, and no cross-
configuration recalibration occurs in this script.  The recovered implementation
is numerically equivalent to the archived workbook outputs; the historical
program itself is not available.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.affinity import scale
from shapely.ops import unary_union

NS = {"s": "http://www.w3.org/2000/svg"}


def polygon_of(element: ET.Element) -> Polygon:
    node = element.find("s:polygon", NS)
    if node is None:
        raise ValueError("Expected a direct SVG polygon")
    numbers = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", node.get("points", ""))
    polygon = Polygon(np.asarray(numbers, dtype=float).reshape(-1, 2))
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Invalid SVG polygon; no automatic repair applied")
    return polygon


def aggregate(pl: np.ndarray, tx_power: float) -> np.ndarray:
    # All receivers have equal weights. The four cases add Txs cumulatively.
    power = np.power(10.0, (tx_power - pl) / 10.0)
    return 10.0 * np.log10(np.cumsum(power.mean(axis=1)))


def run(folder: Path) -> dict:
    cfg = json.loads((folder / "recovery_config.json").read_text(encoding="utf-8"))
    svg = folder / cfg["svg"]
    if hashlib.sha256(svg.read_bytes()).hexdigest() != cfg["svg_sha256"]:
        raise ValueError("SVG hash mismatch")
    root = ET.parse(svg).getroot()
    parent = {child: node for node in root.iter() for child in node}
    buckets = {name: [] for name in ("Space", "Wall", "Door", "Window")}
    space_by_id = {}
    factor = 1.0 / cfg["scale_units_per_m"]
    for e in root.iter():
        category = e.get("class", "").split(" ")[0]
        if category not in buckets:
            continue
        node = e
        while node is not None:
            if "transform" in node.attrib:
                raise ValueError("Transformed structural polygon requires explicit handling")
            node = parent.get(node)
        p = scale(polygon_of(e), xfact=factor, yfact=factor, origin=(0, 0))
        buckets[category].append(p)
        if category == "Space":
            space_by_id[e.get("id")] = p

    opening_polygons = buckets["Door"] + buckets["Window"]
    all_openings = unary_union(opening_polygons)
    wall_fragments = []
    for wall in buckets["Wall"]:
        cut = wall.difference(all_openings)
        wall_fragments.extend(p for p in shapely.get_parts(cut)
                              if isinstance(p, Polygon) and not p.is_empty)
    if len(wall_fragments) != 76:
        raise ValueError("Unexpected wall-fragment count")

    baseline = np.load(folder / "reference_and_proposed.npz", allow_pickle=False)
    freqs = np.asarray(cfg["frequency_GHz"], dtype=float)
    tx = np.asarray(cfg["tx_xyz_m"], dtype=float)
    heights = np.asarray(cfg["rx_heights_m"], dtype=float)
    theta = np.asarray(cfg["C1_parameters"], dtype=float)
    models = ["MWM", "3GPP", "CIF", "ABGSS", "ABGDS", "mmMAGIC"]
    predictions = {name: np.empty((3, 4, 18)) for name in models}
    arrays = {"frequency_GHz": freqs, "WI_ARP_dBm": baseline["WI_ARP_dBm"],
              "tx_room_ids": np.asarray(cfg["tx_room_ids"], dtype=int), "tx_xyz": tx}
    geometric = []
    for rec in cfg["rooms"]:
        r = int(rec["room_id"])
        polygon = space_by_id[rec["svg_id"]]
        inner = polygon.buffer(-cfg["inward_buffer_m"], join_style=cfg["buffer_join_style"])
        x0, y0, x1, y1 = inner.bounds
        xx, yy = np.meshgrid(np.arange(x0, x1 + 1e-9, cfg["grid_spacing_m"]),
                             np.arange(y0, y1 + 1e-9, cfg["grid_spacing_m"]))
        xy = np.column_stack([xx.ravel(), yy.ravel()])
        xy = xy[shapely.contains_xy(inner.buffer(cfg["grid_boundary_tolerance_m"]),
                                   xy[:, 0], xy[:, 1])]
        if len(xy) != rec["source_points_per_height"]:
            raise ValueError(f"Rx count mismatch for room {r}")
        coords = np.stack([np.broadcast_to(tx[:, None, :2], (4, len(xy), 2)),
                           np.broadcast_to(xy[None, :, :], (4, len(xy), 2))], axis=2)
        lines = shapely.linestrings(coords.reshape(-1, 2, 2))
        wall = np.sum([shapely.intersects(lines, p) for p in wall_fragments], axis=0).reshape(4, -1)
        opening = np.sum([shapely.intersects(lines, p) for p in opening_polygons], axis=0).reshape(4, -1)
        horizontal = ((xy[None, :, :] - tx[:, None, :2]) ** 2).sum(axis=-1)
        distance = np.sqrt(horizontal[:, :, None] + (tx[:, 2, None, None] - heights[None, None, :]) ** 2).reshape(4, -1)
        wall = np.repeat(wall, len(heights), axis=1)
        opening = np.repeat(opening, len(heights), axis=1)
        ld = np.log10(np.maximum(distance, cfg["distance_min_m"]))
        arrays[f"room{r}_xyz"] = np.column_stack([np.repeat(xy, len(heights), axis=0), np.tile(heights, len(xy))])
        arrays[f"room{r}_distance"] = distance
        arrays[f"room{r}_wall"] = wall
        arrays[f"room{r}_open"] = opening
        arrays[f"room{r}_features"] = np.stack([10 * ld, wall, opening], axis=-1)
        for fi, f in enumerate(freqs):
            b0, n, lw, lo = theta[fi]
            lf = np.log10(f)
            los = 32.4 + 17.3 * ld + 20 * lf
            nlos = 17.30 + 38.3 * ld + 24.9 * lf
            d = np.maximum(distance, cfg["distance_min_m"])
            losses = {
                "MWM": 32.4 + 20 * lf + b0 + 10 * n * ld + lw * wall + lo * opening,
                "3GPP": np.maximum(los, nlos),
                "CIF": 32.4 + 20 * lf + 31.9 * (1 + 0.06 * (f - 24.2) / 24.2) * ld,
                "ABGSS": nlos,
                "ABGDS": 33 + 24.9 * lf + 17 * np.log10(np.minimum(d, 6.9))
                            + 41.7 * np.log10(np.maximum(d / 6.9, 1)),
                "mmMAGIC": np.maximum(13.8 * ld + 33.6 + 20.3 * lf,
                                       36.9 * ld + 15.2 + 26.8 * lf),
            }
            for name, pl in losses.items():
                predictions[name][fi, :, r - 1] = aggregate(pl, cfg["P_tx_dBm"])
        geometric.append({"room_id": r, "points_per_height": len(xy),
                          "area_delta_m2": polygon.area - rec["source_area_m2"],
                          "centroid_delta_m": float(np.linalg.norm(np.array(polygon.centroid.coords[0])
                                                     - rec["source_centroid_m"]))})


    np.savez_compressed(folder / "link_features_confirmed.npz", **arrays)
    np.savez_compressed(folder / "C1_forward_predictions.npz", **predictions)
    report = {"Rx_total": sum(g["points_per_height"] for g in geometric) * len(heights),
              "wall_fragments":len(wall_fragments),
              "door_window_polygons":len(opening_polygons),
              "geometry_checks":geometric}
    (folder / "geometry_rebuild_check.json").write_text(json.dumps(report, indent=2),encoding="utf-8")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder",type=Path,required=True)
    run(parser.parse_args().folder)
