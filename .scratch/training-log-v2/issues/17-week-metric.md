# 17: 周体重列：失焦保存与非法还原

Type: task
Status: ready-for-agent
Claimed by: 主线会话
Blocked by: 16
Refs: [spec.md](../spec.md) 实现决策 21–24

## What to build

月历每行右侧多出周体重列：输入框占位 `kg`，本周已有体重时预填；失焦即 `PUT /metrics/{week_start}`；成功用返回的 metric 就地更新该行（不重拉月历、不刷新整页）；体重非法时输入框还原成上次保存值，并在该行内提示。

## Acceptance criteria

- [ ] 每行都有周体重输入框；已有记录的周预填当前值，空周为空（不显示 0）
- [ ] 失焦保存成功，该行立刻显示新值，无需刷新页面
- [ ] 保存时把该周已有的体脂率与备注原值一并回传，保存后二者仍在
- [ ] 非法输入（空、`abc`、负数）不落库：输入框还原成上次保存值 + 行内提示
- [ ] 请求期间该输入框禁用，连点不产生第二次写入
- [ ] `bash scripts/verify.sh` 全绿、生成物零 diff

## Notes

- **最关键的坑（spec 决策 23）**：`PUT /metrics/{week_start}` 是**整体替换**，只传 `weight` 会把该周原本填过的 `body_fat_pct` 与 `note` 静默清成 NULL。这两个字段至今没有 UI（v1 也没有），更容易被忘掉——必须从当前行 metric 里读回来一起传。验收里有一条专门钉它。
- 体重非法是 422，不是 400：校验在契约层就拦住了，handler 都进不去，所以「不落库」是结构性的，前端只需还原 + 提示。
- v1 的做法是整页重载 + 顶部 flash；v2 不重载，用「还原 + 行内提示」，语义等价（SRS FR-10.2「前端在周体重列提示」）。
- 本票与 18 都改 `MonthGrid` 与月历视图：按编号顺序串行提交，开工前先 `git log` / `git status` 确认 16 已提交。

## Answer

**已落地（2026-10-24，主线会话）。**

### 做了什么

- 新 `components/WeekMetric.vue`：props = `weekStart` + `metric`；自己持有该行 metric（初始取 props，父级换月重取时随 `watch` 同步）、输入框文本、保存中标记、行内错误。失焦即 `saveWeekMetric`；成功用返回的 metric 就地替换该行并回填规范化文本；`watch` 之外的本地编辑不打扰父级。
- `MonthGrid.vue`：第 8 列从占位空 `td` 换成 `<WeekMetric :week-start :metric>`（`colspan="8"` 仍只有一处）。

### 关键裁定

1. **整体替换陷阱（spec 决策 23）**：保存时把该行 `metric.body_fat_pct`（`String()` 直转，不用 `weightText` 以免截断精度改变原值）与 `metric.note` 原值一并回传；行内没有这两个字段的 UI，但它们绝不被前端静默清掉。
2. 「没改就不发请求」基准是 `trim(text) === weightText(savedMetric)`：空框路过失焦、加空格失焦都不会触发 422；非法输入（空/`abc`/负数）到服务端 422 → 还原成上次保存值 + 行内 `.error` 提示（v1 是整页重载 + 顶部 flash，此处语义等价的「还原 + 行内」）。
3. 非 422 失败（网络等）不还原用户已输入的文本，只行内显示归一后的中文消息，下次失焦可重试。
4. 请求期间输入框禁用（AC：连点不产生第二次写入）；保存成功后文本回填为服务端解析后的规范显示（`72kg` → `72`）。

### 验证

`bash scripts/verify.sh` 全绿：pytest 193 例（后端零改动）、生成物（`docs/openapi.json` / `api-types.ts`）零 diff、oxlint / oxfmt / vue-tsc / vite build 通过。
