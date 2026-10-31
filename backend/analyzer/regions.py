"""区域检测：文字带、装饰图标、头像椭圆。

所有检测结果都会返回给前端，用户可以在界面上拖动/缩放重新框选，
再让后端按新区域重算 —— 自动检测只是给个起点。
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def detect_text_region(frames: list[np.ndarray], art_alpha: np.ndarray,
                       lower_ratio: float = 0.38, rel_thr: float = 0.45) -> dict:
    """在画面下半部分找「文字带」。

    可靠信号：文字是画面里最亮的一批像素，在全宽行剖面上形成一个明显的台阶；
    而上方的美术（羽毛）虽然也亮，但亮像素数量少且分散。
    """
    if not frames:
        return {"box": [0, 0, 0, 0], "score": 0.0, "rows": []}
    ref = np.median(np.stack(frames).astype(np.float32), axis=0).astype(np.uint8)
    H, W = ref.shape[:2]
    gray = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY) if cv2 is not None else \
        0.299 * ref[..., 0] + 0.587 * ref[..., 1] + 0.114 * ref[..., 2]

    # 很亮的像素才算文字（羽毛的亮度低于此）
    thr = float(np.percentile(gray, 99.5)) * 0.72
    thr = max(thr, 150.0)
    counts = (gray > thr).sum(axis=1)

    y0 = int(H * lower_ratio)
    region = counts[y0:]
    if region.size == 0:
        return {"box": [0, 0, 0, 0], "score": 0.0, "rows": []}
    hi = float(np.percentile(region, 96))
    thr_row = max(hi * rel_thr, 12.0)

    # 找出所有候选行段，按「平均亮像素密度」评分（文字带比羽毛带密得多）
    best = (0.0, 0, 0, 0.0)
    i = 0
    while i < region.size:
        if region[i] >= thr_row:
            j = i
            while j < region.size and region[j] >= thr_row:
                j += 1
            seg = region[i:j]
            if j - i >= 6:
                density = float(seg.mean())          # 每行平均亮像素数
                span = j - i
                score = density * min(1.0, span / 24.0)
                if score > best[0]:
                    best = (score, y0 + i, y0 + j, density)
            i = j
        else:
            i += 1
    if best[0] <= 0:
        return {"box": [0, int(H * 0.62), W, int(H * 0.80)], "score": 0.0, "rows": []}

    ry0, ry1 = best[1], best[2]
    # 行内再找列范围
    band = (gray[ry0:ry1] > thr)
    cols = np.nonzero(band.sum(axis=0) > 0)[0]
    if len(cols) < 10:
        return {"box": [0, ry0, W, ry1], "score": 0.2, "rows": [ry0, ry1]}
    x0, x1 = int(cols.min()), int(cols.max()) + 1
    # 左右各切掉 3% 宽（可能混进边缘装饰）
    pad = int(W * 0.012)
    return {"box": [x0 + pad, ry0, x1 - pad, ry1],
            "score": round(float(best[3] / max(1.0, hi)), 3),
            "rows": [ry0, ry1],
            "brightThreshold": round(thr, 1)}


def detect_avatar_ellipse(frames: list[np.ndarray], art_alpha: np.ndarray,
                          text_box: list[int]) -> dict:
    """在美术层中央找头像椭圆（低纹理、颜色成片的区域）。"""
    if not frames:
        return {"box": [0, 0, 0, 0], "cx": 0, "cy": 0, "rx": 0, "ry": 0}
    ref = np.median(np.stack(frames).astype(np.float32), axis=0).astype(np.uint8)
    H, W = ref.shape[:2]
    gray = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY) if cv2 is not None else \
        0.299 * ref[..., 0] + 0.587 * ref[..., 1] + 0.114 * ref[..., 2]

    # 美术层的重心作为椭圆中心先验
    ys, xs = np.nonzero(art_alpha > 0.5)
    if len(xs) == 0:
        return {"box": [0, 0, 0, 0], "cx": W / 2, "cy": H / 2, "rx": W * 0.07, "ry": H * 0.1}
    cx0, cy0 = float(xs.mean()), float(ys.mean())

    # 平滑度：局部标准差
    g = gray.astype(np.float32)
    k = 9
    mu = cv2.blur(g, (k, k)) if cv2 is not None else g
    mu2 = cv2.blur(g * g, (k, k)) if cv2 is not None else g * g
    std = np.sqrt(np.maximum(mu2 - mu * mu, 0))

    smooth = (std < 16) & (art_alpha > 0.6)
    # 只在美术重心附近找
    yy, xx = np.mgrid[0:H, 0:W]
    near = ((xx - cx0) ** 2 / (W * 0.16) ** 2 + (yy - cy0) ** 2 / (H * 0.22) ** 2) < 1.0
    smooth &= near
    smooth = cv2.morphologyEx(smooth.astype(np.uint8), cv2.MORPH_OPEN,
                              np.ones((5, 5), np.uint8)) if cv2 is not None else smooth
    n, labels, stats, cent = cv2.connectedComponentsWithStats(smooth, 8)
    best, best_score = None, -1
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 400:
            continue
        bx, by, bw, bh = (stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],
                          stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        fill = area / max(1, bw * bh)
        score = area * (0.4 + fill)
        if score > best_score:
            best_score = score
            best = (bx, by, bw, bh)
    if best is None:
        cx, cy = cx0, cy0
        rx, ry = W * 0.065, H * 0.105
    else:
        bx, by, bw, bh = best
        cx, cy = bx + bw / 2, by + bh / 2
        rx, ry = bw / 2 * 1.06, bh / 2 * 1.12
    return {"box": [int(cx - rx), int(cy - ry), int(cx + rx), int(cy + ry)],
            "cx": round(float(cx), 1), "cy": round(float(cy), 1),
            "rx": round(float(rx), 1), "ry": round(float(ry), 1)}


def clamp_box(box, W: int, H: int) -> list[int]:
    x0, y0, x1, y1 = box
    x0 = max(0, min(int(x0), W - 1)); y0 = max(0, min(int(y0), H - 1))
    x1 = max(x0 + 1, min(int(x1), W)); y1 = max(y0 + 1, min(int(y1), H))
    return [x0, y0, x1, y1]
