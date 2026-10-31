"""文字样式采样：从原视频的文字区反推填充色 / 描边色 / 辉光色 / 字号。"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _hex(rgb) -> str:
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    return "#%02x%02x%02x" % (r, g, b)


def sample_text_style(frames: list[np.ndarray], text_box: list[int]) -> dict:
    if not frames:
        return {}
    ref = np.median(np.stack(frames).astype(np.float32), axis=0).astype(np.uint8)
    H, W = ref.shape[:2]
    x0, y0, x1, y1 = [max(0, v) for v in text_box]
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return {}
    reg = ref[y0:y1, x0:x1].astype(np.float32)
    lum = 0.299 * reg[..., 0] + 0.587 * reg[..., 1] + 0.114 * reg[..., 2]
    h = reg.shape[0]

    bright = lum > (np.percentile(lum, 96) * 0.72)
    if bright.sum() < 20:
        bright = lum > np.percentile(lum, 85)

    # 上半 / 下半的填充色
    top = reg[: max(1, h // 4)][bright[: max(1, h // 4)]].reshape(-1, 3)
    bot = reg[3 * h // 4:][bright[3 * h // 4:]].reshape(-1, 3)
    fill_top = np.median(top, axis=0) if len(top) else np.array([255, 255, 245])
    fill_bot = np.median(bot, axis=0) if len(bot) else np.array([255, 245, 210])

    # 描边色：字形紧邻的暗像素
    dark = (lum < np.percentile(lum, 22)) & (lum > 6)
    stroke = np.median(reg[dark].reshape(-1, 3), axis=0) if dark.sum() > 10 else np.array([42, 28, 16])

    # 辉光色：文字区外扩一圈里「饱和且偏亮」的像素
    pad = max(6, int(h * 0.14))
    ex0, ey0 = max(0, x0 - pad), max(0, y0 - pad)
    ex1, ey1 = min(W, x1 + pad), min(H, y1 + pad)
    ext = ref[ey0:ey1, ex0:ex1].astype(np.float32)
    el = 0.299 * ext[..., 0] + 0.587 * ext[..., 1] + 0.114 * ext[..., 2]
    sat = ext.max(axis=2) - ext.min(axis=2)
    glow_mask = (sat > 28) & (el > 30) & (el < 245)
    if glow_mask.sum() > 20:
        glow = np.median(ext[glow_mask].reshape(-1, 3), axis=0)
    else:
        glow = np.array([225, 255, 155])

    # 字号 ≈ 字形高度
    rows = np.nonzero(bright.sum(axis=1) > 2)[0]
    glyph_h = int(rows.max() - rows.min() + 1) if len(rows) else h

    return {
        "fillTop": _hex(fill_top),
        "fillBot": _hex(fill_bot),
        "stroke": _hex(stroke),
        "glow": _hex(glow),
        "glyphHeight": glyph_h,
        "textBox": [x0, y0, x1, y1],
    }
