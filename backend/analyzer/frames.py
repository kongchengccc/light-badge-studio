"""视频抽帧与元信息探测（依赖 ffmpeg / ffprobe）。"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image


def _run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"命令失败: {' '.join(cmd[:4])}\n{p.stderr[-2000:]}")
    return p.stdout


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe(path: str | Path) -> dict:
    """读取视频元信息。"""
    out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ])
    data = json.loads(out)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        raise RuntimeError("文件里没有视频流")
    fps = 0.0
    if v.get("avg_frame_rate") and "/" in v["avg_frame_rate"]:
        a, b = v["avg_frame_rate"].split("/")
        fps = float(a) / float(b) if float(b) else 0.0
    if not fps:
        fps = float(v.get("r_frame_rate", "30/1").split("/")[0]) or 30.0
    dur = float(data.get("format", {}).get("duration") or v.get("duration") or 0.0)
    return {
        "width": int(v["width"]),
        "height": int(v["height"]),
        "fps": round(fps, 4),
        "duration": round(dur, 3),
        "codec": v.get("codec_name", ""),
        "pix_fmt": v.get("pix_fmt", ""),
        "has_audio": any(s.get("codec_type") == "audio" for s in data.get("streams", [])),
    }


def extract_frames(path: str | Path, outdir: str | Path,
                   max_frames: int = 96, fps: float | None = None) -> list[str]:
    """把视频抽成 PNG 序列，返回文件路径列表。

    fps=None 表示按原帧率抽（上限 max_frames 帧）。
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    meta = probe(path)
    target = fps or meta["fps"]
    # 帧数太多就降采样，保证分析耗时可控。
    # 注意方向：要让帧数变少，抽帧率必须【调低】；
    # 写成 target*total/max_frames 会把帧率调高，ffmpeg 只能复制帧（所有帧都一样）。
    total = max(1, int(round(meta["duration"] * target)))
    if total > max_frames:
        target = target * max_frames / total
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(path),
           "-vf", f"fps={target:.6f}", "-q:v", "2", str(outdir / "%05d.png")]
    _run(cmd)
    return sorted(str(p) for p in outdir.glob("*.png"))


def load_frames(paths: list[str], max_side: int = 1280) -> tuple[list[np.ndarray], float]:
    """读入帧序列（灰度化前的 RGB uint8），过大的按比例缩小。"""
    frames: list[np.ndarray] = []
    scale = 1.0
    if paths:
        with Image.open(paths[0]) as im:
            w, h = im.size
        if max(w, h) > max_side:
            scale = max_side / max(w, h)
    for p in paths:
        with Image.open(p) as im:
            im = im.convert("RGB")
            if scale != 1.0:
                im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))),
                               Image.LANCZOS)
            frames.append(np.asarray(im, dtype=np.uint8))
    return frames, scale
