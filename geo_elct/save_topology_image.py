import os
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
from typing import List, Dict, Tuple
import cv2

__all__ = [
    "build_topology_graph",
    "save_topology_image",
    "save_to_excel",
    "save_rooms_excel",
    "compose_room_stats",
]


# --------------------------------------------------------------------------------------
# 1) 构图（可选）
# --------------------------------------------------------------------------------------

def build_topology_graph(rooms: List[Dict], edges: List[Dict]):
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("build_topology_graph 依赖 networkx，请先 pip install networkx")

    G = nx.Graph()
    for r in rooms:
        G.add_node(r["id"], area=r["area"], room_type=r.get("room_type", ""))

    type_map = {"door": "门", "window": "窗", "wall": "墙", "opening": "开敞"}
    pair2types = defaultdict(set)
    for e in edges:
        pair = tuple(sorted((e["roomA"], e["roomB"])))
        pair2types[pair].add(type_map.get(e["type"], e["type"]))

    for (a, b), tset in pair2types.items():
        G.add_edge(a, b, types="|".join(sorted(tset)))
    return G


# --------------------------------------------------------------------------------------
# 2) 基础工具
# --------------------------------------------------------------------------------------

def _compute_room_centroids(region_id_map: np.ndarray) -> Dict[int, Tuple[float, float]]:
    """返回房间ID → (y, x) 的质心坐标（图像坐标系）"""
    centroids: Dict[int, Tuple[float, float]] = {}
    ids = np.unique(region_id_map)
    ids = ids[ids > 0]
    for rid in ids:
        ys, xs = np.where(region_id_map == rid)
        if ys.size == 0:
            continue
        cy = ys.mean()
        cx = xs.mean()
        centroids[int(rid)] = (float(cy), float(cx))
    return centroids


def _pick_times_new_roman(font_path: str | None, size: int) -> ImageFont.FreeTypeFont:
    """优先使用 Times New Roman；若找不到则回退系统常见路径/默认字体。
    - Windows 常见路径: C:/Windows/Fonts/times.ttf 或 timesbd.ttf 或 timesi.ttf
    - macOS: /System/Library/Fonts/Supplemental/Times New Roman.ttf
    - Linux: /usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf (若已安装)
    """
    candidates = []
    if font_path:
        candidates.append(font_path)
    candidates.extend([
        "C:/Windows/Fonts/timesbd.ttf",
        "C:/Windows/Fonts/times.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/Library/Fonts/Times New Roman.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",  # 接近的回退
    ])
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------------------
# 3) 论文增强版绘制：质心放置 + 半径尽可能大（不越界）+ Halo + 高亮配色
# --------------------------------------------------------------------------------------

