# 训练记录 v2 — 地图

## Destination

训练记录 v2 落地：按 `docs/SRS.md`（v1.0）与 `docs/HLD.md`（v1.4）的契约，把单机 Flask v1 重写为 FastAPI + Vue3 多用户版；`scripts/verify.sh` 全绿，旧 `app/` 删除，README 双模式。地图结束 = 无决策残留、可整包交付出执行。

## Notes

- 契约单一来源：`docs/SRS.md` + `docs/HLD.md`；D1–D13 已锁定，执行时照做，不重新决策。
- 本 effort 覆盖执行（Notes 覆盖默认「只产决策」）：HLD 已裁定几乎全部决策，本图只解决残余的工具链决策（票 01/02/03），之后转交执行。
- 每会话先读：`docs/agents/issue-tracker.md`、`docs/agents/domain.md`、`AGENTS.md`。
- 硬不变量（票 03 落进 AGENTS.md）：隔离不越 service 层；parsing 不抛错；api-types.ts 禁手改；verify.sh 是唯一质量入口。

## Decisions so far

<!-- 空：尚未解决任何票 -->

- 票 01（工具链版本）：全部锁定 —— 后端 fastapi 0.161.1 / uvicorn 0.54.0 / sqlalchemy 2.1.6 / pydantic 2.14.1 / bcrypt 5.0.0 / pyjwt 2.15.1 / pytest 9.1.1 / ruff 0.17.2 / mypy 2.4.0 / mutmut 3.8.0；前端 vue 3.5.44 / vue-router 5.4.0 / vite 8.3.5 / plugin-vue 6.0.10 / typescript **5.9.3**（latest 7.0.2 无编译器 API，vue-tsc+openapi-typescript 跑不了）/ vue-tsc 3.3.13 / oxlint 1.89.0 / oxfmt 0.74.0 / openapi-typescript 7.13.0；Python ≥3.11、Node ^20.19||>=22.12。三处硬发现：oxfmt **无 `--exclude`**（改用 `'!**/*.vue'`）、oxfmt 0.74.0 其实能格式化 .vue（内置 Prettier）、oxlint 对 .vue 无 no-unused-vars 且默认告警不失败（需 `--deny-warnings`）。清单与实测证据：[`.scratch/training-log-v2/research/01-toolchain-versions.md`](research/01-toolchain-versions.md)
- 票 02（走通骨架，已确认）：`backend/`（uv.lock + FastAPI `/health` + TestClient）与 `frontend/`（package-lock + Vite/Vue3/TS strict，单路由消费生成类型）可跑；`bash scripts/verify.sh` 全绿（ruff→mypy→pytest→openapi 导出→api-types 生成→禁手改 diff→oxlint→oxfmt→vue-tsc→vite build）；禁手改 = 重新生成后 `git diff --exit-code`，已实测能拦住 staged 手改。新踩到：pytest 需 `pythonpath=["."]`、oxfmt 还要排除生成物 `'!src/api-types.ts'`、Starlette 1.9 弃用 httpx（警告不失败）、mutmut 默认跳过且 Windows 需 WSL。确认后已提交（`d25bd9c`），禁手改关随生成物入库实际生效。细节：[`issues/02-walking-skeleton.md`](issues/02-walking-skeleton.md)
- 票 03（AGENTS.md）：定稿五节 —— verify 唯一入口与真实关卡顺序、五条硬不变量（隔离在 service 层 / parsing 不抛错 / api-types.ts 禁手改 / openapi.json 生成物 / verify.sh 唯一入口）、backend+frontend+docs 目录职责、契约变更闭环、dev 双端口命令；`## Agent skills` 块保留。版本与工具链理由只留指针（HLD §12.0/§12.1、票 01 research）。[`issues/03-agents-md.md`](issues/03-agents-md.md)
- 票 04（后端数据层，已落地）：10 表 ORM = users + v1 九表（表名沿用 v1 单数，仅新表叫 `users`）；全业务表带 `user_id`（`UserScoped` mixin）；唯一键收紧为 (user_id, 原键) 四条 + `template_day(template_id, day_index)` + `day_note(plan_day_id)` + `actual_item(plan_day_id, planned_item_id)`（prefill 幂等，NULL 不冲突）；级联 = plan_day→三子表全删、planned_item→actual_item 仅 `ON DELETE SET NULL`、cycle_template→天/条目。两处实现裁定：① 引擎/会话工厂挂 `app.state`（`db.py` 提供 create_db_engine/create_session_factory/get_db），HLD §5.1 的模块级 `engine/SessionLocal` 会让 openapi 导出顺手建库、并逼测试用环境变量+模块重载；② SQLite 每连接 `PRAGMA foreign_keys=ON`（默认关，不开则 SET NULL/CASCADE 静默失效）+ `journal_mode=WAL`；密钥 `TL_SECRET` > `data/secret.key` > 首启生成。测试固件改为 `dataclasses.replace(settings, data_dir=tmp_path)` 换库。verify 全绿（16 例）。[`issues/04-backend-data-layer.md`](issues/04-backend-data-layer.md)
- 票 06（前端骨架，已落地）：三路由 + 全局守卫（无 token → /login，已登录访问 /login 回 /calendar）；api.ts 唯一出海口 = token 注入 + 401 清会话跳登录 + 错误归一（detail 字符串/422 数组/网络失败 status 0）；stores.ts = reactive 会话 + localStorage 容错同步。两处裁定：① 401 跳转用 `setOnUnauthorized` 回调注册（避免 api.ts↔router.ts 循环依赖）；② LoginView 提交禁用——/auth/* 未进契约，不手写请求形状（D13），健康检查下沉为 BackendStatus 组件留在公开页。verify 全绿。[`issues/06-frontend-skeleton.md`](issues/06-frontend-skeleton.md)
- 票 05（parsing 移植，已落地）：`backend/app/parsing.py` 与 v1 `app/parsing.py` 语义 1:1（kg/公斤/千克 不区分大小写剥除、逗号当小数点、`>0` 才有效、组数 `>0` 整数、reps 仅 trim、无效回 `None`/空串绝不抛错）；唯一实现差异是把 v1 `parse_sets` 的 `str(raw)` 去掉（`raw` 已收窄为 `str`，行为等价）。测试 13 例搬自 v1 并补单位/零负/自由文本/「永不抛错」参数化。未加 `math.isfinite` 守卫（v1 也接受 `inf`），保持移植忠实度。[`issues/05-parsing-port.md`](issues/05-parsing-port.md)

## Not yet specified

- 执行层里程碑：认证、隔离机制、calendar/days/templates/metrics 各业务域、类型契约闭环（openapi.json→api-types.ts）、后端测试矩阵、前端组件交互平移、prod 静态托管、验收收尾 —— HLD 已逐项裁定，是执行不是决策；待前沿（票 02/04/06）推进后毕业成执行票，现在不预切。
- 质量关残余细节：oxfmt 对 .vue 的回退阈值（「git diff --stat 突增即回退」的具体判据）待定；api-types.ts 禁手改已定稿为「重新生成 + `git diff --exit-code`」，空窗方案已确认（未入库只警告）。
- 验收判据：手动冒烟清单的确切步骤、删除旧 `app/` 的触发时机 —— 待全链路走通后精确。

## Out of scope

- 智能建议 / 反馈推荐（SRS 明确推迟）
- UI 重设计（本次仅平移 v1 交互，D9）
- 移动端适配、云部署、HTTPS / 公网暴露（SRS §2.4）
- 忘记密码 / 邮箱找回、第三方登录（SRS §1.2）
- 旧数据迁移（D8：空库起步，data/app.db 弃置）
