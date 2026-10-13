# 训练记录 v1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本地跑起一个训练记录应用：月历点格子就地展开当天详情，「计划」与「实际完成」两块分开，外加按周的身体数据和可复用的循环模板。

**Architecture:** 单体 Flask 应用，服务端渲染（Jinja2 + 手写 CSS），数据落 SQLite（SQLAlchemy 管）。页面用一小段原生 JS 做「点格子取片段、就地展开、表单局部刷新」，其余都是普通 POST。不引前端框架、不引 UI 组件库。

**Tech Stack:** Python 3.11+、Flask、Flask-SQLAlchemy、SQLite、pytest、Jinja2、原生 CSS/JS。

**Spec:** `docs/superpowers/specs/2026-10-13-training-log-design.md`

## Global Constraints

- 项目根目录就是 `D:\Code\训练规划`。如果它还不是独立 git 仓库，先在它里面 `git init`；不要动上层 `D:\Code` 仓库。
- 单人本地使用：不做登录、权限、多用户、云同步、手机版。
- 数据库文件固定在 `data/app.db`，`data/` 写进 `.gitignore`。
- 界面文案全中文。日期一律 `YYYY-MM-DD`，按本地时区解释，禁止 `datetime.utcnow()`。
- `reps` 是**文本**字段，允许 `8-12`、`12/12/10/8`、空；`weight_kg` 是小数（kg），允许 2.5 步进、允许空；`sets` 是整数或空。
- 「计划」与「实际完成」在页面上必须视觉分开，任何任务不得把两者合成一个列表。
- 视觉是硬要求（spec 第 5 节）：不要「后台管理系统」的样子。样式集中在 `app/static/app.css`，颜色和间距用 CSS 变量。
- 外部依赖只有 Flask、Flask-SQLAlchemy（开发依赖 pytest）。安装依赖需要联网。
- 每个任务结束时 `pytest -q` 必须全绿，然后提交。

## Review Focus

1. **日期边界**：跨月、月末、2 月、闰年、以周一为一周起点——把日期当字符串处理会炸。
2. **半填记录**：只有计划没有实际、只有重量没有次数、次数是手写文本——页面不能崩、不能显示 `None`。
3. **一周跨月**：月历某一行可能一半属于上/下个月，周身体数据挂在这一行上要能正常显示。
4. **模板铺在已有数据上**：不能静默覆盖使用者已经写好的计划，要跳过并报告跳过了几天。
5. **重量输入**：`100`、`102.5`、`100kg`、`102,5`、空、乱输——解析不能 500。

---

## 文件结构

```
app/
  __init__.py        create_app()、注册蓝图、建表入口
  db.py              SQLAlchemy 实例（唯一）
  models.py          ORM 模型（9 张表）
  parsing.py         输入解析：重量 / 组数 / 次数
  calendar.py        月历：month_grid() + 路由
  days.py            某天的片段 + 计划 / 实际 / 感受的读写路由
  metrics.py         每周身体数据
  cycle.py           循环模板：模板 CRUD + 铺到日历
  templates/
    base.html
    calendar.html
    _day_detail.html
    templates_list.html
  static/
    app.css
    app.js          点格子取片段、就地展开、表单局部刷新
tests/
  conftest.py
  test_models.py  test_parsing.py  test_calendar.py  test_day_detail.py
  test_plan_items.py  test_actual_items.py  test_notes.py
  test_metrics.py  test_cycle.py
docs/visual-drafts/   三个视觉方向样张 + 选定结果
data/                 数据库（不进版本库）
pyproject.toml  .gitignore  README.md
```

---

### Task 1: 项目骨架与数据模型

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `app/__init__.py`, `app/db.py`, `app/models.py`, `tests/conftest.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: 无
- Produces: `create_app(config: dict | None = None) -> Flask`；`app.db.db`（SQLAlchemy 实例）；模型 `Exercise, PlanDay, PlannedItem, ActualItem, BodyMetric, DayNote, CycleTemplate, TemplateDay, TemplateItem`

- [ ] **Step 1: 写失败的测试** `tests/conftest.py` + `tests/test_models.py`

```python
# conftest.py
import pytest
from app import create_app
from app.db import db as _db

