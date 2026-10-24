# 票 01 · v2 工具链精确版本清单

> 输入：`issues/01-toolchain-versions.md`（D13「依赖一律版本锁定」的落地）
> 核验时间：**2026-10-23**（PyPI JSON API / npm registry / 官方文档 / GitHub Releases）
> 核验环境：Windows 10.0.19045 · Node v24.16.0 · npm 11.13.0 · Python 3.13.12 · uv 0.12.5
> 本文件是票 02 的直接输入；标注【实测】的条目为本次在本机亲自跑出的结果，其余为【注册表】/【官方文档】。

---

## 0. 一页结论（可直接落盘）

```toml
# pyproject.toml
requires-python = ">=3.11"

dependencies = [
  "fastapi==0.161.1",
  "uvicorn[standard]==0.54.0",
  "sqlalchemy==2.1.6",
  "pydantic==2.14.1",
  "bcrypt==5.0.0",          # HLD §7 明确 bcrypt(cost=12)；见 §3.1 关于 pwdlib/argon2 的分歧说明
  "pyjwt==2.15.1",          # HLD §7 需要 JWT
]

[project.optional-dependencies]
dev = [
  "pytest==9.1.1",
  "httpx==0.28.1",          # FastAPI TestClient 依赖
  "ruff==0.17.2",
  "mypy==2.4.0",
  "mutmut==3.8.0",          # Windows 需 WSL，见 §4.2
]
```

```json
{
  "engines": { "node": "^20.19.0 || >=22.12.0" },
  "devDependencies": {
    "vue": "3.5.44",
    "vue-router": "5.4.0",
    "vite": "8.3.5",
    "@vitejs/plugin-vue": "6.0.10",
    "typescript": "5.9.3",
    "vue-tsc": "3.3.13",
    "oxlint": "1.89.0",
    "oxfmt": "0.74.0",
    "openapi-typescript": "7.13.0",
    "prettier": "3.9.10"
  }
}
```

**三个必须知道的结论（都会直接改掉 HLD §12.0 的命令/假设）：**

1. `oxfmt` **没有 `--exclude` 参数**——HLD 里 `oxfmt --check frontend/src --exclude=.vue` 会直接报错退出 1【实测】。正确写法：`oxfmt --check frontend/src '!**/*.vue'`。
2. `oxfmt@0.74.0` **已经能格式化 `.vue`**（走内置的 Prettier，无需另装 prettier）【实测】。所以「仅 .ts/.js」这条限制现在是**可选的保守选择**，不是技术必需；而且它产出的就是 Prettier 的结果，「回退 Prettier」等于没回退。
3. `oxlint` 对 `.vue` **只 lint `<script>` 块，且 `no-unused-vars` 在 SFC 内不生效**【实测】：同样的死变量写在 `.ts` 里报错、写在 `.vue` 里静默通过。`.vue` 的质量关实际是 `vue-tsc` 兜的。

TypeScript 的版本是本票唯一的真分叉：**最新稳定版是 7.0.2，但它不能用于本栈**（7.0 不发布编译器 API，`vue-tsc` / `openapi-typescript` 都跑不了）。可落地的组合经实测有两个，推荐 `typescript@5.9.3` 单版本（见 §3.2）。

---

## 1. 后端（Python）

