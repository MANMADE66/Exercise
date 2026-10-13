from app.parsing import parse_reps, parse_sets, parse_weight


def test_parse_weight_accepts_common_forms():
    assert parse_weight("100") == 100.0
    assert parse_weight("102.5") == 102.5
    assert parse_weight("100kg") == 100.0
    assert parse_weight("102,5") == 102.5
    assert parse_weight(" 100 ") == 100.0


def test_parse_weight_returns_none_on_junk():
    for junk in ["", "  ", "随便", "-", "abc"]:
        assert parse_weight(junk) is None


def test_parse_sets_and_reps():
    assert parse_sets("4") == 4
    assert parse_sets("") is None
    assert parse_sets("x") is None
    assert parse_reps(" 8-12 ") == "8-12"
    assert parse_reps("") == ""
