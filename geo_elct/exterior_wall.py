import numpy as np
from typing import List, Dict, Tuple, Set

from .detect_adjacency import _get_boundary_pixels

_DIRECTIONS: List[Tuple[int, int]] = [(-1, 0), (1, 0), (0, -1), (0, 1)]
_WALL_CODE: int = 2
_BLOCKED_CODES: Set[int] = {0, 1, 8, 50}
_WINDOW_ICON: int = 1
_DOOR_ICON: int = 2
_ICON_NAME = {_WINDOW_ICON: 'window', _DOOR_ICON: 'door'}


def _shoot_ray_to_outside(region_map: np.ndarray,
                          palette_map: np.ndarray,
                          start: Tuple[int, int],
                          direction: Tuple[int, int],
                          self_id: int,
                          max_wall_thickness: int):
    H, W = region_map.shape
    dx, dy = direction
    x, y = start[0] + dx, start[1] + dy

    if not (0 <= x < H and 0 <= y < W):
        return None
    if region_map[x, y] == self_id:
        return None

    wall_pixels: Set[Tuple[int, int]] = set()
    wall_cnt = 0

    while 0 <= x < H and 0 <= y < W:
        rid = region_map[x, y]
        pal = palette_map[x, y]

        if rid == 0 and pal in _BLOCKED_CODES and pal != _WALL_CODE:
            return wall_pixels if wall_pixels else None

        if pal == _WALL_CODE:
            wall_pixels.add((x, y))
            wall_cnt += 1
            if wall_cnt >= max_wall_thickness:
                return None

        if rid != 0:
            return None
        if pal in _BLOCKED_CODES and pal != _WALL_CODE:
            return None

        x += dx
        y += dy

    # 有些外墙紧贴着图像边缘，不加入这一步会漏掉检测这部分外墙
    if wall_pixels:
        return wall_pixels

    return None


def exterior_wall_segments(region_map: np.ndarray,
                           palette_map: np.ndarray,
                           max_wall_thickness: int) -> Dict[int, List[Tuple[str, int, int]]]:
    """
    返回 {room_id: [(direction, length, thickness), ...]} 外墙分段尺寸字典，合并同方向同厚度的墙段，
    并删除厚度大于长度的异常段。
    """
    result: Dict[int, List[Tuple[str, int, int]]] = {}
    for rid in [i for i in np.unique(region_map) if i > 0]:
        segments = []
        visited = set()

        for (x, y) in _get_boundary_pixels(region_map, rid):
            for direction in _DIRECTIONS:
                pix = _shoot_ray_to_outside(region_map, palette_map,
                                            (x, y), direction, rid, max_wall_thickness)
                if pix:
                    pix_frozen = frozenset(pix)
                    if pix_frozen in visited:
                        continue
                    visited.add(pix_frozen)
                    coords = np.array(list(pix))

                    dx, dy = direction
                    if dx != 0:
                        wall_dir = 'horizontal'
                        length = np.ptp(coords[:, 1]) + 1
                        thickness = np.ptp(coords[:, 0]) + 1
                    else:
                        wall_dir = 'vertical'
                        length = np.ptp(coords[:, 0]) + 1
                        thickness = np.ptp(coords[:, 1]) + 1

                    # 合并相同方向与厚度的外墙
                    merged = False
                    for i, (existing_dir, existing_length, existing_thickness) in enumerate(segments):
                        if existing_dir == wall_dir and existing_thickness == thickness:
                            segments[i] = (existing_dir, existing_length + length, existing_thickness)
                            merged = True
                            break
                    if not merged:
                        segments.append((wall_dir, length, thickness))

        # 删除厚度大于长度的异常段
        segments = [seg for seg in segments if seg[2] <= seg[1]]

        result[rid] = segments

    return result


