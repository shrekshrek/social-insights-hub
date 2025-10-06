#!/usr/bin/env bash
set -euo pipefail

if ! docker compose ps postgres-db >/dev/null 2>&1; then
  echo "postgres-db container not running; start it with 'docker compose up -d postgres-db'" >&2
  exit 1
fi

docker compose exec postgres-db \
  psql -U postgres -d fastapi_db -P pager=off -c "SELECT id, username, email FROM users ORDER BY id;"