| 包 | 当前稳定版 | 发布日 | 来源（一手） | 已知坑 / 备注 |
|---|---|---|---|---|
| fastapi | **0.161.1** | 2026-10-22 | https://pypi.org/pypi/fastapi/json | `requires_python >=3.10`；`requires_dist` 要求 `pydantic>=2.9.0`、`starlette>=0.46.0` |
| uvicorn | **0.54.0** | 2026-09-25 | https://pypi.org/pypi/uvicorn/json | `>=3.10`。`[standard]` 里的 `uvloop` 带 `sys_platform != "win32"` 条件 → **Windows 上静默不装 uvloop**，行为与 Linux 略有差异 |
| sqlalchemy | **2.1.6** | 2026-10-21 | https://pypi.org/pypi/sqlalchemy/json · https://docs.sqlalchemy.org/en/21/changelog/migration_21.html | `requires_python >=3.11`（2.1 起高于 FastAPI 的 3.10 底线）。2.1 what's-new：「Python version compatibility starts at version 3.11」；「Asyncio "greenlet" dependency no longer installs by default」→ 本项目是同步 engine，**不需要 greenlet**。changelog_21：「Removed the deprecated mypy plugin」→ **mypy 配置里不要再写 `plugins = ["sqlalchemy"]`** |
| pydantic | **2.14.1** | 2026-10-11 | https://pypi.org/pypi/pydantic/json | `>=3.10`；PyPI 上**不存在 3.x**（扫 `3.*` 无结果）→ v2 就是当前线 |
| bcrypt | **5.0.0** | 2025-09-25 | https://pypi.org/pypi/bcrypt/json | HLD §7 指定 `bcrypt(cost=12)`，故锁 5.0.0。**不要用 passlib**：pwdlib README 写明「Starting Python 3.13, `passlib` won't work anymore」，本机正是 3.13.12。直接 `import bcrypt` 即可 |
| pyjwt | **2.15.1** | 2026-09-28 | https://pypi.org/pypi/pyjwt/json | `>=3.9`。HLD §7 的 JWT 签发/校验用它（票面未列，但落锁时必须补上） |
| pytest | **9.1.1** | 2026-06-19 | https://pypi.org/pypi/pytest/json | `>=3.10`；mutmut 3.8.0 声明 `pytest>=6.2.5`，兼容 |
| ruff | **0.17.2** | 2026-10-22 | https://pypi.org/pypi/ruff/json · https://github.com/astral-sh/ruff/releases | wheel `>=3.7`，3.11/3.12/3.13 都行。**0.17.0 起默认 `target-version` 从 py310 抬到 py311** → 必须在 `pyproject.toml` 写死 `requires-python`/`target-version`，否则规则集随版本漂 |
| mypy | **2.4.0** | 2026-10-01 | https://pypi.org/pypi/mypy/json · https://mypy.readthedocs.io/en/stable/changelog.html | `>=3.10`。2.4「Mypy now uses the new native parser by default. It's based on the Ruff parser」→ 报错文案/行号与旧版有差异；`-n auto` 并行不再是实验特性 |
| mutmut | **3.8.0** | 2026-09-12 | https://pypi.org/pypi/mutmut/json · https://mutmut.readthedocs.io/en/latest/ | `>=3.10`。**POSIX-only**：文档原文「Mutmut must be run on a system with fork support. This means that if you want to run on windows, you must run inside WSL.」3.x 用 `mutmut run` / `mutmut browse`（textual TUI），配置在 `[tool.mutmut]` 且路径必须是数组（`source_paths = [...]`）；`paths_to_mutate` 已在 3.6.0 更名 |
| starlette | 1.9.0（传递依赖） | 2026-10-18 | https://pypi.org/pypi/starlette/json | 已到 1.x，`>=3.11`；FastAPI 接受 `>=0.46.0`。不必显式锁，但它是 **3.11 底线的来源之一** |
| httpx | 0.28.1 | 2024-12-06 | https://pypi.org/pypi/httpx/json | 近两年未更新，TestClient 够用；不用它跑异步 |
| pwdlib | 0.3.1（可选） | 2026-08-12 | https://pypi.org/pypi/pwdlib/json | FastAPI 官方教程现在的推荐路径（`pwdlib[argon2]`），与本项目 HLD 的 bcrypt 决定冲突，**不采用**；见 §3.1 |

---

## 2. 前端（npm）

