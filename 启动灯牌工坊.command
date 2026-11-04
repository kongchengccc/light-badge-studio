#!/bin/bash
# ============================================================
#  灯牌工坊 · 本地启动器
#  双击本文件即可。不需要注册任何网站、不需要云服务。
#  首次运行会自动建虚拟环境装依赖（约 2~5 分钟），之后秒开。
# ============================================================
cd "$(dirname "$0")" || exit 1
PORT=${LB_PORT:-8000}
VENV="$PWD/.venv"
PY="$VENV/bin/python"

# venv 不存在或坏了 → 重建
if [ ! -x "$PY" ] || ! "$PY" -c "import fastapi,uvicorn,cv2,numpy,PIL" >/dev/null 2>&1; then
  echo "▸ 准备环境（第一次会下载依赖，请耐心）…"
  BASE=""
  for c in /usr/local/bin/python3 /opt/homebrew/bin/python3 python3.11 python3.12 python3.13 python3 python; do
    if command -v "$c" >/dev/null 2>&1; then BASE="$c"; break; fi
  done
  [ -z "$BASE" ] && { echo "❌ 没找到 python3"; read -r; exit 1; }
  echo "   用 $BASE 建虚拟环境"
  "$BASE" -m venv "$VENV" || { echo "❌ 建虚拟环境失败"; read -r; exit 1; }
  PY="$VENV/bin/python"
  "$PY" -m pip install -q --upgrade pip
  if ! "$PY" -m pip install -q -r requirements.txt; then
    echo "   ⚠️ 默认源失败，换阿里云镜像…"
    "$PY" -m pip install -q -r requirements.txt \
      -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com \
      || { echo "❌ 依赖安装失败"; read -r; exit 1; }
  fi
fi

command -v ffmpeg >/dev/null 2>&1 || echo "⚠️  缺 ffmpeg：导出透明 MOV 会失败（brew install ffmpeg）"
[ -d "/Applications/Google Chrome.app" ] || echo "⚠️  缺 Chrome：服务端渲染需要它"

echo ""
echo "  ▸ 灯牌工坊已启动 → http://127.0.0.1:$PORT"
echo "    停止：关掉这个终端窗口，或按 Control+C"
echo ""
( sleep 3; open "http://127.0.0.1:$PORT" ) &
"$PY" -m uvicorn backend.app:app --host 127.0.0.1 --port "$PORT"
