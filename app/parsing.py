import re

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
    if raw is None:
        return None
    text = str(raw).strip()
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
