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

    // Two message boxes get the button: the main one and a thread's reply box. They share one panel.
    const SLOTS = {
        main: { input: () => document.getElementById('input'), row: () => document.getElementById('mention-toggles-row'),
                box: () => document.getElementById('input-row'), id: 'sc-agentpick-btn', fallback: () => '' },
        thread: { input: () => document.getElementById('sc-thread-input'), row: () => document.querySelector('#sc-thread .sc-thread-bar'),
                  box: () => document.querySelector('#sc-thread .sc-thread-compose'), id: 'sc-agentpick-tbtn',
                  // in a thread the agent you're talking to is already known
                  fallback: () => (window.scThreadAgent ? window.scThreadAgent() : '') || '' },
    };
    const state = { main: { btn: null, current: null }, thread: { btn: null, current: null } };
    let pop = null, slot = 'main';
    // the button and agent of the box whose panel is open
    let btn = null, current = null;

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

    function updateSlot(name) {
        const S = SLOTS[name], st = state[name];
        const input = S.input(), row = S.row();
        if (!input || !row) { if (st.btn && !st.btn.isConnected) st.btn = null; return; }
        if (!Object.keys(team()).length) { st.btn?.remove(); st.btn = null; st.current = null; if (slot === name) closePop(); return; }
        const hits = mentioned(input.value);
        const h = hits.length === 1 ? hits[0] : (hits.length ? '' : S.fallback());
        if (st.btn && st.btn.isConnected && st.current === h) return;
        if (slot === name && st.current !== h && !pop?.dataset.pinned) closePop();
        st.current = h;
        if (!st.btn || !st.btn.isConnected) {
            const b = document.createElement('button');
            b.type = 'button';
            b.id = S.id;
            b.className = 'sc-agentpick-btn';
            b.setAttribute('aria-haspopup', 'dialog');
            b.addEventListener('click', (e) => {
                e.stopPropagation();
                if (pop && slot === name) { closePop(); return; }
                closePop();
                slot = name; btn = b; current = state[name].current;
                openPop();
            });
            // after + and ⚡, in the same place in both boxes
            const anchor = row.querySelector('#sc-shortcut-btn, .sc-shortcut-btn') || row.querySelector('#sc-attach-btn, #sc-thread-attach');
            if (anchor) anchor.after(b); else row.prepend(b);
            st.btn = b;
        }
        const b = st.btn;
        b.title = h ? `${label(h)}: model and effort` : 'Agent model and effort';
        b.setAttribute('aria-label', b.title);
        b.classList.toggle('generic', !h);
        // Remix equalizer-line when no single agent is @'d
        b.innerHTML = h ? (window.scAvatarHtml ? window.scAvatarHtml(h) : esc(label(h)).slice(0, 1))
            : '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M6.17 18a3.001 3.001 0 0 1 5.66 0H22v2H11.83a3.001 3.001 0 0 1-5.66 0H2v-2h4.17Zm6-7a3.001 3.001 0 0 1 5.66 0H22v2h-4.17a3.001 3.001 0 0 1-5.66 0H2v-2h10.17Zm-6-7a3.001 3.001 0 0 1 5.66 0H22v2H11.83a3.001 3.001 0 0 1-5.66 0H2V4h4.17ZM9 6a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm6 7a1 1 0 1 0 0-2 1 1 0 0 0 0 2Zm-6 7a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"/></svg>';
        if (slot === name) { btn = b; current = h; }
    }
    function update() { updateSlot('main'); updateSlot('thread'); }

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
        await loadConns();
        if (!pop || (pop.dataset.pinned || current) !== h) return;
        render(h, p, false);
    }

    // Which AI services this Mac has (Settings → Connections), fetched once per open.
    let conns = null;
    async function loadConns() {
        try { const r = await fetch('/api/scranton/connections', { headers: H() }); if (r.ok) conns = await r.json(); } catch (_) { /* keep the old list */ }
        return conns || [];
    }
    const SHORT = { claude: 'Claude', codex: 'ChatGPT', cursor: 'Cursor' };
    const svgX = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 10.586l4.95-4.95 1.414 1.414-4.95 4.95 4.95 4.95-1.414 1.414-4.95-4.95-4.95 4.95-1.414-1.414 4.95-4.95-4.95-4.95L7.05 5.636z"/></svg>';
    const svgBack = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M10.828 12l4.95 4.95-1.414 1.414L8 12l6.364-6.364 1.414 1.414z"/></svg>';

    // Service first (Claude / ChatGPT / Cursor), then that service's model: when one plan
    // runs out, switch the agent to another in two clicks.
    function render(h, p, changed) {
        const st = (window.scAgentState && window.scAgentState(h)) || 'offline';
        const models = (p.models || []).slice();
        if (p.model && !models.some(([v]) => v === p.model)) models.push([p.model, p.model]);
        const efforts = p.efforts || [];
        const svc = (conns || []).map((c) => {
            const usable = c.installed && c.connected !== false;
            const why = !c.installed ? 'Not installed on this Mac' : c.connected === false ? 'Not signed in: Settings → Connections' : (c.plan || '');
            return `<button type="button" class="sc-ap-svc${c.id === p.provider ? ' on' : ''}" data-svc="${esc(c.id)}" title="${esc(why)}"${usable || c.id === p.provider ? '' : ' disabled'} aria-pressed="${c.id === p.provider}">${esc(SHORT[c.id] || c.name)}</button>`;
        }).join('');
        pop.innerHTML = `
            <div class="sc-ap-head">
                ${pop.dataset.pinned ? `<button type="button" class="sc-ap-tool sc-ap-back" data-a="back" title="All agents" aria-label="All agents">${svgBack}</button>` : ''}
                <span class="sc-ap-av">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span>
                <span class="sc-ap-name"><b>${esc(label(h))}</b><small class="${esc(st)}">${STATE[st] || st}</small></span>
                <button type="button" class="sc-ap-tool" data-a="close" title="Close" aria-label="Close">${svgX}</button>
            </div>
            ${svc ? `<div class="sc-ap-field"><span>Service</span><div class="sc-ap-svcs" role="group" aria-label="Service">${svc}</div></div>` : ''}
            <div class="sc-ap-row">
                <label class="sc-ap-sel"><span>Model</span><select data-k="model">${models.map(([v, l]) => `<option value="${esc(v)}"${v === (p.model || '') ? ' selected' : ''}>${esc(l || v || 'Default')}</option>`).join('')}</select></label>
                ${efforts.length ? `<label class="sc-ap-sel"><span>Thinking</span><select data-k="effort"><option value="">Automatic</option>${efforts.map((x) => `<option value="${esc(x)}"${x === p.effort ? ' selected' : ''}>${esc(x[0].toUpperCase() + x.slice(1))}</option>`).join('')}</select></label>` : ''}
            </div>
            ${changed ? `<div class="sc-ap-note"><span>${st === 'offline' ? 'Used next time it starts.' : changed === 'svc' ? 'Takes effect after a restart. It starts a fresh session.' : 'Takes effect after a restart.'}</span>${st !== 'offline' ? '<button type="button" class="sc-btn primary sm" data-a="restart">Restart now</button>' : ''}</div>`
              : `<div class="sc-ap-foot">${st !== 'offline'
                ? '<button type="button" class="sc-ap-link" data-a="restart">Restart</button><button type="button" class="sc-ap-link" data-a="stop">Stop</button>'
                : '<button type="button" class="sc-btn primary sm" data-a="start">Start</button>'}</div>`}`;
        const save = async (key, value) => {
            const r = await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, { method: 'POST', headers: H(),
                body: JSON.stringify({ action: 'set', key, value }) }).catch(() => null);
            const ok = r && r.ok && (await r.json().catch(() => ({}))).ok !== false;
            if (!ok) window.scToast && window.scToast("Couldn't save. Is Scranton running?");
            return ok;
        };
        pop.onchange = async (e) => {
            const sel = e.target.closest('[data-k]');
            if (!sel || !(await save(sel.dataset.k, sel.value))) return;
            p[sel.dataset.k] = sel.value;
            render(h, p, true);
        };
        pop.onclick = async (e) => {
            const sv = e.target.closest('[data-svc]');
            if (sv) {
                e.stopPropagation();
                if (sv.disabled || sv.dataset.svc === p.provider) return;
                sv.disabled = true;
                if (!(await save('provider', sv.dataset.svc))) { sv.disabled = false; return; }
                // the new service has its own models: load them
                let np = null;
                try { const r = await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, { headers: H() }); if (r.ok) np = await r.json(); } catch (_) { /* below */ }
                if (pop && np && np.handle) render(h, np, 'svc');
                return;
            }
            const el = e.target.closest('[data-a]');
            const a = el?.dataset.a;
            if (!a) return;
            e.stopPropagation();
            if (a === 'back') { openList(); return; }
            if (a === 'close') { closePop(); btn?.focus(); return; }
            el.disabled = true;
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
        const box = (SLOTS[slot].box() || btn).getBoundingClientRect();
        const w = pop.offsetWidth;
        pop.style.left = `${Math.max(8, Math.min(r.left - 8, window.innerWidth - w - 8))}px`;
        pop.style.bottom = `${window.innerHeight - box.top + 8}px`;
    }

    function boot() {
        const input = document.getElementById('input');
        if (!input) return;
        ['input', 'change', 'keyup', 'focus'].forEach((ev) => document.addEventListener(ev, (e) => {
            if (e.target && (e.target.id === 'input' || e.target.id === 'sc-thread-input')) update();
        }, true));
        // chips and send set .value directly; check again shortly after any click in either box
        document.addEventListener('click', (e) => { if (e.target.closest?.('#input-row, #sc-thread')) setTimeout(update, 0); });
        (window.scOnTeamChange = window.scOnTeamChange || []).push(update);
        document.addEventListener('click', (e) => { if (pop && !e.target.closest('#sc-agentpick, .sc-agentpick-btn')) closePop(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && pop) { closePop(); btn?.focus(); } });
        window.addEventListener('resize', place);
        setInterval(update, 1500);   // after send the box is cleared without an event
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