def save_topology_image(region_id_map: np.ndarray,
                        rooms: List[Dict],
                        edges: List[Dict],
                        rough_img_path: str,
                        save_path: str,
                        font_path: str | None = None,
                        *,
                        node_margin_px: int = 3,
                        edge_width_px: int = 14,
                        node_shrink_ratio: float = 0.85,
                        node_fill_rgba: tuple = (255, 210, 120, 235),  # 柔和暖黄
                        node_outline_rgba: tuple = (0, 0, 0, 255),
                        edge_blue_rgba: tuple = (0, 140, 255, 255),
                        edge_gray_rgba: tuple = (80, 80, 80, 255),  # 加深灰
                        edge_green_rgba: tuple = (0, 200, 100, 255),
                        halo_extra_px: int = 6,
                        area_ratio_limit: float = 2.5  # 面积差距阈值，>此值则跳过更小的基准
                        ) -> None:
    """论文增强版：质心放置，自动适配字号，圆片略缩小，管道加粗提亮。
    * 每个单图内优先统一圆半径；当最小房间的圆片与其他房间 **面积差距过大** 时，
      选择第2小（或第3小、...）作为统一基准，直到满足阈值；
      极小房间仍用自身最小半径，其它房间统一为所选基准半径。
    * 数字使用文本中心锚点，确保位于圆心。
    其它逻辑保持不变。
    """
    if len(rooms) == 0:
        print(f"[WARN] {rough_img_path}: 无房间，跳过保存拓扑图")
        return

    # 背景
    bg = cv2.imread(rough_img_path, cv2.IMREAD_UNCHANGED)
    if bg is None:
        raise FileNotFoundError(rough_img_path)
    bg_rgba = cv2.cvtColor(bg, cv2.COLOR_BGRA2RGBA) if (bg.ndim == 3 and bg.shape[2] == 4) \
        else cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)
    canvas = Image.fromarray(bg_rgba)
    draw = ImageDraw.Draw(canvas, "RGBA")

    id2center = _compute_room_centroids(region_id_map)
    ids = np.unique(region_id_map)
    ids = ids[ids > 0]

    # 每个房间的可用最大半径（距边界距离 - 留白）
    id2safeR = {}
    for rid in ids:
        if rid not in id2center:
            continue
        mask = (region_id_map == rid).astype(np.uint8)
        if mask.sum() == 0:
            continue
        dt = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
        cy, cx = id2center[rid]
        iy, ix = int(round(cy)), int(round(cx))
        iy = np.clip(iy, 0, dt.shape[0] - 1)
        ix = np.clip(ix, 0, dt.shape[1] - 1)
        safeR = float(dt[iy, ix]) - float(node_margin_px)
        if safeR <= 0:
            y0, y1 = max(0, iy - 3), min(dt.shape[0], iy + 4)
            x0, x1 = max(0, ix - 3), min(dt.shape[1], ix + 4)
            safeR = np.max(dt[y0:y1, x0:x1]) - float(node_margin_px)
        id2safeR[int(rid)] = max(0.0, safeR)

    # 画边：Halo + 主线（不变）
    pair2types = defaultdict(set)
    for e in edges:
        pair = tuple(sorted((e["roomA"], e["roomB"])) )
        pair2types[pair].add(e["type"])

    for (a, b), tset in pair2types.items():
        if a not in id2center or b not in id2center:
            continue
        y1, x1 = id2center[a]
        y2, x2 = id2center[b]

        has_wall = "wall" in tset
        has_doorwin = any(t in tset for t in ("door", "window"))
        if has_wall and has_doorwin:
            color = edge_blue_rgba
        elif has_wall:
            color = edge_gray_rgba
        else:
            color = edge_green_rgba

        draw.line((x1, y1, x2, y2), fill=(255, 255, 255, 235), width=int(edge_width_px + halo_extra_px))
        draw.line((x1, y1, x2, y2), fill=color, width=int(edge_width_px))

    # ——自适应选择统一圆大小的“第 k 小”——
    id2maxR = {rid: id2safeR[rid] * node_shrink_ratio for rid in id2safeR}
    base_rad = None
    if len(id2maxR) > 0:
        # 按半径升序排列 (rid, rad)
        sorted_r = sorted(id2maxR.items(), key=lambda x: x[1])
        n = len(sorted_r)
        # 从最小开始，若与"其余更大房间"的平均面积差距过大，则提升到下一档
        # 面积 ∝ r^2，因此比较 (mean_r_big^2 / r_k^2)
        for k in range(n):
            r_k = max(1e-6, sorted_r[k][1])  # 避免除零
            if k == n - 1:
                # 只有一个房间或已到最后，直接用这个
                base_rad = r_k
                break
            bigger = [r for _, r in sorted_r[k+1:]]
            mean_big = sum(bigger) / len(bigger)
            area_ratio = (mean_big * mean_big) / (r_k * r_k)
            if area_ratio <= area_ratio_limit:
                base_rad = r_k
                break
        # 给个下限，避免太小影响可读性
        base_rad = max(10.0, float(base_rad))

    # 画节点：使用 base_rad 统一；极小房间自动更小（min(base_rad, safeR_node)）
    for r in rooms:
        rid = r["id"]
        if rid not in id2center:
            continue
        cy, cx = id2center[rid]
        safeR_node = id2safeR.get(rid, 0.0) * node_shrink_ratio
        if base_rad is None:
            rad = safeR_node
        else:
            rad = float(min(base_rad, safeR_node))

        # 自动调整字号（基于最终 rad）
        txt = str(rid)
        font_size = max(12, int(rad * 1.1))
        font = _pick_times_new_roman(font_path, font_size)

        # 用文本中心锚点测量与绘制，确保居中
        def _measure_centered(t: str, f):
            try:
                bb = draw.textbbox((0, 0), t, font=f, anchor='mm')
                return bb[2] - bb[0], bb[3] - bb[1], True
            except TypeError:
                bb = draw.textbbox((0, 0), t, font=f)
                return bb[2] - bb[0], bb[3] - bb[1], False

        tw, th, has_anchor = _measure_centered(txt, font)
        while max(tw, th) > 1.6 * rad and font_size > 6:
            font_size -= 1
            font = _pick_times_new_roman(font_path, font_size)
            tw, th, has_anchor = _measure_centered(txt, font)

        # 绘制白底 + 黄色圆
        draw.ellipse((cx - (rad + 2), cy - (rad + 2), cx + (rad + 2), cy + (rad + 2)),
                     fill=(255, 255, 255, 255))
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                     fill=node_fill_rgba, outline=node_outline_rgba, width=3)

        # 居中放文字
        if has_anchor:
            draw.text((float(cx), float(cy)), txt, fill=(0, 0, 0, 255), font=font, anchor='mm')
        else:
            draw.text((cx - tw / 2, cy - th / 2), txt, fill=(0, 0, 0, 255), font=font)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    canvas.save(save_path)

