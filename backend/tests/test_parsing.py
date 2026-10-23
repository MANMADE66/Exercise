"""容错解析回归（SRS FR-6.4、FR-7.2；v1 `tests/test_parsing.py` 搬运）。"""

from __future__ import annotations

import pytest
from app.parsing import parse_reps, parse_sets, parse_weight


def test_parse_weight_accepts_common_forms() -> None:
    assert parse_weight("100") == 100.0
    assert parse_weight("102.5") == 102.5
    assert parse_weight("100kg") == 100.0
    assert parse_weight("102,5") == 102.5
    assert parse_weight(" 100 ") == 100.0


def test_parse_weight_strips_all_supported_units() -> None:
    assert parse_weight("100公斤") == 100.0
    assert parse_weight("100千克") == 100.0
    assert parse_weight("100KG") == 100.0
    assert parse_weight("100 kg") == 100.0


def test_parse_weight_returns_none_on_junk() -> None:
    for junk in ["", "  ", "随便", "-", "abc", "100kgkg是啥"]:
        assert parse_weight(junk) is None


def test_parse_weight_requires_positive_value() -> None:
    assert parse_weight("0") is None
    assert parse_weight("-20") is None
    assert parse_weight("0,0") is None


def test_parse_weight_handles_none() -> None:
    assert parse_weight(None) is None


def test_parse_sets_and_reps() -> None:
    assert parse_sets("4") == 4
    assert parse_sets("") is None
    assert parse_sets("x") is None
    assert parse_reps(" 8-12 ") == "8-12"
    assert parse_reps("") == ""


def test_parse_sets_requires_positive_integer() -> None:
    assert parse_sets(" 5 ") == 5
    assert parse_sets("0") is None
    assert parse_sets("-3") is None
    assert parse_sets("4.5") is None
    assert parse_sets(None) is None


def test_parse_reps_keeps_free_text() -> None:
    assert parse_reps("12/12/10/8") == "12/12/10/8"
    assert parse_reps(None) == ""


@pytest.mark.parametrize("junk", ["", "  ", "随便", "-", "abc", "None", "1e", "kg"])
def test_parsers_never_raise(junk: str) -> None:
    """硬不变量：无效输入只回 None / 空串，不抛错。"""
    assert parse_weight(junk) is None
    assert parse_sets(junk) is None
    assert parse_reps(junk) == junk.strip()
