"""Geometry behavior checks independent of segmentation correction modes."""
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from geo_elct.detect_adjacency import detect_adjacency
from geo_elct.extract_rooms import extract_rooms
from geo_elct.save_topology_image import save_to_excel


def opening_fixture(specifications):
    """Build separated rectangular openings (type, length, thickness, roomB)."""
    region = np.zeros((80, 45), dtype=np.int32)
    region[:, :12] = 1
    region[:, 18:] = 2
    icons = np.zeros(region.shape, dtype=np.uint8)
    y = 5
    for icon_type, length, thickness, room_b in specifications:
        region[y:y + length, 12 + thickness:] = room_b
        icons[y:y + length, 12:12 + thickness] = icon_type
        y += length + 5
    wall = (region == 0).astype(np.uint8)
    palette = np.where(wall, 2, region + 2).astype(np.uint8)
    return region, wall, icons, palette


def openings(specifications, aggregation="by_thickness_v1"):
    return [edge for edge in detect_adjacency(
        *opening_fixture(specifications), max_wall_thickness=20,
        opening_aggregation=aggregation) if edge["type"] in {"door", "window"}]


class OpeningAggregation(unittest.TestCase):
    def test_single_opening_keeps_length_and_thickness(self):
        expected = [{"roomA": 1, "roomB": 2, "type": "door",
                     "num": 1, "length": 8, "width": 3}]
        self.assertEqual(openings([(1, 8, 3, 2)]), expected)
        self.assertEqual(openings([(1, 8, 3, 2)], "legacy_width_sum"), expected)

    def test_same_thickness_sums_lengths_and_counts_components(self):
        edge, = openings([(1, 8, 3, 2), (1, 11, 3, 2)])
        self.assertEqual((edge["length"], edge["width"], edge["num"]), (19, 3, 2))
        legacy, = openings([(1, 8, 3, 2), (1, 11, 3, 2)], "legacy_width_sum")
        self.assertEqual((legacy["length"], legacy["width"], legacy["num"]), (19, 6, 2))

    def test_different_thicknesses_keep_separate_dimension_records(self):
        edges = openings([(1, 8, 3, 2), (1, 11, 5, 2)])
        self.assertEqual([(e["length"], e["width"], e["num"]) for e in edges],
                         [(8, 3, 1), (11, 5, 1)])

    def test_room_pairs_and_interface_types_are_separate(self):
        edges = openings([(1, 8, 3, 2), (2, 9, 3, 2), (1, 10, 3, 3)])
        self.assertEqual([(e["roomB"], e["type"], e["length"], e["width"])
                          for e in edges],
                         [(2, "door", 8, 3), (3, "door", 10, 3), (2, "window", 9, 3)])

    def test_export_count_is_dimension_records_not_components(self):
        edges = openings([(1, 8, 3, 2), (1, 11, 3, 2), (1, 9, 5, 2)])
        base = Path(os.environ.get("GEO_ELCT_TEST_TMP", tempfile.gettempdir()))
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="opening_export_", dir=base) as directory:
            file = Path(directory)/"edges.xlsx"
            save_to_excel(edges, str(file))
            row = pd.read_excel(file).iloc[0]
        self.assertEqual(int(row["Count"]), 2)
        self.assertEqual([(int(row[f"Length_{k}"]), int(row[f"Width_{k}"]))
                          for k in (1, 2)], [(19, 3), (9, 5)])
        self.assertEqual(sum(edge["num"] for edge in edges), 3)

    def test_invalid_aggregation_fails_before_reading_arrays(self):
        with self.assertRaises(ValueError):
            detect_adjacency(None, None, None, None, 20, opening_aggregation="unknown")

    def test_perimeter_and_search_bounds_preserve_morphological_definition(self):
        palette = np.zeros((35, 50), dtype=np.uint8)
        palette[3:9, 3:13] = 3  # 6x10: gradient=(8x12)-(4x8)=64.
        palette[17:27, 25:39] = 4  # 10x14: gradient=(12x16)-(8x12)=96.
        _, rooms, minimum, exterior = extract_rooms(palette)
        self.assertEqual([(r["area"], r["perimeter"]) for r in rooms], [(60, 64), (140, 96)])
        self.assertEqual(minimum, 6.4)
        self.assertEqual(exterior, 9.6)


if __name__ == "__main__":
    unittest.main()
