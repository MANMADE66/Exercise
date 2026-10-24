Type: task
Status: ready-for-agent
Blocked by: 09

## Question

落地实际完成记录四个写端点（SRS FR-7、HLD §9.1）。全部返回**新鲜日聚合**（D7）。

- `POST /days/{date}/actual/prefill`：为每个尚无对应实际条目的计划条目复制一条 ActualItem（带 `planned_item_id`）；**重复调用幂等**
- `PATCH /actual-items/{id}`：逐字段更新 weight/sets/reps/note；**字段缺省不清空**，传空字符串 = 该字段置 NULL（FR-7.2）
- `POST /days/{date}/actual-items`：计划外条目（`planned_item_id` 为 NULL），另可带 note
- `DELETE /actual-items/{id}`：直接删除
- `services/days_service.py` 承接；`routers/days.py` 只做映射

## Comments

- **本票最大的技术坑：PATCH 的三态语义**。字段要区分「缺省」（不动）/ `null`（置空）/ 空串（置空），而 `weight: str | None = None` 分不出「缺省」和显式 `null`。用 `model_fields_set` 逐字段判断，别用 `exclude_unset` 一把梭 —— 后者会把「显式传 null」也当成缺省，静默丢更新。这是 FR-7.2 的原话「字段缺省不清空，传空字符串含义为该字段置 NULL/空」，必须逐字段验。
- **prefill 幂等靠双重保险**：票 04 已加 `UNIQUE(plan_day_id, planned_item_id)`（计划外条目该列为 NULL，不冲突）。v1 是「先查 `already` 集合再补」（`app/days.py:prefill_actual`），v2 沿用 + 撞唯一键时回滚重算，保证重入安全。**预填复制当前计划值**（`weight_kg`/`sets`/`reps` 都抄），不是抄模板。
- **v1 缺口需裁定**：v1 prefill 在该日无 PlanDay 时静默 no-op 返回空聚合；v2 保持 no-op（不隐式建日 —— prefill 是「照计划复制」，没计划就无可复制）。
- `position` 递增取 `len(plan_day.actuals)`（v1 一致）；因 prefill 与新增共用该计数，同一请求内的多条要沿用一个递增值，别在循环里重复算同一个 `len()`。
- 隔离：`require_actual_item`（票 08 已建）出 404；`PATCH` 与 `DELETE` 按 id 取，父链校验到 `plan_day.user_id`。
- 测试按 HLD §12.0 `days` 行：prefill 幂等（连调两次条数不变）、行内更新三态、计划外新增、删除、隔离（B patch/delete A 的条目 404）。

## Answer
