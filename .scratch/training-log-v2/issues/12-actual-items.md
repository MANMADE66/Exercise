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

已落地 `6e731b9`（`bash scripts/verify.sh` 全绿，**140 例** = 原 114 + 本票 26）。

### 端点与契约

```
POST   /days/{iso_date}/actual/prefill  body —                     → DayAggregate
POST   /days/{iso_date}/actual-items   body ActualItemCreate       → DayAggregate
PATCH  /actual-items/{actual_item_id}  body ActualItemUpdate       → DayAggregate
DELETE /actual-items/{actual_item_id}  —                           → DayAggregate
```

- `ActualItemCreate` = 票 11 的 `PlanItemCreate` + `note`：两者同构，故「动作名去空白后非空」
  抽成私有基类 `_ExerciseNamed`（空动作名 422、不落库，与计划条目同一中文文案）。私有基类被
  OpenAPI 内联进两个 schema，没有多余组件泄漏进契约。
- `ActualItemUpdate` 四个字段全 `str | None = None`、**无默认以外的约束**：`str | None` 的 `None`
  表示「显式置空」，缺席表示「不动」，两者在值上不可分（见下）。
- 路径参数名用 `actual_item_id` 而非 HLD 表里的 `{id}`（URL 形状不变，OpenAPI 参数标签更明确，
  与票 11 的 `plan_item_id` 同口径）。

### 产物

- `services/days_service.py`：`prefill_actual_items` / `add_actual_item` / `update_actual_item` /
  `delete_actual_item`（全部 `commit()` 后调 `aggregate_day`，D7）；内部 `_copy_missing_actuals` /
  `_linked_planned_item_ids` / `_actual_siblings` / `_parse_note` / `_ACTUAL_FIELD_UPDATES`；
  `_renumber` 泛化为 `Sequence[PositionedT]`（计划条目与实际条目共用）。
- `routers/days.py`：新增第三个 `APIRouter(prefix="/actual-items")`，`main.py` 多 include 一行；
  四个端点都只做「解析 → service → 返回」，404 无 try/except（`core/errors.py` 全局处理器产出）。
- `tests/test_actual_items.py`（26 例，含票面要求的五组覆盖点）。
- `docs/HLD.md` §5.1 目标树说明更新到票 12。

### 三处实现裁定

1. **PATCH 三态靠 `model_fields_set`，且必须显式写列名**。字段缺省与显式 `null` 的值都是 `None`，
   用 `exclude_unset`/`exclude_none` 或「值是 `None` 就跳过」的一把梭会静默丢掉「置空」那一态；
   实现是 `for field in changes.model_fields_set: setattr(item, column, parse(...))`，四个字段逐个验。
   **踩到的坑**：契约字段叫 `weight`、列却叫 `weight_kg`，第一版直接
   `setattr(item, field, ...)` 把值写到了一个非映射的 Python 属性上 —— 不报错、不落库、响应里
   照旧回旧值（`sets`/`reps`/`note` 恰好同名，于是**只有 weight 静默失效**，三例三态测试当场抓住）。
   落定形态是一张 `_ACTUAL_FIELD_UPDATES: dict[str, tuple[列名, 解析器]]`，并配一条不变量测试：
   契约字段集与映射键集相等、每个列名都真实存在于 `ActualItem.__table__.columns`。
2. **prefill 不隐式建日，且没有 `db.commit()` 之外的写动作**。当天无 PlanDay → 静默 no-op 返回空
   聚合（照票面裁定：prefill 是「照计划复制」，没计划就无可复制），与同文件里计划外新增的
   「隐式建日」是两个语义，测试各钉一例（no-op 用例顺带断言 PlanDay/ActualItem/Exercise 三表计数
   全为 0）。
3. **prefill 并发撞唯一键 = 整批回滚重算一次**（票面「双重保险」后手）。
   `with db.begin_nested()` 走一整个复制回合，撞 `UNIQUE(plan_day_id, planned_item_id)` 只回滚这批
   复制（不连坐调用方事务里已 flush 的行，取向同 `_insert_or_refetch`），重算走真实查询即看见对方
   刚提交的行，于是只补剩下的；重算仍撞就抛出，不吞。测试用 monkeypatch 让第一次
   `_linked_planned_item_ids` 返回空集，确定性地走完 `IntegrityError` 分支（另一会话已补上「深蹲」
   时，重算后只补「卧推」，总数为 2 不冒 500）。

### 照搬 v1 的部分（票面未要求改动的语义）

- **复制当前计划值**（`weight_kg` / `sets` / `reps` 三列抄计划条目，不是抄模板），`note` 留 NULL。
- **已练过的行不覆盖**：`already = {planned_item_id}` 只过滤「有对应实际条目」，计划值后来改过也不回灌
  （测试里实际值 `sets=1` + 备注保留）。
- **position 一律末位追加**：prefill 与新增共用 `len(_actual_siblings(...))` 计数；同一请求内多条
  沿用一个递增变量（不在循环里重算 `len()`，否则全挤同一号）；删除后剩余 position 重排回 `0..n-1`
  （理由同票 11 裁定 ③：否则下一条添加撞号）。prefill 之后再新增落在末尾也有一例钉住。
- **解析口径**：`weight`/`sets` 解析失败或空串 → NULL，`reps` 空串 → 空串（自由文本），
  `note` trim 后为空 → NULL（`(note or "").strip() or None`）。
- 隔离：`PATCH`/`DELETE` 经 `require_actual_item`（父链校验到 `plan_day.user_id`），B 动 A 的条目
  404 且与「不存在」同码同文案、A 的数据毫发无损；prefill 也只看得见自己的计划日。

### 给票 13 的接口

- 四个写端点的收尾形态与 11 一致：service `commit()` → `aggregate_day(...)`，router
  `response_model=DayAggregate`。票 13 的 `PUT /days/{iso}/note` 照同一形态接，不需要补 GET。
- `position` 的两表共用重排已是泛型 `_renumber`；票 13 用不到，但票 14 若要在 `template_service`
  里维护 `TemplateItem.position`，建议从本模块导出或搬一份同形实现。
- 测试 helper（`_prefill` / `_create` / `_patch` / `_delete` / `_seed_actual`）可直接改形状复用。

### mutmut（仍本机未验证）

本票把「三态逐字段更新」与「prefill 幂等重算」两条最值得变异的逻辑放进了 `days_service.py`
（已在 `source_paths` 内），但本机 `uv run mutmut run` 仍被上游拒绝（缺 `os.fork`；`wsl.exe -l -v`
无已安装发行版）。记账同票 02/09/11：待 WSL/CI 补跑，不阻塞本票闭环。
