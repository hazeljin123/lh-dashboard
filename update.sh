#!/bin/bash
# 生猪期货季节性看板 一键日更脚本
set -e
BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 拉取最新行情..."
python3.11 scripts/fetch_data.py
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 构建看板..."
python3.11 scripts/build_dashboard.py
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 更新完成: dashboard.html"
cp -f dashboard.html "/workspace/生猪期货价格季节性看板.html"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 已同步交付文件: /workspace/生猪期货价格季节性看板.html"
