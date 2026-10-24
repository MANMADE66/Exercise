Type: task
Status: ready-for-agent
Blocked by: 09
Claimed by: pi

## Question

落地感受笔记保存（SRS FR-8、HLD §9.1）。

- `PUT /days/{date}/note` {text}：整段保存；空字符串合法 = 清空原文；返回新鲜日聚合（D7）
- 隐式建日规则：**该日无 PlanDay 且文本非空**时才建 PlanDay；文本为空且无 PlanDay 时**不写任何数据**（FR-8.2）
- `services/days_service.py` 承接；`routers/days.py` 只做映射

## Comments

- v1 语义（`app/days.py:save_note`）照搬：`text` 先 `strip()`；`plan_day is None and text` 才 `get_or_create_plan_day`；`plan_day` 存在则 upsert `day_note`（新建或改 `text`）。
- **1:1 由 DB 保证**：`day_notes.plan_day_id` 唯一（票 04 已建）。所以业务上只有 upsert 一条路，不需要 `require_day_note` —— 票 08 已裁定不做该 helper（入口恒为按日期，按 id 的 helper 是死代码），本票不要重新加。
- `text` 的 trim 边界：v1 对空串 `strip()` 后仍是空串，落库为空 `DayNote`（当 PlanDay 已存在时）。FR-8.1「为空字符串时仍保存（清空原文）」正是这个行为 —— 不要「空串就删 DayNote 行」，那是另一种语义。
- 日期非法 → 400（同票 09 的 400 口径，不走 FastAPI 的 422）。
- 测试按 HLD §12.0 `days` 行：空串清空、隐式建日仅在有文本时、无 PlanDay + 空文本零写入（断言 `plan_days` 表行数不变）、隔离（B 写 A 的日期 → 落到 B 自己名下，而不是写进 A 的行 —— 因为 `plan_days` 唯一键是 `(user_id, date)`，同一天两个用户各有一行）。

## Answer
