"""图层分离：把「美术主体」和「背景粒子 / 文字」分开。

思路：
  * persist[y,x] = 该像素在多少比例的帧里是亮的 → 静态美术高，瞬时粒子低
  * art_rgb      = 逐像素时间中值 → 抹掉会动的粒子，保留美术本体
  * art_alpha    = 亮度抠像 × persist 门限 → 只保留持续存在的美术
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _smoothstep(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    t = np.clip((x - lo) / max(1e-6, hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def luma(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def separate_art(frames: list[np.ndarray], min_area: int = 400,
                 remove_green_glow: bool = True) -> dict:
    """分离「美术主体」与「背景粒子 / 文字辉光」。

    四步：
      1. 亮度抠像（暗部软化，白羽高光保真）
      2. 蓝色 bokeh 粒子抑制（按色相 B-(R+G)/2）
      3. 黄绿色文字辉光剥离（按 G>R 且 G>B；金色 R>G、蓝白 B>=G 都不受影响）
      4. 连通域去噪：删掉面积过小的孤立块（残留粒子）
    """
    if not frames:
        raise RuntimeError("没有帧")
    stack = np.stack(frames).astype(np.float32)
    lum = np.stack([luma(f) for f in stack])
    # 用 75 分位而不是中值：细羽毛在帧间会闪，中值会把它们压暗到抠不出来
    ref = np.percentile(stack, 75, axis=0)
    R, G, B = ref[..., 0], ref[..., 1], ref[..., 2]
    L = luma(ref)
    BD = B - (R + G) / 2.0

    alpha = _smoothstep(L, 5.0, 62.0)

    # 持续性：静态的东西（美术、蓝色音符）每帧都在，粒子只是一闪而过
    thr_p = float(np.percentile(lum, 72))
    persist = (lum > thr_p).mean(axis=0)

    # 蓝色粒子抑制：只杀「蓝色 + 瞬时」的像素，静态蓝色装饰（音符）保留
    kill = _smoothstep(BD, 14, 45) * (1 - _smoothstep(L, 120, 200)) \
        * (1 - _smoothstep(persist, 0.30, 0.70))
    alpha = alpha * (1 - kill)

    # 黄绿色文字辉光剥离
    if remove_green_glow:
        green = _smoothstep(G - R + 6, 0, 10) * _smoothstep(G - B - 10, 0, 14)
        alpha = alpha * (1 - green * 0.96)

    # 连通域：删掉孤立小块
    if cv2 is not None:
        m = (alpha > 0.12).astype(np.uint8)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        keep = np.zeros_like(m)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= min_area:
                keep |= (labels == i)
        alpha = alpha * keep

    return {
        "alpha": alpha.astype(np.float32),
        "rgb": ref.astype(np.uint8),
        "persist": (lum > np.percentile(lum, 72)).mean(axis=0).astype(np.float32),
        "threshold": float(np.percentile(lum, 72)),
        "lum": L.astype(np.float32),
    }


def strip_region(alpha: np.ndarray, rgb: np.ndarray, box: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """把某个矩形区域从美术层里抠掉（用于去掉原文字）。返回 (新alpha, 新rgb)。"""
    x0, y0, x1, y1 = box
    h, w = alpha.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    a = alpha.copy()
    r = rgb.copy()
    a[y0:y1, x0:x1] = 0.0
    r[y0:y1, x0:x1] = 0
    return a, r


def find_colored_specks(alpha: np.ndarray, rgb: np.ndarray, box: tuple[int, int, int, int],
                        min_area: int = 24) -> list[dict]:
    """在指定区域里找出「小的、饱和的」独立块 —— 通常就是星星/音符这类装饰图标。"""
    import cv2
    x0, y0, x1, y1 = box
    h, w = alpha.shape
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    sub_rgb = rgb[y0:y1, x0:x1]
    sub_a = alpha[y0:y1, x0:x1]
    if sub_rgb.size == 0:
        return []
    hsv = cv2.cvtColor(sub_rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1]
    val = hsv[..., 2]
    mask = ((sub_a > 0.5) & (sat > 42) & (val > 60)).astype(np.uint8) * 255
    n, labels, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        bx = int(stats[i, cv2.CC_STAT_LEFT]) + x0
        by = int(stats[i, cv2.CC_STAT_TOP]) + y0
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        # 颜色 = 该块内像素的中位色
        m = labels[y0 - by:y1 - by, x0 - bx:x1 - bx] == i
        cols = sub_rgb[m] if m.any() else sub_rgb.reshape(-1, 3)
        out.append({
            "box": [bx, by, bx + bw, by + bh],
            "area": area,
            "color": [int(v) for v in np.median(cols, axis=0)],
            "sat": float(np.median(hsv[..., 1][m])) if m.any() else 0.0,
        })
    return out


# ------------------------------------------------------------------
# 文字辉光检测
# 灯牌这类素材的美术主色是「金(20~55°) + 白 + 蓝灰(200~220°)」，
# 而文字辉光是「黄绿色(50~115°)」，色相上是分开的，靠这个把文字从美术里剥离。
TEXT_HUE_LO, TEXT_HUE_HI = 48, 118


def detect_text_glow(rgb: np.ndarray, art_alpha: np.ndarray,
                     lower_ratio: float = 0.30, min_area: int = 400) -> dict:
    """找出文字（及其辉光）所在的区域。

    返回 {'mask': 布尔图, 'box': [x0,y0,x1,y1], 'hue': 主色相, 'score': 置信度}
    """
    H, W = rgb.shape[:2]
    if cv2 is None:
        return {"mask": np.zeros((H, W), bool), "box": [0, 0, 0, 0], "hue": 0, "score": 0.0}

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, sat, val = hsv[..., 0].astype(np.int32), hsv[..., 1], hsv[..., 2]

    inband = (hue >= TEXT_HUE_LO) & (hue <= TEXT_HUE_HI) & (sat > 55) & (val > 70)
    below = np.zeros((H, W), bool)
    below[int(H * lower_ratio):] = True
    mask = (inband & below).astype(np.uint8)

    # 形态学连成一片
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    n, labels, stats, cent = cv2.connectedComponentsWithStats(mask, 8)
    best, best_score = None, 0.0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < min_area:
            continue
        # 越宽、越靠下、越成片越可信
        score = (w / W) * 2.0 + (area / (H * W)) * 3.0 + (y / H) * 0.6
        if score > best_score:
            best_score = score
            best = (i, int(x), int(y), int(w), int(h))
    if best is None:
        return {"mask": np.zeros((H, W), bool), "box": [0, 0, 0, 0], "hue": 0, "score": 0.0}

    i, x, y, w, h = best
    sel = labels[y:y + h, x:x + w] == i
    mh = float(np.median(hue[y:y + h, x:x + w][sel]))
    out = np.zeros((H, W), bool)
    out[y:y + h, x:x + w] = sel
    # 往上下扩一点，把字形本体也包进来（字是白/米色，不在色相带里）
    grow = cv2.dilate(out.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21)))
    return {"mask": grow.astype(bool), "box": [x, y, x + w, y + h],
            "hue": round(mh, 1), "score": round(best_score, 3)}


def apply_text_mask(alpha: np.ndarray, rgb: np.ndarray,
                    text_mask: np.ndarray, feather: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """把文字区域从美术层里挖掉（保留周围羽毛的软边）。"""
    if text_mask is None or not text_mask.any():
        return alpha, rgb
    m = text_mask.astype(np.uint8)
    if cv2 is not None:
        m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (feather * 2 + 1,) * 2))
    a = alpha.copy()
    r = rgb.copy()
    a[m > 0] = 0.0
    r[m > 0] = 0
    return a, r


def strip_text_glyphs(alpha: np.ndarray, rgb: np.ndarray,
                      text_box: tuple[int, int, int, int],
                      bright_thr: float = 200.0, grow: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """把文字「字形本体」从美术层里剥离。

    只抠文字自身的亮像素（+ 一点膨胀吃掉描边），绝不做整块矩形切割，
    所以吊坠、羽尖这些美术细节一根都不会少。
    """
    if cv2 is None:
        return alpha, rgb
    H, W = alpha.shape
    x0, y0, x1, y1 = text_box
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return alpha, rgb
    reg = rgb[y0:y1, x0:x1].astype(np.float32)
    lum = 0.299 * reg[..., 0] + 0.587 * reg[..., 1] + 0.114 * reg[..., 2]
    m = ((lum > bright_thr) & (alpha[y0:y1, x0:x1] > 0.2)).astype(np.uint8)
    # 文字的黄绿辉光残影也要一起抹掉
    rr, gg, bb = reg[..., 0], reg[..., 1], reg[..., 2]
    greenish = (_smoothstep(gg - rr + 6, 0, 10) * _smoothstep(gg - bb - 10, 0, 14) > 0.35)
    m = np.maximum(m, (greenish & (alpha[y0:y1, x0:x1] > 0.05)).astype(np.uint8))
    if m.sum() < 30:
        return alpha, rgb
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (grow * 2 + 1,) * 2))
    a = alpha.copy()
    r = rgb.copy()
    sel = m > 0
    a[y0:y1, x0:x1][sel] = 0.0
    r[y0:y1, x0:x1][sel] = 0
    return a, r
