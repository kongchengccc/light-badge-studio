"""分析器单元测试（不依赖真实视频，用合成帧）。"""
import numpy as np
import pytest

from backend.analyzer import layers, regions, motion, particles, style


def make_frames(n=12, w=320, h=240):
    """合成一段：黑底 + 一个静止的亮方块（美术）+ 几个移动的小点（粒子）+ 一条静态文字带。"""
    frames = []
    for i in range(n):
        f = np.zeros((h, w, 3), np.uint8)
        f[40:140, 40:200] = (230, 225, 215)        # 美术主体
        f[180:200, 20:300] = (240, 238, 230)      # 文字带
        for k in range(6):                         # 粒子向右漂
            x = int((20 + k * 45 + i * 4) % (w - 8)) + 4
            y = 20 + k * 30
            f[y:y + 3, x:x + 3] = (90, 170, 255)
        frames.append(f)
    return frames


def test_separate_art_keeps_subject():
    fr = make_frames()
    art = layers.separate_art(fr)
    a = art["alpha"]
    assert a[60:130, 60:190].mean() > 0.8, "美术主体应当被保留"
    assert a[10:30, 10:30].mean() < 0.2, "背景应当被抠掉"


def test_detect_text_region():
    fr = make_frames()
    art = layers.separate_art(fr)
    det = regions.detect_text_region(fr, art["alpha"])
    x0, y0, x1, y1 = det["box"]
    assert 170 <= y0 <= 190 and 195 <= y1 <= 210, f"文字行应落在 180~200，实际 {det['box']}"
    assert x1 > x0


def test_motion_grid_shape():
    fr = make_frames()
    art = layers.separate_art(fr)
    mo = motion.analyze_motion(fr, art["alpha"], grid_w=8, grid_h=6)
    g = mo["grid"]
    assert g["w"] == 8 and g["h"] == 6
    assert len(g["data"]) == 6
    assert len(g["data"][0]) == 8
    assert len(g["data"][0][0]) == 4, "每个格子 4 个通道 (ax,bx,ay,by)"
    assert 0.5 < mo["period"] < 12


def test_particles_measured():
    fr = make_frames()
    art = layers.separate_art(fr)
    p = particles.measure_particles(fr, art["alpha"], fps=len(fr))
    assert "speed" in p and "angle" in p and "color" in p
    assert len(p["color"]) == 3


def test_style_sampling():
    fr = make_frames()
    st = style.sample_text_style(fr, [20, 180, 300, 200])
    assert st["fillTop"].startswith("#")
    assert st["glyphHeight"] > 0


def test_strip_text_glyphs_removes_text():
    fr = make_frames()
    art = layers.separate_art(fr)
    before = art["alpha"][175:205, 20:300].sum()
    a2, _ = layers.strip_text_glyphs(art["alpha"], art["rgb"], (20, 178, 300, 202))
    after = a2[175:205, 20:300].sum()
    assert after < before * 0.5, "文字字形应被剥离"
