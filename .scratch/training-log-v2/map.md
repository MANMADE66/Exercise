# 训练记录 v2 — 地图

## Destination

训练记录 v2 落地：按 `docs/SRS.md`（v1.0）与 `docs/HLD.md`（v1.5）的契约，把单机 Flask v1 重写为 FastAPI + Vue3 多用户版；`scripts/verify.sh` 全绿，旧 `app/` 删除，README 双模式。地图结束 = 无决策残留、可整包交付出执行。

## 完成情况（2026-10-24）

**票 01–15 全部闭环**（业务域 7 张票 09–15 落完；每票均带 `## Answer`，Status 一律保持 `ready-for-agent` —— 按 `docs/agents/issue-tracker.md`，`## Answer` 才是闭环标记，不另设 done 标签）：

| 票 | 事项 | 落地 |
|---|---|---|
| 01 | 工具链版本锁定 | `d25bd9c` 之前，清单见 HLD §12.1 |
| 02 | 走通骨架 + verify.sh | `d25bd9c`，2026-10-24 复验签收 |
| 03 | AGENTS.md 操作约定 | `6bdf6e4` |
| 04 | 后端数据层（10 表） | `8eabf15` |
| 05 | parsing 移植 | `ecaa7cc` |
| 06 | 前端骨架（三路由） | `517fe3c` |
| 07 | 认证与会话（bcrypt + JWT + /auth/*） | `c333e4f` |
| 08 | 归属隔离与 404 归一（`isolation.py` + `core/errors.py` + A/B 工厂） | `3287232` |
| 09 | 日聚合读（`GET /days/{iso}` + `DayAggregate` + `aggregate_day`） | `2be4f8b` |
| 10 | 月历聚合（`GET /calendar` + `CalendarAggregate`） | `731e732` |
| 11 | 计划条目增删移（FR-6 三端点 + 并发 get-or-create 回滚重查） | `3999ad0` |
| 12 | 实际完成记录四端点（FR-7 prefill / PATCH 三态 / 计划外新增 / 删除） | `6e731b9` |
| 13 | 感受笔记（FR-8 整段保存 + 条件隐式建日） | `7c73255` |
| 14 | 循环模板 CRUD 与 apply 铺排（FR-9：天数归一 / 已排日期跳过不覆盖） | `2c733c8` |
| 15 | 周体重 upsert（FR-10：`PUT /metrics/{week_start}` + 周一归一 + 非法体重 422 不落库） | `4ce9c04` |

## 前沿（2026-10-24 切票，业务域）

雾区「执行层里程碑」的 7 张票（09–15）**全部闭环**，业务域后端契约齐了：09 `2be4f8b`、10
`731e732`、11 `3999ad0`、12 `6e731b9`、13 `7c73255`、14 `2c733c8`、15 `4ce9c04`。

| 票 | 事项 | 落地 |
|---|---|---|
| 09 | [日聚合读（`GET /days/{iso}` + `DayAggregate`）](issues/09-day-aggregate.md) | ✅ `2be4f8b` |
| 10 | [月历聚合（`GET /calendar`）](issues/10-calendar-aggregate.md) | ✅ `731e732` |
| 11 | [计划条目增删移（FR-6）](issues/11-plan-items.md) | ✅ `3999ad0` |
| 12 | [实际记录与 prefill（FR-7）](issues/12-actual-items.md) | ✅ `6e731b9` |
| 13 | [感受笔记（FR-8）](issues/13-day-note.md) | ✅ `7c73255` |
| 14 | [循环模板（FR-9）](issues/14-templates.md) | ✅ `2c733c8` |
| 15 | [周体重（FR-10）](issues/15-week-metrics.md) | ✅ `4ce9c04` |

**下一轮的前沿回到雾区**：前端组件平移（MonthGrid · DayDetail · WeekMetric · TopBar + 三个 view
接真实请求）**已切成 16–20（见下）**—— 后端 14 个端点的契约全部机器生成到 `api-types.ts`（D13 的
阻塞理由已消失）。prod 静态托管（D11）与删除旧 `app/` 仍等全链路走通后再切（见「Not yet specified」）。

切票理由（保留原文）：09 是**唯一的根** —— FR-6/7/8 的每个写操作都返回整天聚合（D7），契约与
`aggregate_day` 必须先有。10 与 15 只依赖已闭环的隔离层，故一并放进前沿并行。11–14 的业务规则
写进票面（v1 语义 + 需裁定的缺口），等 09 闭环即可直接开工。**11、12、13 按序闭合**；14 与 15
按「各碰自己的新文件」并行 —— 事后看这个判断只对了一半：两者都改 `schemas.py` / `main.py` /
生成物，实际只能错开提交（票 14 的 `## Answer` 已记账，下一轮同动契约的票必须串行）。

### 前沿（2026-10-24 二次切票，前端平移）

前端五票已按 [`spec.md`](spec.md) 切出，全部 `Status: ready-for-agent`、无 `Claimed by`，可放手让
代理领：

| 票 | 事项 | 阻塞于 |
|---|---|---|
| 16 | [月历只读网格 + 共享层预置（14 个出海口包装 · 纯函数 · 方向 A 样式 · 顶栏）](issues/16-calendar-readonly.md) | — |
| 17 | [周体重列（失焦保存 + 非法还原 + 保住体脂率/备注）](issues/17-week-metric.md) | 16 |
| 18 | [日详情展开：读聚合 + 计划列增删移](issues/18-day-detail-plan.md) | 16 |
| 19 | [实际列与感受（autosave · 预填 · 计划外新增 · 删除）](issues/19-day-detail-actual.md) | 18 |
| 20 | [模板页（列表 · 新建 · 删除 · 铺排）](issues/20-templates-view.md) | 16 |

依赖图：`16 → 17`、`16 → 18 → 19`、`16 → 20`。**文件冲突不是阻塞边**：17 与 18 都动
`MonthGrid` / 月历视图，按编号串行提交；20 只碰模板页自己的文件，可与 17/18 错开。

切分口径改动了一处：spec 建议的第 1 张票原是「共享层一次改完」（纯水平切片、在浏览器里看不出
变化），已并进 16 的月历只读网格 —— 同一票既做 prefactor 又交付一个能亲自点开的竖切。

## Notes

- 契约单一来源：`docs/SRS.md` + `docs/HLD.md`；D1–D13 已锁定，执行时照做，不重新决策。
- 本 effort 覆盖执行（Notes 覆盖默认「只产决策」）：HLD 已裁定几乎全部决策，本图只解决残余的工具链决策（票 01/02/03）与骨架落地（票 04/05/06），此后转交执行线（07 起）。
- 每会话先读：`docs/agents/issue-tracker.md`、`docs/agents/domain.md`、`AGENTS.md`。
- 硬不变量（票 03 落进 AGENTS.md）：隔离不越 service 层；parsing 不抛错；api-types.ts 禁手改；verify.sh 是唯一质量入口。
- **同树并行**：多会话在同一工作树开发时，后开工者先 `git log` / `git status` 确认前一张票已提交，再改共享文件（`schemas.py` / `main.py` / 生成物 `openapi.json` / `api-types.ts`）；新文件（service / router / 测试）可先写。票 09 与票 10 就是这么错开的。

## Decisions so far


- 票 01（工具链版本）：全部锁定 —— 后端 fastapi 0.161.1 / uvicorn 0.54.0 / sqlalchemy 2.1.6 / pydantic 2.14.1 / bcrypt 5.0.0 / pyjwt 2.15.1 / pytest 9.1.1 / ruff 0.17.2 / mypy 2.4.0 / mutmut 3.8.0；前端 vue 3.5.44 / vue-router 5.4.0 / vite 8.3.5 / plugin-vue 6.0.10 / typescript **5.9.3**（latest 7.0.2 无编译器 API，vue-tsc+openapi-typescript 跑不了）/ vue-tsc 3.3.13 / oxlint 1.89.0 / oxfmt 0.74.0 / openapi-typescript 7.13.0；Python ≥3.11、Node ^20.19||>=22.12。三处硬发现：oxfmt **无 `--exclude`**（改用 `'!**/*.vue'`）、oxfmt 0.74.0 其实能格式化 .vue（内置 Prettier）、oxlint 对 .vue 无 no-unused-vars 且默认告警不失败（需 `--deny-warnings`）。清单与实测证据：[`.scratch/training-log-v2/research/01-toolchain-versions.md`](research/01-toolchain-versions.md)
- 票 02（走通骨架，已确认）：`backend/`（uv.lock + FastAPI `/health` + TestClient）与 `frontend/`（package-lock + Vite/Vue3/TS strict，单路由消费生成类型）可跑；`bash scripts/verify.sh` 全绿（ruff→mypy→pytest→openapi 导出→api-types 生成→禁手改 diff→oxlint→oxfmt→vue-tsc→vite build）；禁手改 = 重新生成后 `git diff --exit-code`，已实测能拦住 staged 手改。新踩到：pytest 需 `pythonpath=["."]`、oxfmt 还要排除生成物 `'!src/api-types.ts'`、Starlette 1.9 弃用 httpx（警告不失败）、mutmut 默认跳过且 Windows 需 WSL。确认后已提交（`d25bd9c`），禁手改关随生成物入库实际生效。细节：[`issues/02-walking-skeleton.md`](issues/02-walking-skeleton.md)
- 票 03（AGENTS.md）：定稿五节 —— verify 唯一入口与真实关卡顺序、五条硬不变量（隔离在 service 层 / parsing 不抛错 / api-types.ts 禁手改 / openapi.json 生成物 / verify.sh 唯一入口）、backend+frontend+docs 目录职责、契约变更闭环、dev 双端口命令；`## Agent skills` 块保留。版本与工具链理由只留指针（HLD §12.0/§12.1、票 01 research）。[`issues/03-agents-md.md`](issues/03-agents-md.md)
- 票 04（后端数据层，已落地）：10 表 ORM = users + v1 九表（表名沿用 v1 单数，仅新表叫 `users`）；全业务表带 `user_id`（`UserScoped` mixin）；唯一键收紧为 (user_id, 原键) 四条 + `template_day(template_id, day_index)` + `day_note(plan_day_id)` + `actual_item(plan_day_id, planned_item_id)`（prefill 幂等，NULL 不冲突）；级联 = plan_day→三子表全删、planned_item→actual_item 仅 `ON DELETE SET NULL`、cycle_template→天/条目。两处实现裁定：① 引擎/会话工厂挂 `app.state`（`db.py` 提供 create_db_engine/create_session_factory/get_db），HLD §5.1 的模块级 `engine/SessionLocal` 会让 openapi 导出顺手建库、并逼测试用环境变量+模块重载；② SQLite 每连接 `PRAGMA foreign_keys=ON`（默认关，不开则 SET NULL/CASCADE 静默失效）+ `journal_mode=WAL`；密钥 `TL_SECRET` > `data/secret.key` > 首启生成。测试固件改为 `dataclasses.replace(settings, data_dir=tmp_path)` 换库。verify 全绿（16 例）。[`issues/04-backend-data-layer.md`](issues/04-backend-data-layer.md)
- 票 06（前端骨架，已落地）：三路由 + 全局守卫（无 token → /login，已登录访问 /login 回 /calendar）；api.ts 唯一出海口 = token 注入 + 401 清会话跳登录 + 错误归一（detail 字符串/422 数组/网络失败 status 0）；stores.ts = reactive 会话 + localStorage 容错同步。两处裁定：① 401 跳转用 `setOnUnauthorized` 回调注册（避免 api.ts↔router.ts 循环依赖）；② LoginView 提交禁用——/auth/* 未进契约，不手写请求形状（D13），健康检查下沉为 BackendStatus 组件留在公开页。verify 全绿。[`issues/06-frontend-skeleton.md`](issues/06-frontend-skeleton.md)
- 票 05（parsing 移植，已落地）：`backend/app/parsing.py` 与 v1 `app/parsing.py` 语义 1:1（kg/公斤/千克 不区分大小写剥除、逗号当小数点、`>0` 才有效、组数 `>0` 整数、reps 仅 trim、无效回 `None`/空串绝不抛错）；唯一实现差异是把 v1 `parse_sets` 的 `str(raw)` 去掉（`raw` 已收窄为 `str`，行为等价）。测试 13 例搬自 v1 并补单位/零负/自由文本/「永不抛错」参数化。未加 `math.isfinite` 守卫（v1 也接受 `inf`），保持移植忠实度。[`issues/05-parsing-port.md`](issues/05-parsing-port.md)

- 票 02 复验（2026-10-24，骨架签收）：`bash scripts/verify.sh` 全绿（EXIT=0，32 例）。三处更新：① **oxfmt 收编 `.vue`**——实测 5 个 SFC 零 diff，`'!**/*.vue'` 排除属策略而非能力限制，已撤销，主链只剩 `'!src/api-types.ts'`（生成物），HLD §12.0 同步改写；② **mutmut 本机不可验**——`wsl.exe -l -v` 显示无已安装发行版，而 mutmut 依赖 `os.fork`，门控保留、记账为「本机未验证」，待 `days_service` 落地票在 WSL/CI 补跑；③ **HLD §5.1 校准**——`db.py` 改为 `create_db_engine` / `create_session_factory` / `get_db` 挂 `app.state`，§5.2 补每连接 `PRAGMA foreign_keys=ON`，未落地模块标明「随执行票创建」。同时建立根目录 `CONTEXT.md`（7 术语 + 3 条易混边界，`docs/adr/` 不建——D1–D13 已在 HLD 决策索引，避免双写）。详 [`issues/02-walking-skeleton.md`](issues/02-walking-skeleton.md)
- 执行层切票（2026-10-24）：只切关键路径两票 —— 07（认证与会话：`security.py` + `deps.py` + `/auth/*` + 契约闭环 + LoginView 解除提交禁用）与 08（归属隔离：service 层 `user_id` 收窄、父链校验、404 同码同文案、A/B 测试助手，`Blocked by: 07`）。其余业务域等地基落地后再切，避免空转。

