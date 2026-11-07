"""End-to-end walkthrough of Scranton in a real browser (needs playwright + Chrome).
Start a fresh server first (./scranton.sh start with no teammates, or run.py),
then: python tools/e2e_walkthrough.py. Prints PASS/FAIL per check."""
import asyncio, json, time, urllib.request, urllib.error, sys
from pathlib import Path
from playwright.async_api import async_playwright

B = "http://127.0.0.1:8300"
DATA = Path(__file__).resolve().parent.parent / "data"
results = []

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""), flush=True)

def http(path, body=None, headers=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=data, method=method or ("POST" if body is not None else "GET"),
                               headers={"content-type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

def queue(name):
    p = DATA / f"{name}_queue.jsonl"
    return p.read_text() if p.exists() else ""

tok = {}
def register(base):
    s, b = http("/api/register", {"base": base})
    d = json.loads(b); tok[d["name"]] = d["token"]; return d["name"]

def send(name, text, ch):
    return http("/api/send", {"text": text, "channel": ch, "sender": name}, {"authorization": f"Bearer {tok[name]}"})

def hb(name, active=False):
    http(f"/api/heartbeat/{name}", {"active": active}, {"authorization": f"Bearer {tok[name]}"})

async def main():
    # --- server-side security checks
    s, _ = http("/", headers={"host": "evil.example:8300"})
    check("index refuses unknown Host (DNS rebinding guard)", s == 403, s)
    s, _ = http("/api/register", {"base": "pm"}, {"x-forwarded-for": "100.64.0.9"})
    check("agent registration refused through a proxy (Tailscale)", s == 403, s)
    s, _ = http("/api/scranton/team")
    check("team endpoint needs the session token", s == 403, s)
    s, _ = http("/static/avatars/01-project-manager-bear.jpg")
    check("avatars are served", s == 200, s)

    for b in ["pm", "dev", "visual", "visualqa"]:
        register(b)
    for n in tok: hb(n, n == "visual")

    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=__import__("os").environ.get("CHROME") or None, args=["--no-sandbox"])
        ctx = await br.new_context(viewport={"width": 1440, "height": 900})
        pg = await ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        await pg.goto(B + "/"); await pg.wait_for_timeout(2000)

        check("title is Scranton", (await pg.title()) == "Scranton")
        chans = await pg.locator("#channel-sidebar-list .channel-sidebar-row").evaluate_all("els => els.map(e => e.dataset.channel)")
        check("channels: general, lu-portfolio, scranton-feedback", chans == ["general", "lu-portfolio", "scranton-feedback"], chans)
        check("no permanent team column (threads use the right side)", await pg.locator("#team-panel").is_hidden())
        n_dm = await pg.locator("#sc-dm-list .sc-dm-row").count()
        check("DM list lists all 15 teammates", n_dm == 15, n_dm)
        imgs = await pg.locator("#sc-dm-list .sc-dm-avatar img").count()
        check("14 portraits shown in the DM list", imgs == 14, imgs)
        working = await pg.locator("#sc-dm-list .sc-dm-row.working").count()
        check("working status shows (visual)", working == 1, working)
        name = (await pg.locator("#sc-me-name").inner_text()).strip()
        check("you are 'Lu'", name == "Lu", name)

        # channel message with @mention routes; plain message does not
        await pg.click("#channel-sidebar-list >> text=lu-portfolio"); await pg.wait_for_timeout(500)
        await pg.fill("#input", "@dev please set up the routes"); await pg.keyboard.press("Escape"); await pg.click("#send")
        await pg.wait_for_timeout(1200)
        check("@dev in a channel reaches dev", "please set up the routes" in queue("dev"))
        await pg.fill("#input", "just thinking out loud"); await pg.click("#send"); await pg.wait_for_timeout(1000)
        check("plain channel message reaches nobody", all("thinking out loud" not in queue(n) for n in tok))

        # DM without @
        await pg.click("#sc-dm-list .sc-dm-row >> text=视觉设计师"); await pg.wait_for_timeout(1500)
        active = await pg.evaluate("window.activeChannel")
        check("clicking a DM opens dm-visual", active == "dm-visual", active)
        await pg.fill("#input", "three directions please"); await pg.click("#send"); await pg.wait_for_timeout(1200)
        check("plain DM to visual reaches visual only", "three directions please" in queue("visual")
              and "three directions please" not in queue("visualqa"))
        chans2 = await pg.locator("#channel-sidebar-list .channel-sidebar-row").evaluate_all("els => els.map(e => e.dataset.channel)")
        check("dm channel stays out of Channels list", "dm-visual" not in chans2, chans2)
        chips_visible = await pg.locator("#mention-toggles-row button:visible").count()
        check("@ chips hidden in a DM", chips_visible <= 1, chips_visible)

        # Activity: mention + DM reply
        send("pm", "@Lu 三个封面方向放在 PR #14 了，等你挑。", "lu-portfolio")
        send("visual", "方向已出，见下。", "dm-visual")
        send("dev", "routes done @pm", "lu-portfolio")  # not for Lu
        await pg.wait_for_timeout(1500)
        badge = (await pg.locator("#sc-inbox-badge").inner_text()).strip()
        check("Activity badge counts 2 (mention + DM)", badge == "2", badge)
        await pg.click("#sc-inbox-row"); await pg.wait_for_timeout(500)
        tab = (await pg.locator("#sc-inbox .sc-tab.active").inner_text()).strip()
        check("Activity opens on Mentions", tab == "Mentions", tab)
        items = await pg.locator(".sc-inbox-item").count()
        check("Mentions shows 1 item", items == 1, items)
        await pg.click("#sc-inbox .sc-tab[data-kind=dm]"); await pg.wait_for_timeout(300)
        check("DMs tab shows the DM reply", await pg.locator(".sc-inbox-item").count() == 1)
        await pg.click("#sc-inbox .sc-tab[data-kind=all]"); await pg.wait_for_timeout(300)
        check("All shows 2, not the message to @pm", await pg.locator(".sc-inbox-item").count() == 2)
        await pg.select_option("#sc-inbox-from", "pm"); await pg.wait_for_timeout(300)
        check("From filter: only 项目经理", await pg.locator(".sc-inbox-item").count() == 1)
        await pg.select_option("#sc-inbox-from", ""); await pg.wait_for_timeout(200)
        await pg.click(".sc-inbox-item >> nth=0"); await pg.wait_for_timeout(800)
        check("clicking an item closes Activity", await pg.locator("#sc-inbox").is_hidden())
        badge = (await pg.locator("#sc-inbox-badge").inner_text()).strip()
        check("opened item is marked read (badge 1)", badge == "1", badge)
        await pg.click("#sc-inbox-row"); await pg.check("#sc-inbox-unread", force=True); await pg.wait_for_timeout(300)
        await pg.click("#sc-inbox .sc-tab[data-kind=all]"); await pg.wait_for_timeout(200)
        check("Unread toggle hides read items", await pg.locator(".sc-inbox-item").count() == 1)
        await pg.click("text=Mark all read"); await pg.wait_for_timeout(300)
        check("Mark all read clears badge", await pg.locator("#sc-inbox-badge").is_hidden())
        await pg.click("#sc-inbox button[aria-label=Close]")

        # collapse + persistence
        await pg.click("#sc-menu-btn"); await pg.wait_for_timeout(300)
        check("sidebar collapses", await pg.locator("#channel-sidebar").is_hidden())
        await pg.reload(); await pg.wait_for_timeout(1500)
        check("collapse survives reload", await pg.locator("#channel-sidebar").is_hidden())
        await pg.click("#sc-menu-btn"); await pg.wait_for_timeout(300)
        await pg.click(".sc-section-header[data-section=dms] .sc-section-toggle"); await pg.wait_for_timeout(200)
        check("DM section folds", await pg.locator("#sc-dm-list").is_hidden())
        await pg.click(".sc-section-header[data-section=dms] .sc-section-toggle")

        # my avatar
        await pg.set_input_files("#sc-me-file", str(Path(__file__).resolve().parent.parent / "static" / "scranton-icon.png")); await pg.wait_for_timeout(800)
        check("your picture can be set", await pg.locator("#sc-me-avatar img").count() == 1)

        # no settings bar; rename yourself from the profile chip
        check("settings bar and gear are gone", await pg.locator("#settings-toggle").is_hidden() and await pg.locator("#settings-bar").is_hidden())
        await pg.click("#sc-me-name"); await pg.fill(".sc-me-input", "Lu J"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(800)
        check("rename yourself from the profile chip", (await pg.locator("#sc-me-name").inner_text()).strip() == "Lu J"
              and (await pg.evaluate("username")) == "Lu J")
        await pg.click("#sc-me-name"); await pg.fill(".sc-me-input", "Lu"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(800)
        pass

        # phone
        m = await br.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        m.on("pageerror", lambda e: errs.append("phone: " + str(e)))
        await m.goto(B + "/"); await m.wait_for_timeout(1500)
        check("phone: sidebar hidden by default", not await m.locator("#channel-sidebar").evaluate("e => e.getBoundingClientRect().right > 0"))
        await m.click("#sc-menu-btn"); await m.wait_for_timeout(400)
        check("phone: ☰ opens channels drawer", await m.locator("#channel-sidebar").evaluate("e => e.getBoundingClientRect().left >= 0"))
        await m.click("#channel-sidebar-list >> text=general"); await m.wait_for_timeout(400)
        check("phone: picking a channel closes drawer", not await m.evaluate("document.body.classList.contains('sc-drawer-channels')"))
        check("phone: no team drawer button (team is in DMs)", await m.locator("#sc-team-btn").is_hidden())
        pass

        # review fixes
        await pg.evaluate("window.ws.send(JSON.stringify({type:'channel_create', name:'dm-nobody'}))")
        await pg.wait_for_timeout(600)
        check("dm- channel for a non-teammate is refused", "dm-nobody" not in await pg.evaluate("window.channelList"))
        await pg.evaluate("window.ws.send(JSON.stringify({type:'channel_rename', old_name:'lu-portfolio', new_name:'dm-pm'}))")
        await pg.wait_for_timeout(600)
        check("renaming a channel to dm-… is refused", "lu-portfolio" in await pg.evaluate("window.channelList"))
        await pg.evaluate("window.ws.send(JSON.stringify({type:'message', channel:'ghost', text:'stray message'}))")
        await pg.wait_for_timeout(800)
        ch = await pg.evaluate("[...document.querySelectorAll('.message')].filter(e => e.textContent.includes('stray message')).map(e => e.dataset.channel)[0]")
        check("message to an unknown channel lands in #general", ch == "general", ch)
        token = await pg.evaluate("window.SESSION_TOKEN || ''")
        log = (DATA / "logs" / "server.log").read_text() if (DATA / "logs" / "server.log").exists() else ""
        check("session token never appears in the server log", token and token not in log, "token found in log" if token in log else "")
        await pg.reload(); await pg.wait_for_timeout(1500)
        await pg.click("#channel-sidebar-list >> text=lu-portfolio"); await pg.wait_for_timeout(500)
        mine = await pg.locator(".message.self .avatar-wrap").count()
        check("your picture shows on your old messages after reload", mine >= 1, mine)

        check("no JavaScript errors anywhere", not errs, errs[:3])
        await br.close()

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    sys.exit(1 if failed else 0)

asyncio.run(main())