@pytest.fixture
def app(tmp_path):
    app = create_app({"SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path/'t.db'}",
                      "TESTING": True})
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()

@pytest.fixture
def client(app):
    return app.test_client()
```

```python
# test_models.py
from datetime import date
from app.db import db
from app.models import Exercise, PlanDay, PlannedItem, ActualItem

def test_plan_day_roundtrip(app):
    with app.app_context():
        db.session.add(PlanDay(date=date(2026, 10, 13), kind="train", title="胸 + 二头"))
        db.session.commit()
        row = PlanDay.query.one()
        assert row.kind == "train" and row.title == "胸 + 二头"

def test_planned_and_actual_are_separate_tables(app):
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train")
        e = Exercise(name="卧推")
        db.session.add_all([d, e]); db.session.flush()
        p = PlannedItem(plan_day=d, exercise=e, weight_kg=100, sets=4, reps="8-12", position=0)
        db.session.add(p); db.session.flush()
        a = ActualItem(plan_day=d, planned_item=p, exercise=e, weight_kg=102.5, sets=4,
                       reps="12/12/10/8", position=0)
        db.session.add(a); db.session.commit()
        assert PlannedItem.query.one().weight_kg == 100
        assert ActualItem.query.one().planned_item_id == p.id

def test_plan_day_date_is_unique(app):
    import pytest
    from sqlalchemy.exc import IntegrityError
    with app.app_context():
        db.session.add_all([PlanDay(date=date(2026, 10, 13)), PlanDay(date=date(2026, 10, 13))])
        with pytest.raises(IntegrityError):
            db.session.commit()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_models.py -q`
Expected: FAIL，报 `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: 实现骨架**

`pyproject.toml`：项目名 `training-log`，`requires-python = ">=3.11"`，依赖 `flask`、`flask-sqlalchemy`，开发依赖 `pytest`；配置 pytest 的 `testpaths = ["tests"]`。
`.gitignore`：`data/`、`__pycache__/`、`.pytest_cache/`、`*.pyc`、`.venv/`。
`app/db.py`：`db = SQLAlchemy()`。
`app/models.py`：按 spec §10 定义九张表。
  - `Exercise`: `id, name(unique, not null), body_part, created_at`
  - `PlanDay`: `id, date(Date, unique, not null, index), kind("train"|"rest"), title, note`
  - `PlannedItem`: `id, plan_day_id(FK), exercise_id(FK), weight_kg(Float, nullable), sets(Integer, nullable), reps(String, nullable), position(Integer)`
  - `ActualItem`: 同上 + `planned_item_id(FK, nullable)` + `note`
  - `BodyMetric`: `id, week_start(Date, unique), weight_kg(Float, not null), body_fat_pct(Float, nullable), note`
  - `DayNote`: `id, plan_day_id(FK, unique), text, updated_at`
  - `CycleTemplate`: `id, name, length_days(Integer), created_at`
  - `TemplateDay`: `id, template_id(FK), day_index(Integer), kind, title`
  - `TemplateItem`: `id, template_day_id(FK), exercise_id(FK), sets, reps, position`
  - 关系（测试里直接用到了，必须建）：`PlanDay.items` / `PlanDay.actuals` / `PlanDay.note`；`PlannedItem.plan_day` / `.exercise`；`ActualItem.plan_day` / `.exercise` / `.planned_item`；`TemplateDay.items`；`TemplateItem.exercise`。
`app/__init__.py`：`create_app(config=None)`——建 Flask、读配置（默认 `SQLALCHEMY_DATABASE_URI` 指向 `data/app.db` 并确保目录存在）、`db.init_app(app)`、返回 app。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_models.py -q`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 项目骨架与数据模型"
```

---

