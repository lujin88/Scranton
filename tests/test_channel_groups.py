"""Her own groups of channels in the sidebar."""
import scranton_groups as G

CH = ["general", "lu-portfolio", "ai-pet", "eon-slide", "dm-pm"]


def test_create_move_fold_rename_delete():
    gs, err = G.apply([], CH, "create", {"name": "Archive", "channel": "ai-pet"})
    assert not err and gs == [{"id": 1, "name": "Archive", "channels": ["ai-pet"], "collapsed": False}]
    gs, err = G.apply(gs, CH, "create", {"name": "Slides"})
    gs, err = G.apply(gs, CH, "move", {"channel": "eon-slide", "id": 2})
    gs, err = G.apply(gs, CH, "move", {"channel": "ai-pet", "id": 2})             # a channel is in one group at a time
    assert [g["channels"] for g in gs] == [[], ["eon-slide", "ai-pet"]]
    gs, err = G.apply(gs, CH, "collapse", {"id": 2, "on": True})
    assert gs[1]["collapsed"] is True
    gs, err = G.apply(gs, CH, "rename", {"id": 2, "name": "Decks"})
    assert gs[1]["name"] == "Decks"
    gs, err = G.apply(gs, CH, "move", {"channel": "ai-pet", "id": 0})             # out again
    assert gs[1]["channels"] == ["eon-slide"]
    gs, err = G.apply(gs, CH, "delete", {"id": 2})
    assert not err and [g["name"] for g in gs] == ["Archive"]                     # the channels themselves are untouched


def test_what_is_refused():
    gs, _ = G.apply([], CH, "create", {"name": "Archive"})
    assert G.apply(gs, CH, "create", {"name": "archive"})[1]                      # same name
    assert G.apply(gs, CH, "create", {"name": "  "})[1]
    assert not G.apply(gs, CH, "move", {"channel": "general", "id": 1})[1]     # Lu, 11-25: general can be grouped too
    for ch in ("dm-pm", "nope"):
        assert G.apply(gs, CH, "move", {"channel": ch, "id": 1})[1]
    assert G.apply(gs, CH, "move", {"channel": "ai-pet", "id": 9})[1]
    assert G.apply(gs, CH, "rename", {"id": 9, "name": "x"})[1]
    full = [{"id": i, "name": f"g{i}", "channels": []} for i in range(1, G.MAX_GROUPS + 1)]
    assert G.apply(full, CH, "create", {"name": "one more"})[1]


def test_groups_follow_a_renamed_or_deleted_channel():
    gs = [{"id": 1, "name": "Archive", "channels": ["ai-pet", "eon-slide"]}]
    assert G.renamed(gs, "ai-pet", "pet")[0]["channels"] == ["pet", "eon-slide"]
    assert G.removed(gs, "ai-pet")[0]["channels"] == ["eon-slide"]