- 票 08（归属隔离，已落地 `3287232`）：`app/services/isolation.py` 是判断归属的唯一地方 —— `select_owned(model, user_id)` 供列表/聚合收窄；`find_plan_day` / `find_exercise` / `find_body_metric` 按业务键查、不存在回 `None`；`require_planned_item` / `require_actual_item` / `require_template` / `require_template_day` / `require_template_item` 按 id 取且**父链每一层都校验 user_id**（只信子表冗余列会漏掉「A 的条目挂到 B 的模板下」的脏行，测试用 `update().values(user_id=...)` 造这种行验证双方都 404）。404 用 `app/core/errors.py`（`NOT_FOUND_DETAIL` + `NotFoundError` + `create_app` 注册的全局处理器）而非每处 try/except：物理上只有一个文案出口，业务 router 连 catch 都不用写。`require_day_note` 故意不做（DayNote 1:1 挂 PlanDay，入口恒为 `PUT /days/{iso}/note`，按 id 的 helper 是死代码）。conftest 新增 `Actor` + `actor_a`/`actor_b`（直插 users + 签真 JWT，跳过 bcrypt）+ `Factories`（plan_day / planned_item / actual_item / template / template_day / template_item / body_metric / exercise，commit 后 HTTP 可见）。verify 全绿（**71 例**，契约零 diff）。[`issues/08-isolation.md`](issues/08-isolation.md)