### Task 2: 视觉方向三选一（人工门，必须在做页面之前完成）

**Files:**
- Create: `docs/visual-drafts/direction-a.html`, `direction-b.html`, `direction-c.html`, `docs/visual-drafts/README.md`, `app/static/app.css`

**Interfaces:**
- Consumes: 无
- Produces: `app/static/app.css` 里的 CSS 变量（颜色 / 间距 / 字号 / 圆角）；选定方向的记录

- [ ] **Step 1: 做三份静态样张**

每份样张是**单文件 HTML**（内联样式，不依赖服务器），用同一份假数据画出两样东西：一个月的月历 + 某一天展开后的详情（计划与实际完成两块分开）。三个方向要有明显可辨的差别，例如：极简黑白 + 一个大面积留白；深色底 + 高对比强调色；浅灰卡片 + 细腻描边与层次。三个方向都必须满足 spec 第 5 节。

- [ ] **Step 2: 交给使用者挑**

把三份样张的路径和截图给使用者，请他选一个（或提修改意见）。**没选之前不要开始 Task 3。**

- [ ] **Step 3: 把选定方向落成样式令牌**

把选定方向的颜色、间距、字号、圆角抽成 `app/static/app.css` 顶部的 CSS 变量（`:root { --color-bg: ...; }`），并在 `docs/visual-drafts/README.md` 里记录：选的是哪一份、为什么、以及取到的令牌清单。

- [ ] **Step 4: 提交**

```bash
git add -A && git commit -m "feat: 视觉方向样张与样式令牌"
```

---

### Task 3: 月历页

**Files:**
- Create: `app/calendar.py`, `app/templates/base.html`, `app/templates/calendar.html`, `tests/test_calendar.py`
- Modify: `app/__init__.py`（注册蓝图）, `app/static/app.css`

**Interfaces:**
- Consumes: Task 1 的模型与 `create_app`
- Produces: `month_grid(year: int, month: int) -> list[list[date | None]]`（周一为一周起点，整周补齐，月初日前和月末日后都是 `None`）；路由 `GET /?month=YYYY-MM` → 月历 HTML，每格带 `data-date="YYYY-MM-DD"`

- [ ] **Step 1: 写失败的测试** `tests/test_calendar.py`

```python
from datetime import date
from app.calendar import month_grid

def test_month_grid_starts_on_monday_and_pads():
    weeks = month_grid(2026, 10)          # 2026-10-01 是周四
    assert len(weeks) == 5
    assert weeks[0][:3] == [None, None, None]
    assert weeks[0][3] == date(2026, 10, 1)
    assert weeks[4][5] == date(2026, 10, 31)
    assert weeks[4][6] is None

def test_month_grid_february():
    assert sum(1 for w in month_grid(2026, 2) for d in w if d) == 28
    assert sum(1 for w in month_grid(2024, 2) for d in w if d) == 29

def test_calendar_route_renders_month(client):
    html = client.get("/?month=2026-10").get_data(as_text=True)
    assert 'data-date="2026-10-01"' in html
    assert 'data-date="2026-10-31"' in html
    assert 'data-date="2026-11-01"' not in html

def test_calendar_route_defaults_to_current_month(client):
    assert client.get("/").status_code == 200

def test_calendar_shows_train_day_title(client, app):
    from app.db import db
    from app.models import PlanDay
    with app.app_context():
        db.session.add(PlanDay(date=date(2026, 10, 13), kind="train", title="胸 + 二头"))
        db.session.commit()
    html = client.get("/?month=2026-10").get_data(as_text=True)
    assert "胸 + 二头" in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_calendar.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'app.calendar'`

- [ ] **Step 3: 实现**

