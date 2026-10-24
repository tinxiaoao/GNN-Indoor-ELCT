import numpy as np
import cv2
from typing import List, Dict, Tuple, Set

from . import DEFAULT_OPENING_AGGREGATION, OPENING_AGGREGATIONS

"""
detect_adjacency.py  ‑ 统一室内拓扑提取模块
------------------------------------------------
功能:
    1. 门 / 窗  (door / window)
    2. 墙体隔墙 (wall)
    3. 无墙开敞 (opening)

新特性:
    • 限制墙体射线最大穿透长度 = min_avg_len (所有房间最小平均边长)。
    • 射线方向采用 4‑邻域 (N/E/S/W) 减少沿墙滑行误连。

调用示例:
    region_map, rooms, min_avg_len = extract_rooms(wall_label_array)
    edges = detect_adjacency(region_map, wall_array, icon_array, wall_label_array, min_avg_len)
返回:
    List[Dict]  每条记录字段:
        roomA, roomB, type (door/window/wall/opening), length, width
"""

# ----------------------------
# 常量
# ----------------------------
_DIRECTIONS: List[Tuple[int, int]] = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 4‑邻域
_WALL_CODE: int = 2  # palette 中: 墙体
_BLOCKED_CODES: Set[int] = {0, 1, 8, 50}  # palette 中: 室外 / 阻断


# ======================================================================
# 辅助函数 —— 墙体隔墙检测
# ======================================================================

def _get_boundary_pixels(region_map: np.ndarray, room_id: int) -> List[Tuple[int, int]]:
    """返回 room_id 在 region_map 中的边界像素坐标列表 (4 邻域判定)"""
    H, W = region_map.shape
    coords = np.argwhere(region_map == room_id)
    boundary = []
    for x, y in coords:
        for dx, dy in _DIRECTIONS:
            nx, ny = x + dx, y + dy
            if nx < 0 or nx >= H or ny < 0 or ny >= W or region_map[nx, ny] != room_id:
                boundary.append((x, y))
                break
    return boundary


def _shoot_ray(region_map: np.ndarray,
               palette_map: np.ndarray,
               start: Tuple[int, int],
               direction: Tuple[int, int],
               self_id: int,
               max_wall_thickness: float):
    """沿给定方向从 start 像素发射射线, 若成功穿墙到另一房间则返回 (target_id, wall_pixels_set)"""
    H, W = region_map.shape
    dx, dy = direction
    x, y = start[0] + dx, start[1] + dy

    # 初步过滤
    if x < 0 or x >= H or y < 0 or y >= W:
        return None
    if region_map[x, y] == self_id:
        return None  # 切向/内向
    if region_map[x, y] == 0 and palette_map[x, y] in _BLOCKED_CODES and palette_map[x, y] != _WALL_CODE:
        return None  # 首步阻断

    wall_pixels: Set[Tuple[int, int]] = set()
    wall_count = 0
    max_wall_thickness = int(round(max_wall_thickness))

    while True:
        # 越界终止
        if x < 0 or x >= H or y < 0 or y >= W:
            return None

        rid = region_map[x, y]
        pal = palette_map[x, y]

        # 撞到房间
        if rid != 0:
            if rid == self_id:
                return None  # 凹形回到自身
            if wall_pixels:
                return rid, wall_pixels  # 成功穿墙
            return None  # 没穿墙直接相邻

        # 非房间像素处理
        if pal in _BLOCKED_CODES:
            return None
        if pal == _WALL_CODE:
            wall_pixels.add((x, y))
            wall_count += 1
            if wall_count >= max_wall_thickness:
                return None  # 超过允许墙厚

        # 前进
        x += dx
        y += dy


def _wall_edges(region_map: np.ndarray,
                palette_map: np.ndarray,
                max_wall_thickness: float) -> List[Dict]:
    """遍历房间 → 边界像素 → 射线 , 收集墙体隔墙，逐段计算长度和厚度"""
    edge_map: Dict[Tuple[int, int], Set[Tuple[int, int]]] = {}
    for rid in [i for i in np.unique(region_map) if i > 0]:
        for (x, y) in _get_boundary_pixels(region_map, rid):
            for dx, dy in _DIRECTIONS:
                nx, ny = x + dx, y + dy
                # 内向或越界方向直接跳过
                if not (0 <= nx < region_map.shape[0] and 0 <= ny < region_map.shape[1]):
                    continue
                if region_map[nx, ny] == rid:
                    continue
                res = _shoot_ray(region_map, palette_map, (x, y), (dx, dy), rid, max_wall_thickness)
                if res is None:
                    continue
                tgt, wall_px = res
                if not wall_px:
                    continue
                key = (rid, tgt) if rid < tgt else (tgt, rid)
                edge_map.setdefault(key, set()).update(wall_px)

    edges: List[Dict] = []

    # 新逻辑: 墙体像素区域局部连通域分析并逐段计算长度和厚度
    for (a, b), px in edge_map.items():
        wall_mask = np.zeros(region_map.shape, dtype=np.uint8)
        for p in px:
            wall_mask[p] = 1

        # 局部连通域分析
        num_labels, labels_im = cv2.connectedComponents(wall_mask, connectivity=4)

        for lbl in range(1, num_labels):
            coords = np.argwhere(labels_im == lbl)
            min_r, min_c = coords.min(axis=0)
            max_r, max_c = coords.max(axis=0)

            height = max_r - min_r + 1
            width = max_c - min_c + 1

            # ----------- 几何法厚度计算 -----------
            area = len(coords)                    # 墙段像素总数
            length_px = max(height, width)        # 墙段长度
            thickness_value = int(round(area / length_px))
            thickness_value = max(thickness_value, 1)  # 最小1像素
            thickness_value = min(thickness_value, min(height, width))  # 不超过墙段短边

            edges.append({
                "roomA": int(a),
                "roomB": int(b),
                "type": "wall",
                "length": int(max(height, width)),
                "width": int(thickness_value)
            })

    return edges