- 票 07（认证与会话，已落地 `c333e4f`）：`core/security.py`（bcrypt cost=12；JWT HS256，`sub` 必须是字符串否则 PyJWT 解码即报 InvalidSubjectError；坏/过期/缺声明一律解出 `None`）+ `core/deps.py`（`HTTPBearer(auto_error=False)`：缺 header 默认是 403，必须改成 401；三个失败分支收进 `_unauthorized()`，并导出 `CurrentUser`/`TokenPolicyDep` 给票 08）+ `services/auth_service.py`（票面只列 router，但硬不变量 1 要求写操作与业务判断在 service；并发注册撞唯一键回滚成同一 409 语义）+ `routers/auth.py`（只做 409/401 映射）。契约：`Credentials`（注册/登录共用）/`UserPublic`/`TokenResponse`；422 中文文案必须用 `PydanticCustomError`，`ValueError` 会被加 `Value error, ` 前缀。三处裁定：① 密码 >72 字节（bcrypt 5.x 硬上限，按字节不按字符）拦成 422 而非静默截断；② 登录用同一 `Credentials`，用户名 <3 字符回 422（FR-2.5 只约束「密码错 vs 用户不存在」）；③ 测试用 `add_api_route(include_in_schema=False)` 挂 `/_test/whoami` 探针，五种 401 走真实 HTTP 路径。前端 `api.ts` 增 `register`/`login`、`stores.ts` 的 `SessionUser` 换成 `components["schemas"]["UserPublic"]`、`LoginView` 解除提交禁用。顺带闭环票 02 遗留问题 3：`httpx 0.28.1` → `httpx2 2.16.0`（starlette testclient 优先 import httpx2），pytest 0 warning，HLD §12.1 与 research §9 已同步。[`issues/07-auth-session.md`](issues/07-auth-session.md)

