#!/bin/bash
# 启动星声变调工坊
cd "$(dirname "$0")"
PYTHONPATH="$PWD/../vendor" exec python3 server.py "${1:-8765}"
