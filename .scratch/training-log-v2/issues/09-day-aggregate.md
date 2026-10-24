Type: task
Status: ready-for-agent

## Question

落地日聚合读与 `DayAggregate` 契约（SRS FR-5、HLD §9.1/§9.2）。这是全部业务域票的根：FR-6/7/8 的每个写操作都返回「新鲜日聚合」（D7），所以契约必须先有。

- `GET /days/{iso_date}`：PlanDay（`kind` / `title`）+ 全部 PlannedItem（按 `position`）+ 全部 ActualItem（按 `position`）+ DayNote 文本
- `services/days_service.py`：`aggregate_day(db, *, user_id, day)` 组装聚合；顺带落 `get_or_create_plan_day`（默认 `kind="train"`、`title=None`，与 v1 `app/days.py:19` 一致）供 11/12/14 复用
- `schemas.py` 补 `DayAggregate` / `PlannedItemOut` / `ActualItemOut`（HLD §5.1 已点名 `DayAggregate` 命名）→ 重跑 verify 让 `docs/openapi.json` 与 `frontend/src/api-types.ts` 机器生成
- `routers/days.py`：薄层，只做参数解析 + `CurrentUser` + 聚合返回

## Comments

- **读取不隐式创建**（FR-5.2）：无记录的日期返回空结构（`kind`/`title` 为 null、三个列表为空、`note` 为空串），**不落库**。这与 v1 的 `get_or_create_plan_day` 相反 —— v1 在读路径上不建，但写路径上建；v2 读路径必须无副作用，否则 GET 会写库。
- **日期非法返回 400，不是 422**：HLD §9.2 明确 400「日期或月份格式非法」。FastAPI 把路径参数标成 `date` 会直接吐 422，所以 router 收 `str` 自行解析、失败抛 400（对照票 07 的 422 文案经验：这里走 HTTPException 400，不经 Pydantic）。
- **与票 10 的语义差**：calendar 的 `?month=` 非法要**静默回退当月**（FR-4.2），days 的日期非法要 **400**。两套错误语义不要收进同一个 helper。
- 隔离：聚合查询一律经 `services/isolation.py` 的 `select_owned` 收窄，routers 不碰 `user_id` 过滤（硬不变量 1）。
- 本票不含任何写端点；`kind` 只从 `train`/`rest` 取值（models 默认 `train`），不改状态机。
- **mutmut 首跑点在这票**（HLD §12.0：`source_paths` = `app/parsing.py` 与 `app/services/days_service.py`）。本机无 WSL 发行版（票 02 复验已记账），门控保留、标「本机未验证」，若卡住不阻塞本票闭环。
- 测试按 HLD §12.0 `days` 行起头：聚合初值（空日）、position 排序、隔离（B 读 A 的日期看不到内容）。

## Answer
