Type: task
Status: ready-for-agent
Blocked by: 09
Claimed by: pi（2026-10-24）

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

## Answer

已落地并全绿（2026-10-24，`bash scripts/verify.sh`：ruff → ruff format → mypy strict → pytest
**193 例**（票 14 新增 22 例，票 15 并行新增 18 例）→ openapi 导出 → api-types 生成 → 禁手改 diff
→ oxlint → oxfmt → vue-tsc → vite build；EXIT=0）。

### 契约形状（已机器生成到 `docs/openapi.json` / `frontend/src/api-types.ts`）

```
TemplateAggregate { id, name, length_days, days: TemplateDayOut[] }   # GET 返回它的数组
TemplateDayOut    { day_index, kind: "train"|"rest", title: str|null, items: TemplateItemOut[] }
TemplateItemOut   { exercise, position }                              # 模板不含重量
TemplateCreate    { name?, length_days?, days?: TemplateDayIn[] }     # coerce_numbers_to_str
TemplateDayIn     { kind: str = "train", title?, items: TemplateItemIn[] }
TemplateItemIn    { exercise }
TemplateApplyRequest { start: str }                                   # 非法 → 400，不是 422
TemplateApplyResult  { created, skipped, skipped_dates: date[] }
```

### 产物

- `services/template_service.py`：`list_templates` / `create_template` / `delete_template` /
  `apply_template` + 归一规则（`_name` / `_length` / `_kind` / `_title` / `_exercises`）+ 批量组装
  （`_aggregates` / `_days_by_template` / `_items_by_day`，列表 3 条查询而不是每模板每天各查一次）。
- `routers/templates.py`：四个薄端点（`GET` / `POST` / `DELETE /{id}` / `POST /{id}/apply`），
  `main.py` 多 include 一行。
- `schemas.py`：模板 8 个模型（段落注释写明「模板不含重量」「days 下标即 day_index」）。
- `tests/test_templates.py`（**22 例**）：骨架映射与 strip、空名回退、天数非法回退 8（6 种输入）、
  超界截断 12、`days` 多出的天被忽略、kind 归一（`rest`/`REST`/`legs`/缺省）、动作自动入本人动作库、
  列表排序与 A/B 互不可见、删除级联天与条目、跨用户/不存在删除 404、apply 铺排（kind/title/
  动作/position、weight/sets/reps 全 NULL）、**已有 PlanDay 跳过且不覆盖**（断言原 title、原条目
  id 与重量组数未变）、重复 apply 全跳过、B 的同日计划不阻挡 A、跨用户 apply 404（且双方都没铺）、
  `start` 非法 400（4 种输入，表内零变化）、脏行（条目指向别人动作库）列表不可见且 apply 不抄。

### 七处实现裁定

1. **`length_days` 与 `start` 都收原始文本**：Pydantic 标成 `int` / `date` 会把「非法回退 8」
   和「400 日期格式非法」变成 422 —— 两条都是票面/SRS 明确要求的**非报错**语义（与票 11 的重量
   「收原始文本」同一取向）。`TemplateCreate` 加 `ConfigDict(coerce_numbers_to_str=True)`，前端顺手
   传 `8` 也照收（都归一成文本再走 `parse_sets`）。
2. **`TemplateDayIn.kind` 收裸 `str`，不标 `DayKind`**：FR-9.2 的规则是「非 `rest` 一律 `train`」，
   标成 `Literal` 会把填错的 kind 变成 422 整单拒绝 —— 与「静默归一」正好相反。归一落在 `_kind()`，
   测试钉住 `"REST"` / `"legs"` / 缺省都落 `train`。
3. **`TemplateItemIn.exercise` 不校验非空**（与计划条目的 `_ExerciseNamed` 相反，刻意的差异）：
   v1 的输入是一行一个动作名、空行被忽略；JSON 形状下与之对应的就是「strip 后为空的动作名跳过」，
   由 service 的 `_exercises()` 处理。plan-item 那边空动作名 422 是票 11 的裁定，两者输入形态不同，
   不复用同一条规则。
