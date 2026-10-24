"""Geo-ELCT release candidate: given semantic maps to two pixel-unit tables."""
__version__ = "0.1.0-candidate"

# Opening-size aggregation is independent of segmentation correction modes.
OPENING_AGGREGATIONS = ("by_thickness_v1", "legacy_width_sum")
DEFAULT_OPENING_AGGREGATION = "by_thickness_v1"
