Type: task
Status: ready-for-agent
Claimed by: pi（2026-10-24）

## Question

落地周体重 upsert（SRS FR-10、HLD §9.1）。无阻塞依赖：只碰 `body_metrics` 一张表。

- `PUT /metrics/{week_start}` {weight（必填合法）, body_fat?, note?}：按 `(user_id, week_start)` upsert，返回该周 metric
- weight 非法时**不落库**，返回可展示的错误（FR-10.2）—— HLD §9.2 定 422
- `services/metrics_service.py`（或并入 `calendar_service.py`，见下）；`routers/metrics.py`

## Comments

- **week_start 归一在服务端**：v1 `app/metrics.py:save_metric` 收任意日期，`week_start_for(day) = day - timedelta(days=day.weekday())` 算周一再 upsert。路径参数叫 `week_start`，但**不能假设调用方传的就是周一** —— 传周三也要落到该周周一那行。若 SRS 的 `{week_start}` 想收紧为「必须周一，否则 400」，那是新的裁定，本票不要顺手加（v1 没有这个约束）。
- 解析沿用 `parse_weight`（容错，非法 → None）：weight 为 None 即非法 → 422 且不落库；`body_fat` 走同一解析，非法 → NULL（不报错，可选字段）；`note` strip 后空 → NULL。v1 三处都是这个行为。
- 服务文件归属：HLD §5.1 目标树里没有 `metrics_service.py`，`calendar_service.py` 承担「周聚合行」的读。**票内裁定**：写逻辑放 `services/metrics_service.py`（新文件，需同步 HLD §5.1 目录树与「尚未落地」清单），读逻辑留 `calendar_service.py` —— 或者反向把两者都收进 `calendar_service.py`。二选一，选定后同步 HLD，别留两处模糊。
- 与票 10 共用 `BodyMetricOut` 契约形状：票 15 在票 10 之后落时直接复用；反之则本票先定形状、票 10 沿用。
- 隔离：`find_body_metric`（票 08 已建）按 `(user_id, week_start)` 查；upsert 落库时 `user_id` 取当前用户。**易漏点**：A 与 B 可以各有同一周的 metric 行（唯一键是 `(user_id, week_start)`），B 的 PUT 绝不能改到 A 的行。
- 测试按 HLD §12.0 `metrics` 行：同周 upsert（第二次改 weight 不新增行）、周一起点归一（传周三落到周一那行）、非法体重 422 且表内零变化、隔离（B 写同周不影响 A 的行）。

## Answer

已落地（`bash scripts/verify.sh` 全绿；本票新增 `backend/tests/test_metrics.py` **18 例**）。

### 端点与契约

```
PUT /metrics/{week_start}   body BodyMetricUpdate { weight, body_fat?, note? }   → BodyMetricOut
```

- `week_start` 路径参数收 `str`，不用 `datetime.date`（否则 FastAPI 直接吐 422，与 HLD §9.2「日期格式非法 → 400」不符）。归一到周一在 service（`week_start_for`），传周三 / 周日都落到该周周一那一行。
- 三个字段收**原始文本**（与计划条目的 weight 同构）。`weight` 必填，非法 → **422（Pydantic 原生）+ 一行不写**：校验挂在 `BodyMetricUpdate.weight` 的 `field_validator` 上（`parse_weight` 给 None 即 `PydanticCustomError`），请求进不到 handler，库自然零变化；422 `detail` 里的 msg 就是 FR-10.2 要的「可展示的错误」（`api.ts` 已把 422 数组拼成中文串）。
- 响应复用票 10 定的 `BodyMetricOut`（无新增响应模型），**不返回月历聚合**：写周体重只动一行，前端改那一格即可，不必重发 `GET /calendar`。

### 产物

