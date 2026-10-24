Type: task
Status: ready-for-agent
Blocked by: 07

## Question

落地归属隔离与错误码归一（HLD §8、§9.2，SRS §2.2）：

- service 层所有查询用当前 `user_id` 收窄；按 id 取资源必须经父链校验归属（如 `template_item → template_day → template`）
- 不属于当前用户的一切读写删 → 404，与「不存在」同码同文案（同一处 helper 产出，禁止各处手写）
- `conftest.py` 补隔离测试助手：用户 A/B + 各自计划日 / 模板 / 体重的工厂，供后续业务域票直接复用

## Comments

- 本票不新增业务域路由；业务域票（calendar / days / templates / metrics）在此之后各自接上，届时只需调用隔离 helper。
- 隔离测试必须先于业务域测试存在：HLD §12.0 把「隔离」列为安全关键项（B 对 A 的 day/calendar/templates 读写删均 404；列表互相不可见；exercise 命名空间互不可见）。
- 硬不变量：判断只允许发生在 service 层，routers 不得自行拼 `user_id` 过滤条件。