`month_grid(year, month) -> list[list[date | None]]`：用 `calendar.monthrange` 算天数，用 `date.weekday()`（周一=0）算补齐位置，切成整周。
路由：解析 `month` 查询参数（缺省用 `date.today()`；格式错误回退到当月，不报 500），查该月全部 `PlanDay`，渲染 `calendar.html`。
页面：`base.html` 提供骨架和 `app.css` 引入；`calendar.html` 渲染月份标题、上一月/下一月链接、周一到周日的表头、每周一行、每天一格（`data-date`、日期数字、训练日标题或「休息」、已记录实际完成的日子加 `has-log`）。样式按 Task 2 选定的方向。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest -q`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 月历页"
```

---

### Task 4: 每日详情片段 + 就地展开

**Files:**
- Create: `app/days.py`, `app/templates/_day_detail.html`, `app/static/app.js`, `tests/test_day_detail.py`
- Modify: `app/__init__.py`, `app/templates/calendar.html`（格子加展开锚点）

**Interfaces:**
- Consumes: Task 1 模型、Task 3 的月历页
- Produces: `GET /day/YYYY-MM-DD` → 返回 HTML **片段**（不是整页），片段里必须有两个分开的容器 `id="planned"` 与 `id="actual"`；`app.js` 暴露 `openDay(日期字符串)`，点到格子就在该周下方插入片段，再点收起

- [ ] **Step 1: 写失败的测试** `tests/test_day_detail.py`

```python
from datetime import date
import pytest
from app.db import db
from app.models import Exercise, PlanDay, PlannedItem, ActualItem

@pytest.fixture
def seeded(app):
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train", title="胸 + 二头")
        e = Exercise(name="卧推")
        db.session.add_all([d, e]); db.session.flush()
        db.session.add(PlannedItem(plan_day=d, exercise=e, weight_kg=100, sets=4,
                                   reps="8-12", position=0))
        db.session.add(ActualItem(plan_day=d, exercise=e, weight_kg=95, sets=3,
                                  reps="12/10/8", position=0, note="最后一组没做完"))
        db.session.commit()

def test_day_fragment_has_two_separate_sections(client, seeded):
    html = client.get("/day/2026-10-13").get_data(as_text=True)
    assert 'id="planned"' in html and 'id="actual"' in html
    assert html.index('id="planned"') < html.index('id="actual"')
    assert "卧推" in html and "100" in html and "95" in html
    assert "最后一组没做完" in html

def test_day_fragment_for_empty_day_has_both_sections(client):
    html = client.get("/day/2026-10-20").get_data(as_text=True)
    assert 'id="planned"' in html and 'id="actual"' in html
    assert "None" not in html

def test_day_fragment_never_touches_other_days(client, seeded):
    html = client.get("/day/2026-10-14").get_data(as_text=True)
    assert "卧推" not in html
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_day_detail.py -q`
Expected: FAIL（404 或模块不存在）

- [ ] **Step 3: 实现**

`days.py`：`GET /day/<iso_date>` 用 `date.fromisoformat` 解析，非法日期返回 400；查该日 `PlanDay`（可能不存在）、`PlannedItem` 与 `ActualItem`（按 `position`），渲染 `_day_detail.html`。
`_day_detail.html`：两个 `<section id="planned">` / `<section id="actual">`，各自一个标题和一张小表；空态写「还没安排」/「还没记录」；不输出 `None`（空值一律渲染成空串）。
`app.js`：点 `.day-cell` → `fetch('/day/'+date)` → 在所属周行下方插入 `<tr class="day-detail"><td colspan="7">…</td></tr>`；再点同一格收起；同一时刻只展开一天。用 `defer` 引入。
`calendar.html` 的格子加 `data-date` 与可点样式。样式按 Task 2 方向。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest -q`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 每日详情片段与就地展开"
```

---

### Task 5: 计划录入与编辑

**Files:**
- Create: `app/parsing.py`, `tests/test_parsing.py`, `tests/test_plan_items.py`
- Modify: `app/days.py`, `app/templates/_day_detail.html`

