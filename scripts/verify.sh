#!/usr/bin/env bash
# 唯一质量入口（HLD §12.0 / D13）：ruff → mypy → pytest → openapi → api-types.ts 禁手改
#   → oxlint/oxfmt → vue-tsc → vite build。
#
# 用法：bash scripts/verify.sh
# 变异测试默认不跑（mutmut 依赖 os.fork）：RUN_MUTMUT=1 bash scripts/verify.sh（Windows 须在 WSL 内）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31m✗ %s\033[0m\n' "$1" >&2; exit 1; }
ok() { printf '\033[1;32m✓ %s\033[0m\n' "$1"; }

# ---------- 环境底线（HLD §12.1） ----------
step "环境底线"
command -v uv >/dev/null 2>&1 || fail "缺少 uv（Python 锁文件重放依赖它）"
command -v node >/dev/null 2>&1 || fail "缺少 node"
command -v npm >/dev/null 2>&1 || fail "缺少 npm"

NODE_VERSION="$(node -v)"
NODE_MAJOR="${NODE_VERSION#v}"
NODE_MAJOR="${NODE_MAJOR%%.*}"
NODE_REST="${NODE_VERSION#v*.}"
NODE_MINOR="${NODE_REST%%.*}"
if (( NODE_MAJOR == 20 )); then
  (( NODE_MINOR >= 19 )) || fail "Node 需 ^20.19.0 || >=22.12.0，当前 $NODE_VERSION"
elif (( NODE_MAJOR == 22 )); then
  (( NODE_MINOR >= 12 )) || fail "Node 需 ^20.19.0 || >=22.12.0，当前 $NODE_VERSION"
elif (( NODE_MAJOR < 20 )); then
  fail "Node 需 ^20.19.0 || >=22.12.0，当前 $NODE_VERSION"
fi
ok "node $NODE_VERSION · uv $(uv --version | awk '{print $2}')"

# ---------- 后端 ----------
step "uv sync --frozen（按 uv.lock 精确重放）"
(cd "$BACKEND" && uv sync --frozen --quiet)

step "ruff check"
(cd "$BACKEND" && uv run --frozen ruff check app tests)

step "ruff format --check"
(cd "$BACKEND" && uv run --frozen ruff format --check app tests)

step "mypy strict"
(cd "$BACKEND" && uv run --frozen mypy)

step "pytest"
(cd "$BACKEND" && uv run --frozen pytest)

# ---------- 契约生成链（Pydantic → openapi.json → api-types.ts） ----------
step "导出 docs/openapi.json"
(cd "$BACKEND" && uv run --frozen python "$ROOT/scripts/export_openapi.py")

if [ ! -d "$FRONTEND/node_modules" ]; then
  step "安装前端依赖（npm ci）"
  (cd "$FRONTEND" && npm ci --no-audit --no-fund)
fi

step "生成 frontend/src/api-types.ts"
(cd "$FRONTEND" && npm run --silent api:types)

step "api-types.ts 禁手改检查"
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  if git -C "$ROOT" ls-files --error-unmatch docs/openapi.json frontend/src/api-types.ts \
      >/dev/null 2>&1; then
    if ! git -C "$ROOT" diff --exit-code -- docs/openapi.json frontend/src/api-types.ts; then
      fail "生成物与重新生成的结果不一致：不要手改 api-types.ts / openapi.json，改 Pydantic 模型后重跑 verify"
    fi
  else
    printf '  ! 生成物尚未入库：git add docs/openapi.json frontend/src/api-types.ts 之后本关才生效\n'
  fi
fi

# ---------- 前端 ----------
step "oxlint --deny-warnings"
(cd "$FRONTEND" && npx --no-install oxlint --deny-warnings src)

step "oxfmt --check（.vue 暂不参与、api-types.ts 为生成物，正确性由 vue-tsc 承担）"
(cd "$FRONTEND" && npx --no-install oxfmt --check src '!**/*.vue' '!src/api-types.ts')

step "vue-tsc --noEmit（TS strict + noUncheckedIndexedAccess）"
(cd "$FRONTEND" && npx --no-install vue-tsc --noEmit -p tsconfig.json)

step "vite build"
(cd "$FRONTEND" && npx --no-install vite build)

# ---------- 变异测试（可选，POSIX only） ----------
if [ "${RUN_MUTMUT:-0}" = "1" ]; then
  case "$(uname -s)" in
    MINGW* | MSYS* | CYGWIN*) fail "mutmut 依赖 os.fork，请在 WSL 内运行 verify.sh" ;;
  esac
  step "mutmut run"
  (cd "$BACKEND" && uv run --frozen mutmut run)
else
  printf '\n\033[1;33m· mutmut 已跳过（RUN_MUTMUT=1 启用；Windows 须在 WSL 内）\033[0m\n'
fi

printf '\n\033[1;32m全部关卡通过 ✓\033[0m\n'