# --------------------------------------------------------------------------------------
# 4) Excel 输出（保持与你现有逻辑一致）
# --------------------------------------------------------------------------------------

def save_to_excel(edges: List[Dict], save_path: str) -> None:
    """列: 房间1 | 房间2 | 连接类型 | 数量 | length | width (墙体分段合并)"""
    en = {"door": "Door", "window": "Window", "wall": "Wall", "opening": "Opening"}

    aggregated: Dict[Tuple[int, int, str], list] = {}
    for e in edges:
        key = (e["roomA"], e["roomB"], e["type"])
        if e["type"] == "wall" and "segments" in e:
            aggregated.setdefault(key, []).extend(e["segments"])
        else:
            aggregated.setdefault(key, []).append({"length": e["length"], "width": e["width"]})

    rows = []
    for (roomA, roomB, conn_type), segments in aggregated.items():
        row = {"RoomA": roomA, "RoomB": roomB, "ConnectionType": en.get(conn_type, conn_type), "Count": len(segments)}
        for i, seg in enumerate(segments, 1):
            row[f"Length_{i}"] = seg["length"]
            row[f"Width_{i}"] = seg["width"]
        rows.append(row)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    pd.DataFrame(rows).to_excel(save_path, index=False)


# --------------------------------------------------------------------------------------
# 5) 房间属性合并 + 导出
# --------------------------------------------------------------------------------------

def compose_room_stats(ext_wall_stats, opening_stats):
    """
    返回 combined_stats: { room_id: {"walls": [...], "openings": [...]} }
      - walls    : [(wall_dir, length_px, thickness_px), ...]
      - openings : [(type('door'/'window'), direction, length_px, thickness_px), ...]
    """
    combined = {}
    rids = set(ext_wall_stats.keys()) | set(opening_stats.keys())
    for rid in rids:
        combined[rid] = {
            "walls": ext_wall_stats.get(rid, []),
            "openings": opening_stats.get(rid, [])
        }
    return combined


def save_rooms_excel(rooms, room_stats, out_path, sheet_rooms_name: str = "Rooms") -> None:
    """
    单表 Rooms：
      RoomID | Type | Area | Perimeter | WallDir_* / ExtWallLength_* / ExtWallWidth_* | OpenType_* / OpenDir_* / OpenLength_* / OpenWidth_*
    """
    en_open = {"door": "Door", "window": "Window"}

    max_walls = 0
    max_opens = 0
    for r in rooms:
        rid = r["id"]
        stats = room_stats.get(rid, {"walls": [], "openings": []})
        max_walls = max(max_walls, len(stats.get("walls", [])))
        max_opens = max(max_opens, len(stats.get("openings", [])))

    rows = []
    for r in rooms:
        rid = r["id"]
        stats = room_stats.get(rid, {"walls": [], "openings": []})
        wall_segments = stats.get("walls", [])
        open_segments = stats.get("openings", [])

        row = {"RoomID": rid, "Type": r.get("room_type", ""), "Area": r["area"], "Perimeter": r["perimeter"]}

        for i in range(1, max_walls + 1):
            if i <= len(wall_segments):
                wall_dir, length, thickness = wall_segments[i - 1]
                row[f"WallDir_{i}"] = wall_dir
                row[f"ExtWallLength_{i}"] = int(length)
                row[f"ExtWallWidth_{i}"] = int(thickness)
            else:
                row[f"WallDir_{i}"] = ""
                row[f"ExtWallLength_{i}"] = None
                row[f"ExtWallWidth_{i}"] = None

        for j in range(1, max_opens + 1):
            if j <= len(open_segments):
                typ, direc, length, thickness = open_segments[j - 1]
                row[f"OpenType_{j}"] = en_open.get(str(typ).lower(), typ)
                row[f"OpenDir_{j}"] = direc
                row[f"OpenLength_{j}"] = int(length)
                row[f"OpenWidth_{j}"] = int(thickness)
            else:
                row[f"OpenType_{j}"] = ""
                row[f"OpenDir_{j}"] = ""
                row[f"OpenLength_{j}"] = None
                row[f"OpenWidth_{j}"] = None

        rows.append(row)

    base_cols = ["RoomID", "Type", "Area", "Perimeter"]
    wall_cols = []
    for i in range(1, max_walls + 1):
        wall_cols += [f"WallDir_{i}", f"ExtWallLength_{i}", f"ExtWallWidth_{i}"]
    open_cols = []
    for j in range(1, max_opens + 1):
        open_cols += [f"OpenType_{j}", f"OpenDir_{j}", f"OpenLength_{j}", f"OpenWidth_{j}"]

    df = pd.DataFrame(rows)
    df = df[base_cols + wall_cols + open_cols]

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with pd.ExcelWriter(out_path) as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_rooms_name)
