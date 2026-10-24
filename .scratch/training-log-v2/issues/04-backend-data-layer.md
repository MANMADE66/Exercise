Type: task
Status: ready-for-agent
Blocked by: 02
Claimed by: pi

## Question

落地数据层（HLD §5、SRS §4）：

- 把 v1 `app/model
- ` 的 9 表搬为 SQLAlchemy，新增 users 表（共 10 表），全表加 `user_id` 外键；
- 唯一键收紧为 `(user_id, 原键)`：exercises(user_id, name)、plan_days(user_id, date)、body_metrics(user_id, week_start)、template_days(template_id, day_index)、day_notes(plan_day_id)；
- 级联约定：删 plan_day 级联 planned_items / actual_items / day_notes；删 planned_item **不**级联 actual_item，仅置空 planned_item_id；删 cycle_template 级联天/条目；
- db.py：SQLite WAL + create_all + secret.key 首启生成持久化（HLD §5.2）。

产出 `backend/app/models.py`、`db.py`、`core/config.py`。

## Answer

数据层已落地，`bash scripts/verify.sh` 全绿（16 例 pytest：health 1 + 本次新增数据层 15）。

### 产物

```
backend/app/core/config.py   # Settings：data_dir / db_path / secret_key_path / token_ttl_days / jwt_algorithm
                             # TL_ENV · TL_DATA_DIR · TL_DB_PATH · TL_SECRET · TL_TOKEN_TTL_DAYS 覆盖
backend/app/models.py        # 10 表：users + v1 九表（原表名），UserScoped mixin 统一带 user_id
backend/app/db.py            # create_db_engine / create_session_factory / init_db / get_db / load_or_create_secret_key
backend/app/main.py          # lifespan：建库(WAL)+create_all+密钥落盘 → app.state.engine / session_factory / secret_key
backend/tests/conftest.py    # tmp_path 换库的 app_settings/app/client/db_session 固件
backend/tests/test_db.py     # 10 表齐备、业务表全有 user_id、WAL、PRAGMA foreign_keys、密钥持久化/环境变量优先、默认路径
backend/tests/test_models.py # 四条复合唯一键、prefill 唯一（NULL 除外）、三种级联语义
```

旧 `backend/app/config.py` 删除（按票 04 迁到 `core/config.py`），`routers/health.py` 同步改 import。

### 约束落点（与票面对齐）

- **唯一键**：`uq_exercise_user_id_name`、`uq_plan_day_user_id_date`、`uq_body_metric_user_id_week_start`、`uq_template_day_template_id_day_index`、`day_note.plan_day_id unique`，外加 HLD §5.2 的 `uq_actual_item_plan_day_id_planned_item_id`（prefill 幂等；`planned_item_id` 为 NULL 的计划外条目不冲突，SQLite 视 NULL 互不相等）。
- **级联**：plan_day → planned_item / actual_item / day_note（ORM `all, delete-orphan` + FK `ON DELETE CASCADE`）；planned_item → actual_item **不删**，FK `ON DELETE SET NULL` + `passive_deletes=True`（历史保留，FR-6.2）；cycle_template → template_day → template_item 级联。
- **外键真的生效**：每连接 `PRAGMA foreign_keys=ON`（SQLite 默认关，不显式开则 SET NULL / CASCADE 静默失效）；`journal_mode=WAL` 由 `init_db` 设置。
- **密钥**：`TL_SECRET` > `data/secret.key`（存在且非空即复用）> 首启 `secrets.token_urlsafe(48)` 落盘；POSIX 下 best-effort `chmod 600`。

### 两处实现层面的裁定（契约不变）

1. **引擎/会话工厂挂 `app.state`，不是模块级 `engine` / `SessionLocal` 全局**。HLD §5.1 写的是「db.py: engine / SessionLocal / get_db」，这里换成 `create_db_engine` / `create_session_factory` / `get_db`（`get_db` 从 `request.app.state` 取工厂）。理由：① `scripts/export_openapi.py` 导入 `app.main` 时不得碰磁盘（模块级 engine 会在取契约时顺手建 `backend/data/app.db`）；② 测试用 `dataclasses.replace(settings, data_dir=tmp_path)` 换库即可，不必靠环境变量+模块重载；③ 没有可变模块全局，mypy strict 不用到处 `assert ... is not None`。
2. **表名沿用 v1 单数**（`exercise`/`plan_day`/…），只有新表叫 `users`（SRS §4 明确「沿用原版 9 表结构」+「users 表」）。表名不属 API 契约，保持 v1 原样能让移植参考继续对得上。

### 交给后续票的义务（服务层，不在本票范围）

- 子表 `user_id` 是 SRS FR-3.1 要求的冗余列：**写入时必须与父链一致**（计划条目取 plan_day.user_id，模板条目取 template.user_id），否则父链隔离与列过滤会分叉。
- `load_or_create_secret_key` 只提供密钥值；bcrypt/JWT 编解码仍归 `core/security.py`（未落地的票）。
- `[tool.mutmut] source_paths` 仍是 `app`：等 `parsing.py` / `days_service.py` 落地再按 HLD §12.0 收窄到那两个文件。
