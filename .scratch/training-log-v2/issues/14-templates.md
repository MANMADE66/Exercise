Type: task
Status: ready-for-agent
Blocked by: 09

## Question

落地循环模板（SRS FR-9、HLD §9.1），含 `services/template_service.py` 与 `routers/templates.py`。

- `GET /templates`：当前用户全部模板 + 逐日骨架（含条目）
- `POST /templates` {name?, length_days, days[{kind, title, items[]}]}：新建，返回新模板
- `DELETE /templates/{id}`：删除（级联天/条目），返回模板列表
- `POST /templates/{id}/apply` {start}：从起始日按 `day_index` 逐日铺排；**已有 PlanDay 的日期跳过，绝不覆盖**；返回 `{created, skipped, skipped_dates}`
- `schemas.py` 补模板契约 → 重跑 verify 生成

## Comments

- v1 语义（`app/cycle.py`）照搬，全部要点按原样复刻：
  - 名称：`strip()` 后为空 → `"未命名循环"`
  - 天数：`parse_sets(length_days) or 8`，再 `max(1, min(length, 12))` —— 非法/缺省回退 **8**，超界**静默截断 12**，不报错（FR-9.2）
  - 逐日：`kind` 只取 `train`/`rest`（非 `"rest"` 一律 `train`）；`title` strip 后空 → NULL
  - 条目：每行一个动作名，**忽略空行**；`position` 从 0 递增；`sets`/`reps` **恒为 NULL**（FR-9.2「模板不含重量」）
- **HLD §5.2 那句「apply 时仅复制骨架字段（exercise、sets、reps、position）」需读对**：因为模板侧 `sets`/`reps` 恒 NULL，复制过去也恒 NULL。不要因此给 POST /templates 加 sets/reps 入参 —— 形状以 SRS §5 的 `items:[{exercise,...}]` 为准。
- apply 的关键判定是「该日期是否**已有 PlanDay**」，不是「是否已填内容」，且查的是**当前用户**的 `(user_id, date)`（票 04 的唯一键）。跳过计数与 `skipped_dates` 都要回给前端提示（v1 只回一个中文句子，v2 结构化）。
- apply 会建 PlanDay 并复制骨架 —— 复用票 09 的 days_service 助手，但**不能**走 `get_or_create_plan_day`（那是「没有就建」，apply 要「有就跳过」），两者语义相反。
- 隔离：`require_template`（票 08 已建）出 404；跨用户 apply → 404（HLD §12.0 `templates` 行明确要求这条）。
- 测试按 HLD §12.0 `templates` 行：长度截断 12 / 回退 8、apply 跳过已排日期且不覆盖（断言原 PlanDay 的 title 未变）、`created`/`skipped` 计数、跨用户 apply 404、`GET /templates` 互不可见。

## Answer
