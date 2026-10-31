"""冒烟测试：用内置示例跑一遍完整分析流程。"""
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.analyzer import analyze_video  # noqa: E402

SAMPLE = ROOT / "backend" / "samples" / "demo.mp4"


def main():
    if not SAMPLE.exists():
        print("跳过：没有内置示例视频")
        return 0
    tmp = Path(tempfile.mkdtemp(prefix="lb_smoke_"))
    try:
        proj = analyze_video(SAMPLE, tmp, max_frames=40)
        assert (tmp / "project.json").exists()
        assert (tmp / "assets" / "badge.png").exists()
        assert proj["canvas"]["w"] > 0
        print("✅ 冒烟测试通过：", {k: proj[k] for k in ("canvas",)})
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
