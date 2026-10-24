Type: task
Status: ready-for-agent

## Question

落地月历聚合读与 `CalendarAggregate` 契约（SRS FR-4、HLD §9.1）。可与票 09 并行：只读、不依赖日聚合形状。

- `GET /calendar?month=YYYY-MM`（可缺省）
- `services/calendar_service.py`：整周网格（周一为起点，月初日前 / 月末日后补 `null`）+ 每个 PlanDay 的 `kind`/`title` + `logged_dates` + 每周边界日期 + 该周 BodyMetric
- `schemas.py` 补 `CalendarAggregate` / `CalendarCell` / `CalendarWeek` / `BodyMetricOut` → 重跑 verify 生成契约
- `routers/calendar.py`：薄层

## Comments

- v1 语义照搬（`app/calendar.py`，这次不重新设计，D9）：
  - `month_grid`：`[None] * first.weekday()` 前补、尾部补到 7 的整数倍，再切片成周
  - `parse_month`：`date.fromisoformat(f"{raw}-01")` 失败或缺失 → 回退**当月**，服务端不报错（FR-4.2）
  - `logged_dates` = 有 ActualItem 的日期集合（`PlanDay join ActualItem` + `distinct`），不是「有 PlanDay」的日期
  - 周行 = `week_start`（该周第一个非 null 日期的周一）+ 该周 `BodyMetric`
- **翻月不加端点**（FR-4.4）：`prev`/`next` 由前端算或带 `month` 重请；服务端只认 `?month=`。v1 的 `shift_month` 是模板侧 helper，v2 归前端。
- **BodyMetric 只读不写**：写入在票 15。本票的 `BodyMetricOut` 与票 15 的响应模型是同一个 —— 契约形状一次定好，两票同时改同一段 `schemas.py` 时注意先来后到（票 15 在票 10 之后合入则直接复用）。
- 隔离：`PlanDay` / `ActualItem` / `BodyMetric` 三处查询全部经 `select_owned` 收窄。**易漏点**：`logged_dates` 的 join 查询也必须带 `user_id`，否则 A 的日历会显示 B 的记录日。
- 测试按 HLD §12.0 `calendar` 行：非法 month 回退、网格补 null、`logged_dates` 正确、周聚合行（周一起点 + metric 挂对行）、隔离（B 的记录不出现在 A 的日历）。

## Answer