- 票 10（月历聚合，已落地 `731e732`）：`services/calendar_service.py` 与 v1 `app/calendar.py` 同义 —— `month_grid` 整周补齐（`[None]*first.weekday()` 前补 + 补到 7 的整数倍）、`parse_month` 非法/缺省静默回退当月（FR-4.2，与 days 的 400 是两套语义、刻意不收进同一 helper）、`logged_dates` = `PlanDay join ActualItem` + `distinct` 且 **join 也带 `user_id`**（A 的日历不得出现 B 的记录日）。契约 `CalendarAggregate{year, month, weeks[], logged_dates[]}` → `CalendarWeek{week_start, cells[7], metric}` → `CalendarCell{date, kind, title}` + `BodyMetricOut`（票 15 直接复用形状）。三处裁定：① 补齐位是 `null`、空格子不是 —— 当月某天无 PlanDay 时格子仍在、只是 kind/title 为 null，前端据此区分「不在本月」与「没排计划」；② `week_start` 契约收紧为非空（每行必有真实日期；跨月首行落在上一个月，如 2026-07 首行 = 2026-06-29），`week_start_for` 只此一份，票 15 的写入归一复用；③ 响应回生效的 `year`/`month`（回退后前端要基准算 prev/next），`today` 不进契约。踩坑：`CalendarCell.date` 字段名与类型同名会让 Pydantic 报 `unevaluable-type-annotation`，故 `schemas.py` 加模块别名 `IsoDate = date`。verify 全绿（79 例）。[`issues/10-calendar-aggregate.md`](issues/10-calendar-aggregate.md)

