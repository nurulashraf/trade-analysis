#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
exec uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}"
