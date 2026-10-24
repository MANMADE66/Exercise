Type: task
Status: ready-for-agent

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