- 票 09（日聚合，已落地 `2be4f8b`）：`services/days_service.py` 两件产物 —— `aggregate_day` 只读组装（无 PlanDay 时返回空结构、**GET 不落库**，与 v1 读路径相反）、`get_or_create_plan_day` 只 `flush()` 不 `commit()`（供 11/12/13 复用；默认 `kind="train"`、`title=None`）。契约 `DayAggregate{date, kind, title, planned_items[], actual_items[], note}` + `PlannedItemOut` / `ActualItemOut`（日级写操作复用同一形状，D7），日期字段复用票 10 的 `IsoDate` 别名。六处裁定：① `kind` 用 `Literal["train","rest"]`（前端拿联合类型，脏值宁可炸出来）；② 不加 `has_plan_day` 标志（kind/title 为 null 即信号，同一事实不两处表达）；③ `note` 只读 `day_note` 表，不碰 v1 遗留死列 `plan_day.note`；④ 两个列表各一条 join 查询且 `Exercise.user_id` 也收窄（避免 N+1 与「关系加载绕过 `select_owned`」，脏行对双方不可见）；⑤ `parse_day` 上移 `parsing.py`（不抛错 → 返回 `None`），400 由 router 产出、与 calendar 的静默回退**刻意不共用 helper**；⑥ 并发建 PlanDay 撞 `(user_id, date)` 唯一键的 `IntegrityError` 本票不处理，留票 11 与 `get_or_create_exercise` 一并抽 helper。顺带修掉 SQLAlchemy 2.1 弃用的 `Result.tuples()`（Row 本身即元组），pytest 回到 0 warning。mutmut `source_paths` 按 HLD §12.0 收紧到 `app/parsing.py` + `app/services/days_service.py`；本机实跑被拒（`To run mutmut on Windows, please use the WSL.`），仍记「本机未验证」。verify 全绿（96 例）。[`issues/09-day-aggregate.md`](issues/09-day-aggregate.md)