4. **`days` 数组按小标对应 `day_index`**：多余的天**忽略**（v1 只读 `range(length)` 内的表单字段），
   不足的补默认训练日（`train` / 无标题 / 无条目）。于是 `length_days == len(days)` 恒成立，骨架
   不缺行；两条都有测试。
5. **契约不出 `sets` / `reps` / `weight`，也不出模板日/条目的 id**：模板侧 `sets`/`reps` 是 v1
   遗留列、v2 恒写 NULL，暴露一个永远为 null 的字段只会让前端长出无效输入框；而**没有任何端点按
   模板日或条目定位**（只有整模板的 delete / apply），id 是死字段。因此条目只出 `exercise` +
   `position`（顺序也可由数组顺序读出），天的业务键 `day_index` 保留。
   —— 这正是票面注释要求的读法：HLD §5.2「apply 时仅复制骨架字段（exercise、sets、reps、
   position）」指的是**复制动作**，因为模板侧 sets/reps 恒 NULL，抄过去也恒 NULL；**不给
   `POST /templates` 加 sets/reps 入参**，形状以 SRS §5 的 `items:[{exercise,...}]` 为准。
6. **apply 用 `find_plan_day` + 显式建 `PlanDay`，刻意不走 `get_or_create_plan_day`**：判定是
   「**当前用户**该日期是否已有 PlanDay」（查的是 `(user_id, date)` 唯一键那一行），有就跳过并把
   日期收进 `skipped_dates`（升序，随 `day_index` 递增天然有序），一个字节都不改原计划日；
   与「没有就建」是相反语义（票面注释）。计数与日期一起结构化回给前端（v1 只回一个中文句子）。
7. **逐层收窄 `user_id`，join 上的 `Exercise.user_id` 也收窄**：`_days_by_template` /
   `_items_by_day` 各自带 `select_owned`，条目查询再 join `Exercise` 校验归属 —— 脏行（A 的模板
   条目指向 B 的动作库）对双方都不可见，apply 也不会把脏 `exercise_id` 抄进本人的计划日（有测试；
   与 `days_service._planned_items` 同一取向）。

另两处小裁定：**400 文案单源** —— `routers/templates.py` 直接复用
`routers/days.py:parse_day_or_400()`（router→router 引用一个函数，好过复制第二份
`INVALID_DATE_DETAIL`）；**写端点一律 200**（POST / DELETE 都不改状态码），与其他业务端点一致，
前端只看 body。

### 与票 15 的并行记账

票 15 在同一工作树并行开发（`map.md` Notes 允许），共享文件撞在一起：`schemas.py` 的模板契约被
票 15 的提交 `4ce9c04` 一并带走，本票的提交 `2c733c8` 补齐 router / service / tests 与重新生成的
契约（`docs/openapi.json` / `api-types.ts` 含两票全部路径）。两次提交各自 verify 全绿，最终
HEAD 契约与源码一致。教训记账：**14 与 15 其实不能真并行** —— 都改 `schemas.py` / `main.py` /
生成物，下一轮若还有两张票同时动契约，应按序等前一张提交后再开工（票 09/10 的错开做法）。

### 给后续（前端）票的接口

- 类型：`components["schemas"]["TemplateAggregate"]` / `TemplateDayOut` / `TemplateItemOut` /
  `TemplateCreate` / `TemplateApplyResult` 已可用。
- 模板页交互：`GET /templates` 一次拿全（含逐日骨架），`POST` 拿新模板、`DELETE` 拿剩余列表
  （都可整体替换，不必补发 GET），apply 后用 `skipped_dates` 提示「已排过的日期不动」并刷新月历。
- `POST /templates` 的 `length_days` 传数字或文本都行（服务端归一），但 `days` 的下标就是
  `day_index`，别指望「按天传 key」。
