// Scranton: when your message @s exactly one agent, a button with their face appears in the
// message box toolbar. It opens a small panel to switch that agent's model and thinking effort,
// or restart / stop it (the Buzz pattern). Same settings as Settings → Agents → them.
(function () {
    'use strict';
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const H = () => ({ 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN });
    const ic = (n, s = 18) => (window.scIcon ? window.scIcon(n, s) : '');
    const team = () => (window.scGetTeam && window.scGetTeam()) || {};
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    const STATE = { working: 'Working', available: 'Online', offline: 'Not running', pending: 'Starting' };

    let btn = null, pop = null, current = null;

    // Which agents does the text @? Longest labels first, so "@UX 调研员" isn't read as "@UX".
    function mentioned(text) {
        const names = [];
        for (const h of Object.keys(team())) { names.push([h, h]); names.push([String(label(h)), h]); }
        names.sort((a, b) => b[0].length - a[0].length);
        const found = new Set();
        let rest = String(text || '');
        for (const [n, h] of names) {
            if (!n) continue;
            const tag = '@' + n;
            if (rest.includes(tag)) { found.add(h); rest = rest.split(tag).join(' '); }
        }
        return [...found];
    }

    function update() {
        const input = document.getElementById('input');
        const row = document.getElementById('mention-toggles-row');
        if (!input || !row) return;
        const hits = mentioned(input.value);
        const h = hits.length === 1 ? hits[0] : null;
        if (!h) { btn?.remove(); btn = null; current = null; closePop(); return; }
        if (btn && current === h) return;
        current = h;
        if (!btn) {
            btn = document.createElement('button');
            btn.type = 'button';
            btn.id = 'sc-agentpick-btn';
            btn.setAttribute('aria-haspopup', 'dialog');
            btn.addEventListener('click', (e) => { e.stopPropagation(); pop ? closePop() : openPop(); });
            row.querySelector('.sc-shortcut-btn, #sc-shortcut-btn')?.after(btn) || row.prepend(btn);
            if (!btn.isConnected) row.prepend(btn);
        }
        btn.title = `${label(h)}: model and effort`;
        btn.setAttribute('aria-label', btn.title);
        btn.innerHTML = window.scAvatarHtml ? window.scAvatarHtml(h) : esc(label(h)).slice(0, 1);
    }

    function closePop() { pop?.remove(); pop = null; btn?.setAttribute('aria-expanded', 'false'); }

    async function openPop() {
        const h = current;
        if (!h) return;
        closePop();
        pop = document.createElement('div');
        pop.id = 'sc-agentpick';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', `${label(h)} settings`);
        pop.innerHTML = '<p class="sc-ap-loading">Loading…</p>';
        document.body.appendChild(pop);
        place();
        btn?.setAttribute('aria-expanded', 'true');
        let p = null;
        try { const r = await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, { headers: H() }); if (r.ok) p = await r.json(); } catch (_) { /* below */ }
        if (!pop || current !== h) return;
        if (!p || !p.handle) { pop.innerHTML = '<p class="sc-ap-loading">Couldn\'t load this teammate.</p>'; return; }
        render(h, p, false);
    }

    function render(h, p, changed) {
        const st = (window.scAgentState && window.scAgentState(h)) || 'offline';
        const models = (p.models || []).slice();
        if (p.model && !models.some(([v]) => v === p.model)) models.push([p.model, p.model]);
        const efforts = p.efforts || [];
        pop.innerHTML = `
            <div class="sc-ap-head">
                <span class="sc-ap-av">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span>
                <span class="sc-ap-name"><b>${esc(label(h))}</b><small class="${esc(st)}">${STATE[st] || st}${p.provider_name ? ' · ' + esc(p.provider_name) : ''}</small></span>
                ${st !== 'offline' ? `<button type="button" class="sc-ap-tool" data-a="restart" title="Restart" aria-label="Restart">${ic('refresh')}</button>
                <button type="button" class="sc-ap-tool" data-a="stop" title="Stop" aria-label="Stop"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6 5H18C18.5523 5 19 5.44772 19 6V18C19 18.5523 18.5523 19 18 19H6C5.44772 19 5 18.5523 5 18V6C5 5.44772 5.44772 5 6 5ZM7 7V17H17V7H7Z"/></svg></button>`
                : `<button type="button" class="sc-btn primary sm" data-a="start">Start</button>`}
            </div>
            <div class="sc-ap-row">
                <label class="sc-ap-sel"><span>Model</span><select data-k="model">${models.map(([v, l]) => `<option value="${esc(v)}"${v === (p.model || '') ? ' selected' : ''}>${esc(l || v || 'Default')}</option>`).join('')}</select></label>
                ${efforts.length ? `<label class="sc-ap-sel"><span>Thinking</span><select data-k="effort"><option value="">Automatic</option>${efforts.map((x) => `<option value="${esc(x)}"${x === p.effort ? ' selected' : ''}>${esc(x[0].toUpperCase() + x.slice(1))}</option>`).join('')}</select></label>` : ''}
            </div>
            ${changed ? `<div class="sc-ap-note"><span>${st === 'offline' ? 'Used next time it starts.' : 'Takes effect after a restart.'}</span>${st !== 'offline' ? '<button type="button" class="sc-btn primary sm" data-a="restart">Restart now</button>' : ''}</div>` : ''}`;
        pop.onchange = async (e) => {
            const sel = e.target.closest('[data-k]');
            if (!sel) return;
            const r = await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, { method: 'POST', headers: H(),
                body: JSON.stringify({ action: 'set', key: sel.dataset.k, value: sel.value }) }).catch(() => null);
            const ok = r && r.ok && (await r.json().catch(() => ({}))).ok !== false;
            if (!ok) { window.scToast && window.scToast("Couldn't save. Is Scranton running?"); return; }
            p[sel.dataset.k] = sel.value;
            render(h, p, true);
        };
        pop.onclick = async (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (!a) return;
            e.target.closest('[data-a]').disabled = true;
            await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, { method: 'POST', headers: H(), body: JSON.stringify({ action: a }) }).catch(() => null);
            window.scToast && window.scToast({ restart: `Restarting ${label(h)}…`, stop: `${label(h)} stopped.`, start: `Starting ${label(h)}…` }[a]);
            closePop();
        };
        place();
    }

    function place() {
        if (!pop || !btn) return;
        // above the whole message box, so it never covers what you're typing
        const r = btn.getBoundingClientRect();
        const box = (document.getElementById('input-row') || btn).getBoundingClientRect();
        const w = pop.offsetWidth;
        pop.style.left = `${Math.max(8, Math.min(r.left - 8, window.innerWidth - w - 8))}px`;
        pop.style.bottom = `${window.innerHeight - box.top + 8}px`;
    }

    function boot() {
        const input = document.getElementById('input');
        if (!input) return;
        ['input', 'change', 'keyup', 'focus'].forEach((ev) => input.addEventListener(ev, update));
        // chips and send set .value directly; check again shortly after any click in the box
        document.getElementById('input-row')?.addEventListener('click', () => setTimeout(update, 0));
        (window.scOnTeamChange = window.scOnTeamChange || []).push(update);
        document.addEventListener('click', (e) => { if (pop && !e.target.closest('#sc-agentpick, #sc-agentpick-btn')) closePop(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && pop) { closePop(); btn?.focus(); } });
        window.addEventListener('resize', place);
        setInterval(update, 1500);   // after send the box is cleared without an event
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