- 票 11（计划条目增删移，已落地 `3999ad0`）：`services/days_service.py` 新增 `add_planned_item` / `delete_planned_item` / `move_planned_item`（全部 `commit()` → `aggregate_day`，D7）+ `get_or_create_exercise` + 内部 `_siblings` / `_renumber` / `_insert_or_refetch`；`routers/days.py` 增第二个 `APIRouter(prefix="/plan-items")`（同模块两个前缀，`main.py` 多 include 一行）。契约 `PlanItemCreate{exercise, weight?, sets?, reps?}`（重量/组数/次数收**原始文本**，标数字类型会把 `60kg` 422 掉、违背 FR-6.4）+ `PlanItemMove{direction: up|down}`。四处裁定：① 空动作名（含纯空白）422 而非 v1 静默 no-op；② 并发 get-or-create 用 **SAVEPOINT**（`with db.begin_nested()`）而非 `db.rollback()` —— 写路径上计划日已 flush 在同一事务里，整事务回滚会连坐；撞唯一键回滚这一条后重查复用，重查仍空则重抛；③ **删除后把剩余 position 重排为 0..n-1**（票面新增裁定）：添加用 `position = len(items)` + 「position 全组连续」两个约束只能靠删完重排同时成立，否则留空洞会让下一条撞号；④ `reps` 照搬 v1 原样落库（空输入存空串而非 NULL），只有 weight/sets 解析失败存 NULL。`reps`/`exercise` 的 v1 语义、move 的「全组重排而非只换两个值」、删除靠 `ON DELETE SET NULL` 保留实际条目均照搬。verify 全绿（**114 例**，原 96 + 本票 18，含两例 monkeypatch 造的并发撞键路径）；mutmut 本机仍不可跑（无 WSL），记账同前。[`issues/11-plan-items.md`](issues/11-plan-items.md)

- 票 12（实际完成记录四端点，已落地 `6e731b9`）：`services/days_service.py` 新增 `prefill_actual_items` / `add_actual_item` / `update_actual_item` / `delete_actual_item`（全 `commit()` → `aggregate_day`，D7）+ 内部 `_copy_missing_actuals` / `_linked_planned_item_ids` / `_actual_siblings` / `_parse_note` / `_ACTUAL_FIELD_UPDATES`；`routers/days.py` 增第三个 `APIRouter(prefix="/actual-items")`（`main.py` 多 include 一行）。契约 `ActualItemCreate`（票 11 `PlanItemCreate` + `note`，抽私有基类 `_ExerciseNamed` 共用「动作名非空」规则，内联进两个 schema 不泄漏组件）+ `ActualItemUpdate`（四字段全 `str | None = None`）。三处裁定：① **PATCH 三态**用 `changes.model_fields_set` 逐字段判（显式 `null` 与缺席的值都是 `None`，`exclude_none`/`exclude_unset` 一把梭会静默丢更新）；且**必须显式写列名** —— 契约字段 `weight` 对应列 `weight_kg`，`setattr(item, field, ...)` 会静默写到非映射属性上不报错不落库（`sets`/`reps`/`note` 恰好同名，只有 weight 失效，三态测试当场抓住），落定形态是 `_ACTUAL_FIELD_UPDATES: dict[str, tuple[列名, 解析器]]` + 一条不变量测试（契约字段集 = 映射键集、列名真实存在于 `__table__.columns`）；② **prefill 当天无 PlanDay 静默 no-op**（不隐式建日 —— 没计划就无可复制），与同文件计划外新增的「隐式建日」是两个语义，各一例钉住；③ **并发撞 `UNIQUE(plan_day_id, planned_item_id)` 整批回滚重算一次**（`with db.begin_nested()` 跑完整复制回合，重算走真实查询只见对方新行，仍撞则抛），monkeypatch 让首次 `_linked_planned_item_ids` 返回空集以确定性走完 `IntegrityError` 分支。照搬 v1：复制**当前计划值**、已练过的行不回灌、position 末位追加（同一请求内多条沿用递增变量）+ 删后重排 `0..n-1`、`reps` 空串存空串而 `note` trim 后为空存 NULL。verify 全绿（**140 例**，原 114 + 本票 26）；mutmut 仍本机不可跑（无 WSL）。[`issues/12-actual-items.md`](issues/12-actual-items.md)

