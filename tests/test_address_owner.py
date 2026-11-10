import mcp_bridge as m


def test_opening_address_gets_at():
    assert m._address_owner("Lu，是我排慢了") == "@Lu，是我排慢了"
    assert m._address_owner("Lu: 3 件事") == "@Lu: 3 件事"
    assert m._address_owner("\nLu, ok") == "\n@Lu, ok"


def test_talking_about_lu_stays_plain():
    for t in ("Lu 选了 A", "@Lu，已经", "Luke，hi", "等 Lu 定", "收到"):
        assert m._address_owner(t) == t