# === 新增：与外界相邻的门窗检测（与外墙同逻辑） ===  8.12
def _shoot_ray_to_outside_openings(region_map: np.ndarray,
                                   palette_map: np.ndarray,
                                   icon_map: np.ndarray,
                                   start: Tuple[int, int],
                                   direction: Tuple[int, int],
                                   self_id: int,
                                   max_wall_thickness: int) -> Dict[int, Set[Tuple[int, int]]]:
    H, W = region_map.shape
    dx, dy = direction
    x, y = start[0] + dx, start[1] + dy

    if not (0 <= x < H and 0 <= y < W):
        return {}
    if region_map[x, y] == self_id:
        return {}

    found: Dict[int, Set[Tuple[int, int]]] = {_WINDOW_ICON: set(), _DOOR_ICON: set()}
    wall_cnt = 0

    while 0 <= x < H and 0 <= y < W:
        rid = region_map[x, y]
        pal = palette_map[x, y]

        # 抵达室外（非墙阻断）=> 成功
        if rid == 0 and pal in _BLOCKED_CODES and pal != _WALL_CODE:
            return {k: v for k, v in found.items() if v}

        # 穿越墙体：记录厚度并看 icon
        if pal == _WALL_CODE:
            wall_cnt += 1
            iv = icon_map[x, y]
            if iv == _WINDOW_ICON:
                found[_WINDOW_ICON].add((x, y))
            elif iv == _DOOR_ICON:
                found[_DOOR_ICON].add((x, y))
            if wall_cnt >= max_wall_thickness:
                return {}  # 过厚，丢弃

        # 室内或其它阻断（非墙）
        if rid != 0:
            return {}
        if pal in _BLOCKED_CODES and pal != _WALL_CODE:
            return {}

        x += dx
        y += dy

    # 贴边当作外界（与外墙逻辑一致）
    non_empty = {k: v for k, v in found.items() if v}
    return non_empty


def exterior_opening_segments(region_map: np.ndarray,
                              palette_map: np.ndarray,
                              icon_map: np.ndarray,
                              max_wall_thickness: int) -> Dict[int, List[Tuple[str, str, int, int]]]:
    """
    返回 {room_id: [(opening_type, direction, length, thickness), ...]}
    opening_type ∈ {'door','window'}; direction ∈ {'horizontal','vertical'}
    合并条件：同“类型+方向+厚度”，并过滤厚度>长度的异常段。
    """
    result: Dict[int, List[Tuple[str, str, int, int]]] = {}

    for rid in [i for i in np.unique(region_map) if i > 0]:
        segments: List[Tuple[str, str, int, int]] = []
        visited_by_type = {'door': set(), 'window': set()}

        for (x, y) in _get_boundary_pixels(region_map, rid):
            for direction in _DIRECTIONS:
                openings = _shoot_ray_to_outside_openings(
                    region_map, palette_map, icon_map,
                    (x, y), direction, rid, max_wall_thickness
                )
                if not openings:
                    continue

                for icon_code, pix in openings.items():
                    if not pix:
                        continue
                    opening_type = _ICON_NAME.get(icon_code)
                    if not opening_type:
                        continue

                    pix_frozen = frozenset(pix)
                    if pix_frozen in visited_by_type[opening_type]:
                        continue
                    visited_by_type[opening_type].add(pix_frozen)

                    coords = np.array(list(pix))
                    dx, dy = direction
                    if dx != 0:
                        opening_dir = 'horizontal'
                        length = int(np.ptp(coords[:, 1])) + 1
                        thickness = int(np.ptp(coords[:, 0])) + 1
                    else:
                        opening_dir = 'vertical'
                        length = int(np.ptp(coords[:, 0])) + 1
                        thickness = int(np.ptp(coords[:, 1])) + 1

                    # 合并：类型+方向+厚度
                    merged = False
                    for i, (etype, edir, elen, ethk) in enumerate(segments):
                        if etype == opening_type and edir == opening_dir and ethk == thickness:
                            segments[i] = (etype, edir, elen + length, ethk)
                            merged = True
                            break
                    if not merged:
                        segments.append((opening_type, opening_dir, length, thickness))

        # 过滤异常
        segments = [seg for seg in segments if seg[3] <= seg[2]]
        result[rid] = segments

    return result
