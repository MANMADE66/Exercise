# SRS — 训练记录 v2（前后端分离 + 多用户）

软件需求规格说明书
版本 1.0 · 依据 2026-10 访谈确定 · 决策来源见文末设计树索引

---

## 1. 引言

### 1.1 目的
本文档定义「训练记录」v2 的完整需求：将现有单机单人 Flask 服务端渲染应用，重构为**前后端分离、支持多用户登录**的完整 Web 产品。

### 1.2 范围
- **包含**：注册/登录/登出、月历视图、每日计划管理、实际完成记录、感受笔记、循环模板、周体重记录；全新的 FastAPI 后端 API 与 Vue3 SPA 前端；用户数据隔离；后端自动化测试。
- **不包含**：智能建议/反馈推荐功能（README「下一步」条目，明确推迟）；UI 新设计（用户后续自行设计，本次仅平移现有交互）；移动端专门适配；云部署；忘记密码/邮箱找回；第三方登录。

### 1.3 术语
| 术语 | 含义 |
|---|---|
| PlanDay | 某个日期的计划日（含 kind: train/rest、title） |
| PlannedItem | 计划条目：动作、重量 kg、组数、次数（自由文本）、顺序 |
| ActualItem | 实际条目：同计划条目字段 + 备注，可关联 planned_item |
| DayNote | 当日感受文本（1 天 1 条） |
| BodyMetric | 周体重记录（以周一为唯一键，1 周 1 条，可含体脂率与备注） |
| CycleTemplate | 循环模板（N 天骨架），TemplateDay / TemplateItem 为其日/条目 |
| 聚合读 | 一次请求返回某日期的全部计划+实际+感受数据 |

### 1.4 参考文档
- 原设计：`docs/superpowers/specs/2026-10-13-training-log-design.md`
- 原计划：`docs/superpowers/plans/2026-10-13-training-log-v1.md`
- 原实现：`app/`（将被移除或归档，功能语义以本 SRS 为准）

---

## 2. 总体描述

### 2.1 产品定位
小团队（约数人）使用的私密训练记录本。每个成员在**不同设备**上通过浏览器登录，记录各自独立的训练计划与实际完成情况。系统**不替用户规划训练**，只做忠实记录。

### 2.2 用户角色
| 角色 | 权限 |
|---|---|
| 未登录访客 | 仅可访问登录页与注册页 |
| 登录用户 | 对**自己名下**的全部数据做任意增删改查；无法读写他人任何数据 |

无管理员角色（用户名即身份，开放注册，团队内部信任）。

### 2.3 运行环境
- 后端：Python 3.11+，FastAPI + Uvicorn，单进程即可；SQLite 单文件库。
- 前端：现代桌面浏览器（Chrome/Edge/Firefox），Vue3 构建的静态文件。
- 网络：局域网内多设备访问 `http://<主机IP>:8000`；开发期前端 5173 / 后端 8000。

### 2.4 约束与假设
- 团队成员互相信任，注册不做审核；token 泄露是最大安全面，故有效期 7 天。
- SQLite 单写者：并发极低（几人错峰记录），不做写冲突优化。
- 不需要 HTTPS（内网明文可接受）；若未来暴露公网需补 TLS 与限流，本版不做。

---

## 3. 功能需求

优先级约定：P0 = 本版必须；P1 = 本版尽力；P2 = 以后再说。

### FR-1 注册（P0）
- FR-1.1 注册仅需用户名 + 密码。用户名 3–20 字符，全局唯一，去除首尾空白；密码最少 6 位。
- FR-1.2 密码以 bcrypt（或等价强哈希）存储，任何接口不得返回密码字段。
- FR-1.3 用户名已存在 / 任何字段不合规时，返回明确的中文错误信息（区分「用户名已被占用」「用户名太短」等）。
- FR-1.4 注册成功即视为登录成功，直接返回 token。

### FR-2 登录 / 会话 / 登出（P0）
- FR-2.1 登录凭据为用户名 + 密码；成功返回 JWT（含 user_id、过期时间）。
- FR-2.2 有效期 7 天；不做 refresh token；过期后 API 返回 401，前端跳转登录页重登。
- FR-2.3 除注册/登录外，所有 API 必须校验 `Authorization: Bearer <token>`，无效或缺失一律 401。
- FR-2.4 登出为纯前端行为：清除本地存储的 token 并跳转登录页（无服务端会话表）。
- FR-2.5 密码错误时返回统一模糊错误「用户名或密码不对」，不区分二者。

### FR-3 用户数据隔离（P0，最高安全优先级）
- FR-3.1 所有业务表（plan_days、planned_items、actual_items、day_notes、body_metrics、cycle_templates、template_days、template_items、exercises）增加 `user_id` 外键，唯一键均改为 (user_id, 原键) 组合（如 (user_id, date)）。
- FR-3.2 任何按 id 定位的资源（条目、模板、笔记……）必须先校验归属：id 存在但不属于当前用户时，一律返回 **404**（与「不存在」不可区分，防枚举）。
- FR-3.3 列表/查询接口只返回当前用户的数据，禁止任何跨用户聚合。
- FR-3.4 动作库（Exercise）按用户独立：A 用户创建的「深蹲」对 B 用户不可见、不可复用。

