# 概要设计文档（HLD）— 训练记录 v2

版本 1.5 · 上游需求：`docs/SRS.md` v1.0 · 决策索引见文末
（v1.3：补充 §12.0 工具链与质量关 —— 格式化、静态检查、类型检查与变异测试；新增决策 D12，裁定变异测试仅落后端，前端维持 D10 无自动化测试）
（v1.4：AI-first 技术栈调整 —— D13 前端 TypeScript strict + OpenAPI 生成前端类型 + 单命令质量关 + 依赖版本锁定）
（v1.5：落实 D13 的版本锁定 —— 新增 §12.1 精确版本清单（2026-10-23 实测定版）；修正 §12.0 的 oxfmt 命令（无 `--exclude` 参数）与 oxlint 的 `.vue` 覆盖边界；TypeScript 锁定 5.9.3 而非 latest 7.x；证据见 `.scratch/training-log-v2/research/01-toolchain-versions.md`）
（本文档定义模块划分、数据结构、接口契约与关键流程；逐项与 SRS 编号对应）

---

## 1. 引言

### 1.1 目的与范围
本文档把 SRS 的功能需求（FR-1~FR-10）与非功能需求（NFR-1~NFR-5）映射为可实施的软件结构：总体架构、模块职责、数据库模式、API 契约、认证与安全机制、前端结构、关键流程与部署形态。**不含**逐函数的详细设计（详细设计随实现给出）。

### 1.2 上游约束（摘要，均已在访谈中锁定）
| # | 决策 | 落点 |
|---|---|---|
| D1 | 小团队多人、不同设备访问 | 登录 + 全表 user_id 隔离 |
| D2 | FastAPI 后端，JSON API | §2, §8 |
| D3 | 前端 Vite + Vue3 + vue-router | §9 |
| D4 | SQLite + SQLAlchemy，保留换库余地 | §5 |
| D5 | JWT 7 天、无 refresh、开放注册、仅用户名+密码 | §7 |
| D6 | 完全数据隔离（含动作库），越权一律 404 | §5、§8 |
| D7 | 动作式 + 聚合读 API，写操作回传日聚合 | §9 |
| D8 | 空库起步，不迁移旧数据；旧 Flask 代码移除 | §13 |
| D9 | 交互原样平移（就地展开/autosave/预填/移动） | §10 |
| D10 | 后端 pytest 重写为 API 断言；前端无自动化测试 | §12 |
| D11 | 单仓库 backend/ + frontend/；dev/prod 双启动模式 | §13 |
| D12 | 前端质量关 = oxlint + oxfmt（无测试框架，不变异）；变异测试仅后端 mutmut，目标 parsing/位置维护逻辑 | §12.0 |
| D13 | AI-first：前端升级为 TypeScript strict；前端类型经 OpenAPI 从后端契约机器生成（不手写）；质量关汇总为单一命令 `scripts/verify.sh`；依赖一律版本锁定（清单见 §12.1） | §2、§5、§10、§12.0、§12.1 |

---

## 2. 技术选型