| 包 | 当前稳定版 | 发布日 | 来源 | 已知坑 / 备注 |
|---|---|---|---|---|
| vue | **3.5.44** | 2026-10-13 | https://registry.npmjs.org/vue | dist-tags：`latest=3.5.44`，`rc=3.6.0-rc.13`（2026-10-23）→ **3.6 尚未稳定** |
| vite | **8.3.5** | 2026-10-21 | https://registry.npmjs.org/vite/latest · https://vite.dev/guide/ | `engines.node = "^20.19.0 \|\| >=22.12.0"`；文档：「Vite requires Node.js version 20.19+, 22.12+」 |
| @vitejs/plugin-vue | **6.0.10** | 2026-10-10 | https://registry.npmjs.org/@vitejs/plugin-vue/latest | peers：`vue ^3.2.25 \|\| ^3.6.0-rc.10`（3.5.44 ✓）、`vite ^5 \|\| ^6 \|\| ^7 \|\| ^8`（8.3.5 ✓）；`engines.node` 同上 |
| vue-router | **5.4.0** | 2026-10-07 | https://registry.npmjs.org/vue-router/latest · https://github.com/vuejs/router/releases | peer `vue ^3.5.34 \|\| ^4.0.0` → **要求 vue ≥ 3.5.34**（3.5.44 ✓）。5.0 带 query 归一化等 **breaking changes** → 必须锁精确版本，别写 `^5` |
| typescript | 最新稳定 **7.0.2**；**本项目锁 5.9.3** | 7.0.2：2026-07-08；5.9.3：2025-09-30 | https://registry.npmjs.org/typescript · https://devblogs.microsoft.com/typescript/announcing-typescript-7-0 | 见 §3.2。MS 公告原文：「While TypeScript 7.0 is here, **it does not ship with an API**」 |
| vue-tsc | **3.3.13** | 2026-10-10 | https://registry.npmjs.org/vue-tsc/latest · https://github.com/vuejs/language-tools/releases | peer 声明 `typescript >=5.0.0`（宽于实际）。维护者说明（language-tools#5381）：「All published packages … still require the TypeScript 6 JS API, because TS 7.0 ships no programmatic API」→ **7.x 不可用** |
| oxlint | **1.89.0** | 2026-10-19 | https://registry.npmjs.org/oxlint/latest · https://github.com/oxc-project/oxc/releases（`oxlint_v1.89.0`，prerelease=false） | `engines.node ^20.19 \|\| >=22.12`。语义化策略（https://oxc.rs/docs/guide/usage/linter/versioning.html）：**minor 升版新增规则、新增报错不算 breaking** → 必须锁精确版本 |
| oxfmt | **0.74.0** | 2026-10-19 | https://registry.npmjs.org/oxfmt/latest · GH `oxfmt_v0.74.0` | 仍 0.x。**无 `--exclude`**；`.vue` 走内置 Prettier（见 §3.3）；默认 `printWidth = 100`（Prettier 默认 80） |
| openapi-typescript | **7.13.0** | 2026-02-11 | https://registry.npmjs.org/openapi-typescript/latest · https://github.com/openapi-ts/openapi-typescript/releases | peer 硬声明 `typescript "^5.x"`；8 个月无新版。→ 决定了 TS 的选型（§3.2） |
| prettier | **3.9.10** | 2026-10-10 | https://registry.npmjs.org/prettier/latest | 仅作编辑器/`.vue` 兜底；`engines.node >=14` |

Node 底线：vite / plugin-vue / oxlint / oxfmt **四者 `engines` 完全一致** = `^20.19.0 || >=22.12.0`。本机 Node v24.16.0 满足；`verify.sh` 建议直接断言 `node -v` 主版本 ≥ 22.12 或 ≥ 20.19。

---

## 3. 三个关键风险项的结论

### 3.1 bcrypt 实现：HLD 定 bcrypt，但 FastAPI 官方已改推 Argon2

- 一手证据（FastAPI 官方文档 `docs/en/docs/tutorial/security/oauth2-jwt.md`，渲染页 https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/）：
  > 「pwdlib is a great Python package to handle password hashes. **The recommended algorithm is "Argon2"**.」`$ uv add "pwdlib[argon2]"`
  同页源码 `docs_src/security/tutorial005_py310.py` 开头即 `from pwdlib import PasswordHash`，示例哈希为 `$argon2id$v=19$m=65536,t=3,p=4$…`。
- HLD §7 写死 `bcrypt(cost=12)`，且 D1–D13「已锁定，不重新决策」。**本票不翻案**，按 HLD 锁 `bcrypt==5.0.0`；但把分歧记在这里，供 HLD 主人自行决定是否在 v1.5 改成 `pwdlib[argon2]==0.3.1` + `argon2-cffi==25.1.0`。
- 无论走哪条路，**都不能用 passlib**（Python 3.13 起失效，本机就是 3.13.12）。若将来要 pwdlib 包 bcrypt，`pwdlib[bcrypt]` 允许 `bcrypt>=4.1.2`，5.0.0 满足。

### 3.2 TypeScript：7.0.2 是「当前稳定版」，但本栈用不了

事实链（全部一手）：

1. `dist-tags.latest = 7.0.2`；typescriptlang.org 首页：「TypeScript 7.0 is now available, 7.1 is currently in beta.」
2. TS 7.0 **不带编译器 API**（MS 公告原文见 §2 表）；`vue-tsc` 仍依赖 TS 的 JS API。
3. `openapi-typescript@7.13.0` 的 peer 是 `typescript: "^5.x"`；对 TS 7 有已复现的运行时崩溃（openapi-ts#2841：`TypeError: Cannot read properties of undefined (reading 'createKeywordTypeNode')`）；放宽 peer 的 PR #2773 **关闭未合并**，#2872（仍 open）自述「The generator's Node API changes **require a major release**」。

