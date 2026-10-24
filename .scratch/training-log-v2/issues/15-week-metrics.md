Type: task
Status: ready-for-agent

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
