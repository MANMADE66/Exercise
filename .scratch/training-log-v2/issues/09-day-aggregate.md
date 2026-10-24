Type: task
Status: ready-for-agent
Claimed by: pi（2026-10-24）

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

已落地并全绿（2026-10-24，`bash scripts/verify.sh` 一次通过：ruff → ruff format → mypy strict → pytest **96 例**（原 79 + 本票 17）→ openapi 导出 → api-types 生成 → 禁手改 diff → oxlint → oxfmt → vue-tsc → vite build；pytest 0 warning）。

### 契约形状（已机器生成到 `docs/openapi.json` / `frontend/src/api-types.ts`）

```
DayAggregate { date, kind: "train"|"rest"|null, title: str|null,
               planned_items: PlannedItemOut[], actual_items: ActualItemOut[], note: str }
PlannedItemOut { id, exercise, weight_kg, sets, reps, position }
ActualItemOut  { id, planned_item_id, exercise, weight_kg, sets, reps, note, position }
```

### 产物

- `schemas.py`：`PlannedItemOut` / `ActualItemOut` / `DayAggregate`（`date` 字段复用票 10 的 `IsoDate` 别名 —— `date: date` 会自指注解、Pydantic 报 `unevaluable-type-annotation`）。
- `services/days_service.py`：`aggregate_day(db, *, user_id, day)`（只读组装）+ `get_or_create_plan_day(db, *, user_id, day)`（默认 `kind="train"`、`title=None`，只 `flush()`）。
- `routers/days.py`：`GET /days/{iso_date}` 薄层；`parse_day_or_400()` + `INVALID_DATE_DETAIL = "日期格式非法，需 YYYY-MM-DD"` 供票 11/12/13 同文件复用。
- `parsing.py`：`parse_day(raw) -> date | None`（v1 `app/days.py:parse_day` 上移）。
- `tests/test_days.py`（8 例）+ `tests/test_parsing.py` 的 `parse_day`（3 个用例函数，含 7 项参数化，共 9 例 → 合计 17 例）：空日初值与「GET 不落库」、两组 position 排序（同 position 用 id 兜底）、字段映射（含 note、`planned_item_id`）、A/B 隔离（B 拿空结构而非 404）、非法日期 400、401、`get_or_create` 默认值与幂等。
- `pyproject.toml`：`[tool.mutmut] source_paths` 从 `["app"]` 收紧为 `["app/parsing.py", "app/services/days_service.py"]`（HLD §12.0）。
- `docs/HLD.md` §5.1：目标树标注更新到票 09，并加「`parse_day` 在 `parsing.py`、400 还是回退由调用方定」的指针。

### 六处实现裁定

1. **`kind` 用 `Literal["train", "rest"]`（不是裸 `str`）**：前端拿到的是联合类型，写 `v-if` 时不用再猜取值；契约只说这两个值（models 默认 `train`），脏值宁可让响应校验炸出来也不要静默透传。
2. **不加 `has_plan_day` 标志**：`kind`/`title` 为 null 就是「当天没排计划」的信号，多一个布尔字段等于同一事实两处表达，前端还能写出互相矛盾的状态。
3. **`note` 只读 `day_note` 表，不读 `plan_day.note` 列**：那一列是 v1 遗留死列（v1 的笔记一直写 `day_note`，见 `app/days.py:204`）；v2 照旧不碰它，避免出现「两个字段都叫 note、语义不同」的隐患。
4. **两个列表各用一条 join 查询，且 `join` 上的 `Exercise.user_id` 也收窄**：既避免逐条 lazy load（N+1），又不让关系加载绕过 `select_owned`；「A 的条目指向 B 的动作库」这种脏行对**双方都不可见**，与票 08 的父链校验同一取向。
5. **`parse_day` 放进 `parsing.py`，400 由 router 产出**：硬不变量 2（parsing 不抛错）对日期同样成立 —— 解析只回 `None`，「400 还是静默回退」是**调用方的错误语义**。故 days 走 400、calendar 的 `?month=` 走回退，两者刻意不共用 helper（票面注释要求）。
6. **`get_or_create_plan_day` 只 `flush()` 不 `commit()`**：写操作（票 11/12/13）需要「拿 id → 继续插条目 → 一次提交」，事务归调用方收尾；并发撞 `(user_id, date)` 唯一键的 `IntegrityError` 本票不加处理（单用户本地路径），票 11 的 `get_or_create_exercise` 要按同一手法回滚重查，届时可一并抽 helper。

顺带修掉一处弃用：`db.execute(...).tuples()` 在 SQLAlchemy 2.1 已弃用（Row 本身就是元组），改为直接迭代 Row，pytest 从 8 warnings 回到 0。

### 给票 11–14 的接口

- 写操作 `commit()` 之后调 `days_service.aggregate_day(db, user_id=..., day=...)`，直接当 `response_model=DayAggregate` 的返回值（D7：不再让前端补发 GET）。
- 隐式建日用 `days_service.get_or_create_plan_day(...)`：返回的对象已 `flush`（id 可用），**不代你 commit**；票 13 的「文本非空才建」在 service 里判，不要在 router 里判。
- 新增 `/days/{iso_date}/...` 端点直接用 `routers/days.py:parse_day_or_400()`，400 文案只有 `INVALID_DATE_DETAIL` 一处。
- 前端类型：`components["schemas"]["DayAggregate"]` / `PlannedItemOut` / `ActualItemOut` 已可用。
- 测试写法（mypy strict 友好）：`DayAggregate.model_validate(response.json())` 后按字段断言，别用 `dict[str, object]`（下标会退化成 object，`test_days.py` 初版就是这么被 mypy 打回的）。

### mutmut（本机未验证，门控保留）

`source_paths` 已按 HLD §12.0 收紧。本机实跑 `uv run mutmut run` 被直接拒绝：`To run mutmut on Windows, please use the WSL.`（mutmut 3.8.0 依赖 `os.fork`，上游 issue #397 未解），且 `wsl.exe -l -v` 仍是「没有已安装的分发版」→ 本条与票 02 的记账一致：待 WSL/CI 补跑，不阻塞本票闭环。

### 未做 / 留给后续

- 写端点（票 11/12/13）与 `template_service`（票 14）不在本票；`DayAggregate` 的形状已按它们的需求定好（`id` / `position` / `planned_item_id` / `note` 都在）。
- 本票与票 10 在同一工作树并行开发，票 10 先提交（`731e732`）后本票才动 `schemas.py` / `main.py`，两次提交各自重生成契约，无冲突。
