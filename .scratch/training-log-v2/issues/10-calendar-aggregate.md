Type: task
Status: ready-for-agent
Claimed by: pi（2026-10-24）

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

已落地 `731e732`。实现与裁定：

- **`services/calendar_service.py`**：`month_grid` / `parse_month` 与 v1 `app/calendar.py` 逐行同义（前补 `[None]*first.weekday()`、尾部补到 7 的整数倍、`date.fromisoformat(f"{raw}-01")` 失败即回退当月）；`week_start_for(day) = day - timedelta(days=day.weekday())` 落在这里，作为周起点的**唯一**算法（票 15 的写入归一复用，不另写一份）。`calendar_month(db, *, user_id, month)` 是唯一入口，`?month=` 解析在 service 内、routers 只透传字符串。
- **契约形状**（`schemas.py`）：`CalendarAggregate{year, month, weeks[], logged_dates[]}` → `CalendarWeek{week_start, cells[7], metric}` → `CalendarCell{date, kind, title}`，`BodyMetricOut{week_start, weight_kg, body_fat_pct, note}`。三个裁定：
  1. **补齐位是 `null`，空格子不是**：`cells: list[CalendarCell | None]`，`null` 恒为「月初日前 / 月末日后」；当月某天没有 PlanDay 时格子仍在，只是 `kind`/`title` 为 `null`（前端据此区分「不在本月」与「没排计划」）。
  2. **`week_start` 非空**：v1 模板里 `week_start` 可能为 `None`（只为渲染兜底），但 `month_grid` 保证每行至少有真实日期，故契约收紧为 `date`；跨月首行的 `week_start` 落在上一个月（如 2026-07 首行 = 2026-06-29），这是 D9 照搬 v1 的结果。
  3. **返回生效的 `year`/`month`**：`?month=` 非法被静默回退后，前端必须知道实际展示的是哪个月（FR-4.4 的 prev/next 由前端算，需要基准）；`today` 不进契约，前端本地取。
- **`logged_dates`**：`select(PlanDay.date).join(ActualItem).where(PlanDay.user_id, ActualItem.user_id, 月区间).distinct()`，升序返回。join 的 `user_id` 与 `select_owned` 同形收窄（票面点名的易漏点），并加了隔离用例反向验证。
- **`BodyMetricOut`**：本票先定形状，票 15 直接复用；`metric` 为 `null` 表示该周没记录（不存在「空记录」，CONTEXT.md「BodyMetric」）。
- **类型坑（记一笔）**：`CalendarCell` 的字段就叫 `date`，类体里写 `date: date` 会让注解指向字段自身，Pydantic 报 `unevaluable-type-annotation`；`schemas.py` 因此加了模块级别名 `IsoDate = date`，日历三个模型的日期字段统一用它。
- **测试** `backend/tests/test_calendar.py`（9 例）：非法/缺省 month 回退当月、网格补 null（2026-02 首行补 6 格 / 末行补 1 格）、格子 kind/title、`logged_dates` 判据（只有计划日不算、多条实际条目只出现一次、月外记录不进集合）、周一起点 + metric 挂对行（含跨月首行）、A/B 隔离（B 的计划日/记录日/周体重都不出现，反向亦然）、无 token 401。
- verify 全绿（**79 例**，契约重生成零手改）。过程中发现票 09 的 `days_service.py` / `routers/days.py` / `test_days.py` 已在同一工作树里被并行改动（其 `schemas.py` 半边未落，mypy/ruff 会红），本票验证时把这三份未跟踪文件临时移出后再跑 verify、随即原样移回（md5 校验一致），提交只含票 10 的路径，未触碰票 09 的在途文件。

### 票 09 落地后的回看（`099e8ef`）

票 09 合入（`2be4f8b`）后逐行对了两票的产物：**月历在功能上不依赖日聚合的任何返回内容** ——
FR-4.3 规定月历只出概要、日详情由 FR-5 另发 `GET /days/{iso}`，`CalendarCell{date,kind,title}`
与 `DayAggregate{date,kind,title,planned_items,actual_items,note}` 是两套形状（前者还要能表达
补齐位的 `null` 格，后者表达不了）；`aggregate_day()` 也不该被月历复用（5–6 周 × 7 天逐日聚合
就是 N+1）。09 反而复用了我这票先定的 `IsoDate` 别名，说明共享点落在类型层而非响应形状。

顺着这次对照做了三处去重（契约零 diff，`openapi.json` / `api-types.ts` 不变）：

1. **`DayKind` 别名**：`kind` 的两值原本在 10 与 09 各写一遍收窄（`cast(Literal[...])` vs
   `# type: ignore[arg-type]`）。收进 `schemas.DayKind`，`DayAggregate` 与 `CalendarCell` 共用，
   两个 service 都用 `cast(DayKind, plan_day.kind)` —— `type: ignore` 会把脏值静默放行，
   `cast` 至少指向契约里那一个别名。
2. **`parse_month` 改走 `parsing.parse_day`**：09 把 `parse_day` 提到 `parsing.py`（硬不变量 2），
   于是本票不再自带一份 `date.fromisoformat` 的 try/except —— 「认不出」的判定全库只剩一处，
   「回退当月」的错误语义仍留在 `calendar_service`，与 days 的「非法 → 400」照旧不共用。
3. **测试改用 `CalendarAggregate.model_validate(response.json())`**：与 `test_days.py` 同一手法，
   断言打的是生成契约的字段名（D13），而不是手抄的 `dict[str, Any]` 键；顺带把 `dict[str, Any]`
   下标（mypy 会退化成 `Any`）换成属性访问。

未动的一处（跨票，留给后续）：`DbSession = Annotated[Session, Depends(get_db)]` 现在在
`routers/auth.py` 与 `routers/days.py` 各定义一次，本票的 `routers/calendar.py` 内联第三次 ——
应该搬进 `core/deps.py` 一处导出。它不属任何业务票的语义，故本票只记账不改。
