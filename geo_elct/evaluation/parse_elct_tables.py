import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


ROOM_WALL_RE = re.compile(r"^WallDir_(\d+)$", re.IGNORECASE)
OPEN_TYPE_RE = re.compile(r"^OpenType_(\d+)$", re.IGNORECASE)
EDGE_LENGTH_RE = re.compile(r"^Length_(\d+)$", re.IGNORECASE)


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def text_or_none(value: Any, *, lower: bool = False) -> Optional[str]:
    if is_blank(value):
        return None
    text = str(value).strip()
    if lower:
        text = text.lower()
    return text


def number_or_none(value: Any) -> Optional[float]:
    if is_blank(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def int_if_whole(value: Any) -> Any:
    number = number_or_none(value)
    if number is None:
        return text_or_none(value)
    if float(number).is_integer():
        return int(number)
    return number


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def finite_numbers(values: Iterable[Optional[float]]) -> List[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    nums = finite_numbers(values)
    if not nums:
        return None
    return float(sum(nums) / len(nums))


def total(values: Iterable[Optional[float]]) -> float:
    return float(sum(finite_numbers(values)))


def repeated_indices(columns: Iterable[str], pattern: re.Pattern[str]) -> List[int]:
    found = []
    for col in columns:
        match = pattern.match(str(col))
        if match:
            found.append(int(match.group(1)))
    return sorted(set(found))


def parse_room_table(room_xlsx: str | Path) -> List[Dict[str, Any]]:
    df = pd.read_excel(room_xlsx)
    wall_indices = repeated_indices(df.columns, ROOM_WALL_RE)
    open_indices = repeated_indices(df.columns, OPEN_TYPE_RE)

    rooms: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        exterior_walls: List[Dict[str, Any]] = []
        for idx in wall_indices:
            direction = text_or_none(row.get(f"WallDir_{idx}"), lower=True)
            length = number_or_none(row.get(f"ExtWallLength_{idx}"))
            width = number_or_none(row.get(f"ExtWallWidth_{idx}"))
            if direction is None and length is None and width is None:
                continue
            exterior_walls.append({
                "direction": direction,
                "length": length,
                "width": width,
            })

        exterior_openings: List[Dict[str, Any]] = []
        for idx in open_indices:
            opening_type = text_or_none(row.get(f"OpenType_{idx}"), lower=True)
            direction = text_or_none(row.get(f"OpenDir_{idx}"), lower=True)
            length = number_or_none(row.get(f"OpenLength_{idx}"))
            width = number_or_none(row.get(f"OpenWidth_{idx}"))
            if opening_type is None and direction is None and length is None and width is None:
                continue
            exterior_openings.append({
                "type": opening_type,
                "direction": direction,
                "length": length,
                "width": width,
            })

        room = {
            "room_id": int_if_whole(row.get("RoomID")),
            "room_type": text_or_none(row.get("Type")),
            "area": number_or_none(row.get("Area")),
            "perimeter": number_or_none(row.get("Perimeter")),
            "exterior_walls": exterior_walls,
            "exterior_openings": exterior_openings,
        }
        room.update({
            "exterior_wall_count": len(exterior_walls),
            "exterior_wall_total_length": total(w["length"] for w in exterior_walls),
            "exterior_wall_mean_width": mean(w["width"] for w in exterior_walls),
            "exterior_opening_count": len(exterior_openings),
            "exterior_opening_total_length": total(o["length"] for o in exterior_openings),
            "exterior_opening_mean_width": mean(o["width"] for o in exterior_openings),
        })
        rooms.append(room)

    rooms.sort(key=lambda r: room_sort_key(r["room_id"]))
    return rooms


def room_sort_key(room_id: Any) -> Tuple[int, Any]:
    number = number_or_none(room_id)
    if number is not None:
        return (0, float(number))
    return (1, str(room_id))


def normalize_room_pair(room_a: Any, room_b: Any) -> Tuple[Any, Any]:
    a = int_if_whole(room_a)
    b = int_if_whole(room_b)
    return tuple(sorted((a, b), key=room_sort_key))


def parse_edge_table(edge_xlsx: str | Path) -> List[Dict[str, Any]]:
    df = pd.read_excel(edge_xlsx)
    length_indices = repeated_indices(df.columns, EDGE_LENGTH_RE)

    edges: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        room_a, room_b = normalize_room_pair(row.get("RoomA"), row.get("RoomB"))
        conn_type = text_or_none(row.get("ConnectionType"), lower=True)
        segments: List[Dict[str, Optional[float]]] = []
        for idx in length_indices:
            length = number_or_none(row.get(f"Length_{idx}"))
            width = number_or_none(row.get(f"Width_{idx}"))
            if length is None and width is None:
                continue
            segments.append({"length": length, "width": width})

        widths = finite_numbers(seg["width"] for seg in segments)
        edge = {
            "roomA": room_a,
            "roomB": room_b,
            "connection_type": conn_type,
            "source_count": int_if_whole(row.get("Count")),
            "segments": segments,
            "segment_count": len(segments),
            "total_length": total(seg["length"] for seg in segments),
            "mean_width": mean(seg["width"] for seg in segments),
            "max_width": max(widths) if widths else None,
            "min_width": min(widths) if widths else None,
        }
        edges.append(edge)

    edges.sort(key=lambda e: (room_sort_key(e["roomA"]), room_sort_key(e["roomB"]), str(e["connection_type"])))
    return edges


def write_json(path: str | Path, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(json_safe(payload), f, ensure_ascii=False, indent=2)


def flatten_for_csv(record: Dict[str, Any]) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, (list, dict)):
            flattened[key] = json.dumps(json_safe(value), ensure_ascii=False)
        else:
            flattened[key] = value
    return flattened


def write_csv(path: str | Path, records: List[Dict[str, Any]]) -> None:
    rows = [flatten_for_csv(record) for record in records]
    fieldnames: List[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_canonical_tables(
    room_xlsx: str | Path,
    edge_xlsx: str | Path,
    out_dir: str | Path,
    *,
    write_csv: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    rooms = parse_room_table(room_xlsx)
    edges = parse_edge_table(edge_xlsx)

    write_json(out_path / "room_table_canonical.json", rooms)
    write_json(out_path / "edge_table_canonical.json", edges)
    if write_csv:
        globals()["write_csv"](out_path / "room_table_canonical.csv", rooms)
        globals()["write_csv"](out_path / "edge_table_canonical.csv", edges)
    return rooms, edges


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse Geo-ELCT Excel tables into canonical JSON/CSV.")
    parser.add_argument("--room-xlsx", required=True, help="Path to debug_roomself.xlsx.")
    parser.add_argument("--edge-xlsx", required=True, help="Path to debug_topology_edges.xlsx.")
    parser.add_argument("--out-dir", required=True, help="Output directory for canonical files.")
    parser.add_argument("--no-csv", action="store_true", help="Write JSON only.")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    rooms, edges = write_canonical_tables(
        room_xlsx=args.room_xlsx,
        edge_xlsx=args.edge_xlsx,
        out_dir=args.out_dir,
        write_csv=not args.no_csv,
    )
    print(json.dumps({"room_count": len(rooms), "edge_count": len(edges)}, indent=2))


if __name__ == "__main__":
    main()
