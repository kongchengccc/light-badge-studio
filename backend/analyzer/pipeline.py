"""分析流水线：视频 → 美术层 PNG + 运动场 + 粒子参数 + 文字样式。

    analyze_video(src, outdir, regions=None) -> dict (project.json 内容)
"""
from __future__ import annotations

import json
import math
import shutil
import time
from pathlib import Path

import numpy as np
from PIL import Image

from . import frames as F
from . import layers as L
from . import motion as M
from . import particles as P
from . import regions as R
from . import style as S

ANALYSIS_VERSION = 3


def _save_rgba(rgb: np.ndarray, alpha: np.ndarray, path: Path) -> None:
    rgb = np.asarray(rgb, np.float32)
    a = np.clip(alpha, 0, 1)[..., None]
    # 反预乘：RGB 还原成「不透明时的颜色」
    out_rgb = np.where(a > 0.02, np.clip(rgb / np.maximum(a, 0.02), 0, 255), 0)
    arr = np.dstack([out_rgb, a[..., 0] * 255]).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path)


def _ellipse_alpha(shape, cx, cy, rx, ry, feather=2.0):
    H, W = shape
    yy, xx = np.mgrid[0:H, 0:W]
    d = np.sqrt(((xx - cx) / max(1.0, rx)) ** 2 + ((yy - cy) / max(1.0, ry)) ** 2)
    a = np.clip((1.0 - d) * min(rx, ry) / feather, 0, 1)
    return a.astype(np.float32)