**Interfaces:**
- Consumes: Task 4 的片段
- Produces: `parse_weight(raw: str) -> float | None`、`parse_sets(raw: str) -> int | None`、`parse_reps(raw: str) -> str`（去空白，允许空串）；路由 `POST /day/<date>/plan`（表单字段 `exercise, weight, sets, reps`）、`POST /plan-item/<id>/delete`、`POST /plan-item/<id>/move`（`direction=up|down`）；动作名输入即入 `Exercise` 表

- [ ] **Step 1: 写失败的测试**

```python
# test_parsing.py
from app.parsing import parse_weight, parse_sets, parse_reps

def test_parse_weight_accepts_common_forms():
    assert parse_weight("100") == 100.0
    assert parse_weight("102.5") == 102.5
    assert parse_weight("100kg") == 100.0
    assert parse_weight("102,5") == 102.5
    assert parse_weight(" 100 ") == 100.0

def test_parse_weight_returns_none_on_junk():
    for junk in ["", "  ", "随便", "-", "abc"]:
        assert parse_weight(junk) is None

def test_parse_sets_and_reps():
    assert parse_sets("4") == 4
    assert parse_sets("") is None
    assert parse_sets("x") is None
    assert parse_reps(" 8-12 ") == "8-12"
    assert parse_reps("") == ""
```

```python
# test_plan_items.py
from datetime import date
from app.db import db
from app.models import Exercise, PlanDay, PlannedItem

def test_add_plan_item_creates_exercise_and_item(client, app):
    r = client.post("/day/2026-10-13/plan",
                    data={"exercise": "卧推", "weight": "100", "sets": "4", "reps": "8-12"})
    assert r.status_code in (200, 204)
    with app.app_context():
        assert PlanDay.query.filter_by(date=date(2026, 10, 13)).one().kind == "train"
        assert Exercise.query.filter_by(name="卧推").count() == 1
        item = PlannedItem.query.one()
        assert (item.weight_kg, item.sets, item.reps) == (100.0, 4, "8-12")

def test_add_plan_item_reuses_existing_exercise(client, app):
    client.post("/day/2026-10-13/plan", data={"exercise": "卧推", "weight": "100"})
    client.post("/day/2026-10-14/plan", data={"exercise": "卧推", "weight": "102.5"})
    with app.app_context():
        assert Exercise.query.count() == 1
        assert PlannedItem.query.count() == 2

def test_junk_weight_does_not_500(client):
    assert client.post("/day/2026-10-13/plan",
                       data={"exercise": "卧推", "weight": "随便"}).status_code in (200, 204)

def test_delete_plan_item(client, app):
    client.post("/day/2026-10-13/plan", data={"exercise": "卧推"})
    with app.app_context():
        pid = PlannedItem.query.one().id
    client.post(f"/plan-item/{pid}/delete")
    with app.app_context():
        assert PlannedItem.query.count() == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_parsing.py tests/test_plan_items.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`parsing.py`：三个纯函数（按上面断言实现；重量先去掉 `kg/公斤` 再统一逗号为小数点，失败返回 `None`）。
`days.py`：`POST /day/<date>/plan` 在 `PlanDay` 不存在时创建（`kind="train"`），`Exercise` 用 `name` 做 upsert，`position` 取当日最大值 +1；所有写操作完成后**返回该日的详情片段**（复用 Task 4 的渲染函数），这样前端可以直接替换。
`_day_detail.html`：计划区加一行输入表单（动作 / 重量 / 组数 / 次数 + 添加按钮），每条下面有删除与上移下移。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest -q`；再手动打开浏览器点一遍添加/删除
Expected: PASS，且页面上添加后立刻出现

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 计划录入与编辑"
```

---

### Task 6: 实际完成（按计划预填 + 编辑）

**Files:**
- Create: `tests/test_actual_items.py`
- Modify: `app/days.py`, `app/templates/_day_detail.html`, `app/static/app.js`

**Interfaces:**
- Consumes: Task 5 的解析函数与片段渲染
- Produces: `POST /day/<date>/actual/prefill`（把当天 `PlannedItem` 复制成 `ActualItem`，跳过已经存在同 `planned_item_id` 的条目，返回片段）；`POST /day/<date>/actual`（新增或按 `id` 更新，字段同计划 + `note`）；`POST /actual-item/<id>/delete`

- [ ] **Step 1: 写失败的测试**

```python
from datetime import date
from app.db import db
from app.models import Exercise, PlanDay, PlannedItem, ActualItem

