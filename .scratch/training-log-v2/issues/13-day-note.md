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

已落地 `7c73255`（`bash scripts/verify.sh` 全绿，**153 例** = 原 140 + 本票 13）。

### 端点与契约

```
PUT /days/{iso_date}/note   body DayNoteUpdate { text }   → DayAggregate
```

`DayNoteUpdate.text` 是**必填 `str`**（不是 `str | None`，也没有默认空串）：PUT 的语义是「整段替换」，
缺省静默当成「清空」会让一次拼错的请求静默删掉用户写的东西。要清空就显式传 `""` —— 这也正好
与 FR-8.1 的「空串仍保存」对齐。缺 `text` 走 Pydantic 原生 422，且两表零写入（有一例断言）。

### 产物

- `services/days_service.py`：`save_day_note`（`commit()` → `aggregate_day`，D7）；新增内部
  `_find_day_note`，并把原来的 `_note_text` 改成调它（读路径与写路径共用一个查询，不再各写一份
  `select_owned(DayNote, ...)`）。
- `routers/days.py`：`PUT /days/{iso_date}/note` 接在 `router`（日期前缀那组）上，仍只做
  「`parse_day_or_400` → service → 返回」，无需新 `APIRouter`，`main.py` 不动。
- `tests/test_day_note.py`（13 例）。

### 三处裁定

1. **空文本不删行**（票面注释明确的第一条）。`save_day_note("")` 走的是 upsert：已有 DayNote 就
   把 `text` 改成空串，没有就插一条空文本行。测试同时钉了「清空后 `day_note` 行数仍为 1」与
   「重复清空不增行」，把「删行」那种替代语义堵死。
2. **隐式建日的条件是「无 PlanDay 且 strip 后非空」**（FR-8.2）。`text.strip()` 先行，所以纯空行
   （`"   \n  "`）与空串同路：无 PlanDay 时一行都不写，有 PlanDay 时清空原文 —— 两种结果都有用例。
   这里刻意**不复用**票 12 `add_actual_item` 那种无条件 `get_or_create_plan_day`：那三个写端点
   「写条目必须有日」，而笔记路径按 FR-8.2 允许不建日。
3. **并发首次写笔记撞唯一键走 `_insert_or_refetch`**（票 11 那个 savepoint + 重查 helper）。
   `day_note.plan_day_id` 唯一（票 04），两个请求同时「查不到 → 插」时后者会 `IntegrityError`；
   helper 只回滚这一条、重查复用，随后统一 `note.text = normalized` 覆盖 —— 与 v1 的「后写覆盖」
   一致，且不连坐同事务里刚 flush 的计划日。测试用 monkeypatch 让 `_find_day_note` 首次返回
   `None`，确定性地走完撞键分支（结论：1 行、文本为后写值）。

### 照搬 v1 的部分（`app/days.py:save_note`）

- `text` 先 `strip()` 再落库；GET 不做二次 trim（`_note_text` 存什么回什么，`test_days.py` 里
  钉住的 `"  累但爽  "` 原样返回仍然成立）。
- 已有 PlanDay 时**不碰 kind/title**：笔记路径只 upsert DayNote（有例断言写入后 `title` 仍在）。
- 没有 `require_day_note`（票 08 已裁定不做）：入口恒为按日期，按 id 的 helper 是死代码。

### 隔离

唯一键是 `(user_id, date)`，同一天两人各有一行 —— B `PUT` 同日落到 B 自己名下（隐式建 B 的
PlanDay），A 的笔记原封不动（有例同时断言两表计数各为 2 与两边文本）。

### mutmut

`days_service.py` 在 `source_paths` 内，本票的 straddle 分支（空文本/非空文本 × 有无 PlanDay）
正好是变异目标区，但本机 `uv run mutmut run` 仍被上游拒绝（缺 `os.fork`，无 WSL 发行版）。
记账同票 02/09/11/12：待 WSL/CI 补跑，不阻塞闭环。
