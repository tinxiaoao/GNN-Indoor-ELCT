"""Build original MWM link features at the actual WI receiver coordinates."""
from __future__ import annotations

from pathlib import Path
import re
import xml.etree.ElementTree as ET

import numpy as np
import shapely
from shapely.affinity import scale
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

NS = {"s": "http://www.w3.org/2000/svg"}


def _polygon(element: ET.Element) -> Polygon:
    node = element.find("s:polygon", NS)
    if node is None:
        raise ValueError("Expected a direct SVG polygon")
    values = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", node.get("points", ""))
    polygon = Polygon(np.asarray(values, dtype=float).reshape(-1, 2))
    if polygon.is_empty or not polygon.is_valid:
        raise ValueError("Invalid structural SVG polygon; no geometry repair is applied")
    return polygon


def build(folder: Path, validated: dict) -> tuple[dict, str]:
    cfg = validated["config"]
    root = ET.parse(folder / "source.svg").getroot()
    parent = {child: node for node in root.iter() for child in node}
    buckets = {name: [] for name in ("Space", "Wall", "Door", "Window")}
    spaces = {}
    factor = 1.0 / cfg["scale_units_per_m"]
    for element in root.iter():
        category = element.get("class", "").split(" ")[0]
        if category not in buckets:
            continue
        node = element
        while node is not None:
            if "transform" in node.attrib:
                raise ValueError("Transformed SVG structural polygons require explicit handling")
            node = parent.get(node)
        polygon = scale(_polygon(element), xfact=factor, yfact=factor, origin=(0, 0))
        buckets[category].append(polygon)
        if category == "Space":
            spaces[element.get("id")] = polygon
    opening_polygons = buckets["Door"] + buckets["Window"]
    all_openings = unary_union(opening_polygons)
    walls = []
    for wall in buckets["Wall"]:
        cut = wall.difference(all_openings)
        walls.extend(part for part in shapely.get_parts(cut)
                     if isinstance(part, Polygon) and not part.is_empty)

    transform = np.asarray(cfg["wi_to_svg_m"], dtype=float)
    def mapped(points):
        result = np.array(points, dtype=float, copy=True)
        result[:, :2] = np.column_stack((result[:, :2], np.ones(len(result)))) @ transform[:2].T
        return result
    tx = mapped(cfg["tx_xyz_m"])
    for index, room in enumerate(cfg["tx_room_ids"]):
        polygon = spaces[cfg["rooms"][room - 1]["svg_id"]]
        if not polygon.contains(Point(tx[index, :2])):
            raise ValueError(f"Verified transmitter is outside its Room {room} polygon")

    arrays = {"frequency_GHz": np.asarray(cfg["frequency_GHz"]),
              "tx_room_ids": np.asarray(cfg["tx_room_ids"]), "tx_xyz": tx,
              "input_fingerprint_sha256": np.asarray(validated["fingerprint"])}
    # C-1 preservation depends on its actual Tx, Rx, geometry and WI targets.
    import hashlib
    c1 = hashlib.sha256((folder / "source.svg").read_bytes())
    def fingerprint_array(array):
        value = np.ascontiguousarray(array, dtype="<f8")
        c1.update(str(value.shape).encode()); c1.update(value.tobytes())
    for value in (cfg["frequency_GHz"], [cfg["P_tx_dBm"], cfg["distance_min_m"]],
                  tx[0], validated["WI_ARP_dBm"][:, 0]):
        fingerprint_array(value)
    for record in cfg["rooms"]:
        room = record["room_id"]
        xyz = mapped(validated["rx"][room])
        # Keep every exported point; no reconstructed lattice or count target.
        coords = np.stack((np.broadcast_to(tx[:, None, :2], (4, len(xyz), 2)),
                           np.broadcast_to(xyz[None, :, :2], (4, len(xyz), 2))), axis=2)
        lines = shapely.linestrings(coords.reshape(-1, 2, 2))
        wall = np.zeros(len(lines), dtype=int)
        opening = np.zeros(len(lines), dtype=int)
        for polygon in walls:
            wall += shapely.intersects(lines, polygon)
        for polygon in opening_polygons:
            opening += shapely.intersects(lines, polygon)
        wall = wall.reshape(4, -1); opening = opening.reshape(4, -1)
        distance = np.linalg.norm(xyz[None, :, :] - tx[:, None, :], axis=2)
        features = np.stack((10 * np.log10(np.maximum(distance, cfg["distance_min_m"])),
                             wall, opening), axis=-1)
        arrays[f"room{room}_xyz"] = xyz
        arrays[f"room{room}_distance"] = distance
        arrays[f"room{room}_wall"] = wall
        arrays[f"room{room}_open"] = opening
        arrays[f"room{room}_features"] = features
        fingerprint_array(xyz); fingerprint_array(features[0])
    return arrays, c1.hexdigest()