| 项 | 选型 | 理由 |
|---|---|---|
| 后端框架 | FastAPI + Uvicorn | 访谈锁定（D2）；原生异步、内置数据校验、自动 OpenAPI 文档 |
| ORM / 数据库 | SQLAlchemy + SQLite（单文件库） | 零运维，小团队规模足够；标准 ORM 写表模型，未来切 PostgreSQL 仅改连接串（D4） |
| 认证 | JWT（HS256，7 天有效期） | 前后端分离 + 多设备，token 不依赖 cookie/同源；无 refresh（内网可信环境，重登成本可接受）（D5） |
| 密码哈希 | bcrypt（cost=12） | 业界标准，自带逐哈希盐。注：FastAPI 官方教程现已改推 `pwdlib[argon2]`；本项目维持 bcrypt（D5 侧决定），改动面仅 `core/security.py`。**不得引入 passlib**（Python 3.13 起失效） |
| 前端 | Vite + Vue3 + vue-router，TypeScript strict | 状态驱动 UI（月历/展开/自动保存）组件化收益明显；构建产物即纯静态（D3）；TS strict 让类型成为可执行契约——AI 辅助开发中类型错误即编译错误，当场拦截（D13） |
| 状态管理 | 不引入 Pinia/Vuex；localStorage + 视图内 reactive | 三路由规模不需要全局状态树 |
| 测试 | pytest + FastAPI TestClient | 后端 API 直测；前端不写自动化测试（D10） |
| 质量工具链 | 后端 ruff（lint+format）+ mypy strict；前端 oxlint + oxfmt（beta，锁版本）+ vue-tsc；变异测试后端 mutmut | FastAPI 强依赖类型标注，类型检查近乎白捡；oxlint 兼容 ESLint，对 `.vue` **只覆盖 `<script>` 块**（无 `no-unused-vars`、无模板规则）；oxfmt 的 `.vue` 走**内置 Prettier**（非 native，官方标注 native 移植进行中），故 `.vue` 的正确性由 `vue-tsc` strict 承担（D12/D13，版本见 §12.1） |
| 依赖锁定 | Python 用 uv/pip 编译锁文件，前端 package-lock.json 必须入库 | AI-first 关键前提：质量关必须可确定重放——代理与人在任何机器上跑同一命令得到同一结果，环境漂移会让所有检查失真（D13） |
| 部署 | 单进程 FastAPI 同时托管 API 与静态前端（prod）；开发期双端口 + CORS | 内网小团队单地址访问，零反向代理（D11） |

---

## 3. 上游决策落点详述

（访谈结论逐条映射，详见 §1.2 表；其中旧数据处置以「重新开始、空库起步」的明确裁定为准。）

---

## 4. 总体架构

### 4.1 架构图

```
┌────────────── 浏览器（各成员设备，Vue3 SPA 静态文件）──────────────┐
│  视图：LoginView │ CalendarView │ TemplatesView                    │
│  组件：MonthGrid / DayDetail / WeekMetric / TopBar                 │
│  状态：localStorage(token, user) + 各视图内最新聚合快照              │
│  api.ts：fetch 封装 · token 注入 · 401 统一跳登录                   │
└─────────────────────────────┬──────────────────────────────────────┘
                             │ HTTP/JSON（Authorization: Bearer <JWT>）
                             ▼
┌────────────── FastAPI 后端（uvicorn :8000）──────────────────────────┐
│ main.py      create_app · CORS(dev) · 静态托管 dist (prod)           │
│ routers/     auth · calendar · days · templates · metrics           │
│              （HTTP 薄层：参数→service→状态码映射）                    │
│ core/deps    get_db · get_current_user（JWT 解码 + 查库）             │
│ services/    isolation · calendar · days · templates                │
│              （业务规则 + 隔离过滤 + 事务 + 聚合组装）                  │
│ models.py    10 表 SQLAlchemy ORM                                    │
│ parsing.py   重量/组数/次数容错解析（语义与旧版一致）                   │
└─────────────────────────────┬──────────────────────────────────────┘
                              ▼
          SQLite 单文件库 backend/data/app.db（WAL 模式）
          JWT 密钥 backend/data/secret.key（首启生成，重启不失效）
```

### 4.2 关键架构决定

1. **单进程单服务**：prod 下 FastAPI 同时承担 API 与前端静态托管，成员只访问 `http://<主机IP>:8000`；dev 才拆 5173/8000 两端口。无反向代理、无缓存层、无队列。
2. **后端三层**：routers 只做参数解析、鉴权依赖与错误码映射；services 持有全部业务规则、隔离过滤与事务；models 仅映射表。parsing 为独立横切模块。
3. **隔离在 service 层强制**：所有查询以当前用户收窄范围；按 id 取资源校验归属链，不匹配一律 404。
4. **无服务端会话**：JWT 自包含，登出是纯前端清 token 行为，没有会话表和登出端点。
5. **密钥持久化**：JWT 签名密钥首启随机生成并写盘，重启不失效既有 token；支持环境变量覆盖。
6. **聚合契约**：日级写操作的响应即最新日聚合，前端整体替换状态，不发二次 GET。

---

## 5. 仓库目录与数据结构

### 5.1 目录结构