- 票 13（感受笔记整段保存，已落地 `7c73255`）：`services/days_service.py` 新增 `save_day_note`（`commit()` → `aggregate_day`，D7）+ 内部 `_find_day_note`（原 `_note_text` 改调它，读/写共用一个 `select_owned(DayNote, …)` 查询）；`routers/days.py` 把 `PUT /days/{iso_date}/note` 接在日期前缀 `router` 上（不新增 `APIRouter`，`main.py` 不动）。契约 `DayNoteUpdate{text}` —— `text` **必填 `str`**（非 `str | None`、无默认空串）：PUT 语义是「整段替换」，缺省静默当清空会让拼错的请求静默删掉用户写的东西，缺 `text` 走 Pydantic 原生 422（两表零写入，有例断言）。三处裁定：① **空文本不删行**（FR-8.1）：`save_day_note("")` 走 upsert，已有 DayNote 改空文本、没有就插空文本行，测试钉「清空后行数仍 1」与「重复清空不增行」堵死「删行」替代语义；② **隐式建日条件 = 无 PlanDay 且 strip 后非空**（FR-8.2）：`text.strip()` 先行，纯空白与空串同路（无 PlanDay 时零写入），刻意不复用票 12 那种无条件 `get_or_create_plan_day` —— 条目端点「写条目必须有日」，笔记路径按 FR-8.2 允许不建日；③ **并发首次写笔记撞 `UNIQUE(plan_day_id)` 走票 11 `_insert_or_refetch`**（savepoint + 重查），随后统一 `note.text = normalized` 覆盖（后写覆盖，与 v1 一致，不连坐同事务刚 flush 的计划日），monkeypatch 让 `_find_day_note` 首次返 `None` 确定性走完撞键分支。照搬 v1 `app/days.py:save_note`：先 strip 再落库、GET 不二次 trim（`"  累但爽  "` 原样返回仍成立）、已有 PlanDay 不碰 kind/title、无 `require_day_note`（票 08 已裁定）。隔离：唯一键 `(user_id, date)`，B 写同日落 B 名下（隐式建 B 的 PlanDay），A 的笔记原封不动。verify 全绿（**153 例**，原 140 + 本票 13）；mutmut 仍本机不可跑（无 WSL），straddle 分支（空/非空 × 有无 PlanDay）记账待补。[`issues/13-day-note.md`](issues/13-day-note.md)

- 票 14（循环模板，已落地 `2c733c8`）：`services/template_service.py` 四个入口（`list_templates` / `create_template` / `delete_template` / `apply_template`）+ 归一（`_name`/`_length`/`_kind`/`_title`/`_exercises`）+ 批量组装（`_aggregates` 一次 3 条查询）；`routers/templates.py` 四薄端点，`main.py` 多 include 一行。契约 `TemplateAggregate{id,name,length_days,days[]}` → `TemplateDayOut{day_index,kind,title,items[]}` → `TemplateItemOut{exercise,position}` + `TemplateCreate` / `TemplateDayIn` / `TemplateItemIn` / `TemplateApplyRequest` / `TemplateApplyResult{created,skipped,skipped_dates}`。七处裁定：① `length_days` 与 `start` 收**原始文本**（标 `int`/`date` 会把「非法回退 8」与「400 日期非法」变成 422），`TemplateCreate` 加 `coerce_numbers_to_str` 让数字也照收；② `TemplateDayIn.kind` 收裸 `str`，归一在 service（`Literal` 会 422 整单，与「非 rest 一律 train」相反）；③ `TemplateItemIn.exercise` **不**校验非空（与 plan-item 的 `_ExerciseNamed` 刻意相反 —— v1「忽略空行」在 JSON 下就是跳过空动作名）；④ `days` 下标即 `day_index`，多出的天忽略、不足的补默认训练日，`length_days == len(days)` 恒成立；⑤ 契约不出 `sets`/`reps`/`weight`/模板日与条目 id（模板侧恒 NULL、无端点按它们定位；HLD §5.2 那句「apply 复制 exercise/sets/reps/position」说的是复制动作，**不给 POST 加 sets/reps 入参**）；⑥ apply 用 `find_plan_day` + 显式建 `PlanDay`（查当前用户 `(user_id,date)`，有就跳过并收进 `skipped_dates`），**刻意不走** `get_or_create_plan_day`，且断言原计划日的 title/条目一个字都没变；⑦ 天/条目查询逐层 `select_owned` + join 上的 `Exercise.user_id` 收窄，脏行列表不可见、apply 不抄。另两处：400 文案单源（`routers/templates.py` 复用 `routers/days.py:parse_day_or_400`，router→router 引用一个函数胜过复制第二份消息）、写端点一律 200。**并行记账**：14 与 15 同树并行的判断只对一半 —— 两者都改 `schemas.py`/`main.py`/生成物，`schemas.py` 的模板契约被 `4ce9c04` 一并带走，本票 `2c733c8` 补齐源码与重新生成的契约；下一轮同动契约的票必须串行。verify 全绿（**193 例**，本票 22 + 票 15 的 18）；mutmut `source_paths` 不含 `template_service.py`（HLD §12.0 只点到 parsing 与 days_service），本机仍不可跑。[`issues/14-templates.md`](issues/14-templates.md)

