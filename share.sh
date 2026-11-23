#!/bin/bash
# 把本地站点通过 Cloudflare 快速隧道分享成一个公网 https 链接
# 用法：./share.sh [端口]
# 注意：这是临时链接，隧道一停就失效，下次启动会换一个新地址。

set -e
PORT="${1:-8765}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
CF="$ROOT/../bin/cloudflared"

if [ ! -x "$CF" ]; then
  echo "找不到 cloudflared：$CF"
  echo "下载：curl -L -o /tmp/cf.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz && tar -xzf /tmp/cf.tgz -C $ROOT/../bin"
  exit 1
fi

# 服务没跑就先起起来
if ! curl -s -m 2 "http://127.0.0.1:$PORT/api/health" > /dev/null; then
  echo "启动服务（端口 $PORT）…"
  cd "$ROOT"
  PYTHONPATH="$ROOT/../vendor" nohup python3 server.py "$PORT" > /tmp/starmusic-share.log 2>&1 &
  sleep 2
fi

echo "建立隧道…"
LOG="/tmp/cloudflared-share.log"
rm -f "$LOG"
"$CF" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > "$LOG" 2>&1 &
CF_PID=$!

# 从日志里抓公网地址
for i in $(seq 1 30); do
  URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)
  if [ -n "$URL" ]; then
    echo ""
    echo "分享链接： $URL"
    echo "（把这条发给朋友即可；关掉这个窗口链接就失效）"
    echo ""
    break
  fi
  sleep 1
done

wait "$CF_PID"