```
训练规划/
├─ backend/
│  ├─ app/                     # FastAPI 工程包
│  │  ├─ main.py               # create_app 工厂、CORS(dev)、静态挂载与 SPA 兜底(prod)
│  │  ├─ db.py                 # create_db_engine / create_session_factory / get_db、密钥持久化；建库 + create_all + WAL + 每连接 PRAGMA foreign_keys=ON
│  │  ├─ core/
│  │  │  ├─ config.py          # 路径常量、环境变量（库路径/SECRET/token 有效期）
│  │  │  ├─ security.py         # bcrypt 哈希与校验、JWT 编解码
│  │  │  ├─ errors.py           # NotFoundError + NOT_FOUND_DETAIL（404 的唯一出口）
│  │  │  └─ deps.py             # get_current_user（Bearer→users 查询→当前用户）
│  │  ├─ models.py              # 10 张表 ORM
│  │  ├─ schemas.py             # Pydantic 请求/响应模型（DayAggregate、CalendarAggregate 等）
│  │  ├─ parsing.py             # 容错解析（无效→None/空字符串，绝不抛错）
│  │  ├─ services/
│  │  │  ├─ isolation.py      # 归属隔离唯一入口：select_owned / require_*（父链）/ find_*
│  │  │  ├─ calendar_service.py # 月历网格、logged_dates、周归属与周聚合行
│  │  │  ├─ days_service.py     # get_or_create、position 维护、prefill 幂等、日聚合组装
│  │  │  └─ template_service.py # 模板 CRUD、apply 逐日检查跳过
│  │  └─ routers/
│  │     ├─ health.py          # 骨架期产物，保留作健康检查 / 前端探活
│  │     └─ auth.py · calendar.py · days.py · templates.py · metrics.py
│  ├─ data/                     # app.db、secret.key（gitignore）
│  └─ tests/                    # conftest + 各域测试（§12）
├─ frontend/
│  ├─ package.json · package-lock.json · vite.config.ts · index.html
│  └─ src/
│     ├─ main.ts                # createApp、router、全局样式（方向 A 令牌迁移）
│     ├─ router.ts              # 三路由 + 全局守卫
│     ├─ api-types.ts           # openapi-typescript 从后端 OpenAPI 生成，禁止手改（D13 契约单源）
│     ├─ api.ts                 # 唯一出海口：token 注入、401 处理、错误归一
│     ├─ stores.ts              # token/user 小状态（localStorage 同步）
│     ├─ views/                 # LoginView.vue · CalendarView.vue · TemplatesView.vue
│     └─ components/            # MonthGrid.vue · DayDetail.vue · WeekMetric.vue · TopBar.vue
├─ docs/                        # SRS.md · HLD.md · openapi.json（后端导出的契约单源）
├─ AGENTS.md                    # AI 代理协作约定：verify 命令、目录结构、硬不变量（隔离不越 service 层、parsing 不抛错、api-types.ts 禁手改）——写给 AI 代理的第一入口
├─ scripts/
│  └─ verify.sh                 # 一命令质量关：ruff → mypy → pytest → oxfmt/oxlint → vue-tsc → vite build
└─ README.md                    # dev / prod 双启动说明
```

> **目标树说明（2026-10-24 校准，票 08 更新）**：`services/calendar_service.py`、`days_service.py`、`template_service.py`、四个业务 router（calendar/days/templates/metrics）与四个业务组件（MonthGrid · DayDetail · WeekMetric · TopBar）**尚未落地**，随后续执行票创建。已落地：`main.py` · `db.py` · `core/config.py` · `core/security.py` · `core/errors.py` · `core/deps.py` · `models.py` · `schemas.py` · `parsing.py` · `services/isolation.py` · `routers/health.py` · `routers/auth.py` · `services/auth_service.py`，前端三路由 + `api.ts` / `stores.ts` / `api-types.ts` / `components/BackendStatus.vue` / 已接入登录注册的 `LoginView.vue`（票 07/08）。

### 5.2 数据结构要点

- 业务表全部带 `user_id` 外键，唯一键由「全局唯一」收紧为「(user_id, 原键)」：
  - exercises: **(user_id, name)** 唯一；
  - plan_days: **(user_id, date)** 唯一（date 建索引）；
  - body_metrics: **(user_id, week_start)** 唯一（week_start 恒为周一）；
  - template_days: **(template_id, day_index)** 唯一；
  - day_notes: plan_day_id 唯一（1:1）。