def analyze_video(src: str | Path, outdir: str | Path,
                  regions: dict | None = None,
                  keep_frames: bool = False,
                  max_frames: int = 96,
                  progress=None) -> dict:
    """分析视频，产出美术层资产 + project.json。"""
    t0 = time.time()
    src = Path(src)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    assets_dir = outdir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    regions = regions or {}

    def say(step, pct):
        if progress:
            progress(step, pct)

    say("探测视频", 5)
    meta = F.probe(src)

    say("抽帧", 12)
    tmp = outdir / "_frames"
    if tmp.exists():
        shutil.rmtree(tmp)
    paths = F.extract_frames(src, tmp, max_frames=max_frames)
    if not paths:
        raise RuntimeError("抽帧失败：视频里没有可解码的画面")
    frame_list, scale = F.load_frames(paths)
    H, W = frame_list[0].shape[:2]

    say("分离美术层与粒子", 28)
    art = L.separate_art(frame_list,
                        remove_green_glow=bool(regions.get("removeGreenGlow", True)))
    alpha = art["alpha"]
    rgb = art["rgb"]

    say("检测文字区域", 40)
    det_text = R.detect_text_region(frame_list, alpha)
    text_box = R.clamp_box(regions.get("textBox") or det_text["box"], W, H)

    say("检测头像区域", 50)
    det_av = R.detect_avatar_ellipse(frame_list, alpha, text_box)
    av = regions.get("avatar")
    if av:
        cx = (av["x"] + av["w"] / 2); cy = (av["y"] + av["h"] / 2)
        rx = av["w"] / 2; ry = av["h"] / 2
    else:
        cx, cy, rx, ry = det_av["cx"], det_av["cy"], det_av["rx"], det_av["ry"]

    say("提取装饰图标", 54)
    # 图标必须在剥离文字之前找（星星/音符会被文字带的遮罩误伤）
    icons = []
    x0, y0, x1, y1 = text_box
    side_bands = [
        (max(0, x0 - 150), max(0, y0 - 90), min(W - 2, x0 + 26), min(H, y1 + 90)),
        (max(0, x1 - 26), max(0, y0 - 90), min(W - 2, x1 + 160), min(H, y1 + 90)),
    ]
    idx = 0
    for band in side_bands:
        for spec in L.find_colored_specks(alpha, rgb, band):
            bx, by, bx2, by2 = spec["box"]
            bw, bh = bx2 - bx, by2 - by
            if bw < 6 or bh < 6 or bw > 120 or bh > 120:
                continue
            sub_a = alpha[by:by2, bx:bx2]
            sub_rgb = rgb[by:by2, bx:bx2]
            if sub_a.max() < 0.4:
                continue
            _save_rgba(sub_rgb, sub_a, assets_dir / f"icon_{idx}.png")
            icons.append({"file": f"assets/icon_{idx}.png", "x": bx, "y": by,
                          "w": bw, "h": bh, "color": spec["color"]})
            idx += 1
            # 图标单独导出后，从美术层里挖掉
            alpha[by:by2, bx:bx2] = 0.0
            rgb[by:by2, bx:bx2] = 0

    say("剥离文字字形", 58)
    # 只抠文字自身的亮像素，美术（吊坠/羽尖）一根不少
    strip_box = (text_box[0], max(0, text_box[1] - 10), text_box[2], text_box[3])
    alpha, rgb = L.strip_text_glyphs(alpha, rgb, strip_box,
                                     bright_thr=det_text.get("brightThreshold", 200))

    say("测量运动场", 64)
    mot = M.analyze_motion(frame_list, alpha, duration=meta["duration"] or None)

    say("测量粒子流", 76)
    par = P.measure_particles(frame_list, alpha, fps=len(frame_list) / max(1e-6, meta["duration"]))

    say("采样文字样式", 84)
    sty = S.sample_text_style(frame_list, text_box)

    # ---------- 产出美术层（文字已在上面剥离，这里不再做矩形切割）----------
    say("导出美术层", 90)
    badge_a = alpha.copy()
    badge_rgb = rgb.copy()

    # 头像椭圆（用于「换头像」时替换）
    av_a = _ellipse_alpha((H, W), cx, cy, rx, ry) * (alpha > 0.35)
    _save_rgba(rgb, av_a, assets_dir / "avatar.png")

    _save_rgba(badge_rgb, badge_a, assets_dir / "badge.png")

    # 预览图（首帧，棋盘底，方便前端显示）
    prev = frame_list[0].copy()
    Image.fromarray(prev).save(outdir / "preview.jpg", quality=88)

    if not keep_frames and tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------- 组装 project.json ----------
    glyph_h = sty.get("glyphHeight", 66)
    text_w = text_box[2] - text_box[0]
    say("生成工程文件", 97)

    project = {
        "version": ANALYSIS_VERSION,
        "id": outdir.name,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "analyzeSeconds": round(time.time() - t0, 2),
        "source": meta,
        "canvas": {"w": W, "h": H},
        "assets": {
            "badge": "assets/badge.png",
            "avatar": "assets/avatar.png",
            "preview": "preview.jpg",
            "icons": icons,
        },
        "text": {
            "content": "恭喜男神荣升20级",
            "box": text_box,
            "y": int((text_box[1] + text_box[3]) / 2),
            "size": int(round(glyph_h * 0.92)),
            "fit": True,
            "maxWidth": int(text_w),
            "spacing": 1,
            "fillTop": sty.get("fillTop", "#ffffff"),
            "fillBot": sty.get("fillBot", "#fffbe8"),
            "stroke": sty.get("stroke", "#241a10"),
            "glow": sty.get("glow", "#c8ff55"),
            "strokeW": 1.2,
            "glowBlur": 5,
            "glowAlpha": 0.8,
            "fatten": 7,
            "shadow": 0.35,
            "glowPulse": 0.12,
            "sub": "",
            "subSize": 26,
            "subY": int((text_box[1] + text_box[3]) / 2) + 62,
            "font": "zcool",
            "iconsFollow": True,
            "iconGap": 10,
        },
        "motion": {
            "enabled": True,
            "period": mot["period"],
            "explained": mot["explained"],
            "grid": mot["grid"],
        },
        "particles": {
            "enabled": True,
            "speed": par["speed"],
            "angle": par["angle"],
            "density": max(40, min(400, int(par["density"] * 12))),
            "size": par["size"],
            "color": par["color"],
        },
        "shine": {"enabled": True, "amount": 0.42, "speed": 110, "bands": 2, "angle": 0.22},
        "detected": {
            "text": det_text,
            "glow": {"box": det_text.get("box"), "score": det_text.get("score", 0)},
            "avatar": {"cx": cx, "cy": cy, "rx": rx, "ry": ry},
            "avatarAuto": det_av,
        },
        "render": {"fps": 30, "duration": round(meta["duration"], 3), "bg": "transparent"},
    }
    (outdir / "project.json").write_text(
        json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    say("完成", 100)
    return project