- `services/metrics_service.py`（新文件 —— 票面二选一里选「写逻辑独立」）：`upsert_week_metric` = `week_start_for` 归一 → `find_body_metric` 按 (user_id, 周起点) 查 → 无行则插、有行则改 → `commit` → 契约。`body_fat` 走同一 `parse_weight` 但非法静默 NULL，`note` strip 后空即 NULL；PUT 整体替换（没传的可选字段写成 NULL，v1 同语义）。
- `routers/metrics.py`（新文件）：复用 `routers/days.parse_day_or_400`（同为 ISO 日期路径参数，400 文案不该有第二份），只做「解析 → service → 返回」；`main.py` 加一行 `include_router(metrics.router)`。
- `schemas.py`：新增 `BodyMetricUpdate` + `WEIGHT_INVALID_MESSAGE`（validator 抛的文案与 422 的 `responses` 描述共用一句）。
- `services/calendar_service.py`：把 ORM → `BodyMetricOut` 的映射抽成 `metric_out()`（公开），月历周行（读）与 PUT 返回值（写）共用一份，不再两处各拼 4 行；`week_start_for` 也还是这一份。
- HLD §5.1 目录树（新增 `services/metrics_service.py` 一行）/ 目标树说明 / §9.1 端点表注记同步；文档里未留「metrics 写逻辑待定」的模糊处。

### 三处裁定

1. **`week_start` 不假设是周一**：照 v1 `save_metric`（任意日期 → `week_start_for` → upsert），本票不顺手加「必须周一否则 400」（那是新的裁定）。测试钉了周一 / 周三 / 周日三种入参都落同一行、`week_start.weekday() == 0`。
2. **非法体重挡在契约层，不在 service**：这样「不落库」是结构性的（handler 都没进），不需要「先写后回滚」，也不需要 service 返回 `None` 让 router 猜错误码。service 里再 `parse_weight` 一次只为把文本变数值并收窄类型（`assert` + 注释指向 validator），不产生第二条错误路径。
3. **并发同周 PUT 撞唯一键**：`UNIQUE(user_id, week_start)`，两个请求同时「查不到 → 插」时后者 `IntegrityError`。`_insert_week_metric` 用 SAVEPOINT 只回滚这一条再重查复用，随后统一写值 → 语义仍是「后写覆盖」。与 `days_service._insert_or_refetch` 同一取向但**没有**复用它：那边是 get-or-create（建了就完事），这边是 upsert（建完还得覆盖值）。

### 隔离

键是 `(user_id, week_start)`：A 与 B 各有同一周的行。测试让 A、B 都 PUT 2026-01-05 那周，断言两行互相独立、A 再 PUT 一次不动 B 的行；另有「日期非法 → 400 而非 422」与「无 token → 401 且零写入」各一例，及「PUT 之后月历该周就有 metric」一例把读写两条路径串起来。

### 流程细节：生成物要先 stage

`verify.sh` 的禁手改关是 `git diff --exit-code -- docs/openapi.json frontend/src/api-types.ts`，比的是 **index 与工作树**。所以**合法**的契约变更跑 verify 会先在那一关「假失败」：先把重新生成的这两个生成物 `git add`，再跑第二遍才全绿。这是票 02 那句「拦住 staged 手改」的另一面，不是新问题。

### 并行会话的记账

本票与票 14（templates）在**同一工作树**并行落地（map Notes「同树并行」）。具体后果三处，都已按下述方式处理：

- **共享文件带上了票 14 的改动**：`backend/app/schemas.py` 里同时有票 14 的 9 个模板契约模型（`TemplateItemOut` / `TemplateDayOut` / `TemplateAggregate` / `TemplateItemIn` / `TemplateDayIn` / `TemplateCreate` / `TemplateApplyRequest` / `TemplateApplyResult`）。它们在本提交里没有任何 router 引用，因此**不出现在** `docs/openapi.json`（已核：HEAD 的 `components.schemas` 只有 `BodyMetricUpdate` 一个新面孔），也不影响任何关卡 —— 票 14 提交自己的路由时它们才真正生效。`main.py` 则相反：本提交的版本**不含** `templates.router`（否则会引用未入库的模块），工作树里保留票 14 那一行等它自己提交。
- **生成物一次性包含两票的契约**：本票落地的 `docs/openapi.json` / `frontend/src/api-types.ts` 只含 `PUT /metrics/{week_start}`；票 14 的两条 templates 路径在它提交时重新生成、随自己的提交入库（本票末尾已重跑生成并暂存，票 14 那边 `git add` 即带上）。
- **HLD §5.1 目标树说明**：本票只写了自己那一份（并把 `metrics` 从「尚未落地」里移出）；票 14 提交时若整段重写该说明，两票的落地清单需要合并一次。
