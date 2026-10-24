Type: task
Status: ready-for-agent
Blocked by: 02
Claimed by: pi

## Question

补全 `AGENTS.md` 的操作性内容（现只有 setup 写入的 `## Agent skills` 块），产出定稿：

- verify 命令：照抄票 02 定稿后的 `scripts/verify.sh` 入口；
- 目录结构：`backend/` + `frontend/` + `docs/` 的职责；
- 硬不变量：隔离不越 service 层、parsing 不抛错、api-types.ts 禁手改、verify.sh 是唯一质量入口。

## Answer

`AGENTS.md` 已定稿（保留 setup 写入的 `## Agent skills` 块原样），新增五节：

1. **质量关**：唯一入口 `bash scripts/verify.sh`，按其真实顺序列出关卡（ruff check → ruff format --check → mypy strict → pytest → 导出 openapi.json → 生成 api-types.ts → 禁手改检查 → oxlint --deny-warnings → oxfmt → vue-tsc → vite build）；mutmut 用 `RUN_MUTMUT=1` 启用、Windows 须 WSL；锁文件入库、升级走票 01 的复核流程。
2. **硬不变量**：① 隔离在 service 层（routers 只做参数/鉴权/错误码，user_id 收窄、归属校验 404、事务都在 services）；② parsing 不抛错（无效 → None/空串）；③ api-types.ts 禁手改（只改 Pydantic，verify 用 regenerate + git diff 拦）；④ openapi.json 是生成物；⑤ verify.sh 是唯一入口。票面的四条均覆盖，另把「openapi.json 也是生成物」补成第五条。
3. **目录职责**：`backend/app/`（main/routers/services/models/schemas/core/parsing）、`backend/tests/`、`frontend/src/`（api.ts 唯一出海口、api-types.ts 生成物）、`docs/`、`scripts/`；旧 `app/`+`tests/`+`run.py` 标注为 v1 参考、v2 代码只写 `backend/`+`frontend/`。
4. **契约变更闭环**：改 schemas.py → 跑 verify → 生成物重新生成 → vue-tsc 指出受影响调用点 → 一并提交。
5. **本地运行**：dev 双端口命令与首次安装命令。

未重复 HLD 的版本清单与工具链理由，只留指针（HLD §12.0/§12.1、票 01 research），避免两处漂移。
