Type: task
Status: ready-for-agent
Claimed by: pi

## Question

落地认证与会话（HLD §7、§9.1，SRS §1.2 / §5）：

- `core/security.py`：bcrypt（cost=12）哈希与校验、JWT HS256 编解码（7 天有效期）
- `core/deps.py`：`get_current_user`（Bearer → users 查询 → 当前用户；无 token / 坏 token / 过期一律 401）
- `routers/auth.py`：`POST /auth/register` · `POST /auth/login`（登出为纯前端清会话，FR-2.4）
- `schemas.py` 补认证契约 → 重跑 verify 让 `docs/openapi.json` 与 `frontend/src/api-types.ts` 机器生成
- 前端 `LoginView` 解除提交禁用，改用生成类型消费（D13 不手写形状）

隔离机制不在本票：本票只交付「能拿到当前用户」的地基。

## Comments

- 上游已定：SECRET 取值优先级 `TL_SECRET` > `data/secret.key` > 首启生成（票 04 已落地于 `db.py`）；`users` 表已在票 04 建好。
- 测试按 HLD §12.0 覆盖矩阵 auth 行：注册成功 / 重复 409 / 用户名长度 / 密码 ≥6；登录成功 / 密码错误统一文案；无 token 401 / 坏 token 401。
- 硬不变量：前端类型只从 `api-types.ts` 取；密钥与哈希细节不得泄漏进 routers（service 层之外不做业务判断）。
- 顺带评估（不阻塞本票）：Starlette 1.9 对 httpx 0.28 的弃用警告是否要换 httpx2（票 02 遗留问题 3）。

## Answer

已落地并全绿（2026-10-24，`bash scripts/verify.sh` 一次通过：ruff → ruff format → mypy strict → pytest **59 例** → openapi 导出 → api-types 生成 → 禁手改 diff → oxlint → oxfmt → vue-tsc → vite build；提交 `c333e4f`）。另跑了一次真 uvicorn（临时 `TL_DATA_DIR`）冒烟：`/health` → 注册（用户名 `"  smoke  "` 落库为 `smoke`）→ 重复注册 409「用户名已被占用」→ 错密码 401「用户名或密码不对」，`secret.key` 首启生成 64 字符。

### 产物

- `app/core/security.py`：`hash_password` / `verify_password`（bcrypt cost=12）、`create_access_token` / `decode_access_token`（HS256，`{sub: str(user_id), iat, exp}`，7 天）。解码失败一律 `None`（坏 token / 过期 / 缺声明 / 签名不符同一出口），`verify_password` 对损坏哈希也只返回 `False`。
- `app/core/deps.py`：`get_token_policy`（从 `app.state.secret_key` + settings 组装 `TokenPolicy`）与 `get_current_user`（`HTTPBearer(auto_error=False)` → 解码 → `db.get(User)`），三个失败分支收进 `_unauthorized()`，一律 401 + `未登录或登录已过期` + `WWW-Authenticate: Bearer`。另导出 `CurrentUser` / `TokenPolicyDep` 两个 `Annotated` 别名供票 08 直接用。
- `app/services/auth_service.py`（票面未列，为满足硬不变量 1 而新增）：`register_user`（唯一性预检 + bcrypt 落库 + 签发；并发撞唯一键时 `IntegrityError` → 回滚 → 同一 409 语义）与 `authenticate_user`（用户名不存在/密码不对合并成一个 `InvalidCredentialsError`）。领域异常 = `UsernameTakenError` / `InvalidCredentialsError`。
- `app/routers/auth.py`：`POST /auth/register`、`POST /auth/login`，只做「领域异常 → 409/401」映射，不碰 bcrypt、密钥、SQL。
- `app/schemas.py`：`Credentials`（注册与登录共用）、`UserPublic`（只有 username）、`TokenResponse`（{token, user}）；422 中文文案用 `PydanticCustomError`（`ValueError` 会带上 `Value error, ` 前缀，不能直接展示给用户）。
- 契约闭环：`docs/openapi.json` 与 `frontend/src/api-types.ts` 均由 verify 机器重生成（openapi 增 4 个 schema + 2 条路径，api-types 增 169 行）。
- 前端：`api.ts` 增 `register` / `login`（类型全部 `components["schemas"][...]`）；`stores.ts` 的 `SessionUser` 改为 `components["schemas"]["UserPublic"]`（删掉手写类型与 TODO）；`LoginView` 解除提交禁用——提交中禁用 + 错误行 + 成功后 `setSession` → `router.replace({name:"calendar"})`。

### 四处实现裁定

1. **密码 72 字节上限拦成 422，不静默截断**：bcrypt 5.x 对 >72 字节密码直接抛 `ValueError`，而 HLD/SRS 只规定 ≥6。截断会让超限部分完全无效（静默降级），故 `schemas` 用 `password_too_long()` 判字节数并给中文提示「密码最长 72 字节（约 72 个英文字符）」。`security.hash_password` 保留同样的守卫，防止绕过 schema 的调用路径。
2. **`Credentials` 注册/登录共用一个模型**：字段与校验完全一致，前端也只消费一种形状（D13 少一个类型、少一处漂移）。副作用：登录时用户名 <3 字符回 422 而非 401；FR-2.5 说的是「密码错误 vs 用户名不存在」不可区分，与此无关。
3. **`get_token_policy` 做成依赖而不是把 `settings` 塞进 service**：service 只收 `TokenPolicy`，不接触 `Request`/`app.state`；router 用 `TokenPolicyDep` 取。
4. **测试用探针端点验证鉴权链**：业务端点尚未落地，`tests/test_auth.py` 用 `app.router.add_api_route(..., include_in_schema=False)` 挂 `/_test/whoami`（受 `get_current_user` 保护），从而把「无 token / 坏 token / 过期 / 他人密钥签发 / user 已删」五种 401 都压到真实 HTTP 路径上，而不是直接调依赖函数。

### 顺带评估：`httpx` → `httpx2`（票 02 遗留问题 3）→ **已切换**

`starlette/testclient.py` 现在优先 `import httpx2`，回退 `httpx` 时抛 `StarletteDeprecationWarning`。`httpx2==2.16.0`（pydantic 组织，requires-python ≥3.11，2026-10-21 上传）装上后 **59 例全过、0 warning**（原 5 条 = 1 条 Starlette 弃用 + 4 条测试自造短密钥；后者已改用 ≥32 字节测试密钥消掉）。故 dev 组 `httpx==0.28.1` → `httpx2==2.16.0`，`uv.lock` 同步（新增 dev-only `httpcore2` / `httpx2-jsfetch` / `truststore`），HLD §12.1 与 research §9 附录同步更新。回退路径：改回 `httpx==0.28.1`（弃用警告不影响结果）。

### 未做 / 留给后续

- 隔离（user_id 收窄、父链 404、A/B 助手）→ 票 08；本票只交付「拿到当前用户」的地基（`CurrentUser` 已就位）。
- 登录与不存在的用户名之间的时序差异（前者不跑 bcrypt）未抹平：内网私密应用、SRS 只要求统一文案，暂不引入 dummy hash。
- `TL_SECRET` 若被人为设成 <32 字节，PyJWT 会发 `InsecureKeyLengthWarning`（不失败）；默认生成的密钥是 64 字符，不受影响。