- actual_items 追加 **UNIQUE(plan_day_id, planned_item_id)**（prefill 幂等加固；planned_item_id 可空，计划外条目为 NULL）。
- 级联约定：删除 plan_day 级联其 planned_items / actual_items / day_notes；删除 planned_item **不**级联 actual_item，仅置空 planned_item_id（历史保留，SRS FR-6.2）；删除 cycle_template 级联天/条目。
- 模板不含重量（SRS FR-9.2）；apply 时仅复制骨架字段（exercise、sets、reps、position）。
- 连接：`create_engine(URL.create("sqlite", database=<abs path>.as_posix()))`，`check_same_thread=False`，启动执行 `journal_mode=WAL` + `create_all()`，并对**每个连接**开 `PRAGMA foreign_keys=ON`（SQLite 默认关，不开则 CASCADE / SET NULL 静默失效）。
- 引擎与会话工厂由 `create_app` 的 lifespan 创建并挂 `app.state`，不在 import 期碰磁盘——否则 `scripts/export_openapi.py` 只为取契约也会顺手建库、生成密钥（票 04 裁定）。

---

## 7. 认证与会话设计

```
POST /auth/register {username, password}
  ├─ 校验：username 3–20 且唯一；password ≥ 6
  │      违规 → 422{detail:中文消息}；username 重复 → 409
  ├─ bcrypt(cost=12) 哈希落库
  └─ 注册即登录：签发 JWT → {token, user}

POST /auth/login {username, password}
  ├─ bcrypt 校验；失败 → 401「用户名或密码不对」（统一文案，不区分用户名/密码错误）
  └─ 成功 → {token, user}

JWT：HS256；payload {sub: user_id, iat, exp = iat + 7d}
  生成/校验：core/security.py；user 不存在 → 401
SECRET：首启随机生成写入 backend/data/secret.key（重启不失效）；环境变量覆盖优先

登出：纯前端清 localStorage.token → 跳 /login（无服务端会话表、无登出端点，SRS FR-2.4）
```

---

## 8. 隔离机制（安全核心，贯穿全部 API）

1. **依赖注入收口**：除 auth 两个端点外全部经过 `get_current_user`；无 token / 坏 token / 过期 → 401。
2. **查询范围化**：service 层所有列表与聚合查询以 user_id 过滤（calendar、days、templates、metrics 全部如此）；plan_day 定位一律 `PlanDay.filter(user_id, date)`。
3. **归属校验**：按 id 操作的资源（plan-item / actual-item / note / template 及其子项）经父链 join 回 user_id，不匹配 **404**，与「不存在」同码同文案——防资源枚举（SRS FR-3.2）。
4. **动作库命名空间**：exercise 按 (user_id, name) 唯一，get_or_create 仅在本人命名空间查找/创建；A 的「深蹲」对 B 不可见（SRS FR-3.4）。
5. **错误归一**：`{"detail": "..."}`；400 日期/月份格式非法；401 鉴权；404 不存在或不属于你；409 用户名重复；422 字段校验。

> 落地位置（票 08）：判断只写在 `app/services/isolation.py`（`select_owned` 列表收窄；`require_*` 父链校验；`find_*` 业务键查找），routers 只传当前 `user_id`，不拼过滤条件；404 的文案与状态码只在 `app/core/errors.py` 产出一次（`NOT_FOUND_DETAIL` + `NotFoundError` + 全局处理器），业务 router 不需要 try/except。

---

## 9. API 端点表

### 9.1 端点表

