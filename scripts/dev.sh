#!/usr/bin/env bash
# 一键启动 dev 双端口：后端 FastAPI :8000 + 前端 Vite :5173。
#
#   bash scripts/dev.sh          # 默认 8000 / 5173
#   BACKEND_PORT=8010 FRONTEND_PORT=5180 bash scripts/dev.sh
#
# 这不是质量关 —— 所有检查/契约导出/类型生成/构建仍只经 `bash scripts/verify.sh`（AGENTS.md 硬不变量 5）。
# 本脚本只做三件事：缺依赖就装、起两个进程、Ctrl-C 时把两个都收干净。
# 日志在 .dev-logs/（已 gitignore）：backend.log / frontend.log。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
LOG_DIR="$ROOT/.dev-logs"

step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }
ok() { printf '\033[1;32m✓ %s\033[0m\n' "$1"; }

# ---------- 环境底线 ----------
step "环境底线"
command -v uv >/dev/null 2>&1 || fail "缺少 uv（安装：https://docs.astral.sh/uv/）"
command -v node >/dev/null 2>&1 || fail "缺少 node"
command -v npm >/dev/null 2>&1 || fail "缺少 npm"
ok "uv $(uv --version | awk '{print $2}') · node $(node -v)"

# ---------- 端口占用（先查再起，免得起了个假的） ----------
port_pids() {
  netstat -ano 2>/dev/null | grep -E "[:.]$1[[:space:]]" | grep -i listening | awk '{print $NF}' | sort -u
}

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  pids="$(port_pids "$port" || true)"
  if [ -n "${pids:-}" ]; then
    fail "端口 $port 已被占用（PID: $(echo "$pids" | paste -sd, -)）；先停掉它，或用 BACKEND_PORT/FRONTEND_PORT 换端口"
  fi
done
ok "端口 $BACKEND_PORT / $FRONTEND_PORT 空闲"

# ---------- 依赖（只补缺，不升级） ----------
step "依赖"
if [ ! -d "$BACKEND/.venv" ]; then
  (cd "$BACKEND" && uv sync --frozen --quiet)
  ok "已按 uv.lock 建后端虚拟环境"
else
  ok "后端虚拟环境已存在（backend/.venv）"
fi
if [ ! -d "$FRONTEND/node_modules" ]; then
  (cd "$FRONTEND" && npm ci --no-audit --no-fund)
  ok "已按 package-lock.json 装前端依赖"
else
  ok "前端依赖已存在（frontend/node_modules）"
fi

mkdir -p "$LOG_DIR"

# ---------- 收尾：先按启动时的 PID 收进程树，再按端口兜底 ----------
kill_tree() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  # Windows（git bash）：taskkill /T 连子进程一起收（uvicorn --reload 的 worker 是子进程）；
  # POSIX 机器上退回 kill。
  taskkill //PID "$pid" //T //F >/dev/null 2>&1 || kill "$pid" >/dev/null 2>&1 || true
}

cleanup() {
  [ "${CLEANED:-0}" = "1" ] && return 0
  CLEANED=1
  printf '\n'
  step "正在停止"
  kill_tree "${BACK_PID:-}"
  kill_tree "${FRONT_PID:-}"
  # 兜底：端口上仍有监听就再收一轮（reload 的 worker 可能已换 PID）
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    for pid in $(port_pids "$port" || true); do
      kill_tree "$pid"
    done
  done
  sleep 1
  ok "后端与前端已停止（日志留在 .dev-logs/）"
}
trap cleanup EXIT INT TERM

# ---------- 后端 ----------
step "启动后端 → http://127.0.0.1:$BACKEND_PORT"
(cd "$BACKEND" && exec uv run --frozen uvicorn app.main:app --reload --port "$BACKEND_PORT") \
  >"$LOG_DIR/backend.log" 2>&1 &
BACK_PID=$!
for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
if ! curl -sf "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; then
  printf '\n--- 后端日志尾部 ---\n' >&2
  tail -20 "$LOG_DIR/backend.log" >&2 || true
  fail "后端没起来（见 .dev-logs/backend.log）"
fi
ok "后端就绪 · $(curl -s "http://127.0.0.1:$BACKEND_PORT/health")"

# ---------- 前端 ----------
step "启动前端 → http://localhost:$FRONTEND_PORT"
(cd "$FRONTEND" && exec npm run dev -- --port "$FRONTEND_PORT" --strictPort) \
  >"$LOG_DIR/frontend.log" 2>&1 &
FRONT_PID=$!
for _ in $(seq 1 120); do
  if curl -sf "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
if ! curl -sf "http://127.0.0.1:$FRONTEND_PORT/" >/dev/null 2>&1; then
  printf '\n--- 前端日志尾部 ---\n' >&2
  tail -20 "$LOG_DIR/frontend.log" >&2 || true
  fail "前端没起来（见 .dev-logs/frontend.log）"
fi
ok "前端就绪"

cat <<EOF

────────────────────────────────────────────────
  打开：  http://localhost:$FRONTEND_PORT
  后端：  http://127.0.0.1:$BACKEND_PORT  （文档 /docs）
  空库起步的话，先在登录页注册一个账号（用户名 3–20 字，密码 ≥6）
  日志：  .dev-logs/backend.log · .dev-logs/frontend.log
  Ctrl-C 一次停掉两个
────────────────────────────────────────────────

EOF

# 前台等两个进程：`wait` 可被信号打断（`tail -f` 不行 —— bash 会等前台命令结束才跑 trap）。
# 任何一方退出（含崩溃）都会走到 trap 的 cleanup，不留孤儿进程。
wait "$BACK_PID" "$FRONT_PID" || true
