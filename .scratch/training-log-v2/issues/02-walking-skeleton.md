Type: prototype
Status: ready-for-agent
Blocked by: 01
Claimed by: pi

## Question

决定并落地「最小可走通骨架」的确切形态，作为 D13「AI-first」的地基（值得一次当面确认）。产出：

- `backend/`（FastAPI 最小 app，至少一个带 Pydantic schema 的端点）与 `frontend/`（Vite + Vue3 + TS strict 最小 SPA）各自可跑；
- `scripts/verify.sh` 串联 ruff → mypy → pytest → oxfmt/oxlint → vue-tsc → vite build，全绿；
- 后端导出 `docs/openapi.json` → openapi-typescript 生成 `frontend/src/api-types.ts` 的机器链路，加一个「禁手改」的机械检查（如 regenerate + `git diff --exit-code`）；
- 依赖按票 01 锁定的版本落锁。

先出一版骨架让人反应，再定稿 verify.sh 与生成链路。

## Comments

- 注（对齐 HLD v1.4 §12.0/D13）：verify.sh 中 oxfmt 调用需带 `--exclude=.vue`（其 .vue 原生格式化仍在移植中）；openapi.json 先由后端导出，再走生成链路，禁手改检查维持 `git diff --exit-code` 方案。依赖锁定按票 01 清单执行。

## Answer

骨架首版已落地并跑通（2026-10-23）。**待你反应后再定稿**，重点看末尾两点。

### 产物

```
backend/
  pyproject.toml          # 票 01 精确版本 + ruff/mypy/pytest 配置
  uv.lock                 # 后端锁文件（入库）
  app/main.py             # create_app：CORS(dev) + health 路由
  app/config.py           # Settings（版本、CORS 来源、dev/prod 开关）
  app/schemas.py          # HealthResponse（Pydantic，契约链起点）
  app/routers/health.py   # GET /health
  tests/conftest.py       # TestClient fixture
  tests/test_health.py    # 1 例
frontend/
  package.json            # 票 01 精确版本 + engines
  package-lock.json       # 前端锁文件（入库）
  tsconfig.json           # strict + noUncheckedIndexedAccess + verbatimModuleSyntax
  vite.config.ts · index.html
  src/main.ts · router.ts · api.ts · api-types.ts（生成物）
  src/views/HealthView.vue · App.vue · style.css
  .oxfmtrc.json（根）     # printWidth 100 显式对齐
docs/openapi.json          # 后端导出，入库
scripts/export_openapi.py  # sort_keys + indent 2，保证确定性
scripts/verify.sh          # 唯一质量入口
.gitattributes             # 生成物与 .sh 统一 LF
```

范围刻意收窄：只有 `/health` 一个端点与一个路由页；db/models/services、认证、prod 静态托管、真实业务视图留给票 04/05/06。

### 跑法

```bash
bash scripts/verify.sh          # 全绿（本机实测）

# dev 双端口
cd backend && uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev      # :5173，页面会调 /health 显示在线状态
```

### 契约链与禁手改

`HealthResponse`（Pydantic）→ `docs/openapi.json`（json.dumps sort_keys）→ openapi-typescript 7.13.0 → `src/api-types.ts` → `api.ts` 用 `components["schemas"]["HealthResponse"]` → HealthView 消费 → vue-tsc strict 复检。

禁手改检查已实测生效：verify 先重新导出/生成，再 `git diff --exit-code -- docs/openapi.json frontend/src/api-types.ts`；手工改动并 `git add` 后跑 verify 会失败（exit 1）。生成物未入库时打印「git add 后本关才生效」的提示——首次提交前没有可比较的基线，这是该方案的唯一空窗。

### 首版踩到的事实（已修/已记）

1. **pytest 需 `pythonpath = ["."]`**：`uv run pytest` 不会自动把 backend/ 放进 sys.path，否则 `from app.main` 直接 ModuleNotFoundError。
2. **oxfmt 要排两个文件模式**，不是只有 .vue：`'!**/*.vue' '!src/api-types.ts'`——生成物也不参与格式化门禁，否则 format check 会要求改生成文件。命令仍然是 `!` glob（oxfmt 无 `--exclude`，与票 01 一致）。
3. **Starlette 1.9 对 httpx 0.28 发 `StarletteDeprecationWarning`**（建议装 httpx2）。当前不影响结果；票 01 锁的 httpx 是否换 httpx2，留到后端测试票再评估，不在骨架里偷改。
4. **mutmut 默认跳过**：`RUN_MUTMUT=1` 启用，Windows（MINGW/MSYS/CYGWIN）直接报错要求进 WSL；`[tool.mutmut] source_paths` 暂为 `app`，等 parsing/days_service 落地再收窄到 HLD §12.0 指定的两个文件。
5. **mypy strict 连 tests 一起查**通过（fixture 有返回标注），未放宽。

### 待你反应的两点

- `scripts/verify.sh` 的关卡顺序、失败文案、以及「mutmut 默认关」是否符合你想要的 AI 自纠回路；
- 生成物未入库时只警告不失败，入库后严格（是否接受这个空窗）。

确认后：把 verify 入口抄进 `AGENTS.md`（票 03），并删掉旧 `app/`/`tests/`/`run.py` 的时机由执行票决定。

### 确认（2026-10-23）

用户确认两点均接受：verify 关卡顺序与 mutmut 默认关保留；「未入库只警告」的空窗接受。骨架已提交（`d25bd9c`），`docs/openapi.json` 与 `frontend/src/api-types.ts` 随提交入库，禁手改检查自此实际生效（复跑 verify：检查关通过，无「尚未入库」提示）。`scripts/export_openapi.py` 补 `newline="\n"`，避免 Windows 写出 CRLF 与 `.gitattributes` 的 LF 约定冲突。

### 复验（2026-10-24，骨架签收）

用户对票 02 的正式签收。当次实测：`bash scripts/verify.sh` 一次全绿（EXIT=0，ruff → ruff format → mypy strict → pytest 32 例 → 导出 openapi.json → 生成 api-types.ts → 禁手改 diff → oxlint --deny-warnings → oxfmt → vue-tsc → vite build），生成物禁手改关已随入库生效。

- **oxfmt 收编 `.vue`**：实测 `oxfmt --check src '**/*.vue'` 对 5 个 SFC 零 diff，原先的 `'!**/*.vue'` 排除属于策略而非能力限制，已撤销；主链只剩 `'!src/api-types.ts'`（生成物）。HLD §12.0 同步改写。
- **mutmut 本机不可验**：`wsl.exe -l -v` 显示「尚未安装用于 Linux 的分发版」，而 mutmut 依赖 `os.fork`。门控保留（`RUN_MUTMUT=1` + 非 MINGW/MSYS/CYGWIN 才执行），记账为「本机未验证」，待 `days_service` 落地那票在 WSL/CI 上补一次真实跑。
- 其余五道关卡的顺序、失败文案、`[tool.mutmut] source_paths` 现状维持不变。
