#!/usr/bin/env bash
# 一键起 Halo 靶子：启动容器 -> 等健康检查 -> 初始化管理员（幂等）。
# 管理员账号密码只存 .env；若 HALO_ADMIN_PASSWORD 为空则生成随机密码并写回 .env。
# 用法: ./scripts/up.sh
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="ai-test-agent-halo"
PORT=8090
IMAGE="${HALO_IMAGE:-registry.fit2cloud.com/halo/halo:2.20}"
DATA_DIR=".runtime/halo2"

# ---- .env ----
if [ ! -f .env ]; then
  cp .env.example .env
  echo "[up] 已从 .env.example 创建 .env（LLM_API_KEY 待填；起 Halo 不依赖它）"
fi
set -a; . ./.env; set +a

if [ -z "${HALO_ADMIN_PASSWORD:-}" ]; then
  PW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(12))')"
  printf '\nHALO_ADMIN_PASSWORD=%s\n' "$PW" >> .env
  export HALO_ADMIN_PASSWORD="$PW"
  echo "[up] 已生成随机管理员密码并写入 .env（不回显）"
fi
if [ -z "${HALO_ADMIN_USER:-}" ]; then
  echo 'HALO_ADMIN_USER=admin' >> .env
  export HALO_ADMIN_USER=admin
fi

# ---- 端口 ----
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[up] 端口 $PORT 已被占用（本任务固定用 8090）。若是本脚本残留容器请先执行 ./scripts/down.sh"
  exit 1
fi

# ---- 容器 ----
mkdir -p "$DATA_DIR"
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  echo "[up] 容器 $NAME 已存在，直接启动（数据卷 $DATA_DIR 保留）"
  docker start "$NAME" >/dev/null
else
  echo "[up] 启动 $NAME ($IMAGE)"
  docker run -d --name "$NAME" \
    -p "$PORT":8090 \
    -v "$PWD/$DATA_DIR":/root/.halo2 \
    "$IMAGE" >/dev/null
fi

# ---- 健康检查：等首页可访问，再等系统就绪 ----
echo -n "[up] 等待 Halo 就绪"
for i in $(seq 1 120); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/" || true)"
  if [ "$code" != "000" ]; then
    ready="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/actuator/health/readiness" || true)"
    if [ "$ready" = "200" ]; then echo " OK"; break; fi
  fi
  echo -n "."
  sleep 2
  if [ "$i" = "120" ]; then
    echo
    echo "[up] 等待超时（120 次轮询）。查看日志: docker logs $NAME"
    exit 1
  fi
done

# ---- 初始化管理员（幂等；已初始化则跳过）----
python3 scripts/init_admin.py

echo "[up] Halo 已就绪: http://localhost:$PORT  控制台: http://localhost:$PORT/console/"
echo "[up] 管理员账号见 .env（HALO_ADMIN_USER / HALO_ADMIN_PASSWORD）"
