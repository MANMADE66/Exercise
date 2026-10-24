Type: task
Status: ready-for-agent
Blocked by: 07
Claimed by: pi

## Question

落地归属隔离与错误码归一（HLD §8、§9.2，SRS §2.2）：

- service 层所有查询用当前 `user_id` 收窄；按 id 取资源必须经父链校验归属（如 `template_item → template_day → template`）
- 不属于当前用户的一切读写删 → 404，与「不存在」同码同文案（同一处 helper 产出，禁止各处手写）
- `conftest.py` 补隔离测试助手：用户 A/B + 各自计划日 / 模板 / 体重的工厂，供后续业务域票直接复用

## Comments

- 本票不新增业务域路由；业务域票（calendar / days / templates / metrics）在此之后各自接上，届时只需调用隔离 helper。
- 隔离测试必须先于业务域测试存在：HLD §12.0 把「隔离」列为安全关键项（B 对 A 的 day/calendar/templates 读写删均 404；列表互相不可见；exercise 命名空间互不可见）。
- 硬不变量：判断只允许发生在 service 层，routers 不得自行拼 `user_id` 过滤条件。

## Answer

已落地并全绿（2026-10-24，`bash scripts/verify.sh` 一次通过：ruff → ruff format → mypy strict → pytest **71 例**（原 59 + 本票 12）→ openapi 导出 → api-types 生成 → 禁手改 diff → oxlint → oxfmt → vue-tsc → vite build；契约无变更，`docs/openapi.json` / `api-types.ts` 零 diff）。

### 产物

- `app/services/isolation.py`：**唯一**允许判断「属不属于当前用户」的地方，三种查法：
  - `select_owned(model, user_id)` → `Select`：列表 / 聚合查询的基座，routers 不再手拼过滤条件；
  - `find_plan_day` / `find_exercise` / `find_body_metric`：按 (user_id, date / name / week_start) 查，不存在返回 `None`（GET /days 的「当天还没有计划日」是正常状态，不能 404）；
  - `require_planned_item` / `require_actual_item` / `require_template` / `require_template_day` / `require_template_item`：按 id 取，**父链每一层同时校验 user_id**（`template_item → template_day → template` 两层 join），失败只抛 `NotFoundError`。
- `app/core/errors.py`：`NOT_FOUND_DETAIL = "资源不存在"`、`NotFoundError`、`not_found_handler`。`create_app` 注册成全局处理器 → 业务 router **不需要为 404 写 try/except**，文案与状态码只有一处。
- `tests/conftest.py`：`Actor`（user_id + token + `headers()`）、`actor_a` / `actor_b` 固件（直插 users + 签真 JWT，跳过 bcrypt）、`Factories`（`plan_day` / `planned_item` / `actual_item` / `template` / `template_day` / `template_item` / `body_metric` / `exercise`，position 缺省按同日现有条目数顺延，造完即 commit 供 HTTP 请求看见）。
- `tests/test_isolation.py`（12 例）：别人的 id 与不存在的 id → 同一异常同一文案；父子链脏行（只翻转 `planned_item.user_id` / `template_item.user_id`）对**双方**都不可见；列表与业务键查询互不串；动作库命名空间互不可见且同名重复取幂等；HTTP 探针端点上 404 体逐字段一致、无 token 先 401。

### 三处实现裁定

1. **404 用全局异常处理器，而不是每个 router `try/except`**：票面要求「同一处 helper 产出」。业务 router 里写映射就等于给 21 次「手写文案」开 21 个口子；`NotFoundError` + `add_exception_handler` 让 404 物理上只有一个出口，router 连 catch 都不用写（硬不变量 1 的分工反而更干净：routers 只解析参数、取 `CurrentUser`）。
2. **父链校验不信任子表的冗余 `user_id`**：每张业务表都带 `user_id`，但只有它自己时，「A 的条目挂到 B 的模板下」这类脏行会各自看见一半。故 `require_*` 一律 join 回父链并逐层断言。测试用 `update(...).values(user_id=...)` 造出这种行，证明它对父子双方都 404。
3. **`require_day_note` 故意不提供**：DayNote 1:1 挂在 PlanDay 上，入口恒为 `PUT /days/{iso}/note`，归属经 `(user_id, date)` 校验已足够；按 id 的 helper 会成为永远不会被调用的死代码（模块 docstring 写明理由）。

### 给后续业务域票的接口

- 列表 / 聚合：`isolation.select_owned(Model, user.id).where(...)`；
- 按日期：`isolation.find_plan_day(db, user_id=..., day=...)`；
- 按 id：`isolation.require_*(db, user_id=..., *_id=...)`，**不要**再写 `select(...).where(model.user_id == ...)`；
- 动作库 get_or_create：先 `isolation.find_exercise(db, user_id=..., name=...)`，没有才 insert；
- 周体重 upsert：先 `isolation.find_body_metric(db, user_id=..., week_start=...)`；
- 测试：`actor_a` / `actor_b` + `make.*` 固件，直接造 A/B 各自的 day / template / metric。

### 未做 / 留给后续

- 业务域 404 断言（B 对 A 的 GET /days、/calendar、模板 apply 等）随各自票补；本票只保证 helper 与 HTTP 归一先就位。
- mutmut 目标仍未包含 `isolation.py`（`[tool.mutmut] source_paths = ["app"]` 全包，首个真实跑点仍押在 `days_service` 落地票，Windows 需 WSL）。