### FR-4 月历视图（P0）
- FR-4.1 `GET /calendar?month=YYYY-MM`：返回该月整周网格（周一为一周起点，首尾以空格补齐）、当月每个 PlanDay 的 kind/title、已记录（存在实际条目）的日期集合、每周边界日期，供前端渲染月历。
- FR-4.2 month 参数格式非法或缺省时回退到当月（服务端不报错）。
- FR-4.3 月历仅展示概要；日详情数据由 FR-5 的聚合接口提供。
- FR-4.4 翻月由前端计算 prev/next 或携带 month 重新请求，不增加专有端点。

### FR-5 日详情聚合（P0）
- FR-5.1 `GET /days/{date}`：返回当天聚合数据——PlanDay（kind/title）、全部 PlannedItem（按 position 排序）、全部 ActualItem（按 position 排序）、DayNote 文本。日期非法返回 400。
- FR-5.2 读取不隐式创建 PlanDay：无记录的日期返回空结构，不落库。

### FR-6 计划管理（P0）
- FR-6.1 添加计划条目 `POST /days/{date}/plan-items`：动作名（自动建入本人动作库）、重量（容错解析）、组数、次数（自由文本）；新条目置于末位。
- FR-6.2 删除计划条目 `DELETE /plan-items/{id}`：级联语义沿用原版——关联的实际条目不受删除影响（其 planned_item_id 置空保留记录）。
- FR-6.3 上下移动 `POST /plan-items/{id}/move`：direction=up/down，交换后重排 position；已在边界时静默成功。
- FR-6.4 重量解析规则：剥离 kg/公斤/千克 单位，逗号作小数点，>0 才有效；组数解析为 >0 整数；两者无效时存 NULL；次数保留原字符串（trim）。解析失败**不报错**。
- FR-6.5 以上写操作均返回 FR-5.1 的整天聚合，前端整体替换状态。

### FR-7 实际完成记录（P0）
- FR-7.1 按计划预填 `POST /days/{date}/actual/prefill`：为每个尚无对应实际条目的计划条目复制一条 ActualItem（含 planned_item_id 关联）；重复调用幂等，不产生重复。
- FR-7.2 行内更新 `PATCH /actual-items/{id}`：逐字段更新重量/组数/次数/备注；字段缺省不清空，传空字符串含义为该字段置 NULL/空（与原文版语义一致）。
- FR-7.3 新增计划外条目 `POST /days/{date}/actual-items`：结构与计划条目一致，另可带备注。
- FR-7.4 删除实际条目 `DELETE /actual-items/{id}`：直接删除。
- FR-7.5 写操作返回整天聚合（同 FR-6.5）。

### FR-8 感受笔记（P0）
- FR-8.1 `PUT /days/{date}/note`：整段保存感受文本；为空字符串时仍保存（清空原文）。
- FR-8.2 保存时若该日无 PlanDay 且文本非空，才隐式创建 PlanDay；文本为空且无 PlanDay 时不创建任何数据。
- FR-8.3 返回整天聚合。

### FR-9 循环模板（P0）
- FR-9.1 `GET /templates`：列出当前用户的全部模板及逐日骨架。
- FR-9.2 创建模板 `POST /templates`：名称（缺省「未命名循环」）、天数 1–12（非法或缺省回退 8，超出静默截断为 12，与原版一致）；逐日 kind（train/rest）、标题、条目（每行一个动作名，忽略空行）。模板不含重量。
- FR-9.3 应用模板 `POST /templates/{id}/apply?start=YYYY-MM-DD`（或 body 传 start）：从起始日按 day_index 逐日铺排；**已有 PlanDay 的日期跳过，绝不覆盖**；返回新建数与跳过数供前端提示。
- FR-9.4 删除模板 `DELETE /templates/{id}`（原版隐含能力，正式开放）。
- FR-9.5 模板资源同样受 FR-3 隔离约束。

### FR-10 周体重（P0）
- FR-10.1 `PUT /metrics/{week_start}`：以周一日期为键 upsert 本人该周的体重（必填、合法否则 422/400）、体脂率（可选）、备注（可选）。
- FR-10.2 体重非法时不落库，返回可展示的错误（前端在周体重列提示）。

---

## 4. 数据模型

沿用原版 9 表结构，全部增加 `user_id`，唯一键调整如下：

| 表 | 调整后的唯一约束 |
|---|---|
| users | username 唯一 |
| exercises | (user_id, name) 唯一 |
| plan_days | (user_id, date) 唯一 |
| body_metrics | (user_id, week_start) 唯一 |
| day_notes | plan_day_id 唯一（随 plan_day 已隔离） |
| 其余（planned_items / actual_items / cycle_templates / template_days / template_items） | 无独立唯一键，经父链隔离 |