def seed_plan(app):
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train")
        e = Exercise(name="卧推")
        db.session.add_all([d, e]); db.session.flush()
        db.session.add(PlannedItem(plan_day=d, exercise=e, weight_kg=100, sets=4,
                                   reps="8-12", position=0))
        db.session.commit()

def test_prefill_copies_plan_without_losing_link(client, app):
    seed_plan(app)
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        a = ActualItem.query.one()
        assert a.weight_kg == 100 and a.sets == 4 and a.reps == "8-12"
        assert a.planned_item_id == PlannedItem.query.one().id

def test_prefill_is_idempotent(client, app):
    seed_plan(app)
    client.post("/day/2026-10-13/actual/prefill")
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        assert ActualItem.query.count() == 1

def test_prefill_keeps_manual_edits(client, app):
    seed_plan(app)
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        aid = ActualItem.query.one().id
    client.post("/day/2026-10-13/actual",
                data={"id": str(aid), "weight": "95", "sets": "3", "reps": "10/8", "note": "没做完"})
    client.post("/day/2026-10-13/actual/prefill")
    with app.app_context():
        a = ActualItem.query.one()
        assert (a.weight_kg, a.sets, a.note) == (95.0, 3, "没做完")

def test_add_extra_actual_item_without_plan(client, app):
    client.post("/day/2026-10-13/actual", data={"exercise": "哑铃弯举", "weight": "12"})
    with app.app_context():
        a = ActualItem.query.one()
        assert a.planned_item_id is None and a.exercise.name == "哑铃弯举"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_actual_items.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`days.py`：三个路由；`prefill` 只补缺失的条目（按 `planned_item_id` 判断），不动已有条目；编辑走 `id` 更新；所有写操作返回当日片段。
`_day_detail.html`：实际区顶部一个「按计划预填」按钮（没有计划时隐藏），每条可编辑（重量 / 组数 / 次数 / 备注）可删除，底部可加额外动作。
`app.js`：表单提交统一走 `fetch` + 用返回片段替换当前展开的详情（不刷新整页）。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 实际完成预填与编辑"
```

---

### Task 7: 每日感受文本

**Files:**
- Create: `tests/test_notes.py`
- Modify: `app/days.py`, `app/templates/_day_detail.html`

**Interfaces:**
- Consumes: Task 4 片段
- Produces: `POST /day/<date>/note`（字段 `text`，按天 upsert，只保留最新一条）；片段底部渲染一个多行输入框

- [ ] **Step 1: 写失败的测试**

```python
from app.db import db
from app.models import DayNote

def test_note_upsert_keeps_one_row(client, app):
    client.post("/day/2026-10-13/note", data={"text": "今天很累"})
    client.post("/day/2026-10-13/note", data={"text": "改主意了：还行"})
    with app.app_context():
        assert DayNote.query.count() == 1
        assert DayNote.query.one().text == "改主意了：还行"

def test_note_shows_in_fragment(client):
    client.post("/day/2026-10-13/note", data={"text": "今天很累"})
    assert "今天很累" in client.get("/day/2026-10-13").get_data(as_text=True)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_notes.py -q` → FAIL

- [ ] **Step 3: 实现**：路由 + 片段里的输入框（失焦或点保存时提交，走 Task 6 的局部替换机制）。

- [ ] **Step 4: 跑测试确认通过**：`pytest -q` → PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 每日感受文本"
```

---

### Task 8: 每周身体数据

**Files:**
- Create: `app/metrics.py`, `tests/test_metrics.py`
- Modify: `app/__init__.py`, `app/templates/calendar.html`, `app/static/app.css`

