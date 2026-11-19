#!/usr/bin/env node
// page-walk: the mechanical half of a jobs-to-be-done walk-through.
//
// Lu, 2026-11-19: "验证的时候模拟用户按 jobs to be done 把每个页面走一遍". Walking a job is a
// judgement (could a first-time visitor do it?), and QA does that by hand in a browser. What does
// not need judgement is whether the page is whole: this script opens each address the way a visitor
// would, at a desktop and a phone width, and lists what is broken, so QA's turn goes to the job
// itself and not to finding a dead link.
//
//   node page-walk.mjs <url> [<url> ...] [--shots dir] [--widths 1440,768,390] [--slow] [--json]
//
// For every address and width it reports: errors in the console, requests that failed, pictures that
// did not load, links that lead nowhere (same site only), content wider than the screen, and
// buttons or links with no name a screen reader could say. --shots saves a full-page picture of each.
// At widths under 700 the page is opened as a touch screen, and anything to tap that is smaller than
// 24px is counted (a finger misses it); 24 to 43px is listed but not counted.
// --slow opens the narrowest width once more on a slow 3G line (400 kbit/s, 400 ms delay) and
// reports when the first content appeared and when the page finished; first content after 5 s counts
// as broken, and with --shots it saves what a visitor sees after 3 seconds.
// Exit code 1 when anything is broken. Needs the `playwright` package (found by itself; or set
// DS_CHECK_MODULES=/path/to/a/project/that/has/it).
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf('--' + name); return i >= 0 && args[i + 1] ? args[i + 1] : dflt; };
const flagNames = new Set(['shots', 'widths']);
const urls = args.filter((a, i) => !a.startsWith('--') && !(i > 0 && flagNames.has(args[i - 1].replace(/^--/, ''))));
if (!urls.length) {
    console.error('usage: node page-walk.mjs <url> [<url> ...] [--shots dir] [--widths 1440,768,390] [--slow] [--json]');
    process.exit(2);
}
const widths = String(opt('widths', '1440,768,390')).split(',').map((w) => Number(w.trim())).filter(Boolean);
const shots = opt('shots', '');
const slow = args.includes('--slow');

function loadPlaywright() {
    const places = [process.env.DS_CHECK_MODULES, process.cwd(), path.dirname(new URL(import.meta.url).pathname),
        path.join(os.homedir(), '.scranton/node-tools/playwright-1.64.1'), path.join(os.homedir(), 'LuJin-Portfolio')].filter(Boolean);
    try { places.push(execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() + '/..'); } catch (_) { /* no npm */ }
    for (const dir of places) {
        for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
            try { return createRequire(path.join(dir, 'x.js'))(name); } catch (_) { /* next */ }
        }
    }
    console.error('page-walk needs the playwright package. Set DS_CHECK_MODULES=/path/to/a/project/that/has/it.');
    process.exit(2);
}

