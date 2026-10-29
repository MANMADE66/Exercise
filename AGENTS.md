# 训练记录 v2

FastAPI + Vue3 多用户重写。契约单一来源：`docs/SRS.md`（v1.0）与 `docs/HLD.md`（v1.5）；D1–D13 已锁定，照做，不重新决策。

## 质量关：只跑 `bash scripts/verify.sh`

唯一质量入口，按序执行并在第一处失败时退出：

`ruff check` → `ruff format --check` → `mypy`（strict）→ `pytest` → 导出 `docs/openapi.json` → 生成 `frontend/src/api-types.ts` → 生成物禁手改检查 → `oxlint --deny-warnings` → `oxfmt --check` → `vue-tsc --noEmit` → `vite build`。

- 报错信息带文件与行号，修到全绿再继续。
- mutmut 默认跳过：`RUN_MUTMUT=1 bash scripts/verify.sh` 启用，Windows 须在 WSL 内。
- 依赖精确锁定（`backend/uv.lock`、`frontend/package-lock.json` 入库）；升级走 `.scratch/training-log-v2/research/01-toolchain-versions.md` §6 的复核流程。

## 硬不变量

1. **隔离在 service 层**：routers 只做参数解析、鉴权依赖与错误码映射；所有查询用当前 `user_id` 收窄，按 id 取资源经父链校验归属，不属于当前用户一律 404（与不存在同码同文案）。写操作与事务在 services。判断只写在 `backend/app/services/isolation.py`（`select_owned` / `find_*` / `require_*`），404 只由 `backend/app/core/errors.py` 产出，不手写过滤条件与文案。
2. **parsing 不抛错**：无效输入返回 `None` / 空串，绝不向上抛异常。
3. **`frontend/src/api-types.ts` 禁手改**：契约变更只改 Pydantic 模型，重跑 verify 机器生成；verify 用「重新生成 + `git diff --exit-code`」拦截手改。
4. **`docs/openapi.json` 是生成物**：由 `scripts/export_openapi.py` 从后端导出，不手写。
5. **verify.sh 是唯一入口**：所有检查、契约导出、类型生成、构建都经它执行；代理不另起命令。

## 目录职责

- `backend/app/`：`main.py`（app 工厂、CORS dev、prod 静态托管）、`routers/`（HTTP 薄层）、`services/`（业务规则 + 隔离 + 事务 + 聚合）、`models.py`（10 表）、`schemas.py`（Pydantic 契约）、`core/`（config/security/deps）、`parsing.py`。
- `backend/tests/`：pytest + TestClient，API 断言；并发隔离用例（A/B 用户）。
- `frontend/src/`：`api.ts` 唯一出海口（token 注入、401 归一）、`api-types.ts` 生成物、`router.ts`、`stores.ts`、`views/`、`components/`。
- `docs/`：`SRS.md`、`HLD.md`、`openapi.json`。
- `scripts/`：`verify.sh`、`export_openapi.py`。
- `app/`、`tests/`、`run.py`：v1 Flask 旧实现，只作移植参考；v2 代码只写 `backend/` 与 `frontend/`，旧实现按执行票删除。

## 契约变更闭环

改 `backend/app/schemas.py` → `bash scripts/verify.sh` → `docs/openapi.json` 与 `api-types.ts` 重新生成 → `vue-tsc` 指出全部受影响的调用点 → 一并提交。前端类型只从生成物取（`components["schemas"][...]`），不手写后端形状。

## 本地运行（dev 双端口）

**一键**（推荐）：

```bat
REM Windows：双击或在 CMD/PowerShell 里执行（自动找 Git Bash，绕开 WSL 的 bash.exe）
dev.cmd
stop.cmd
REM 已装 Git Bash / 在 WSL、macOS、Linux 上时：
bash scripts/dev.sh          # 后端 :8000 + 前端 :5173，Ctrl-C 一次停两个
```

`dev.cmd` / `stop.cmd` 是纯 Windows 包装：`dev.cmd` 从 `where git` 反推 Git 自带的 `bash.exe` 再调 `scripts/dev.sh`；`stop.cmd` 用 `netstat` + `taskkill /T /F` 按端口 8000/5173 收进程树，不依赖 bash。**注意**：CMD/PowerShell 里直接敲 `bash` 会命中 `C:\Windows\System32ash.exe`（WSL 启动器），没装 WSL 时报「没有已安装的分发」——别用它。

它会���缺依赖（`uv sync --frozen` / `npm ci`）、先查端口、等后端 `/health` 就绪再起前端，日志写到 `.dev-logs/`（已 gitignore）。换端口：`BACKEND_PORT=8010 FRONTEND_PORT=5180 bash scripts/dev.sh`。

手工分开起（调试单个进程时用）：

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev        # http://127.0.0.1:5173
```

首次：`cd backend && uv sync`；`cd frontend && npm ci`。

入口文件：后端 `backend/app/main.py`（`create_app()` 工厂 + 模块级 `app`）；前端 `frontend/index.html` → `frontend/src/main.ts`。根目录 `run.py` 是 v1 Flask 启动器，v2 不用它（随旧 `app/` 一起待删）。

开发库与密钥首启自动生成在 `backend/data/`（`app.db` + `secret.key`）；空库起步时先在登录页注册账号。

## Agent skills

### Issue tracker

Local markdown: issues and specs live as `.scratch/<feature-slug>/` files in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical roles, label strings equal to their names (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

### Code review agent

The `code-review` skill reviews a diff along two axes (Standards and Spec).
Spawn **one** sub-agent with `agent: "code-review"`, passing both the Standards
brief and the Spec brief in its prompt. It is read-only, defined in
`.pi/agents/` (project), and reports both axes under `## Standards` and
`## Spec` headings in a single run. If the type isn't present, fall back to
`general-purpose` and paste the read-only constraint into the prompt. Do not
edit the skill's `SKILL.md` to wire this — the skill package updates frequently
and would overwrite it.

### Research sub-agent

When running `research` tasks or the `research` skill, delegate the
reading/investigation legwork to one sub-agent with `agent: "Explore"`
(built-in, read-only). Keep writing the final Markdown findings file in the
main session — only exploration is delegated.