**Interfaces:**
- Consumes: Task 3 的月历、Task 1 的 `BodyMetric`
- Produces: `week_start_for(d: date) -> date`（返回该日期所在周的周一）；`POST /metrics/<week_start>`（`weight` 必填、`body_fat`、`note` 选填，按周 upsert）；月历每周行右侧显示该周体重

- [ ] **Step 1: 写失败的测试**

```python
from datetime import date
from app.metrics import week_start_for
from app.db import db
from app.models import BodyMetric

def test_week_start_is_monday():
    assert week_start_for(date(2026, 10, 13)) == date(2026, 10, 12)
    assert week_start_for(date(2026, 10, 12)) == date(2026, 10, 12)

def test_metric_upsert(client, app):
    client.post("/metrics/2026-10-12", data={"weight": "70.2", "body_fat": "15"})
    client.post("/metrics/2026-10-12", data={"weight": "70.1"})
    with app.app_context():
        assert BodyMetric.query.count() == 1
        assert BodyMetric.query.one().weight_kg == 70.1

def test_bad_weight_does_not_500(client):
    assert client.post("/metrics/2026-10-12", data={"weight": "随便"}).status_code in (200, 204, 400)

def test_calendar_shows_week_weight(client, app):
    client.post("/metrics/2026-10-12", data={"weight": "70.2"})
    assert "70.2" in client.get("/?month=2026-10").get_data(as_text=True)

def test_calendar_shows_metric_for_week_spanning_months(client, app):
    # 2026-11-01 属于 2026-10-26 那一周，10 月的月历那一行要显示它
    client.post("/metrics/2026-10-26", data={"weight": "70.4"})
    assert "70.4" in client.get("/?month=2026-10").get_data(as_text=True)
```

- [ ] **Step 2: 跑测试确认失败**：`pytest tests/test_metrics.py -q` → FAIL

- [ ] **Step 3: 实现**：`week_start_for`、路由（重量解析复用 `parse_weight`，非法则原样返回页面并提示，不 500）、月历每周行加一个「本周体重」小格（可点开编辑）。

- [ ] **Step 4: 跑测试确认通过**：`pytest -q` → PASS

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 每周身体数据"
```

---

### Task 9: 循环模板（定义 + 铺到日历）

**Files:**
- Create: `app/cycle.py`, `app/templates/templates_list.html`, `tests/test_cycle.py`
- Modify: `app/__init__.py`, `app/templates/base.html`（导航加入口）, `app/static/app.css`

**Interfaces:**
- Consumes: Task 1 的 `CycleTemplate/TemplateDay/TemplateItem`、Task 3 的 `PlanDay`
- Produces: `apply_template(template_id: int, start: date) -> tuple[int, int]`（返回「新建天数, 跳过天数」，跳过任何已有 `PlanDay` 的日期，不覆盖）；路由 `GET /templates`、`POST /templates`、`POST /templates/<id>/apply`（字段 `start`）

- [ ] **Step 1: 写失败的测试**

```python
from datetime import date
from app.cycle import apply_template
from app.db import db
from app.models import (CycleTemplate, TemplateDay, TemplateItem, Exercise, PlanDay, PlannedItem)

def make_8day_template(app):
    with app.app_context():
        e = Exercise(name="卧推")
        t = CycleTemplate(name="八天循环", length_days=8)
        db.session.add_all([e, t]); db.session.flush()
        for i in range(8):
            kind = "rest" if i in (3, 7) else "train"
            td = TemplateDay(template=t, day_index=i, kind=kind,
                             title="胸 + 二头" if i == 0 else None)
            db.session.add(td)
            if i == 0:
                db.session.flush()
                db.session.add(TemplateItem(template_day=td, exercise=e, sets=4,
                                            reps="8-12", position=0))
        db.session.commit()
        return t.id