const { chromium } = loadPlaywright();
const browser = await chromium.launch();
const report = [];
const linkSeen = new Map();   // address -> status, so a link on ten pages is asked for once
try {
    for (const url of urls) {
        for (const w of widths) {
            const ctx = await browser.newContext({ viewport: { width: w, height: w < 700 ? 844 : 900 }, isMobile: w < 700, hasTouch: w < 700 });
            const page = await ctx.newPage();
            const found = { url, width: w, console: [], failed: [], pictures: [], links: [], overflow: 0, unnamed: [], small: [], tight: [] };
            page.on('console', (m) => { if (m.type() === 'error') found.console.push(m.text().slice(0, 200)); });
            page.on('pageerror', (e) => found.console.push(String(e).slice(0, 200)));
            page.on('requestfailed', (r) => found.failed.push(`${r.url().slice(0, 140)} (${(r.failure() || {}).errorText || 'failed'})`));
            page.on('response', (r) => { if (r.status() >= 400) found.failed.push(`${r.url().slice(0, 140)} (${r.status()})`); });
            try {
                await page.goto(url, { waitUntil: 'load', timeout: 45000 });
            } catch (e) {
                found.console.push(`did not open: ${String(e).split('\n')[0].slice(0, 160)}`);
                report.push(found);
                await ctx.close();
                continue;
            }
            // scroll to the end the way a reader does, so lazy pictures and sections load
            await page.evaluate(async () => {
                const step = Math.max(300, innerHeight * 0.8);
                for (let y = 0; y < document.documentElement.scrollHeight; y += step) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 120)); }
                scrollTo(0, 0);
            });
            await page.waitForTimeout(500);
            const seen = await page.evaluate(() => {
                const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 1 && r.height > 1 && cs.visibility !== 'hidden' && cs.display !== 'none'; };
                const pictures = [...document.images].filter((i) => vis(i) && i.complete && i.naturalWidth === 0).map((i) => (i.currentSrc || i.src).slice(0, 140));
                const links = [...new Set([...document.querySelectorAll('a[href]')].map((a) => a.href).filter((h) => h.startsWith(location.origin)).map((h) => h.split('#')[0]))];
                const name = (el) => (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || (el.querySelector('img[alt]') || {}).alt || '').trim();
                const unnamed = [...document.querySelectorAll('a[href], button, [role=button]')].filter((el) => vis(el) && !name(el))
                    .map((el) => el.outerHTML.replace(/\s+/g, ' ').slice(0, 100));
                const taps = [...document.querySelectorAll('a[href], button, [role=button], input:not([type=hidden]), select, textarea, summary')].filter(vis)
                    .filter((el) => { const cs = getComputedStyle(el); return cs.pointerEvents !== 'none' && !(el.tagName === 'A' && cs.display === 'inline'); })
                    .map((el) => { const r = el.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), what: (name(el) || el.outerHTML.replace(/\s+/g, ' ')).slice(0, 50) }; });
                return { pictures, links, unnamed: unnamed.slice(0, 8), taps, overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth) };
            });
            found.pictures = seen.pictures; found.unnamed = seen.unnamed; found.overflow = seen.overflow;
            if (w < 700) {
                const say = (t) => `${t.what} (${t.w}×${t.h})`;
                found.small = [...new Set(seen.taps.filter((t) => Math.min(t.w, t.h) < 24).map(say))].slice(0, 12);
                found.tight = [...new Set(seen.taps.filter((t) => Math.min(t.w, t.h) >= 24 && Math.min(t.w, t.h) < 44).map(say))].slice(0, 8);
            }
            if (w === widths[0]) {            // links are the same at every width: ask once
                for (const href of seen.links.slice(0, 60)) {
                    if (!linkSeen.has(href)) {
                        let status = 0;
                        try { status = (await ctx.request.get(href, { timeout: 15000, maxRedirects: 5 })).status(); } catch (_) { status = 0; }
                        linkSeen.set(href, status);
                    }
                    const st = linkSeen.get(href);
                    if (!st || st >= 400) found.links.push(`${href.slice(0, 140)} (${st || 'no answer'})`);
                }
            }
            if (shots) {
                fs.mkdirSync(shots, { recursive: true });
                const name = url.replace(/^https?:\/\//, '').replace(/[^\w.-]+/g, '_').slice(0, 80);
                found.shot = path.join(shots, `${name}-${w}.png`);
                await page.screenshot({ path: found.shot, fullPage: true });
            }
            found.failed = [...new Set(found.failed)].slice(0, 12);
            found.console = [...new Set(found.console)].slice(0, 8);
            report.push(found);
            await ctx.close();
        }
        if (slow) {
            const w = Math.min(...widths);
            const ctx = await browser.newContext({ viewport: { width: w, height: w < 700 ? 844 : 900 }, isMobile: w < 700, hasTouch: w < 700 });
            const page = await ctx.newPage();
            const cdp = await ctx.newCDPSession(page);
            await cdp.send('Network.enable');
            await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 400 * 1024 / 8, uploadThroughput: 400 * 1024 / 8 });
            const found = { url, width: w, slow: true, console: [], failed: [], pictures: [], links: [], overflow: 0, unnamed: [], small: [], tight: [] };
            const t0 = Date.now();
            const done = page.goto(url, { waitUntil: 'load', timeout: 90000 }).then(() => Date.now() - t0).catch(() => null);
            if (shots) {
                await page.waitForTimeout(3000);
                fs.mkdirSync(shots, { recursive: true });
                found.shot = path.join(shots, `${url.replace(/^https?:\/\//, '').replace(/[^\w.-]+/g, '_').slice(0, 80)}-${w}-slow-3s.png`);
                await page.screenshot({ path: found.shot }).catch(() => {});
            }
            found.loadMs = await done;
            found.firstMs = found.loadMs == null ? null : await page.evaluate(() => { const e = performance.getEntriesByName('first-contentful-paint')[0]; return e ? Math.round(e.startTime) : null; });
            if (found.loadMs == null) found.console.push('did not finish loading in 90 s on a slow line');
            report.push(found);
            await ctx.close();
        }
    }
} finally {
    await browser.close();
}

const bad = (f) => f.console.length + f.failed.length + f.pictures.length + f.links.length + (f.overflow > 2 ? 1 : 0) + f.small.length + (f.firstMs > 5000 ? 1 : 0);
const total = report.reduce((n, f) => n + bad(f), 0);
if (args.includes('--json')) {
    console.log(JSON.stringify({ broken: total, pages: report }, null, 2));
} else {
    console.log(`page-walk: ${urls.length} page${urls.length === 1 ? '' : 's'} at ${widths.join(' and ')} wide, ${total ? total + ' thing' + (total === 1 ? '' : 's') + ' broken' : 'nothing broken'}.`);
    for (const f of report) {
        const lines = [
            ...f.console.map((x) => `error in the page: ${x}`),
            ...f.failed.map((x) => `did not load: ${x}`),
            ...f.pictures.map((x) => `picture missing: ${x}`),
            ...f.links.map((x) => `link leads nowhere: ${x}`),
            ...(f.overflow > 2 ? [`content is ${f.overflow}px wider than the screen (scrolls sideways)`] : []),
        ];
        for (const x of f.small) lines.push(`too small to tap: ${x}`);
        if (f.slow && f.firstMs != null) lines.push(`${f.firstMs > 5000 ? '' : '(not counted) '}on slow 3G: first content after ${(f.firstMs / 1000).toFixed(1)} s, finished after ${(f.loadMs / 1000).toFixed(1)} s`);
        if (!lines.length && !f.unnamed.length && !f.tight.length) continue;
        console.log(`\n${f.url} at ${f.width}px${f.slow ? ' (slow 3G)' : ''}${f.shot ? '  [' + f.shot + ']' : ''}`);
        for (const l of lines) console.log(`- ${l}`);
        for (const u of f.unnamed) console.log(`- (not counted) no name for a screen reader: ${u}`);
        for (const u of f.tight) console.log(`- (not counted) smaller than 44px to tap: ${u}`);
    }
    if (shots) console.log(`\nFull-page pictures: ${path.resolve(shots)}`);
}
process.exitCode = total ? 1 : 0;