## Not yet specified

- **前端组件平移**（MonthGrid · DayDetail · WeekMetric · TopBar + 三个 view 接上真实请求 + `app.css` 方向 A 令牌迁移）：**已毕业成 spec** —— [`spec.md`](spec.md)（2026-10-24，`ready-for-agent`）。组件只消费生成契约、不手写形状（D13）；建议切成 5 张票（共享层 → 月历+周体重 → 计划列 → 实际列+感受 → 模板页），票号从 16 起，细节见 spec 的「Further Notes」。
- **prod 静态托管**（D11：`main.py` 挂 `dist` + SPA 兜底、单地址）与**删除旧 `app/`**（含 `tests/`、`run.py`）：都等全链路走通后再切，触发时机现在判不准（删除太早会丢 v1 参考实现）。
- 质量关残余细节：oxfmt 对 `.vue` 的收编已于 2026-10-24 落地（实测零 diff），回退阈值仍保留为「升级 oxfmt 后 `git diff --stat` 突增即回退」；mutmut 门控在本机仍不可验证（无 WSL 发行版）—— 真实跑点已到票 09，11 又把 position 维护与并发重查、12 又把三态逐字段更新与 prefill 幂等重算、13 又把空/非空文本 × 有无 PlanDay 的 straddle 分支堆进了 `days_service.py`，但 `mutmut run` 在 Windows 上仍被上游直接拒绝（缺 `os.fork`），记「本机未验证」，待 WSL/CI 补跑。
- 验收判据（HLD §12.0 已给冒烟主线：登录→月历→展开→autosave→预填→模板 apply→周体重→登出）的**确切步骤与判据**、README 双模式改写、旧实现删除时点 —— 待全链路走通后精确成票。

## Out of scope

- 智能建议 / 反馈推荐（SRS 明确推迟）
- UI 重设计（本次仅平移 v1 交互，D9）
- 移动端适配、云部署、HTTPS / 公网暴露（SRS §2.4）
- 忘记密码 / 邮箱找回、第三方登录（SRS §1.2）
- 旧数据迁移（D8：空库起步，data/app.db 弃置）
- 票 15（周体重，已落地 `4ce9c04`）：`PUT /metrics/{week_start}` → `BodyMetricOut`。写逻辑自立新文件 `services/metrics_service.py`（票面二选一里选「写读分家」，HLD §5.1 目录树已同步），读仍在 `calendar_service.py`，`week_start_for` 与新增的 `metric_out`（ORM→契约的唯一映射）都由那里取。三处裁定：① `week_start` **不假设是周一**——路径参数收任意日期，service 归一到该周周一再 upsert（v1 语义；「必须周一否则 400」是新的裁定，本票不加）；② **非法体重挡在契约层**：`BodyMetricUpdate.weight` 的 validator 用 `parse_weight` 判，非法即 `PydanticCustomError` → 原生 422 且 handler 都进不去，所以「不落库」是结构性的（不必先写后回滚）；`body_fat` 非法静默 NULL、`note` 空白即 NULL、PUT 整体替换（v1 同语义）；③ 并发同周 PUT 撞 `UNIQUE(user_id, week_start)` 时用 SAVEPOINT 只回滚这一条再重查复用（`days_service._insert_or_refetch` 同一取向但不复用：那边 get-or-create，这边建完还要覆盖值）。另记两条流程事实：`verify.sh` 的禁手改关比的是 **index 与工作树**，合法契约变更后要先把重新生成的 `openapi.json` / `api-types.ts` `git add` 再跑第二遍；本票与票 14 同树并行，提交里带了票 14 的模板契约模型（无 router 引用 → 不进 `openapi.json`）与只含本票的生成物。[`issues/15-week-metrics.md`](issues/15-week-metrics.md)