- users 表：id、username、password_hash、created_at。
- 时间戳统一 UTC 存储，展示层不涉及时区换算（日期字段用原生 Date）。
- 旧 `data/app.db` 不迁移：新库置于 `backend/data/app.db`，首启自动建空库。

---

## 5. API 设计（动作式 + 聚合读）

统一约定：JSON 进出；鉴权 401；归属校验失败 404；格式错误 400/422；每个日级写操作响应体为该日的聚合结构（同 FR-5.1）。

```
POST /auth/register          {username, password} → {token, user}
POST /auth/login             {username, password} → {token, user}
GET  /calendar?month=        → 月历聚合（FR-4）
GET  /days/{date}            → 日聚合（FR-5）
POST /days/{date}/plan-items
DELETE /plan-items/{id}
POST  /plan-items/{id}/move  {direction}
POST /days/{date}/actual/prefill
POST  /days/{date}/actual-items
PATCH  /actual-items/{id}
DELETE /actual-items/{id}
PUT  /days/{date}/note       {text}
GET    /templates
POST   /templates            {name, length_days, days:[{kind,title,items:[{exercise,...}]}]}
DELETE /templates/{id}
POST   /templates/{id}/apply {start}
PUT  /metrics/{week_start}   {weight, body_fat?, note?}
```

开发期 CORS：允许 `http://localhost:5173`。

---

## 6. 前端设计

- 技术栈：Vite + Vue3 + vue-router；构建产物为纯静态文件，由 FastAPI 托管于 `/`。
- 路由：`/login`（登录/注册切换）、`/calendar`（月历主页，含周体重列）、`/templates`（模板管理）。
- 路由守卫：无有效 token 一律重定向 `/login`；登录后 `local storage` 保存 token，API 客户端统一注入 Authorization 头，401 时清 token 回登录页。
- 交互平移清单（本次**不重新设计**，后续由用户改版）：
  - 月历格点开就地展开日详情 tr，再点收起；
  - 详情内所有表单局部提交，取回聚合后整体替换；
  - 实际条目行内输入失焦即保存（autosave）；
  - 「按计划预填」「上移/下移」「删除」按钮行为不变；
  - 周体重列失焦保存，非法时列内提示。
- 视觉沿用 `app.css` 的方向 A 令牌（变量组可整体迁移）。

---

## 7. 非功能需求

- NFR-1 性能：单人任一聚合请求 < 200ms（SQLite 本地，天然满足）。
- NFR-2 安全：bcrypt 哈希；JWT 7 天；越权一律 404；错误信息不泄露内部细节。
- NFR-3 可恢复：数据单文件，备份 = 复制库文件。
- NFR-4 兼容：Chrome/Edge/Firefox 最近两个大版本；窗口宽度 ≥ 1024（不专门适配手机）。
- NFR-5 可维护：后端按 routers/models/schemas/services 分层；解析器与原版逻辑一致并保留中文注释。

---

## 8. 测试策略

- 后端 pytest 全部**重写为 JSON API 断言**，覆盖量对齐原 41 例并追加：
  - 注册/登录：合法、用户名重复、各字段违规、密码错误；
  - 鉴权：无 token 401、伪造 token 401；
  - 隔离性：用户 B 对用户 A 所有资源读/写/删均 404，列表互相不可见；
  - 各资源 CRUD + prefill 幂等 + move 边界 + 模板跳过语义；
  - 解析容错回归（单位剥离、逗号小数、非法值存 NULL）；
  - 周体重 upsert 与非法体重拒绝。
- 前端：不写自动化测试；以 `vue-tsc`/构建成功 + 手动冒烟（登录→月历→展开→autosave→模板→体重）为准。

---

## 9. 交付与启动

- 仓库结构：`backend/`（FastAPI 工程）+ `frontend/`（Vite Vue3 工程）；旧 Flask `app/` 在新版验收后删除，git 历史可追溯。
- 开发模式：后端 `uvicorn app.main:app --port 8000 --reload`；前端 `npm run dev`（5173，CORS 已配）。
- 日常模式：前端 `npm run build` → FastAPI 托管 `frontend/dist`；团队成员仅访问 `http://<主机IP>:8000`。
- README 重写为含 dev/prod 两套说明。

---

## 10. 决策索引（访谈结论）

1. 使用场景：小团队多设备 → 登录 + 隔离
2. 后端换 FastAPI，业务逻辑/解析器复用语义
3. 轻量 SPA（Vite+Vue3）
4. 旧数据全部弃置，空库起步（二次确认）
5. 功能冻结平移，不加新功能
6. 单仓库 backend/frontend 双目录
7. JWT 7 天、无 refresh、开放注册、仅用户名+密码
8. 完全数据隔离（含动作库），越权返回 404
9. 动作式聚合 API，写操作回传日聚合
10. 前端交互原样平移，UI 重设计由用户后续进行
11. 后端测试重写为 API 断言，前端无自动化测试
12. dev/prod 双启动模式，README 双套说明
