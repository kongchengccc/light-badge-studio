"""服务端渲染：无头 Chrome 逐帧出图 → ffmpeg 编码。

不用 Playwright（少一个依赖）：用 Chrome 的 --dump-dom 把每帧的 canvas PNG 抠出来。
渲染期间会起一个临时本地 HTTP 服务，保证图片同源（file:// 会污染 canvas 导致导出失败）。
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def find_chrome() -> str | None:
    cands = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    ]
    for c in cands:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "chromium", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    return None


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def _serve(roots: dict[str, Path]) -> tuple[ThreadingHTTPServer, int]:
    class Handler(SimpleHTTPRequestHandler):
        def translate_path(self, path):
            path = path.split("?", 1)[0].split("#", 1)[0]
            for prefix, root in roots.items():
                if path == prefix:
                    path = prefix + "/"
                if path.startswith(prefix + "/"):
                    rel = path[len(prefix) + 1:]
                    return str((root / rel).resolve())
            return str((FRONTEND / path.lstrip("/")).resolve())

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def render_frames(project: dict, project_dir: Path, frames_dir: Path,
                  n_frames: int, fps: int, progress=None,
                  chunk: int = 12) -> Path:
    """渲染出 PNG 序列。"""
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("找不到 Chrome / Chromium，无法服务端渲染")
    frames_dir.mkdir(parents=True, exist_ok=True)

    srv, port = _serve({"/proj": project_dir, "": FRONTEND})
    profile = tempfile.mkdtemp(prefix="lb_render_")
    cfg = {
        "project": project,
        "render": project.get("render", {}),
        "fontUrl": "/proj/fonts/ZCOOLQingKeHuangYou-Subset.woff2",
    }
    cfg_b64 = base64.b64encode(json.dumps(cfg, ensure_ascii=False).encode()).decode()
    from urllib.parse import quote
    cfg_q = quote(cfg_b64, safe="")

    done = 0
    t0 = time.time()
    try:
        while done < n_frames:
            cnt = min(chunk, n_frames - done)
            url = (f"http://127.0.0.1:{port}/export.html?start={done}&count={cnt}"
                   f"&assetBase=/proj/&cfg={cfg_q}")
            cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                   "--hide-scrollbars", f"--user-data-dir={profile}",
                   "--virtual-time-budget=30000", "--dump-dom", url]
            out = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stdout
            got = re.findall(r'data-i="(\d+)"[^>]*>(data:image/png;base64,[A-Za-z0-9+/=]+)<', out)
            if not got:
                raise RuntimeError("渲染失败：浏览器没有输出任何帧")
            for idx, b64 in got:
                raw = base64.b64decode(b64.split(",", 1)[1])
                (frames_dir / f"{int(idx) + 1:04d}.png").write_bytes(raw)
            done += cnt
            if progress:
                progress("渲染帧", int(done / max(1, n_frames) * 70))
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        srv.shutdown()
    return frames_dir


def encode(frames_dir: Path, out_dir: Path, fps: int, formats: list[str],
           size: tuple[int, int], name: str = "灯牌", progress=None) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pat = str(frames_dir / "%04d.png")
    w, h = size
    outs = []
    for i, fmt in enumerate(formats):
        if progress:
            progress(f"编码 {fmt}", 70 + int((i + 1) / len(formats) * 28))
        if fmt == "mp4":
            o = out_dir / f"{name}.mp4"
            subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-i", pat,
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16",
                            "-movflags", "+faststart", str(o)], check=True,
                           capture_output=True)
        elif fmt == "mov":
            o = out_dir / f"{name}_alpha.mov"
            subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-i", pat,
                            "-c:v", "prores_ks", "-profile:v", "4444",
                            "-pix_fmt", "yuva444p10le", "-vendor", "apl0", str(o)],
                           check=True, capture_output=True)
        elif fmt == "webm":
            o = out_dir / f"{name}_alpha.webm"
            subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-i", pat,
                            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                            "-auto-alt-ref", "0", "-b:v", "2M", "-alpha_mode", "1", str(o)],
                           check=True, capture_output=True)
        elif fmt == "gif":
            o = out_dir / f"{name}.gif"
            subprocess.run(["ffmpeg", "-y", "-framerate", str(fps), "-i", pat,
                            "-vf", f"scale={max(1, w // 2)}:{max(1, h // 2)}:flags=lanczos,"
                                   f"split[a][b];[a]palettegen=max_colors=200[p];"
                                   f"[b][p]paletteuse=dither=bayer:bayer_scale=4",
                            "-loop", "0", str(o)], check=True, capture_output=True)
        else:
            continue
        outs.append(str(o))
    return outs
