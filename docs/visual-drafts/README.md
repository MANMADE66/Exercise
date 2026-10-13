# 视觉方向：三个样张与最终选择

三个样张用同一份假数据（2026 年 10 月的月历 + 10 月 13 日展开后的详情）：

- `direction-a.html` — 浅色极简：近白底、大量留白、几乎没有边框、近乎黑白的强调色
- `direction-b.html` — 深色：深底高对比、强调色为蓝
- `direction-c.html` — 浅灰底 + 卡片描边 + 靛蓝强调色

## 选择结果

**选了 A。**

理由：使用者要求「互联网高级感」并且不要「后台管理系统」的样子。B 的深色和 C 的卡片描边都更接近后台工具的印象，而 A 靠留白和字重拉层级，最不容易变丑，也最容易在后续加入新元素时保持干净。

## 令牌

选定的 A 已经抽成 `app/static/app.css` 顶部的 CSS 变量（`:root` 里的 `--bg / --surface / --text / --muted / --hairline / --accent / --accent-soft / --radius / --gap`）。

换到 B 或 C：只替换这组变量即可，页面结构不用动。B 的变量在 `direction-b.html` 的 `:root` 里，C 的在 `direction-c.html` 里。
