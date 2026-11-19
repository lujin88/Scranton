#!/usr/bin/env node
// ds-check: measure a deck or a page in a real browser, write down its design system, and
// check every slide against it. Lu, 2026-11-19: "字体的位置跳来跳去、尺寸不对，这个不是应该系统自己
// 检查的吗？" It should: a title 36px lower on one slide is a number, not an opinion.
//
//   node ds-check.mjs init  <url or file> [--out design-system/tokens.json]
//       Measures every slide and writes tokens.json (the values most slides share) and
//       design-system.md next to it (the same for people, with every odd one out listed).
//   node ds-check.mjs check <url or file> [--tokens design-system/tokens.json] [--shots dir]
//       Exit code 0 when every slide follows tokens.json, 1 when not. Prints one line per
//       difference with the slide number; --shots saves a picture of each slide that fails,
//       the wrong elements outlined in red.
//
// Options: --slide "<css>" (default: found by itself), --width 1440 --height 810, --json.
// Needs the `playwright` package from any project on this computer (found by itself;
// or set DS_CHECK_MODULES=/path/to/project).
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const args = process.argv.slice(2);
const mode = args[0];
const target = args[1];
const opt = (name, dflt) => { const i = args.indexOf('--' + name); return i > 0 && args[i + 1] ? args[i + 1] : dflt; };
const flag = (name) => args.includes('--' + name);
if (!['init', 'check'].includes(mode) || !target) {
    console.error('usage: node ds-check.mjs init|check <url or file> [--tokens f] [--out f] [--slide css] [--shots dir] [--width n] [--height n] [--json]');
    process.exit(2);
}

