#!/usr/bin/env bash
# 停掉并移除 Halo 容器。用法: ./scripts/down.sh [--purge]
#   --purge 额外删除 .runtime/halo2 数据卷（站点数据、管理员账号都会清掉）
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="ai-test-agent-halo"
docker rm -f "$NAME" >/dev/null 2>&1 && echo "[down] 已移除容器 $NAME" || echo "[down] 容器 $NAME 不存在"

if [ "${1:-}" = "--purge" ]; then
  rm -rf .runtime/halo2
  echo "[down] 已删除数据卷 .runtime/halo2"
fi