def test_apply_creates_days_and_items(client, app):
    tid = make_8day_template(app)
    with app.app_context():
        created, skipped = apply_template(tid, date(2026, 10, 12))
        assert (created, skipped) == (8, 0)
        assert PlanDay.query.count() == 8
        day1 = PlanDay.query.filter_by(date=date(2026, 10, 12)).one()
        assert day1.kind == "train" and day1.title == "胸 + 二头"
        assert PlannedItem.query.count() == 1

def test_apply_skips_existing_days_without_overwriting(client, app):
    tid = make_8day_template(app)
    with app.app_context():
        d = PlanDay(date=date(2026, 10, 13), kind="train", title="我自己排的")
        db.session.add(d); db.session.commit()
        created, skipped = apply_template(tid, date(2026, 10, 12))
        assert (created, skipped) == (7, 1)
        assert PlanDay.query.filter_by(date=date(2026, 10, 13)).one().title == "我自己排的"

def test_apply_twice_is_fully_skipped(client, app):
    tid = make_8day_template(app)
    with app.app_context():
        apply_template(tid, date(2026, 10, 12))
        assert apply_template(tid, date(2026, 10, 12)) == (0, 8)
```

- [ ] **Step 2: 跑测试确认失败**：`pytest tests/test_cycle.py -q` → FAIL

- [ ] **Step 3: 实现**：`apply_template` 按 `day_index` 顺序、从 `start` 起逐日建 `PlanDay`（`rest` 也建，`title` 原样带过来），并向 `PlannedItem` 复制 `TemplateItem`（不复制重量——重量不进模板）；跳过已有日期的天数并计数。`GET /templates` 用一个简单表单定义模板（名称、天数、每天的部位/休息与动作行），`POST /templates/<id>/apply` 接收起始日期并显示「新建 N 天，跳过 M 天」。

- [ ] **Step 4: 跑测试确认通过**：`pytest -q` → PASS；再手动铺一次真实八天循环检查页面

- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "feat: 循环模板与铺到日历"
```

---

### Task 10: 收尾自检与 README

**Files:**
- Create: `README.md`
- Modify: 按自检发现的问题就近修改

**Interfaces:**
- Consumes: 全部
- Produces: 能照着启动的 README

- [ ] **Step 1: 端到端走一遍**（浏览器里，按真实使用顺序）
  定义八天循环模板 → 铺到本月 → 点开训练日看详情 → 填写计划（含一个乱输入重量）→ 练完按计划预填实际完成并改两处 → 写一句感受 → 记一次周体重 → 翻到上个月再翻回来 → 检查「计划」和「实际完成」始终分开、没有 `None`、没有 500。
- [ ] **Step 2: 把走查发现的问题修掉**，每修一个补一条测试。
- [ ] **Step 3: 写 README**：怎么装依赖、怎么初始化数据库、怎么启动、数据库文件在哪、怎么备份（复制 `data/app.db`）、以及「第一版不做什么」的一段话。
- [ ] **Step 4: 全量测试**：`pytest -q` → PASS
- [ ] **Step 5: 提交**

```bash
git add -A && git commit -m "docs: README 与收尾自检"
```

---

## 自检记录

- **Spec 覆盖**：月历（T3）、每日详情两块分开（T4）、计划四字段（T5）、实际完成独立（T6）、感受文本（T7）、身体数据按周（T8）、循环模板（T9）、视觉方向与令牌（T2）、形态与技术（T1、Global Constraints）。
- **Review Focus 落点**：日期边界 → T3；半填记录 → T4/T6；跨月周 → T8；模板不覆盖 → T9；重量输入 → T5/T8。
- **类型一致性**：`parse_weight/parse_sets/parse_reps`（T5）被 T6、T8 复用；`month_grid`（T3）只被 T3 用；`week_start_for`（T8）只被 T8 用；片段渲染函数在 T4 定义、T5/T6/T7 复用。
- **未决**：实现者仍需按 T2 选定的视觉方向确定具体配色与排版；表单校验尺度（如重量留空）由实现者定。
