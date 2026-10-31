"""背景粒子参数测量：流速、密度、尺寸、颜色。"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _blobs(gray: np.ndarray, outside: np.ndarray, thr: float,
           min_area: int = 2, max_area: int = 900):
    """在远离美术的区域里找小亮点（粒子）。"""
    m = ((gray > thr) & (outside > 0.5)).astype(np.uint8)
    n, labels, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    out = []
    for i in range(1, n):
        a = int(stats[i, cv2.CC_STAT_AREA])
        if a < min_area or a > max_area:
            continue
        out.append((float(cent[i][0]), float(cent[i][1]), a))
    return out


def _background_mask(art_alpha: np.ndarray) -> np.ndarray:
    """纯背景区（四角 + 远离美术的地方）。"""
    H, W = art_alpha.shape
    m = np.zeros((H, W), np.uint8)
    q = int(min(H, W) * 0.22)
    m[0:q, 0:q] = 1; m[0:q, W - q:W] = 1
    m[H - q:H, 0:q] = 1; m[H - q:H, W - q:W] = 1
    m = cv2.bitwise_and(m, (art_alpha < 0.05).astype(np.uint8))
    return cv2.erode(m, np.ones((9, 9), np.uint8))


def measure_particles(frames: list[np.ndarray], art_alpha: np.ndarray,
                      max_shift: float = 26.0, fps: float = 30.0) -> dict:
    """测量背景粒子的流速 / 方向 / 密度 / 尺寸 / 颜色。

    主估计器：纯背景区上的 Farneback 光流（中位数，对噪点稳健）。
    辅估计器：小球追踪。两者方向不一致时以光流为准。
    """
    if len(frames) < 2:
        return {"speed": 0.0, "angle": 0.0, "density": 0, "size": 1.0,
                "color": [120, 190, 255], "tracked": 0}
    H, W = art_alpha.shape
    mask = _background_mask(art_alpha)
    grays = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) for f in frames]

    # ---- 光流 ----
    flows = []
    for i in range(0, min(len(grays) - 1, 30), 2):
        a = (grays[i] * mask).astype(np.uint8)
        b = (grays[i + 1] * mask).astype(np.uint8)
        try:
            fl = cv2.calcOpticalFlowFarneback(a, b, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        except Exception:
            continue
        fx, fy = fl[..., 0], fl[..., 1]
        sel = (np.abs(fx) + np.abs(fy)) > 0.06
        if sel.sum() < 40:
            continue
        flows.append((float(np.median(fx[sel])), float(np.median(fy[sel]))))
    if flows:
        fv = np.array(flows)
        vx, vy = float(np.median(fv[:, 0])), float(np.median(fv[:, 1]))
    else:
        vx = vy = 0.0

    # ---- 小球追踪（补充尺寸/密度/颜色）----
    thr = max(float(np.percentile(grays[0], 99)) * 0.42, 30)
    def blobs(gray):
        m = ((gray > thr) & (mask > 0)).astype(np.uint8)
        n, lab, st, ce = cv2.connectedComponentsWithStats(m, 8)
        return [(float(ce[i][0]), float(ce[i][1]), int(st[i, cv2.CC_STAT_AREA]))
                for i in range(1, n) if 3 <= st[i, cv2.CC_STAT_AREA] <= 400]
    b1 = blobs(grays[0]); b2 = blobs(grays[1])
    disp = []
    if b1 and b2:
        p1 = np.array([[a, b] for a, b, _ in b1]); p2 = np.array([[a, b] for a, b, _ in b2])
        d = np.linalg.norm(p1[:, None, :] - p2[None, :, :], axis=2)
        used = set()
        for i in range(len(p1)):
            for j in np.argsort(d[i]):
                if j in used:
                    continue
                if d[i, j] > max_shift:
                    break
                used.add(j)
                disp.append((p2[j][0] - p1[i][0], p2[j][1] - p1[i][1]))
                break
    if disp and (abs(vx) + abs(vy) < 0.05):
        dv = np.array(disp, float)
        vx, vy = float(np.median(dv[:, 0])), float(np.median(dv[:, 1]))

    speed = float(np.hypot(vx, vy) * fps)
    angle = float(np.degrees(np.arctan2(vy, vx)))

    areas = [p[2] for p in b1]
    density = float(len(b1))
    size = float(np.sqrt(np.median(areas)) / 3.0) if areas else 1.0

    col = np.array([120, 190, 255], float)
    samples = []
    for i in range(0, len(frames), max(1, len(frames) // 8)):
        f = frames[i]
        m = ((grays[i] > thr) & (mask > 0))
        if m.sum() > 5:
            samples.append(f[m])
    if samples:
        allc = np.concatenate(samples, axis=0).astype(np.float32)
        lum = allc.mean(axis=1)
        col = np.median(allc[lum >= np.percentile(lum, 60)], axis=0)

    return {
        "speed": round(speed, 2),
        "angle": round(angle, 2),
        "density": int(density),
        "size": round(max(0.3, min(4.0, size)), 3),
        "color": [int(v) for v in col],
        "tracked": len(disp),
    }