【实测】在本机 npm 上：

```
$ npm i typescript@6.0.3 openapi-typescript@7.13.0
npm error Could not resolve dependency:
npm error peer typescript@"^5.x" from openapi-typescript@7.13.0
→ 硬失败（不是 warning），ESLint 式 `--legacy-peer-deps` 才能绕过
```

两条可实现路线（**都已在真机上跑通**，不是纸面推断）：

| 路线 | 组合 | 实测结果 | 评价 |
|---|---|---|---|
| **A（推荐）** | `typescript@5.9.3` + `vue-tsc@3.3.13` + `openapi-typescript@7.13.0` | 安装干净无 ERESOLVE；`vue-tsc --noEmit` 能抓出 `.vue` 里的类型错误（exit 2）、干净时 exit 0；`openapi-typescript` 生成 `api-types.ts` 成功且随后 `vue-tsc` 复检通过 | **单一 TS 版本**，整条链一次装好；符合 D13「不接受漂移」。代价：TS 落后两个大版本 |
| B | `typescript@6.0.3` + `vue-tsc@3.3.13`（codegen 另开目录用 TS 5，或 `overrides`） | `vue-tsc` 配 6.0.3 同样能抓 `.vue` 错误（exit 2） | 多一套版本/一层隔离，verify.sh 变复杂；收益（TS 6 语法）本项目中用不到 |

→ **锁 `typescript@5.9.3`**。这是「不是最新，但唯一能让 `openapi-typescript` + `vue-tsc` 共存且实测通过」的版本，正好对上 D13 的「不追求最新但不接受漂移」。

### 3.3 oxfmt 与 `.vue`：官方文档说「移植中」，实测已经可用

- 官方语言支持页（https://oxc.rs/docs/guide/usage/formatter/language-support.html）把格式分 **Native** 与 **Prettier-backed** 两类；`.vue` 在 **Prettier-backed** 一栏，栏头原文：「Delegated to the **bundled Prettier**. **No separate `prettier` install is required.**」Native 列表（JS/TS/JSON/CSS/GraphQL/TOML/YAML/Markdown）里没有 Vue；提示语：「These are being **actively ported to Rust**」。
- 同页两条操作警告：这些格式「require Node.js and are **only available with the `oxfmt` npm package**. The standalone binary from GitHub Releases **skips these files**」；以及「For `.vue` and `.svelte` files, embedded JS/TS (such as `<script>` blocks) is formatted by **native** formatter rather than Prettier.」
- 【实测】`oxfmt@0.74.0`，`node_modules` 里**没有 prettier**：

  ```
  $ oxfmt src/App.vue
  - import {ref} from "vue"          + import { ref } from "vue";
  - const n=ref(0)                   + const n = ref(0);
  - <div class="wrap" >{{n}}         + <div class="wrap">\n    {{ n }}
  → CHANGED by oxfmt
  ```

  即 **`.vue` 确实被格式化了**（script 块走 native、模板走内置 Prettier），且默认风格是「加分号 + printWidth 100」。

**对本项目的含义**：HLD 的「oxfmt 仅用于 .ts/.js」在 0.74.0 上是**过度保守**，但无害；真正的问题是它配套的命令行参数根本不存在：

```
$ oxfmt --check src --exclude=.vue
Error: `--exclude` is not expected in this context      # exit 1
```

0.74.0 的排除机制只有两种（`oxfmt --help` 原文）：「Exclude patterns with `!` prefix like `'!**/fixtures/*.js'`」、「`--ignore-path=PATH`（默认读 `.gitignore` 与 `.prettierignore`）」。所以 §12.0 那一行要么改成

```bash
oxfmt --check frontend/src '!**/*.vue'
```

要么改走 `--ignore-path`（配一个 `.oxfmtignore`）。**票 02 必须照这个改，否则 verify.sh 从第一条就挂。**

