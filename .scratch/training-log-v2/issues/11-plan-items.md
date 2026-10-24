Type: task
Status: ready-for-agent
Claimed by: pi（2026-10-24）
Blocked by: 09

## Question

落地计划管理三个写端点（SRS FR-6、HLD §9.1）。全部返回**新鲜日聚合**（D7，票 09 的 `aggregate_day`）。

- `POST /days/{date}/plan-items` {exercise, weight?, sets?, reps?}：动作名自动建入本人动作库、重量/组数容错解析、**置于末位**（`position = len(items)`）
- `DELETE /plan-items/{id}`：删除计划条目；关联实际条目不受影响，`planned_item_id` 置空保留记录（models 已 `ON DELETE SET NULL`）
- `POST /plan-items/{id}/move` {direction: up|down}：交换后按 enumeration 重排全组 `position`；边界（首个上移 / 末个下移）**静默成功**
- `services/days_service.py` 承接业务规则；`routers/days.py` 只做映射

## Comments

- v1 语义（`app/days.py` 的 `add_plan_item` / `delete_plan_item` / `move_plan_item`）照搬，差异只在错误码归一：
  - 解析：`parse_weight` / `parse_sets` / `parse_reps`，解析失败**存 NULL 不报错**（硬不变量 2，FR-6.4）
  - `reps` 保留原字符串（trim），不是数字
  - move：`siblings = list(plan_day.items)` 后 `swap` + `for position, sibling in enumerate(siblings): sibling.position = position` —— 全组重排，不是只换两个值（否则重复 `position` 会让后续排序不稳定）
- **两处需在票内裁定的 v1 缺口**：
  1. v1 对空 `exercise` 是**静默 no-op**（`if name:` 才写），v2 有 Pydantic，空串应直接 422（`min_length=1`，与票 07 的 `PydanticCustomError` 中文文案同一手法）。SRS 未写，按「不静默吞掉用户输入」裁定。
  2. v1 的 `get_or_create_exercise` 是「先查后建」；`(user_id, name)` 唯一键在并发下会撞 —— `IntegrityError` 要回滚后重查复用，不能冒 500（票 04 已把唯一约束收紧到 `(user_id, 原键)`）。
- 隐式建日在这条路径上**合法**（写操作需要 PlanDay），但 `kind` 一律 `train`、`title` 为 NULL（v1 `get_or_create_plan_day`）。与 FR-8.2 的「文本非空才建」不冲突：那是 note 路径的独立规则，见票 13。
- 404 全部由 `services/isolation.py` 的 `require_planned_item` 产出（票 08 已建），routers 不写 try/except、不自拼文案。
- 测试按 HLD §12.0 `days` 行：plan-item 增删移、边界静默成功、position 全组连续、删除后 actual_item 仍存在且 `planned_item_id IS NULL`、空动作名 422、同级重名动作复用同一 exercise 行、隔离（B 动 A 的条目 404）。

## Answer

已落地并全绿（2026-10-24，`bash scripts/verify.sh` 一次全绿：ruff → ruff format → mypy strict → pytest **114 例**（原 96 + 本票 18）→ openapi 导出 → api-types 生成 → 禁手改 diff → oxlint → oxfmt → vue-tsc → vite build）。

### 契约增量（已机器生成到 `docs/openapi.json` / `frontend/src/api-types.ts`）

```
POST   /days/{iso_date}/plan-items   body PlanItemCreate { exercise, weight?, sets?, reps? }   → DayAggregate
DELETE /plan-items/{plan_item_id}                                                            → DayAggregate
POST   /plan-items/{plan_item_id}/move  body PlanItemMove { direction: "up"|"down" }          → DayAggregate
```

- `PlanItemCreate` 的 `weight` / `sets` / `reps` 收 **原始文本**（`str | None`），不是 `float` / `int`：标成数字类型的话 `"60kg"` 会被 Pydantic 直接 422 拦掉，正好违背 FR-6.4 的「解析失败不报错」。
- `exercise` 用 `field_validator` 先 `strip()` 再判空 → 空串 / 纯空白一律 422（`PydanticCustomError("exercise_required", "动作名不能为空")`，与票 07 同一中文文案手法）。
- 路径参数名用 `plan_item_id` 而非 HLD 表里的 `{id}`（URL 形状不变，只是 OpenAPI 里的参数标签更明确；`id` 会遮蔽内建名）。

### 产物

