"""灯牌工坊 · 后端服务。

  uvicorn backend.app:app --reload --port 8000
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.analyzer import analyze_video            # noqa: E402
from backend import render as R                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STORAGE = Path(os.environ.get("LB_STORAGE", ROOT / "storage")).resolve()
PROJECTS = STORAGE / "projects"
SAMPLES = ROOT / "backend" / "samples"

PROJECTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="灯牌工坊 API", version="1.0.0",
              docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def job_new(kind: str) -> str:
    jid = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[jid] = {"id": jid, "kind": kind, "step": "排队中", "percent": 0,
                     "done": False, "error": None, "created": time.time()}
    return jid


def job_update(jid: str, **kw):
    with JOBS_LOCK:
        if jid in JOBS:
            JOBS[jid].update(kw)


def job_get(jid: str) -> dict | None:
    with JOBS_LOCK:
        return JOBS.get(jid)


# ---------------------------------------------------------------- 静态资源
@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/favicon.svg")
def favicon():
    return FileResponse(FRONTEND / "favicon.svg")


app.mount("/css", StaticFiles(directory=FRONTEND / "css"), name="css")
app.mount("/js", StaticFiles(directory=FRONTEND / "js"), name="js")
app.mount("/fonts", StaticFiles(directory=FRONTEND / "fonts"), name="fonts")


# ---------------------------------------------------------------- 分析
@app.post("/api/analyze")
async def api_analyze(video: UploadFile = File(...)):
    name = Path(video.filename or "upload.mp4").name
    if not name.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi")):
        raise HTTPException(400, "只支持 mp4 / mov / webm 等视频格式")
    pid = uuid.uuid4().hex[:12]
    pdir = PROJECTS / pid
    pdir.mkdir(parents=True, exist_ok=True)
    src = pdir / "source" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    with src.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    jid = job_new("analyze")

    def work():
        try:
            def prog(step, pct):
                job_update(jid, step=step, percent=pct)
            proj = analyze_video(src, pdir, progress=prog)
            job_update(jid, step="完成", percent=100, done=True, projectId=pid)
        except Exception as e:                       # noqa: BLE001
            job_update(jid, step="失败", percent=100, done=True, error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"id": pid, "job": jid}


@app.get("/api/jobs/{jid}")
def api_job(jid: str):
    j = job_get(jid)
    if not j:
        raise HTTPException(404, "任务不存在")
    return j


# ---------------------------------------------------------------- 工程
@app.get("/api/projects/{pid}")
def api_project(pid: str):
    f = PROJECTS / pid / "project.json"
    if not f.exists():
        raise HTTPException(404, "工程不存在")
    return json.loads(f.read_text(encoding="utf-8"))


@app.put("/api/projects/{pid}")
async def api_save(pid: str, body: dict):
    f = PROJECTS / pid / "project.json"
    if not f.exists():
        raise HTTPException(404, "工程不存在")
    proj = json.loads(f.read_text(encoding="utf-8"))
    for k, v in body.items():
        proj[k] = v
    f.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.get("/api/projects/{pid}/file/{path:path}")
def api_asset(pid: str, path: str):
    base = (PROJECTS / pid).resolve()
    f = (base / path).resolve()
    if not str(f).startswith(str(base)) or not f.exists():
        raise HTTPException(404, "素材不存在")
    return FileResponse(f)


# ---------------------------------------------------------------- 字体
@app.get("/api/fonts")
def api_fonts():
    out = [
        {"key": "zcool", "name": "站酷庆科黄油体（最接近原版）",
         "url": "/fonts/ZCOOLQingKeHuangYou-Subset.woff2"},
        {"key": "system", "name": "系统黑体（PingFang / 雅黑）", "url": None},
        {"key": "serif", "name": "系统衬线（宋体）", "url": None},
        {"key": "round", "name": "系统圆体（幼圆）", "url": None},
        {"key": "custom", "name": "自定义（在前端上传）", "url": None},
    ]
    extra = FRONTEND / "fonts"
    for f in sorted(extra.glob("*.woff2")):
        if "ZCOOL" in f.name:
            continue
        out.append({"key": f.stem, "name": f.stem, "url": f"/fonts/{f.name}"})
    return out


# ---------------------------------------------------------------- 示例
@app.get("/api/sample")
def api_sample():
    """内置示例。第一次访问会跑一遍分析（约 40 秒），之后直接读缓存。"""
    src = SAMPLES / "demo.mp4"
    if not src.exists():
        raise HTTPException(404, "没有内置示例")
    pid = "sample"
    pdir = PROJECTS / pid
    pj = pdir / "project.json"
    if pj.exists():
        return {"id": pid, "project": json.loads(pj.read_text(encoding="utf-8"))}
    pdir.mkdir(parents=True, exist_ok=True)
    s = pdir / "source" / src.name
    if not s.exists():
        s.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, s)
    jid = job_new("sample")

    def work():
        try:
            def prog(step, pct):
                job_update(jid, step=step, percent=pct)
            analyze_video(s, pdir, progress=prog)
            job_update(jid, step="完成", percent=100, done=True, projectId=pid)
        except Exception as e:                       # noqa: BLE001
            job_update(jid, step="失败", percent=100, done=True, error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"id": pid, "job": jid}


# ---------------------------------------------------------------- 服务端渲染
@app.post("/api/projects/{pid}/render")
async def api_render(pid: str, body: dict):
    pdir = PROJECTS / pid
    pf = pdir / "project.json"
    if not pf.exists():
        raise HTTPException(404, "工程不存在")
    formats = body.get("formats") or ["mp4"]
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", body.get("name") or "灯牌")[:40]
    project = json.loads(pf.read_text(encoding="utf-8"))
    if body.get("project"):
        for k, v in body["project"].items():
            if k in ("text", "motion", "particles", "shine", "render", "canvas", "avatarRect"):
                project[k] = v
    jid = job_new("render")

    def work():
        try:
            def prog(step, pct):
                job_update(jid, step=step, percent=pct)
            out_dir = pdir / "out"
            frames_dir = out_dir / "frames"
            r = project.get("render", {})
            fps = int(r.get("fps") or 30)
            dur = float(r.get("duration") or 2.44)
            n = max(1, round(dur * fps))
            job_update(jid, step="渲染帧", percent=2)
            R.render_frames(project, pdir, frames_dir, n, fps, progress=prog)
            c = project.get("canvas", {})
            outs = R.encode(frames_dir, out_dir, fps, formats,
                            (int(c.get("w", 960)), int(c.get("h", 720))), name, progress=prog)
            job_update(jid, step="完成", percent=100, done=True, outputs=outs)
        except Exception as e:                       # noqa: BLE001
            job_update(jid, step="失败", percent=100, done=True, error=str(e))

    threading.Thread(target=work, daemon=True).start()
    return {"id": jid}


@app.get("/api/health")
def api_health():
    return {"ok": True, "ffmpeg": bool(shutil.which("ffmpeg")),
            "chrome": bool(R.find_chrome()), "projects": len(list(PROJECTS.iterdir()))}