| 方法/路径 | 请求体/参数 | 成功响应 | 对应 SRS |
|---|---|---|---|
| POST /auth/register | {username, password} | 200 {token, user{username}} | FR-1 |
| POST /auth/login | {username, password} | 200 {token, user} | FR-2 |
| GET /calendar | ?month=YYYY-MM 可缺省 | 日历聚合（9.2/9.3） | FR-4 |
| GET /days/{iso_date} | — | 日聚合（9.2） | FR-5 |
| POST /days/{iso_date}/plan-items | {exercise, weight?, sets?, reps?} | **日聚合** | FR-6.1 |
| DELETE /plan-items/{id} | — | 日聚合 | FR-6.2 |
| POST /plan-items/{id}/move | {direction: up\|down} | 日聚合 | FR-6.3 |
| POST /days/{iso_date}/actual/prefill | — | 日聚合 | FR-7.1 |
| POST /days/{iso_date}/actual-items | {exercise,…, note?} | 日聚合 | FR-7.3 |
| PATCH /actual-items/{id} | 任意子集{weight?, sets?, reps?, note?} | 日聚合 | FR-7.2 |
| DELETE /actual-items/{id} | — | 日聚合 | FR-7.4 |
| PUT /days/{iso_date}/note | {text}（空串合法=清空） | 日聚合 | FR-8 |
| GET /templates | — | 模板列表（含模板日+条目） | FR-9.1 |
| POST /templates | {name?, length_days, days[{kind,title,items[]}]} | 新模板 | FR-9.2 |
| DELETE /templates/{id} | — | 模板列表 | FR-9.4 |
| POST /templates/{id}/apply | {start: ISO} | {created, skipped, skipped_dates} | FR-9.3 |
| PUT /metrics/{week_start} | {weight(必填合法), body_fat?, note?} | 200 该周 metric；weight 非法 422 | FR-10 |

所有 /days 与 plan-item/actual-item 端点在写操作完成后返回**新鲜日聚合**（D7 契约，前端整体替换，不再发 GET）。

### 9.2 错误码约定

统一错误体 `{"detail": "<中文消息>"}`（FastAPI 惯例）：
- 401：未鉴权 / token 无效或过期；
- 400：日期或月份格式非法；
- 404：资源不存在**或不属于当前用户**（二者不可区分，防枚举）；
- 409：用户名重复；
- 422：字段校验失败（Pydantic 原生）。

---

## 11. 关键流程（时序）

```
登录：提交 → /auth/login → bcrypt 校验 → JWT(7d) → localStorage → /calendar
展开：点格 → GET /days/{iso} → DayAggregate → DayDetail 展开行
保存：失焦 → PATCH /actual-items/{id} → 归属校验 → 更新+commit → 返回聚合 → 前端替换
预填：POST /actual/prefill → 幂等复制未关联条目 → 聚合回填
铺排：POST /templates/{id}/apply {start} → 逐日校验已有 plan_day（跳过）→ 新建天+条目
      → commit → 结果 {created, skipped, skipped_dates} → 前端月历刷新+提示
体重：周格失焦 → PUT /metrics/{week_start} → 非法 422 列内提示；合法 upsert → 月历行更新
```

---

## 10. 前端设计

### 10.1 组件划分（Vue3 单文件组件）

（对应 §10.1，见目录结构 §5；组件职责见 §4.1 架构图前端部分。）

### 10.2 类型契约单源（D13）

全部 SFC 使用 `<script setup lang="ts">`，tsconfig 严格模式（strict · noUncheckedIndexedAccess）。前端类型与后端契约共享同一机器可读来源：后端导出 OpenAPI 至 `docs/openapi.json`（入库）→ openapi-typescript 生成 `src/api-types.ts` → api.ts 按生成类型消费。手写不复刻后端形状，杜绝契约漂移；契约变更流程固定为「改 Pydantic 模型 → 导出 openapi.json → 重新生成 api-types.ts → vue-tsc 指出全部受影响调用点」。类型是编译期质量关，不替代测试，D10（前端无自动化测试）维持不变。

---

## 12. 测试设计

### 12.0 工具链与质量关（D12/D13）

