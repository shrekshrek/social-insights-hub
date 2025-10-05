#!/usr/bin/env bash
set -euo pipefail

# 启动本地 Celery Worker
# 依赖 docker-compose 正在运行的 backend 容器

docker-compose exec backend uv run celery -A src.celery_app.celery_app worker --loglevel=info