另外两点会影响「确定性」：
- oxfmt 默认 `printWidth = 100`（Prettier 是 80），且**不读 `package.json` 的 `prettier` 字段**（官方 unsupported-features 页）→ 若要和 Prettier 对齐，需提交 `.oxfmtrc.json` 显式写 `printWidth: 80`。
- oxc 只给 **oxlint** 出了 versioning 政策页，`…/formatter/versioning.html` 是 404 → **oxfmt 的 minor 升版可能重排全树**，锁精确版本 + 升级后跑 `git diff --stat` 是必要的（HLD 的判断成立）。

---

## 4. oxlint 对 `.vue` 的真实覆盖（比官方一句话更窄）

官方口径（https://oxc.rs/docs/guide/usage/linter）：「Framework files (`.vue`, `.svelte`, `.astro`) by linting **only their `<script>` blocks**」；兼容性矩阵脚注（https://oxc.rs/compatibility.html）：「Vue …: **No template linting yet**」（跟踪 issue oxc#15761，仍 open）。`vue` 插件**默认关闭**（plugins 表：`vue` | Default: **No**），需 `--vue-plugin` 或 `.oxlintrc.json` 里 `"plugins": ["vue"]`——注意官方警告「Setting `plugins` **overwrites the default plugin set**」。

【实测】`oxlint@1.89.0` 在本机探针上的行为：

| 探针 | 结果 |
|---|---|
| `.vue` 的 `<script setup>` 里写 `debugger;` | ✅ 报 `eslint(no-debugger)` |
| `.vue` 里写 `const unusedThing = 42`（`<script setup>` 与普通 `<script>` 都试了） | ❌ **无任何诊断** |
| 同样的 `const tsUnused = 7` 写在 `.ts` 里 | ✅ 报 `eslint(no-unused-vars)` |
| `number_of_files` 统计 | 目录扫描时 `.vue` 被计入（确实读入并解析） |
| 有 warning 时退出码 | **0**（不失败）；`--deny-warnings` 或 `--max-warnings=0` → 1 |

结论：**oxlint 能拦住 `.vue` 里的语法级/明显错误，但拦不住死代码**（SFC 内的未使用绑定被放过，合理推测是为模板使用留白，但官方没写）。因此 `.vue` 的真护栏是 `vue-tsc` strict；`verify.sh` 里 oxlint 必须加 `--deny-warnings`（或 `--max-warnings=0`），否则「有告警但全绿」会骗过 AI 自纠回路。

---

## 5. 环境底线（verify.sh 可以据此断言）

| 项 | 要求 | 依据 | 本机 |
|---|---|---|---|
| Python | **≥ 3.11**（sqlalchemy 2.1.6 / starlette 1.9.0 / pydantic-settings 2.16.1 均为 `>=3.11`）；3.12 最稳；3.13 也可 | 各包 `requires_python` | 3.13.12 ✓ |
| Node | `^20.19.0 \|\| >=22.12.0` | vite / plugin-vue / oxlint / oxfmt 的 `engines` | v24.16.0 ✓ |
| npm | ≥ 8.3（仅当使用 `npm:` alias 装 TS 时需要；本方案不需要） | 未取得一手出处，仅经验值 | 11.13.0 ✓ |
| OS | mutmut 需 `os.fork` → **Windows 需 WSL** | mutmut 文档 Requirements | Windows → 需 gate |
| 锁文件 | `uv.lock`（或 `pip-compile`）+ `package-lock.json` 入库 | HLD §12.0 | — |

---

## 6. 复核命令（票 02 落锁前请重跑一次，防 6 天漂移）

```bash
# 后端
for p in fastapi uvicorn sqlalchemy pydantic bcrypt pyjwt pytest ruff mypy mutmut httpx starlette; do
  curl -s "https://pypi.org/pypi/$p/json" | python -c "
import json,sys;d=json.load(sys.stdin);i=d['info']
print(f\"{i['name']:14s} {i['version']:10s} {i['requires_python']}\")"
done

# 前端
for p in vue vue-router vite @vitejs/plugin-vue typescript vue-tsc oxlint oxfmt openapi-typescript prettier; do
  curl -s "https://registry.npmjs.org/$p/latest" | python -c "
import json,sys;d=json.load(sys.stdin)
print(f\"{d['name']:24s} {d['version']:10s} {d.get('engines')}\")"
done
```

---

## 7. 风险与未核实项（不要当成事实用）

