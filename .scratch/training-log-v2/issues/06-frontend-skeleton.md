
Type: task
Status: ready-for-agent
Blocked by: 02
Claimed by: pi

## Question

落地前端骨架（HLD §10、SRS §6），产出可 build 的 `frontend/`：

- Vite + Vue3 + TS strict 工程（tsconfig strict + noUncheckedIndexedAccess）；
- router.ts 三路由 `/login` `/calendar` `/templates` + 全局守卫（无 token 重定向 `/login`）；
- api.ts 唯一出海口：token 注入、401 统一跳登录、错误归一；
- stores.ts：localStorage 同步 token/user。

## Comments

- 注（对齐 HLD v1.4 D13）：落地时骨架须包含 `src/api-types.ts`（票 02 生成的产物，禁手改），api.ts 从生成类型消费；SFC 一律 `<script setup lang="ts">`（HLD §10.2）。

## Answer

已落地并全绿（2026-10-24，verify.sh 一次通过：ruff → mypy → pytest 32 例 → openapi 导出 → api-types 生成 → 禁手改 diff → oxlint → oxfmt → vue-tsc → vite build）。

### 产物

- `src/stores.ts`：`session`（reactive {token, user}）+ `setSession` / `clearSession` / `isAuthenticated`，localStorage 键 `training-log.token` / `training-log.user`；读取容错（坏 JSON → null，不抛错）。`SessionUser` 是本地最小形状，留了 TODO：认证票进契约后换成 `components["schemas"][...]`（D13 不手写后端形状）。
- `src/api.ts`：唯一出海口。token 注入（`Authorization: Bearer`）；401 统一处理 = 先 `clearSession()` 再回调路由层跳登录；错误归一 = `{"detail": ...}` 字符串直取、422 Pydantic 数组拼「；」串、网络层失败归一为 `ApiError(0, ...)`。
- `src/router.ts`：`/` → `/calendar`；`/login`（meta.public）/ `/calendar` / `/templates` + catch-all；全局守卫 = 无 token 一律 `{name: "login"}`，已登录访问 /login 回 /calendar；`setOnUnauthorized` 在此注册（已在 /login 时不重复跳转——登录端点自身的 401 也走同一管道）。
- `src/views/`：LoginView（登录/注册切换表单，提交禁用 + 注明待认证票接契约）、CalendarView / TemplatesView（占位，列明后续范围）；HealthView 删除，健康检查下沉为 `src/components/BackendStatus.vue` 挂进 LoginView，骨架「走通证明」保留在公开页（日历页要 token，认证未上线前不可达）。
- `App.vue`：顶栏按会话渲染（有 token 出导航 + 用户名 + 登出；登出纯前端清会话跳 /login，FR-2.4）。

### 两处实现裁定

1. **401 跳转用回调注册而非 api.ts 直接 import router**：`api.ts → router.ts → views → api.ts` 是循环依赖；改为 api.ts 暴露 `setOnUnauthorized`，router.ts 注册（内聚导航策略）。
2. **LoginView 提交禁用而非先写着**：/auth/* 尚未进 openapi.json，手写请求形状违 D13；表单字段/校验属性就位，契约生成后只补提交函数。
