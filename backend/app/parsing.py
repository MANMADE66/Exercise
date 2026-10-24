"""重量/组数/次数的容错解析（SRS FR-6.4、FR-7.2；HLD §11 横切模块）。

语义与 v1 `app/parsing.py` 1:1 一致：

- 重量：剥掉 kg/公斤/千克（不区分大小写），逗号当小数点，>0 才有效，否则 None；
- 组数：>0 的整数，否则 None；
- 次数：自由文本（`8-12`、`12/12/10/8`、空串都合法），只 trim；
- 日期：路径参数 `{iso_date}` → `date`，认不出返回 None（v1 `app/days.py:parse_day` 上移，
  供 days/templates 复用；**400 还是回退由调用方决定**，这里只负责「不抛错」）；
- 硬不变量：解析失败返回 None / 空串，**绝不抛错**。
"""

from __future__ import annotations

import re
from datetime import date

_UNIT_PATTERN = re.compile(r"(kg|公斤|千克)", re.IGNORECASE)


def parse_weight(raw: str | None) -> float | None:
    """把用户手写的重量变成小数；认不出来就返回 None，绝不抛错。"""
    if raw is None:
        return None
    text = _UNIT_PATTERN.sub("", raw).replace(",", ".").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return value if value > 0 else None


def parse_sets(raw: str | None) -> int | None:
    """组数：>0 的整数；空、负数、非整数一律 None。"""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return None
    return value if value > 0 else None


def parse_reps(raw: str | None) -> str:
    """次数是自由文本：允许 8-12、12/12/10/8、空。"""
    return (raw or "").strip()


def parse_day(raw: str | None) -> date | None:
    """ISO 日期串 → `date`；缺省、空串、非法日期一律 None（如 2026-02-30、2026-1-5）。"""
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None