- `services/days_service.py`：`add_planned_item` / `delete_planned_item` / `move_planned_item`（全部 `commit()` 后调 `aggregate_day` 返回新鲜聚合，D7）；新增 `get_or_create_exercise`；内部 `_siblings` / `_renumber` / `_insert_or_refetch`。
- `routers/days.py`：新增 `plan_items_router = APIRouter(prefix="/plan-items", tags=["days"])`（同一模块两个前缀，`/days/...` 那组仍用 `parse_day_or_400()`）；`main.py` 多 include 一行。三个端点都只做「解析 → service → 返回」，404 不含任何 try/except（由 `core/errors.py` 全局处理器产出）。
- `tests/test_plan_items.py`（18 例）：添加（末位 / 隐式建日 / 动作入库 / 容错解析含 `60kg`·`62,5`·`abc`·`0` / 空动作名 422 且不落库 / 同名复用动作行 / 非法日期 400 / 401）；删除（聚合返回 / 实际条目保留且 `planned_item_id` 为 NULL / position 重排 / 缺 id 404）；移动（交换 + 全组重排 / 脏库重复 position 归一 / 两处边界静默 200 / 非法 direction 422 / 缺 id 404）；隔离（B 删移 A 的条目同码同文案 404、A 数据无损 / 同日期两用户互不干扰）；并发（计划日与动作名各一例撞唯一键复用）。
- `docs/HLD.md` §5.1 目标树说明更新到票 11。

### 四处实现裁定

1. **空动作名 422 而非 v1 的静默 no-op**（票面缺口的裁定照写）：`"   "` 也算空 —— 前端把整行留空提交时，用户需要知道「这条没存进去」，而不是刷新后条目凭空消失。
2. **并发 `get_or_create` 用 SAVEPOINT 而非 `db.rollback()`**：写路径上计划日已 `flush()` 在同一事务里，整事务回滚会把计划日一起丢掉。`_insert_or_refetch` 里 `with db.begin_nested(): add + flush`，撞 `(user_id, date)` / `(user_id, name)` 唯一键只回滚这一条，再重查复用；重查仍查不到说明撞的不是这两条唯一键（数据脏了），直接重抛，不吞异常。两例并发测试用 monkeypatch 让第一次查询「假装没查到」，确定性地走完 `IntegrityError` 分支。
3. **删除后把剩余条目 position 重排为 0..n-1**（票面未写，本票新增的裁定）：添加用 `position = len(items)`（票面明确要求），若删除留下空洞，下一次添加就会撞号产生重复 `position` —— 而那正是票面注释里「重复 position 让排序不稳定」要防的事。两个约束（len 追加 + 全组连续）只能靠「删完顺带重排」同时成立；v1 没有这个动作，但它只影响响应里的顺序号，不改变条目的相对次序。
4. **`reps` 原样落库，空输入存空串而非 NULL**（照搬 v1）：次数是自由文本，`parse_reps` 只 `trim`；`weight` / `sets` 解析失败才存 NULL。测试把三种结局（`"8-12"` / `""` / `"abc"`→null）都钉住了。

### 未变的部分（照票面「照搬 v1」）

- move 语义 = `siblings = 按 (position, id) 升序` → 相邻交换 → `enumerate` 重排全组；边界不换、不报错，仍返回 200 + 当前聚合。
- 删除只删计划条目：`actual_item.planned_item_id` 由 `ON DELETE SET NULL` 置空（`PlannedItem.actual_items` 是 `passive_deletes=True`，交给库而非 ORM 逐行 UPDATE），实际条目与其 `exercise` / 剂量全部保留。
- 隐式建日只在这条写路径上发生：`kind="train"`、`title=None`，与 FR-8.2 的「笔记文本非空才建日」（票 13）是两条独立规则。

### 给票 12/13 的接口

- 三个写端点的收尾形态已定：service 里 `commit()` → `return aggregate_day(...)`，router 直接 `response_model=DayAggregate`。票 12（actual item / prefill）与票 13（note）照同一形态接，不需要再补 GET。
- 需要「动作名 → 本人动作库行」时调 `days_service.get_or_create_exercise(db, user_id=..., name=...)`（已带并发回滚重查），不要各写一份先查后建。
- 需要「末位追加」时用 `len(_siblings(...))`（票 12 的 actual 侧若也按此维护，position 口径与本题一致）；`/actual-items/...` 那组同样建议在本模块加第三个 `APIRouter`，前缀分组不混进 `/days`。
- 测试里的 `_add` / `_delete` / `_move` 三个 HTTP helper 可直接搬到票 12/13 用例里改形状。

### mutmut（仍本机未验证）

`source_paths` 已含 `app/services/days_service.py`，本票把 position 维护、容错解析、并发重查三条逻辑都放进了这个文件 —— 正是变异测试的目标区，但本机 `uv run mutmut run` 仍被上游拒绝（缺 `os.fork`，且 `wsl.exe -l -v` 无已安装发行版）。记账同票 02/09：待 WSL/CI 补跑，不阻塞本票闭环。
