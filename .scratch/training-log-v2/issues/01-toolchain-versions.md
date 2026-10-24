Type: research
Status: ready-for-agent

## Question

锁定 v2 工具链的精确版本，供票 02 的 `scripts/verify.sh` 与 `pyproject.toml` / `package.json` 落锁（D13「依赖一律版本锁定」的落地）。查明并给出可落盘的版本清单：

- 后端：FastAPI、Uvicorn、SQLAlchemy、Pydantic、bcrypt 实现、pytest、ruff、mypy、mutmut 的当前稳定版本；
- 前端：Vue3、Vite、vue-router、TypeScript、vue-tsc、oxlint、oxfmt、openapi-typescript 的当前稳定版本；
- 关键风险：oxlint 对 `.vue` SFC 的支持状态；oxfmt 对 `.vue` 的原生格式化是否已稳定（HLD 标注「仍在移植中」）—— 若不支持，锁哪个版本、`.vue` 由谁格式化（HLD 预案是回退 Prettier）。

输出：一份版本清单（含已知坑备注），作为票 02 的直接输入。

## Comments
- 注（对齐 HLD v1.4 §12.0/D13）：oxfmt 对 .vue 的风险结论已核实 —— 官方语言支持页标注 .vue 原生格式化仍在移植、未稳定，预案维持回退 Prettier；oxlint 对 .vue SFC 的支持已确认可用。本票范围相应收敛（.vue 风险项已答），剩余工作 = 锁定精确版本清单。

## Answer

完整清单（含来源、复核命令与未核实项）：[`research/01-toolchain-versions.md`](../research/01-toolchain-versions.md)。核验日 2026-10-23，标注【实测】的条目在本机亲自跑过。

**落锁版本**

- 后端：`fastapi==0.161.1` · `uvicorn[standard]==0.54.0` · `sqlalchemy==2.1.6` · `pydantic==2.14.1` · `bcrypt==5.0.0` · `pyjwt==2.15.1`（HLD §7 的 JWT，票面漏列）· `pytest==9.1.1` · `ruff==0.17.2` · `mypy==2.4.0` · `mutmut==3.8.0`；`httpx==0.28.1`（TestClient）。
- 前端：`vue==3.5.44` · `vue-router==5.4.0` · `vite==8.3.5` · `@vitejs/plugin-vue==6.0.10` · `typescript==5.9.3` · `vue-tsc==3.3.13` · `oxlint==1.89.0` · `oxfmt==0.74.0` · `openapi-typescript==7.13.0` · `prettier==3.9.10`（仅编辑器/兜底）。
- 环境：Python ≥ 3.11（sqlalchemy 2.1 / starlette 1.9 抬高底线）；Node `^20.19.0 || >=22.12.0`。

**四个会改掉票 02 写法的实测发现**

1. `oxfmt` **没有 `--exclude`**（`Error: --exclude is not expected in this context`，exit 1）。HLD §12.0 的 `oxfmt --check frontend/src --exclude=.vue` 直接挂 → 改 `oxfmt --check frontend/src '!**/*.vue'`（或 `--ignore-path`）。
2. `oxfmt@0.74.0` **已经能格式化 `.vue`**（内置 Prettier，无需另装；实测重排了模板与 script）。「仅 .ts/.js」是保守选择而非技术必需，且其输出与 Prettier 同源 —— 「回退 Prettier」等于没回退。
3. `oxlint` 对 `.vue` 只覆盖 `<script>` 块，且 **`no-unused-vars` 在 SFC 内不报**（同代码在 `.ts` 报、`.vue` 静默）；warning 默认**不**导致非零退出 → verify.sh 必须加 `--deny-warnings`。`.vue` 的真护栏是 `vue-tsc`。
4. TS 的 latest 是 **7.0.2**，但 7.0 不带编译器 API，`vue-tsc` 与 `openapi-typescript`（peer `^5.x`）都跑不了：`npm i typescript@6.0.3 openapi-typescript@7.13.0` **硬失败**。实测唯一干净组合是 `typescript@5.9.3`（安装无冲突、vue-tsc 抓得住 `.vue` 类型错误、codegen→复检全通）→ 锁 5.9.3，刻意偏离 latest。

**留给 HLD v1.5 的事实修正（非重新决策）**：① §12.0 的 oxfmt 命令参数；② 「.vue 仍在移植中故排除」的理由应改为「不采用未 native 化的路径」；③ oxlint 需 `--deny-warnings` 且 `.vue` 的正确性归于 `vue-tsc`；mutmut 在 Windows 需 WSL 门控。

- 结案（2026-10-23）：已落到 `docs/HLD.md` v1.5 —— 新增 §12.1 版本锁定清单；§12.0 命令表三条已改（oxfmt `'!**/*.vue'`、oxlint `--deny-warnings`、mutmut `[tool.mutmut] source_paths` + WSL 门控）；§2 技术选型表与 oxfmt 风险管理段已按实测改写。bcrypt 维持不变，仅在 §2 加注 FastAPI 已改推 `pwdlib[argon2]`。