- **单一确定性命令**：任何质量检查、契约导出、类型生成、编译测试都只能通过 `scripts/verify.sh` 入口执行；代理不自由发挥。这是代理自我纠错回路的基础：报错信息一律指向文件与行号。
- **类型即护栏，而非补丁**：前端 TS strict 保证代理重写的 UI 代码在编译期就被 Pydantic/TS 双重约束——而不是等到 PR 人工审查时才发现。
- **契约变更闭环**：Pydantic → openapi.json → api-types.ts 是单向机器流水线；禁止手写前端 schema——TS 是编译期关，不是测试替代，D10 维持不变。
- **依赖必须锁定**：Python lockfile + package-lock.json 入库；代理生成环境（venv 重建、CI 重建）用锁文件精确重放，不追求最新但不接受漂移。精确版号见 §12.1。
- **oxfmt 风险管理**：`oxfmt@0.74.0` 下 `.vue` 由**内置 Prettier** 处理（非 native 引擎）；2026-10-24 复验 5 个 `.vue` 全部零 diff，故 verify.sh 已把 `.vue` 纳入主链，原「只格式化 `.ts/.js`」的保守策略作废。编辑器侧 Prettier 3.9.10 与本工具同源，不产生两套风格。**默认 `printWidth=100`（Prettier 为 80）且不读 `package.json` 的 `prettier` 字段** → 必须提交 `.oxfmtrc.json` 显式对齐。oxc 只为 oxlint 发布过 semver 政策（formatter 无），minor 升版可重排全树：锁精确版本，升级后 `git diff --stat` 突增即回退。
| 工具 | 命令 | 覆盖范围 |
|---|---|---|
| ruff check | `ruff check backend/` | 后端静态检查（import 顺序、未用变量、语法类错误） |
| ruff format | `ruff format --check backend/` | 后端格式化校验 |
| mypy strict | `mypy backend/` | 后端类型检查（FastAPI 的 Pydantic/Depends 标注白捡的 correctness） |
| vue-tsc | `vue-tsc --noEmit -p frontend` | 前端 TS strict 编译期类型检查——前端的"编译测试"，`vite build` 前必须通过（D13） |
| oxlint | `oxlint --deny-warnings frontend/src` | 前端静态检查（兼容 ESLint）。`.vue` **只 lint `<script>` 块**，且 `no-unused-vars` 在 SFC 内不报（同类死代码写在 `.ts` 里才报）→ `.vue` 不靠它兜底。**必须带 `--deny-warnings`**：默认 warning 不导致非零退出 |
| oxfmt | `oxfmt --check frontend/src '!src/api-types.ts'` | 前端格式化校验，**含 `.vue`**（走内置 Prettier）。**oxfmt 无 `--exclude` 参数**（写了会 `Error: --exclude is not expected in this context` 并退出 1）；排除只能用 `!` 前缀 glob 或 `--ignore-path`。生成物 `api-types.ts` 仍排除（否则门禁会要求改生成文件）。锁版本，输出漂移即回退 |
| 类型契约 | 后端导出 `docs/openapi.json` → openapi-typescript 生成 `api-types.ts` | 前后端类型机器同源，禁止手写前端 schema；契约变更时 vue-tsc 自动指出全部受影响调用点（§10.2、D13） |
| pytest | `pytest backend/tests -q` | 功能回归（§12 覆盖矩阵） |
| mutmut | `mutmut run`（目标配在 `[tool.mutmut] source_paths`） | 变异测试，仅后端业务逻辑：`app/parsing.py` 与 `app/services/days_service.py`（parsing 容错、position 维护）；按 D10 前端无测试套件，不加 Stryker-js。3.6+ 已把 `paths_to_mutate` 更名为 `source_paths`；**依赖 `os.fork`，Windows 须在 WSL 内跑** → verify.sh 需门控此关 |
| verify.sh | `bash scripts/verify.sh` | 将上述全部关卡串联为**一个确定性命令**——这是 AI-first 的核心：代理自我纠错回路只依赖单一入口，不自由发挥 |

- 框架：pytest + FastAPI TestClient（ASGI in-process，临时 SQLite），conftest 造用户 A/B 与 token 封装助手、带 N 条计划的日期工厂。
- 覆盖矩阵（对齐旧 41 例覆盖量并补隔离、鉴权安全面）：

| 域 | 覆盖点 |
|---|---|
| auth | 注册成功/重复 409/用户名长度/密码≥6；登录成功/密码错误统一文案；无 token 401；坏 token 401 |
| 隔离（安全关键） | B 对 A 的 day/calendar/templates 读写删均 404；列表互相不可见；exercise 命名空间互不可见 |
| calendar | 非法 month 回退；网格补 null；logged_dates；周聚合行 |
| days | 聚合初值；plan-item 增删移与边界；prefill 幂等；note 空串清空、隐式建日仅在有文本时 |
| parsing | kg/公斤/千克剥除、逗号小数点、负数/非法值→NULL、reps 自由文本保留 |
| templates | 创建长度截断 12；apply 跳过已排日期且不覆盖、created/skipped 计数；跨用户 apply 404 |
| metrics | 同周 upsert、周一起点、非法体重 422 不落库 |

