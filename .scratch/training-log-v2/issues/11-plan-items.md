Type: task
Status: ready-for-agent
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