def detect_adjacency(region_id_map: np.ndarray,
                     wall_array: np.ndarray,
                     icon_array: np.ndarray,
                     wall_label_array: np.ndarray,
                     max_wall_thickness: float,
                     *, opening_aggregation: str = DEFAULT_OPENING_AGGREGATION) -> List[Dict]:
    """主入口: 返回门/窗/墙/开敞连接的列表"""

    if opening_aggregation not in OPENING_AGGREGATIONS:
        raise ValueError(f"Unknown opening aggregation: {opening_aggregation}")

    region_id_map = region_id_map.astype(np.int32)
    wall_array = wall_array.astype(np.uint8)
    icon_array = icon_array.astype(np.uint8)
    wall_label_array = wall_label_array.astype(np.uint8)

    edges: List[Dict] = []

    # -------------------- 1️⃣ 门 / 窗 --------------------
    def _detect_icon_edges(mask: np.ndarray, icon_type: str):
        """Group components by room pair, type and thickness; sum length only.

        ``num`` counts raster components in each group. ``legacy_width_sum``
        explicitly reproduces the historical sum of both length and width.
        """
        n_lbl, lbl_map = cv2.connectedComponents(mask, connectivity=4)
        agg: Dict[Tuple[int, int, str, int], Dict[str, int]] = {}
        for lbl in range(1, n_lbl):
            ys, xs = np.where(lbl_map == lbl)
            if ys.size == 0:
                continue
            neighbor = set()
            for y, x in zip(ys, xs):
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < region_id_map.shape[0] and 0 <= nx < region_id_map.shape[1]:
                        rid = region_id_map[ny, nx]
                        if rid > 0:
                            neighbor.add(int(rid))
            if len(neighbor) != 2:
                continue  # 忽略与房间不足两侧相邻的连通块
            a, b = sorted(list(neighbor))
            height = ys.max() - ys.min() + 1
            width = xs.max() - xs.min() + 1
            length = max(height, width)
            thick = min(height, width)
            group_thickness = int(thick) if opening_aggregation == "by_thickness_v1" else 0
            key = (a, b, icon_type, group_thickness)
            if key not in agg:
                agg[key] = {"num": 0, "length": 0, "width": 0}
            agg[key]["num"] += 1
            agg[key]["length"] += int(length)
            if opening_aggregation == "by_thickness_v1":
                agg[key]["width"] = int(thick)
            else:
                agg[key]["width"] += int(thick)

        # 输出聚合结果
        for (a, b, _type, _thickness), stats in agg.items():
            edges.append({
                "roomA": a,
                "roomB": b,
                "type": _type,
                "num": stats["num"],
                "length": stats["length"],
                "width": stats["width"]
            })

    _detect_icon_edges((icon_array == 1).astype(np.uint8), "door")
    _detect_icon_edges((icon_array == 2).astype(np.uint8), "window")

    # -------------------- 2️⃣ 墙体隔墙 --------------------
    edges.extend(_wall_edges(region_id_map, wall_label_array, max_wall_thickness))

    # -------------------- 3️⃣ 开敞相邻 --------------------
    open_pairs: Dict[Tuple[int, int], List[Tuple[int, int]]] = {}
    H, W = region_id_map.shape
    for y in range(H):
        for x in range(W):
            rid = region_id_map[y, x]
            if rid == 0:
                continue
            # 右邻
            if x + 1 < W and region_id_map[y, x + 1] not in (0, rid) and wall_array[y, x + 1] == 0:
                key = tuple(sorted((int(rid), int(region_id_map[y, x + 1]))))
                open_pairs.setdefault(key, []).append((y, x))
            # 下邻
            if y + 1 < H and region_id_map[y + 1, x] not in (0, rid) and wall_array[y + 1, x] == 0:
                key = tuple(sorted((int(rid), int(region_id_map[y + 1, x]))))
                open_pairs.setdefault(key, []).append((y, x))

    for (a, b), pts in open_pairs.items():
        mask = np.zeros_like(region_id_map, dtype=np.uint8)
        for y, x in pts:
            mask[y, x] = 1
        n_lbl, lbl_map = cv2.connectedComponents(mask, connectivity=4)
        for lbl in range(1, n_lbl):
            ys, xs = np.where(lbl_map == lbl)
            if ys.size == 0:
                continue
            height = ys.max() - ys.min() + 1
            width = xs.max() - xs.min() + 1
            edges.append({
                "roomA": a,
                "roomB": b,
                "type": "opening",
                "length": int(max(height, width)),
                "width": int(min(height, width))
            })

    return edges
