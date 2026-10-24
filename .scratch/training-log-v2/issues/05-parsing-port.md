Type: task
Status: ready-for-agent
Blocked by: 02
Claimed by: pi

## Question

把 `app/parsing.py` 语义 1:1 移植到 `backend/app/parsing.py`，产出 + 回归：

- 重量：剥 kg/公斤/千克、逗号作小数点、>0 才有效、无效 → None；
- 组数：>0 整数，否则 None；
- 次数：自由文本，trim 保留原串；
- 硬不变量：绝不抛错（解析失败回 None / 空串）；
- 把 `tests/test_parsing.py` 用例搬为 `backend/tests` 回归。

## Answer

parsing 已移植，`bash scripts/verify.sh` 全绿（pytest 32 例 = health 1 + 数据层 15 + parsing 16，其中 parsing 内一例参数化 8 次）。

### 产物

```
backend/app/parsing.py        # parse_weight / parse_sets / parse_reps（v1 语义 1:1）
backend/tests/test_parsing.py # v1 tests/test_parsing.py 三例搬运 + 10 例补充
```

### 语义对照（票面逐条落地）

| 要求 | 落点 |
| --- | --- |
| 剥 kg/公斤/千克 | `_UNIT_PATTERN = re.compile(r"(kg|公斤|千克)", re.IGNORECASE)` + `sub("")`；大小写变体 `KG` 也剥 |
| 逗号作小数点 | `.replace(",", ".")`，且**在剥单位之后**（顺序与原版一致） |
| `>0` 才有效 | `return value if value > 0 else None`；`0`、`-20`、`0,0` → `None` |
| 组数 `>0` 整数 | `int(text)` 失败或 `<=0` → `None`；`4.5` → `None` |
| 次数自由文本 | `(raw or "").strip()`；`8-12`、`12/12/10/8`、`None` → `""` |
| 绝不抛错 | `except ValueError` 兜住 `float`/`int`；`None` 入参短路；`test_parsers_never_raise` 参数化覆盖 |

### 与 v1 的唯一实现差异（不改变语义）

`parse_sets` 里 v1 写 `str(raw).strip()`，此处直接 `raw.strip()`——`None` 已在上面短路，`raw` 此时静态类型就是 `str`，`str(raw)` 是恒等转换，留着只会让 mypy strict 之外多一层噪音。

### 两处刻意保留的 v1 行为（不是遗漏，是可移植的忠实度）

1. `float("inf")` / `float("Infinity")` → `inf`（`inf > 0` 为真）。加 `math.isfinite` 守卫会偏离 v1；真要收紧应在 SRS FR-6.4 里改规则再动代码。
2. `"1,000"` 按逗号小数点解析成 `1.0`（千分位不支持）——同 v1，SRS 也只写「逗号作小数点」。

### 测试覆盖补充

v1 那三例只断言了 `100`/`102.5`/`100kg`/`102,5`/` 100 `/空/`随便`/`-`/`abc`；而 SRS FR-6.4 明写的 `公斤`、`千克`、大小写单位、`0`/负数、`4.5` 组数、`12/12/10/8` 无一条被锁住。这些现已补为独立用例：`test_parse_weight_strips_all_supported_units` / `test_parse_weight_requires_positive_value` / `test_parse_sets_requires_positive_integer` / `test_parse_reps_keeps_free_text`（mutmut 若把 `sub` 改成 `match`、把 `value > 0` 去掉、把 `int` 换成 `float`，这几个会红）。
