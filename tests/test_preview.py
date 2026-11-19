import os
from pathlib import Path

import scranton_preview as pv


def cfg(tmp_path, **extra):
    return {"server": {"port": 8300}, "mcp": {"http_port": 8200, "sse_port": 8201},
            "images": {"upload_dir": str(tmp_path / "uploads")},
            "agents": {"dev": {"cwd": str(tmp_path / "proj"), "worktree": True}}, **extra}


def test_ports_only_dev_ranges_never_scrantons_own(tmp_path):
    c = cfg(tmp_path)
    assert pv.port_ok(c, 4661) and pv.port_ok(c, 3000) and pv.port_ok(c, 5173)
    assert not pv.port_ok(c, 8300)            # Scranton itself
    assert not pv.port_ok(c, 7777) and not pv.port_ok(c, 22) and not pv.port_ok(c, 5432)
    c2 = cfg(tmp_path, preview={"ports": ["8300", "9000-9002"]})
    assert pv.port_ok(c2, 9001) and not pv.port_ok(c2, 8300) and not pv.port_ok(c2, 4661)


def test_files_only_inside_allowed_folders_and_no_secrets(tmp_path):
    c = cfg(tmp_path)
    proj = tmp_path / "proj"
    (proj / "out").mkdir(parents=True)
    (proj / "out" / "deck.html").write_text("<p>hi")
    (proj / ".env").write_text("KEY=1")
    (proj / "out" / "token.txt").write_text("x")
    (tmp_path / "elsewhere.txt").write_text("x")
    os.symlink(tmp_path / "elsewhere.txt", proj / "out" / "link.txt")
    ok, why = pv.file_target(c, str(proj / "out" / "deck.html"))
    assert ok == (proj / "out" / "deck.html").resolve() and why == ""
    assert pv.file_target(c, str(proj / ".env"))[0] is None
    assert pv.file_target(c, str(proj / "out" / "token.txt"))[0] is None
    assert pv.file_target(c, str(tmp_path / "elsewhere.txt"))[0] is None
    assert pv.file_target(c, str(proj / "out" / "link.txt"))[0] is None           # a symlink out of the folder
    assert pv.file_target(c, str(proj / "out" / ".." / ".." / "elsewhere.txt"))[0] is None
    assert pv.file_target(c, str(proj / "out" / "missing.png"))[1] == "not found"
    assert (tmp_path / "proj-worktrees").resolve() in pv.roots(c)
    assert Path.home().resolve() not in pv.roots(cfg(tmp_path, preview={"roots": ["~", "/"]}))


def test_key_is_made_once_and_private(tmp_path):
    k = pv.key(tmp_path)
    assert len(k) >= 32 and pv.key(tmp_path) == k
    assert (tmp_path / "preview.key").stat().st_mode & 0o077 == 0
    a, b = pv.key_for(tmp_path, "p:4661"), pv.key_for(tmp_path, "p:4620")
    assert a != b and a == pv.key_for(tmp_path, "p:4661") and k not in a      # one key per port; the secret stays home


def test_rewrite_points_root_paths_at_the_previewed_port():
    pre = "/preview/K/p/4661"
    html = b'<link href="/a.css"><img src="/img/x.png"><a href="//cdn.x/y">c</a><a href="rel.html">r</a><script src="/_next/static/c.js"></script>'
    out = pv.rewrite(html, "text/html", pre).decode()
    assert f'href="{pre}/a.css"' in out and f'src="{pre}/img/x.png"' in out and f'src="{pre}/_next/static/c.js"' in out
    assert 'href="//cdn.x/y"' in out and 'href="rel.html"' in out
    assert pv.rewrite(b"a{background:url(/bg.png)}", "text/css", pre) == f"a{{background:url({pre}/bg.png)}}".encode()
    assert pv.rewrite(b'p="/_next/"', "application/javascript", pre) == f'p="{pre}/_next/"'.encode()
    assert pv.rewrite(b"\xff\xfe", "text/html", pre) == b"\xff\xfe"


def test_sandbox_keeps_the_page_a_stranger_to_scranton():
    csp = pv.HEADERS["Content-Security-Policy"]
    assert csp.startswith("sandbox") and "allow-same-origin" not in csp
    assert pv.HEADERS["Referrer-Policy"] == "no-referrer"
