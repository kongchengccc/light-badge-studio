#!/usr/bin/env python3
"""命令行版分析器： python3 cli/analyze.py <video> [输出目录]

不需要启动服务，直接产出 assets/ 和 project.json。
"""
import argparse, json, os, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from analyzer import analyze_video  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out", nargs="?", default=None)
    ap.add_argument("--keep-frames", action="store_true")
    ap.add_argument("--max-frames", type=int, default=96)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    out = Path(a.out) if a.out else ROOT / "storage" / "projects" / Path(a.video).stem
    out.mkdir(parents=True, exist_ok=True)
    shutil_src = Path(a.video)
    dst = out / "source" / shutil_src.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        import shutil
        shutil.copy2(shutil_src, dst)

    def prog(step, pct):
        if not a.quiet:
            print(f"\r[{pct:3d}%] {step:<24}", end="", flush=True)

    t = time.time()
    proj = analyze_video(dst, out, keep_frames=a.keep_frames,
                         max_frames=a.max_frames, progress=prog)
    if not a.quiet:
        print()
    print(f"✅ 完成，用时 {time.time()-t:.1f}s → {out}")
    print(json.dumps({
        "text": proj["text"]["box"],
        "motion": {k: proj["motion"][k] for k in ("period", "explained")},
        "particles": proj["particles"],
        "icons": len(proj["assets"]["icons"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