1. **oxfmt 的 `.vue` 输出能否跨版本稳定**：只验证了 0.74.0 的「能格式化」，没验证 0.75/0.80 改动是否重排模板。oxc 未发布 formatter 的 versioning 政策（页面 404）。→ 锁精确版本是唯一保险。
2. **`openapi-typescript@7.13.0` + `typescript@5.9.3`** 已实测跑通（生成 + 复检），但只在本文的极简 spec 上跑过，**没在 HLD 的真实 schema**（10 张表、聚合响应）上跑过；出错风险在「生成物是否可通过 `vue-tsc` strict」，票 02 首次生成时要盯。
3. **`vue-tsc@3.3.13` × `typescript@5.9.3`** 未见于 vue-tsc 的 CI 矩阵声明；peer 只写 `>=5.0.0`。实测能抓 `.vue` 类型错误，但不排除个别高级特性（如 `defineModel` 泛型）与 5.9 的边角不兼容。
4. **`pwdlib[argon2]` / `argon2-cffi` 的 Windows + Python 3.13 wheel**：未核对 PyPI 的文件列表（本方案用 bcrypt，不阻塞）。
5. **oxlint 的 `.vue` 支持起始版本**：确认了「现在支持」且相关 PR（#1814 Vue loader、#1899 双 script 标签）在 2023-12/2024-01 合并，但**没有**追到具体发版号，也没有官方「since vX」说明。
6. **npm 锁文件跨平台一致性**：`package-lock.json` 在 Windows 生成、CI 在 Linux 重放时，`optionalDependencies`（如 oxc 的平台二进制、rollup/esbuild 的 native 包）可能差异 → 建议票 02 的 verify.sh 只断言「装得上 + 命令可跑」，不比对 lock 文件的字节。此条为工程经验，非一手来源。

---

## 8. 给 HLD v1.5 的三条事实修正（不是重新决策）

> 状态：**已应用**（HLD v1.5，2026-10-23）。

1. §12.0 命令表：`oxfmt --check frontend/src --exclude=.vue` → **该参数不存在**，改 `oxfmt --check frontend/src '!**/*.vue'`（或 `--ignore-path`）。
2. §5/§12.0 关于「oxfmt 的 .vue 原生格式化仍在移植中，故仅作用于 .ts/.js」：0.74.0 下 `.vue` **已可格式化**（内置 Prettier，非 native）。保留「仅 .ts/.js」是合法选择（且回退 Prettier 与 oxfmt 输出同源），但理由应从「不支持」改为「不采用尚未 native 化的路径」。
3. §12.0 工具表：`oxlint frontend/src` 建议改 `oxlint --deny-warnings frontend/src`；并注明 `.vue` 仅 `<script>` 块、无 `no-unused-vars`，因此 `.vue` 的正确性由 `vue-tsc` 承担。另：mutmut 一行在 Windows 上需包一层 WSL 检测。

---

## 9. 附录（票 07）：`httpx` → `httpx2` 实测切换

票 02 遗留问题 3、票 07 的顺带评估项。结论：**已切换并验证**。

- **事实 1（注册表）**：`httpx2==2.16.0`，`requires-python >=3.11`，2026-10-21 上传，仓库 `github.com/pydantic/httpx2`。<https://pypi.org/pypi/httpx2/json>
- **事实 2（本地源码）**：`starlette/testclient.py` 先 `import httpx2 as httpx`，失败才回退 `import httpx` 并抛
  `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead.`
  → 装 `httpx2` 即消警，`httpx` 可以移除。
- **实测（2026-10-24，本机）**：`pyproject.toml` dev 组把 `httpx==0.28.1` 换成 `httpx2==2.16.0` → `uv lock` →
  `uv sync --frozen` → `pytest` = **59 passed，0 warning**（此前 5 warnings：1 条 Starlette 弃用 + 4 条测试自造的短密钥告警，
  后者已改用 ≥32 字节测试密钥）。`uv.lock` 变化：移除 `httpx 0.28.1`，新增 `httpx2 2.16.0` / `httpcore2 2.16.0` /
  `httpx2-jsfetch 1.0` / `truststore 0.10.5`（均为 dev 组，不进运行时）。
- **未核实项**：`httpx2` 是 2026-10 才出现的下一代线（major=2），本机只覆盖 TestClient 的同步用法；
  `httpx2` 对异步客户端 API 的破坏性变更未验证（本项目没有直接用 httpx 跑异步，D10 前端无测试套件）。
  锁精确版本 + verify 全绿是当前的保险；若后续某版本 TestClient 行为变化，回退路径是 `httpx==0.28.1`（弃用警告不影响结果）。
