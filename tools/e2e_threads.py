"""Browser test for threads, reactions, copy link, forward and the message menu.
Start a fresh server first, then: CHROME=/path/to/chrome python tools/e2e_threads.py"""
import asyncio, json, urllib.request
from pathlib import Path
from playwright.async_api import async_playwright
B="http://127.0.0.1:8300"; DATA=Path(__file__).resolve().parent.parent/"data"
def http(path, body=None, headers=None):
    r=urllib.request.Request(B+path,data=json.dumps(body).encode() if body is not None else None,headers={"content-type":"application/json",**(headers or {})},method="POST" if body is not None else "GET")
    with urllib.request.urlopen(r) as resp: return json.loads(resp.read() or b"{}")
tok={}
for b in ["pm","dev","visual"]:
    d=http("/api/register",{"base":b}); tok[d["name"]]=d["token"]
def send(n,text,ch,reply_to=None):
    body={"text":text,"channel":ch,"sender":n}
    if reply_to is not None: body["reply_to"]=reply_to
    return http("/api/send",body,{"authorization":f"Bearer {tok[n]}"})
res=[]
def check(name, ok, d=""): res.append(ok); print(("PASS " if ok else "FAIL ")+name+("" if ok else f" [{d}]"))
async def main():
    async with async_playwright() as p:
        br=await p.chromium.launch(executable_path=__import__("os").environ.get("CHROME") or None,args=["--no-sandbox"])
        ctx=await br.new_context(viewport={"width":1440,"height":900}, permissions=["clipboard-read","clipboard-write"])
        pg=await ctx.new_page(); errs=[]; pg.on("pageerror",lambda e:errs.append(str(e)))
        await pg.goto(B+"/"); await pg.wait_for_timeout(1500)
        await pg.click("#channel-sidebar-list >> text=lu-portfolio"); await pg.wait_for_timeout(300)
        await pg.fill("#input","@dev 先把 case study 页面的路由搭好"); await pg.keyboard.press("Escape"); await pg.click("#send"); await pg.wait_for_timeout(800)
        root=await pg.evaluate("Number([...document.querySelectorAll('.message.self')].pop().dataset.id)")
        send("pm","收到，我来跟进。@dev 记得先开分支","lu-portfolio")
        send("dev","好的，路由在做了，大概 10 分钟。","lu-portfolio",reply_to=root)
        send("visual","我顺便把封面方向放这里，@Lu 你看一下。","lu-portfolio",reply_to=root)
        await pg.wait_for_timeout(1200)
        hidden=await pg.evaluate("[...document.querySelectorAll('.message.sc-in-thread')].length")
        check("thread replies leave the main stream", hidden==2, hidden)
        summ=await pg.locator(".sc-thread-summary").inner_text()
        check("summary under the root shows 2 replies", "2 replies" in summ, summ)
        pass
        await pg.click(".sc-thread-summary"); await pg.wait_for_timeout(500)
        check("thread panel opens", await pg.locator("#sc-thread").is_visible())
        n=await pg.locator("#sc-thread .sc-tmsg").count()
        check("panel shows root + 2 replies", n==3, n)
        await pg.fill("#sc-thread-input","路由用 app router 吧"); await pg.keyboard.press("Enter"); await pg.wait_for_timeout(1200)
        q=(DATA/"dev_queue.jsonl").read_text() if (DATA/"dev_queue.jsonl").exists() else ""
        last=[json.loads(l) for l in q.splitlines() if l.strip()][-1] if q.strip() else {}
        q2=(DATA/"visual_queue.jsonl").read_text() if (DATA/"visual_queue.jsonl").exists() else ""
        lastv=[json.loads(l) for l in q2.splitlines() if l.strip()][-1] if q2.strip() else {}
        check("plain thread reply goes to the last teammate who replied, inside the thread", lastv.get("thread")==root and "app router" in lastv.get("text",""), lastv)
        n2=await pg.locator("#sc-thread .sc-tmsg").count()
        check("your reply appears in the panel", n2==4, n2)
        check("…and not in the main stream", await pg.evaluate(f"[...document.querySelectorAll('.message.sc-in-thread')].length")==3)
        # second thread tab
        pm_id=await pg.evaluate("Number([...document.querySelectorAll('.message:not(.self):not(.sc-in-thread)')].filter(e=>e.textContent.includes('我来跟进')).pop().dataset.id)")
        await pg.hover(f"#message-{pm_id}"); await pg.click(f"#message-{pm_id} .sc-tools [data-act=thread]"); await pg.wait_for_timeout(400)
        tabs=await pg.locator(".sc-ttab").count()
        check("second thread opens as a second tab", tabs==2, tabs)
        # reaction
        await pg.hover(f"#message-{pm_id}"); await pg.click(f"#message-{pm_id} .sc-tools [data-act=react]"); await pg.wait_for_timeout(200)
        await pg.click(".sc-emoji-pop [data-emoji='👍']"); await pg.wait_for_timeout(800)
        pill=await pg.locator(f"#message-{pm_id} .sc-reaction.mine").count()
        check("👍 reaction appears and is marked as yours", pill==1, pill)
        await pg.click(f"#message-{pm_id} .sc-reaction.mine"); await pg.wait_for_timeout(800)
        check("clicking your reaction removes it", await pg.locator(f"#message-{pm_id} .sc-reaction.mine").count()==0)
        await pg.hover(f"#message-{pm_id}"); await pg.click(f"#message-{pm_id} .sc-tools [data-act=react]"); await pg.click(".sc-emoji-pop [data-emoji='🎉']"); await pg.wait_for_timeout(600)
        # copy link
        await pg.hover(f"#message-{pm_id}"); await pg.click(f"#message-{pm_id} .sc-tools [data-act=link]"); await pg.wait_for_timeout(300)
        clip=await pg.evaluate("navigator.clipboard.readText()")
        check("copy link gives a #msg- link", clip.endswith(f"#msg-{pm_id}"), clip)
        # forward
        await pg.hover(f"#message-{pm_id}"); await pg.click(f"#message-{pm_id} .sc-tools [data-act=forward]"); await pg.wait_for_timeout(200)
        await pg.click(".sc-menu [data-ch=general]"); await pg.wait_for_timeout(800)
        fwd=await pg.evaluate("[...document.querySelectorAll('.message[data-channel=general]')].some(e=>e.textContent.includes('Forwarded from'))")
        check("forward posts into #general", fwd)
        # more menu
        await pg.hover(f"#message-{pm_id}"); await pg.click(f"#message-{pm_id} .sc-tools [data-act=more]"); await pg.wait_for_timeout(200)
        items=await pg.locator(".sc-menu .sc-menu-item").all_inner_texts()
        check("more menu items", items==["Mark unread","Copy message","Copy link","Forward message","Reply in thread","Delete message"], items)
        pass
        await pg.keyboard.press("Escape")
        # reload keeps reactions + threads
        await pg.reload(); await pg.wait_for_timeout(1800)
        await pg.click("#channel-sidebar-list >> text=lu-portfolio"); await pg.wait_for_timeout(500)
        check("after reload: reaction kept", await pg.locator(f"#message-{pm_id} .sc-reaction").count()>=1)
        check("after reload: thread summary kept", "3 replies" in (await pg.locator(f"#message-{root} .sc-thread-summary").inner_text()))
        # open via link
        await pg.goto(B+f"/#msg-{root}"); await pg.wait_for_timeout(2500)
        check("a #msg link opens the message", await pg.evaluate("window.activeChannel")=="lu-portfolio")
        # phone
        m=await br.new_page(viewport={"width":390,"height":844},device_scale_factor=2,is_mobile=True,has_touch=True)
        await m.goto(B+"/"); await m.wait_for_timeout(1500)
        await m.evaluate("switchChannel('lu-portfolio')"); await m.wait_for_timeout(400)
        await m.tap(".sc-thread-summary"); await m.wait_for_timeout(500)
        check("phone: thread opens full screen", await m.locator("#sc-thread").is_visible())
        pass
        check("no JS errors", not errs, errs[:3])
        await br.close()
    print(f"{sum(res)}/{len(res)} passed")
asyncio.run(main())
import sys; sys.exit(0 if all(res) else 1)