- 前端无自动化测试（D10）：编译期质量关为 `vue-tsc --noEmit` + `npm run build` 通过，另加手动冒烟（登录→月历→展开→autosave→预填→模板 apply→周体重→登出）。

### 12.1 版本锁定清单（D13 落地，2026-10-23 核验）

全部写成 `==` / 精确版号（禁 `^`、`~`、`>=`）；证据与未核实项见 `.scratch/training-log-v2/research/01-toolchain-versions.md`。

| 后端（pyproject，`requires-python = ">=3.11"`） | 锁定版 |
|---|---|
| fastapi / uvicorn[standard] | `0.161.1` / `0.54.0` |
| sqlalchemy / pydantic | `2.1.6` / `2.14.1` |
| bcrypt / pyjwt | `5.0.0` / `2.15.1` |
| pytest / httpx2（TestClient） | `9.1.1` / `2.16.0` |
| ruff / mypy / mutmut | `0.17.2` / `2.4.0` / `3.8.0` |

| 前端（package.json） | 锁定版 | 说明 |
|---|---|---|
| vue / vue-router | `3.5.44` / `5.4.0` | vue-router 5.x 有 breaking changes，必须锁死；要求 vue ≥ 3.5.34 |
| vite / @vitejs/plugin-vue | `8.3.5` / `6.0.10` | 两者 peer 范围吻合 |
| typescript | **`5.9.3`** | **刻意偏离 latest（7.0.2）**：TS 7.0 不发布编译器 API，`vue-tsc` 不可用；`openapi-typescript@7.13.0` 的 peer 是 `^5.x`，装 6.x 会 ERESOLVE 硬失败。5.9.3 是本次实测中唯一跑通全链（安装→codegen→vue-tsc→build）的版本 |
| vue-tsc / openapi-typescript | `3.3.13` / `7.13.0` | 契约生成链的两端 |
| oxlint / oxfmt | `1.89.0` / `0.74.0` | oxlint minor 升版允许新增诊断（官方 semver 政策），故锁死 |
| prettier | `3.9.10` | 仅编辑器/`.vue` 兜底，不入 verify 主链 |

**环境底线**（verify.sh 可断言）：Python ≥ 3.11（由 sqlalchemy 2.1 / starlette 1.9 抬高）；Node `^20.19.0 || >=22.12.0`（vite / plugin-vue / oxlint / oxfmt 的 `engines` 完全一致）。

**落锁前必做**：重跑 `.scratch/training-log-v2/research/01-toolchain-versions.md` §6 的复核命令；版本对不上则按本表重新核定后再写锁文件，禁止直接 follow latest。

---

## 13. 部署与运行

### 13.1 dev 模式（双端口）
```
终端1: cd backend && uvicorn app.main:app --port 8000 --reload
终端2: cd frontend && npm run dev        # Vite dev server :5173，CORS 已放行
```
（可选：vite.config 配 `/…`→8000 代理以省 CORS；默认方案为 CORS。）

### 13.2 prod 模式（单地址，D11）
```
cd frontend && npm run build            # 产物 frontend/dist
uvicorn app.main:app --host 0.0.0.0 --port 8000
# main.py 于 API 路由后挂载：
#   /assets ← StaticFiles(dist/assets)
#   catch-all GET：路径不以已知 API 前缀开头且非资源 → 返回 index.html（history 模式兜底）
```
成员浏览器访问 `http://<主机IP>:8000`。数据/密钥同在 `backend/data/`。

### 13.3 备份
复制 `backend/data/app.db`（WAL 模式下顺带取 `-wal` 旁文件或先停服务）。

---

## 15. 决策索引

（SRS §10 的 12 条访谈结论 + §1.2 表 D1–D13；冲突裁定：旧数据以「重新开始/空库」为准。）