function loadPlaywright() {
    const places = [process.env.DS_CHECK_MODULES, process.cwd(), path.dirname(new URL(import.meta.url).pathname),
        path.join(os.homedir(), 'LuJin-Portfolio')].filter(Boolean);
    try { places.push(execSync('npm root -g', { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() + '/..'); } catch (_) { /* no npm */ }
    for (const dir of places) {
        for (const name of ['playwright', '@playwright/test', 'playwright-core']) {
            try { return createRequire(path.join(dir, 'x.js'))(name); } catch (_) { /* next */ }
        }
    }
    console.error('ds-check needs the playwright package. Run it from a project that has it, or set DS_CHECK_MODULES=/path/to/that/project.');
    process.exit(2);
}

const url = /^https?:\/\//.test(target) ? target : pathToFileURL(path.resolve(target)).href;
const W = Number(opt('width', 1440)), H = Number(opt('height', 810));

// ---- runs inside the page ----
function measure(slideSel) {
    const pick = (sel) => [...document.querySelectorAll(sel)];
    let sel = slideSel;
    if (!sel) sel = ['[data-slide]', 'section.slide', '.slide', '.reveal .slides > section', 'main > section', 'body > section'].find((s) => pick(s).length >= 2) || '';
    const slides = sel ? pick(sel) : [document.body];
    const shown = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 2 && r.height > 2 && cs.display !== 'none' && cs.visibility !== 'hidden'; };
    // The classes that make a slide the current one: on the visible slide, on none of the hidden ones.
    const vis = slides.find(shown), hid = slides.filter((s) => !shown(s));
    // Only names that mean "current" (a cover's own class is also on no other slide, and must stay put).
    const STATE = /^(is-)?(active|visible|current|present|shown?|on|selected)$/i;
    const stateCls = vis && hid.length ? [...vis.classList].filter((c) => STATE.test(c) && !hid.some((h) => h.classList.contains(c))) : [];
    const style = document.createElement('style');
    style.textContent = '*,*::before,*::after{animation:none!important;transition:none!important}';
    document.head.appendChild(style);
    const out = [];
    slides.forEach((s, i) => {
        if (slides.length > 1) {
            slides.forEach((o) => stateCls.forEach((c) => o.classList.toggle(c, o === s)));
            if (!shown(s)) { slides.forEach((o) => { o.style.display = o === s ? '' : 'none'; }); if (!shown(s)) s.style.cssText += ';display:block!important;visibility:visible!important'; }
        }
        const box = s.getBoundingClientRect();
        const texts = [];
        const walker = document.createTreeWalker(s, NodeFilter.SHOW_TEXT);
        const seen = new Set();
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
            const el = n.parentElement;
            if (!n.nodeValue.trim() || !el || seen.has(el) || el.closest('svg,script,style,[data-ds-ignore]')) continue;
            seen.add(el);
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            if (cs.display === 'none' || r.width < 1 || r.height < 1) continue;
            const fam = cs.fontFamily.split(',')[0].trim().replace(/^["']|["']$/g, '');
            if (/remixicon|icon|symbols/i.test(fam)) continue;
            texts.push({ tag: el.tagName.toLowerCase(), cls: typeof el.className === 'string' ? el.className.trim().split(/\s+/).filter(Boolean) : [],
                text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 40), font: fam, size: Math.round(parseFloat(cs.fontSize) * 10) / 10,
                weight: Number(cs.fontWeight) || 400, color: cs.color, left: Math.round(r.left - box.left), top: Math.round(r.top - box.top),
                idx: texts.length });
            el.setAttribute('data-ds-i', `${i}-${texts.length - 1}`);
        }
        // the title: a heading if there is one, else the biggest text in the upper half
        let title = texts.find((t) => /^h[12]$/.test(t.tag));
        if (!title) title = texts.filter((t) => t.top < box.height * 0.5).sort((a, b) => b.size - a.size || a.top - b.top)[0];
        out.push({ n: i + 1, name: s.getAttribute('data-title') || (title && title.text) || '', kind: [...s.classList].filter((c) => !stateCls.includes(c) && c !== 'slide').join('.'),
            free: s.hasAttribute('data-ds-free'), w: Math.round(box.width), h: Math.round(box.height), title: title ? title.idx : -1, texts });
    });
    return { selector: sel, slides: out };
}

const modeOf = (vals) => { const c = new Map(); vals.forEach((v) => c.set(v, (c.get(v) || 0) + 1)); return [...c.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]; };
const spread = (vals) => { const c = new Map(); vals.forEach((v) => c.set(v, (c.get(v) || 0) + 1)); return [...c.entries()].sort((a, b) => b[1] - a[1]); };

function tokensFrom(m) {
    const all = m.slides.flatMap((s) => s.texts.map((t) => ({ ...t, n: s.n })));
    const inSlides = (key) => { const by = new Map(); all.forEach((t) => { if (!by.has(t[key])) by.set(t[key], new Set()); by.get(t[key]).add(t.n); }); return by; };
    const need = Math.min(2, m.slides.length);            // a value is part of the system when 2+ slides use it
    const keep = (key) => [...inSlides(key).entries()].filter(([, set]) => set.size >= need).map(([v]) => v);
    const titled = m.slides.filter((s) => s.title >= 0 && !s.free && s.n > 1);   // slide 1 is the cover: laid out on its own
    const T = (s) => s.texts[s.title];
    return {
        note: 'Written by ds-check init from what the slides use now. Edit it: this file is the rule ds-check check holds every slide to.',
        source: url, viewport: [W, H], slide: m.selector,
        fonts: keep('font'), sizes: keep('size').sort((a, b) => a - b), weights: keep('weight').sort((a, b) => a - b),
        title: titled.length ? { size: modeOf(titled.map((s) => T(s).size)), weight: modeOf(titled.map((s) => T(s).weight)), left: modeOf(titled.map((s) => T(s).left)), top: modeOf(titled.map((s) => T(s).top)), tolerance: 4 } : null,
        free_slides: [1],                                   // slide numbers ds-check leaves alone for title position (cover, section breaks)
    };
}

function compare(m, tk) {
    const out = [];
    const near = (list, v, tol = 0.6) => list.some((x) => Math.abs(x - v) <= tol);
    for (const s of m.slides) {
        const add = (t, what) => out.push({ slide: s.n, name: s.name, mark: `${s.n - 1}-${t.idx}`, text: t.text, what });
        for (const t of s.texts) {
            if (tk.fonts?.length && !tk.fonts.includes(t.font)) add(t, `font ${t.font}, not in the system (${tk.fonts.join(', ')})`);
            const freeTitle = t.idx === s.title && (s.free || (tk.free_slides || []).includes(s.n));   // a cover's title may be its own size
            if (tk.sizes?.length && !near(tk.sizes, t.size) && !freeTitle) add(t, `size ${t.size}px, not in the scale (${tk.sizes.join(', ')})`);
            if (tk.weights?.length && !tk.weights.includes(t.weight)) add(t, `weight ${t.weight}, not in the system (${tk.weights.join(', ')})`);
        }
        const tt = tk.title, t = s.texts[s.title];
        if (tt && t && !s.free && !(tk.free_slides || []).includes(s.n)) {
            const tol = tt.tolerance ?? 4;
            if (Math.abs(t.size - tt.size) > 0.6) add(t, `title is ${t.size}px, the other slides use ${tt.size}px`);
            if (Math.abs(t.left - tt.left) > tol) add(t, `title starts ${t.left}px from the left, the other slides ${tt.left}px (${t.left - tt.left > 0 ? '+' : ''}${t.left - tt.left})`);
            if (Math.abs(t.top - tt.top) > tol) add(t, `title sits ${t.top}px from the top, the other slides ${tt.top}px (${t.top - tt.top > 0 ? '+' : ''}${t.top - tt.top})`);
        }
    }
    return out;
}

function humanDoc(m, tk, odd) {
    const L = [`# Design system (measured ${new Date().toISOString().slice(0, 10)})`, '',
        `Measured from ${m.slides.length} slides of ${url} at ${W}×${H}. The rule itself is tokens.json next to this file; this page is for reading.`, '',
        '## What the slides share', '',
        `- Fonts: ${tk.fonts.join(', ') || 'none found'}`, `- Type sizes (px): ${tk.sizes.join(', ')}`, `- Weights: ${tk.weights.join(', ')}`];
    if (tk.title) L.push(`- Slide title: ${tk.title.size}px, weight ${tk.title.weight}, ${tk.title.left}px from the left and ${tk.title.top}px from the top of the slide (±${tk.title.tolerance}px)`);
    L.push('', '## Odd ones out', '', odd.length ? 'Each line is one place that differs from the above. Fix the slide, or, if it is meant to differ, add the value to tokens.json (or the slide number to free_slides).' : 'None: every slide follows the above.', '');
    for (const o of odd) L.push(`- Slide ${o.slide}${o.name ? ' (' + o.name + ')' : ''}: 「${o.text}」 ${o.what}`);
    return L.join('\n') + '\n';
}

const { chromium } = loadPlaywright();
const browser = await chromium.launch();
try {
    const page = await browser.newPage({ viewport: { width: W, height: H } });
    await page.goto(url, { waitUntil: 'load', timeout: 45000 });
    await page.evaluate(() => document.fonts && document.fonts.ready).catch(() => {});
    await page.waitForTimeout(600);
    const m = await page.evaluate(measure, opt('slide', ''));
    if (mode === 'init') {
        const out = path.resolve(opt('out', 'design-system/tokens.json'));
        const tk = tokensFrom(m);
        const odd = compare(m, tk);
        fs.mkdirSync(path.dirname(out), { recursive: true });
        fs.writeFileSync(out, JSON.stringify(tk, null, 2) + '\n');
        fs.writeFileSync(path.join(path.dirname(out), 'design-system.md'), humanDoc(m, tk, odd));
        console.log(`${m.slides.length} slides measured. Wrote ${out} and design-system.md. ${odd.length} place${odd.length === 1 ? '' : 's'} already differ from what most slides use (listed in design-system.md).`);
    } else {
        const file = path.resolve(opt('tokens', 'design-system/tokens.json'));
        if (!fs.existsSync(file)) { console.error(`No ${file}. Run "ds-check init" once for this project first.`); process.exit(2); }
        const tk = JSON.parse(fs.readFileSync(file, 'utf8'));
        const bad = compare(m, tk);
        const shots = opt('shots', '');
        if (shots && bad.length) {
            fs.mkdirSync(shots, { recursive: true });
            for (const n of [...new Set(bad.map((b) => b.slide))]) {
                const marks = bad.filter((b) => b.slide === n).map((b) => b.mark);
                await page.evaluate(({ sel, n, marks, measureSrc }) => {
                    document.querySelectorAll('[data-ds-bad]').forEach((e) => { e.style.outline = ''; e.removeAttribute('data-ds-bad'); });
                    marks.forEach((k) => { const e = document.querySelector(`[data-ds-i="${k}"]`); if (e) { e.style.outline = '3px solid #e5484d'; e.style.outlineOffset = '2px'; e.setAttribute('data-ds-bad', ''); } });
                    const slides = sel ? [...document.querySelectorAll(sel)] : [document.body];
                    const cur = slides.find((s) => { const r = s.getBoundingClientRect(); return r.width > 2 && getComputedStyle(s).display !== 'none'; });
                    const state = cur ? [...cur.classList].filter((c) => /^(is-)?(active|visible|current|present|shown?|on|selected)$/i.test(c) && !slides.some((o) => o !== cur && o.classList.contains(c))) : [];
                    slides.forEach((o, i) => { state.forEach((c) => o.classList.toggle(c, i === n - 1)); if (o.style.display === 'none' || i === n - 1) o.style.display = i === n - 1 ? '' : 'none'; });
                }, { sel: m.selector, n, marks });
                await page.waitForTimeout(150);
                await page.screenshot({ path: path.join(shots, `slide-${String(n).padStart(2, '0')}.png`) });
            }
        }
        if (flag('json')) console.log(JSON.stringify({ slides: m.slides.length, differences: bad }, null, 2));
        else if (!bad.length) console.log(`ds-check: ${m.slides.length} slides, all follow ${path.basename(file)}.`);
        else {
            console.log(`ds-check: ${bad.length} difference${bad.length === 1 ? '' : 's'} on ${new Set(bad.map((b) => b.slide)).size} of ${m.slides.length} slides.`);
            for (const b of bad) console.log(`- Slide ${b.slide}${b.name ? ' (' + b.name + ')' : ''}: 「${b.text}」 ${b.what}`);
            if (shots) console.log(`Pictures of the slides that differ: ${path.resolve(shots)}`);
        }
        process.exitCode = bad.length ? 1 : 0;
    }
} finally {
    await browser.close();
}
