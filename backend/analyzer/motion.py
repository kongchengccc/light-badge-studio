"""运动场测量：还原「翅膀怎么动」。

对美术层区域做块匹配，得到每个小块在时间上的位移轨迹，
再用正弦模型拟合出 4 个通道 (ax,bx,ay,by)：

    d(t) = ax·cos(ωt) + bx·sin(ωt)   （x 方向）
         = ay·cos(ωt) + by·sin(ωt)   （y 方向）

结果降采样成粗网格存进 project.json，前端双线性插值后逐像素还原，
这样连「不规则抖动」都能保留，不受解析模型限制。
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _gray(frames: list[np.ndarray]) -> np.ndarray:
    out = np.empty((len(frames),) + frames[0].shape[:2], np.float32)
    for i, f in enumerate(frames):
        if cv2 is not None:
            out[i] = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY)
        else:
            out[i] = 0.299 * f[..., 0] + 0.587 * f[..., 1] + 0.114 * f[..., 2]
    return out


def _match(a: np.ndarray, b: np.ndarray, x: int, y: int, bs: int, rad: int):
    """在 b 里找 a[y:y+bs, x:x+bs] 的最佳匹配位置。"""
    templ = a[y:y + bs, x:x + bs]
    H, W = b.shape
    Y0, Y1 = max(0, y - rad), min(H, y + bs + rad)
    X0, X1 = max(0, x - rad), min(W, x + bs + rad)
    if Y1 - Y0 < bs or X1 - X0 < bs or templ.std() < 3:
        return None
    region = b[Y0:Y1, X0:X1]
    if cv2 is not None:
        res = cv2.matchTemplate(region, templ, cv2.TM_CCOEFF_NORMED)
        _, _, _, loc = cv2.minMaxLoc(res)
        return (X0 + loc[0]) - x, (Y0 + loc[1]) - y
    best = (-2, 0, 0)
    for dy in range(-rad, rad + 1):
        for dx in range(-rad, rad + 1):
            patch = b[y + dy:y + dy + bs, x + dx:x + dx + bs]
            if patch.shape != templ.shape:
                continue
            a1 = templ - templ.mean(); b1 = patch - patch.mean()
            n = np.sqrt((a1 * a1).sum() * (b1 * b1).sum())
            if n < 1e-6:
                continue
            c = float((a1 * b1).sum() / n)
            if c > best[0]:
                best = (c, dx, dy)
    return (best[1], best[2]) if best[0] > 0.5 else None


def measure_displacement(gray: np.ndarray, mask: np.ndarray,
                         bs: int = 24, stride: int = 12, rad: int = 16,
                         min_ratio: float = 0.55) -> dict:
    """逐块相对「第 0 帧」的位移轨迹。

    直接拿每帧去和参考帧比，比逐帧累加稳得多（累加会漂移，且一帧失配就前功尽弃）。
    """
    n = gray.shape[0]
    H, W = gray.shape[1], gray.shape[2]
    ref = gray[0]
    cells = []
    for y in range(0, H - bs, stride):
        for x in range(0, W - bs, stride):
            blk = mask[y:y + bs, x:x + bs]
            if blk.mean() < 0.35:                       # 必须是美术区域（alpha 覆盖率）
                continue
            if ref[y:y + bs, x:x + bs].std() < 6:       # 没纹理，匹配不可靠
                continue
            traj = []
            for f in range(1, n):
                r = _match(ref, gray[f], x, y, bs, rad)
                traj.append(None if r is None else (r[0], r[1]))
            good = sum(1 for t in traj if t is not None)
            if good >= max(3, n * min_ratio):
                cells.append((x, y, traj))
    return {"cells": cells, "bs": bs, "stride": stride}


def fit_sinusoid(cells: list[tuple], n_frames: int, fps: float) -> dict:
    """对位移轨迹做频率扫描 + 正弦拟合，返回每个块的 4 个通道。"""
    if len(cells) < 8:
        return {"period": 2.0, "freq": 0.5,
                "channels": np.zeros((0, 2, 2), np.float32),
                "amp": np.zeros((0,), np.float32), "cells": cells, "explained": 0.0}

    # 拼成 (T, N, 2)，缺失帧用 0 并记录掩码
    T = n_frames - 1
    traj = np.zeros((T, len(cells), 2), np.float32)
    valid = np.zeros((T, len(cells)), bool)
    for i, c in enumerate(cells):
        for t, v in enumerate(c[2]):
            if v is not None:
                traj[t, i, 0] = v[0]
                traj[t, i, 1] = v[1]
                valid[t, i] = True

    t = np.arange(T) / max(fps, 1e-6)
    best = (0.0, 0.5)
    for P in np.arange(0.4, 12.01, 0.02):
        w = 2 * np.pi / P
        A = np.stack([np.cos(w * t), np.sin(w * t)], axis=1)
        # 每个块单独解（缺失帧用加权最小二乘近似：直接整体解再按掩码重解）
        coef = np.zeros((2, len(cells) * 2))
        for i in range(len(cells)):
            m = valid[:, i]
            if m.sum() < 4:
                continue
            Ai = A[m]
            Yi = traj[m, i, :]
            try:
                ci, *_ = np.linalg.lstsq(Ai, Yi, rcond=None)
            except Exception:
                continue
            coef[:, i * 2:i * 2 + 2] = ci
        pred = A @ coef
        pred = pred.reshape(T, len(cells), 2)
        num = float(((pred - traj) ** 2)[valid].sum())
        den = float((traj ** 2)[valid].sum())
        explained = 1.0 - num / max(1e-9, den)
        if explained > best[0]:
            best = (explained, float(P))
    explained, period = best

    w = 2 * np.pi / period
    A = np.stack([np.cos(w * t), np.sin(w * t)], axis=1)
    coef = np.zeros((2, len(cells) * 2))
    for i in range(len(cells)):
        m = valid[:, i]
        if m.sum() < 4:
            continue
        try:
            ci, *_ = np.linalg.lstsq(A[m], traj[m, i, :], rcond=None)
        except Exception:
            continue
        coef[:, i * 2:i * 2 + 2] = ci
    ch = coef.T.reshape(len(cells), 2, 2)      # (N, cos/sin, x/y)
    amp = np.hypot(ch[..., 0, :], ch[..., 1, :]).max(axis=1)
    return {
        "period": round(period, 4),
        "freq": round(1.0 / period, 5),
        "explained": round(float(explained), 4),
        "cells": cells,
        "channels": ch.astype(np.float32),
        "amp": amp.astype(np.float32),
    }


def build_grid(fit: dict, shape: tuple[int, int], grid_w: int = 24, grid_h: int = 18,
               min_amp: float = 0.6) -> dict:
    """把逐块结果降采样成粗网格（供前端双线性插值）。"""
    H, W = shape
    cells = fit["cells"]
    ch = fit["channels"]
    if not cells:
        return {"w": grid_w, "h": grid_h, "x0": 0, "y0": 0, "cw": W / grid_w,
                "ch": H / grid_h, "data": [[0.0] * (grid_w * 4) for _ in range(grid_h)],
                "amp": [[0.0] * grid_w for _ in range(grid_h)]}

    xs = np.array([c[0] for c in cells], float)
    ys = np.array([c[1] for c in cells], float)
    gw, gh = min(grid_w, len(cells)), min(grid_h, len(cells))
    # 网格按画面等分
    gx = np.clip(((xs / W) * gw).astype(int), 0, gw - 1)
    gy = np.clip(((ys / H) * gh).astype(int), 0, gh - 1)

    data = np.zeros((gh, gw, 4), np.float32)
    amp = np.zeros((gh, gw), np.float32)
    cnt = np.zeros((gh, gw), np.float32)
    for i in range(len(cells)):
        data[gy[i], gx[i]] += ch[i].reshape(4)
        amp[gy[i], gx[i]] = max(amp[gy[i], gx[i]], float(fit["amp"][i]))
        cnt[gy[i], gx[i]] += 1
    nz = cnt > 0
    data[nz] /= cnt[nz][:, None]
    # 幅度太小的格子（静态区域）直接归零，避免噪声放大
    amp[amp < min_amp] = 0.0
    data[amp < min_amp] = 0.0

    return {
        "w": gw, "h": gh, "x0": 0, "y0": 0,
        "cw": W / gw, "ch": H / gh,
        "data": data.round(4).tolist(),
        "amp": amp.round(3).tolist(),
    }


def analyze_motion(frames: list[np.ndarray], art_alpha: np.ndarray,
                   max_frames: int = 48, grid_w: int = 24, grid_h: int = 18,
                   fps: float = 30.0, duration: float | None = None) -> dict:
    """完整流程：抽帧 → 位移 → 频率扫描 → 网格化。

    fps 必须是「实际抽帧率」（帧数 / 时长），否则周期会算错。
    """
    if len(frames) > max_frames:
        idx = np.linspace(0, len(frames) - 1, max_frames).astype(int)
        sub = [frames[i] for i in idx]
    else:
        sub = frames
    if duration and duration > 0:
        fps = len(sub) / duration
    gray = _gray(sub)
    meas = measure_displacement(gray, art_alpha)
    fit = fit_sinusoid(meas["cells"], gray.shape[0], fps)
    grid = build_grid(fit, art_alpha.shape, grid_w, grid_h)
    return {
        "period": fit["period"],
        "explained": fit["explained"],
        "cells": len(meas["cells"]),
        "grid": grid,
    }
