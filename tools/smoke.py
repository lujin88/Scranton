"""Open every main screen of a running Scranton in headless Chrome, in both themes, and
fail on any page error, console error or failed request. Run before pushing UI changes:

    .venv/bin/python tools/smoke.py [http://127.0.0.1:8300]

Needs Playwright and Google Chrome (no browser download: it uses the installed Chrome).
"""
import asyncio
import os
import shutil
import sys

CHROME = next((p for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                           shutil.which("google-chrome") or "", shutil.which("chromium") or "") if p and os.path.exists(p)), None)


async def run(url):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        sys.exit("smoke: needs Playwright (pip install playwright); no browser download needed")
    problems = []
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        for theme in ("dark", "light"):
            ctx = await br.new_context(viewport={"width": 1440, "height": 900})
            await ctx.add_init_script(f"localStorage.setItem('scranton-theme','{theme}')")
            pg = await ctx.new_page()
            step = ["load"]
            pg.on("pageerror", lambda e: problems.append(f"[{theme}/{step[0]}] page error: {e}"))
            # A missing uploaded file is data, not code (the page shows "no longer on this Mac").
            pg.on("console", lambda m: problems.append(f"[{theme}/{step[0]}] console: {m.text}")
                  if m.type == "error" and "Failed to load resource" not in m.text else None)
            pg.on("response", lambda r: problems.append(f"[{theme}/{step[0]}] {r.status} {r.url}")
                  if r.status >= 400 and "/uploads/" not in r.url else None)

            async def do(name, js, wait=800):
                step[0] = name
                try:
                    await pg.evaluate(js)
                except Exception as e:  # a screen that can't open is a failure too
                    problems.append(f"[{theme}/{name}] {e}")
                await pg.wait_for_timeout(wait)

            await pg.goto(url)
            await pg.wait_for_timeout(2500)
            await do("chat", "document.querySelector('#sc-welcome')?.classList.add('hidden');"
                             "document.querySelector('.channel-sidebar-row:not([data-channel^=\"dm-\"])')?.click()")
            await do("details", "document.getElementById('sc-pane-pill')?.click()")
            await do("members-tab", "document.querySelector('#sc-info [data-i=\"tab-members\"]')?.click()")
            await do("thread", "document.querySelector('.sc-thread-summary')?.click()")
            for sec in ("profile", "appearance", "agents", "connections", "shortcuts", "history"):
                await do(f"settings-{sec}", f"window.scOpenSettings('{sec}')")
            await do("close-settings", "document.querySelector('.sc-st-x')?.click()")
            await do("report", "document.getElementById('sc-report-row')?.click()", 1500)
            await do("activity", "document.getElementById('sc-inbox-row')?.click()")
            await ctx.close()
        await br.close()
    return problems


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8300/"
    problems = asyncio.run(run(url))
    for line in problems:
        print(line)
    print("smoke: OK" if not problems else f"smoke: {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
