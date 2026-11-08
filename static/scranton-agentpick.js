// Scranton: a button in the message box toolbar, always there. It opens a small panel to switch
// an agent's model and thinking effort, or restart / stop it (the Buzz pattern). When your message
// @s exactly one agent the button shows their face and opens straight to them; otherwise it opens
// a list of the team to pick from. Same settings as Settings → Agents → them.
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
        if (!Object.keys(team()).length) { btn?.remove(); btn = null; current = null; closePop(); return; }
        const hits = mentioned(input.value);
        const h = hits.length === 1 ? hits[0] : '';
        if (btn && btn.isConnected && current === h) return;
        if (current !== h && !pop?.dataset.pinned) closePop();
        current = h;
        if (!btn) {
            btn = document.createElement('button');
            btn.type = 'button';
            btn.id = 'sc-agentpick-btn';
            btn.setAttribute('aria-haspopup', 'dialog');
            btn.addEventListener('click', (e) => { e.stopPropagation(); pop ? closePop() : openPop(); });
            // after + and ⚡, so those two sit in the same place as in a thread's reply box
            const anchor = row.querySelector('#sc-shortcut-btn, .sc-shortcut-btn') || row.querySelector('#sc-attach-btn');
            if (anchor) anchor.after(btn); else row.prepend(btn);
        }
        btn.title = h ? `${label(h)}: model and effort` : 'Agent model and effort';
        btn.setAttribute('aria-label', btn.title);
        btn.classList.toggle('generic', !h);
        // Remix equalizer-line when no single agent is @'d
        btn.innerHTML = h ? (window.scAvatarHtml ? window.scAvatarHtml(h) : esc(label(h)).slice(0, 1))
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6.17 18a3.001 3.001 0 0 1 5.66 0H22v2H11.83a3.001 3.001 0 0 1-5.66 0H2v-2h4.17Zm6-7a3.001 3.001 0 0 1 5.66 0H22v2h-4.17a3.001 3.001 0 0 1-5.66 0H2v-2h10.17Zm-6-7a3.001 3.001 0 0 1 5.66 0H22v2H11.83a3.001 3.001 0 0 1-5.66 0H2V4h4.17ZM9 6a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm6 7a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm-6 7a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"/></svg>';
    }

    function closePop() { pop?.remove(); pop = null; btn?.setAttribute('aria-expanded', 'false'); }

    function openList() {
        closePop();
        pop = document.createElement('div');
        pop.id = 'sc-agentpick';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', 'Choose an agent');
        const hs = Object.keys(team());
        pop.innerHTML = `<p class="sc-ap-title">Model and effort</p><ul class="sc-ap-list">${hs.map((h) => {
            const st = (window.scAgentState && window.scAgentState(h)) || 'offline';
            return `<li><button type="button" data-h="${esc(h)}"><span class="sc-ap-av sm">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span><span class="sc-ap-li-name">${esc(label(h))}</span><small class="${esc(st)}">${STATE[st] || st}</small></button></li>`;
        }).join('')}</ul>`;
        pop.onclick = (e) => { const b = e.target.closest('[data-h]'); if (b) { e.stopPropagation(); openPop(b.dataset.h); } };
        document.body.appendChild(pop);
        place();
        btn?.setAttribute('aria-expanded', 'true');
    }

    async function openPop(pick) {
        const h = pick || current;
        if (!h) { openList(); return; }
        closePop();
        pop = document.createElement('div');
        pop.id = 'sc-agentpick';
        pop.setAttribute('role', 'dialog');
        pop.setAttribute('aria-label', `${label(h)} settings`);
        if (pick) pop.dataset.pinned = h;
        pop.innerHTML = '<p class="sc-ap-loading">Loading…</p>';
        document.body.appendChild(pop);
        place();
        btn?.setAttribute('aria-expanded', 'true');
        let p = null;
        try { const r = await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, { headers: H() }); if (r.ok) p = await r.json(); } catch (_) { /* below */ }
        if (!pop || (pop.dataset.pinned || current) !== h) return;
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
                ${pop.dataset.pinned ? `<button type="button" class="sc-ap-tool sc-ap-back" data-a="back" title="All agents" aria-label="All agents"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M10.828 12l4.95 4.95-1.414 1.414L8 12l6.364-6.364 1.414 1.414z"/></svg></button>` : ''}
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
            if (a === 'back') { e.stopPropagation(); openList(); return; }
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
