#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

DEFAULT_USER_DATA_DIR="${SIGNING_PLAYWRIGHT_USER_DATA_DIR:-$BACKEND_DIR/.playwright/xhs}"

if ! command -v node >/dev/null 2>&1; then
  echo "[warn] Node.js 未安装，JavaScript 签名可能不可用。请先安装 Node >= 16." >&2
else
  node -v
fi

cd "$BACKEND_DIR"

echo "[info] 安装 Playwright 浏览器依赖 (chromium)..."
uv run playwright install chromium

echo "[info] 创建用户数据目录: $DEFAULT_USER_DATA_DIR"
mkdir -p "$DEFAULT_USER_DATA_DIR"

echo "[info] Playwright 签名环境准备完成"
