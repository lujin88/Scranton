// Scranton layout (Grok Bot style): no top bar. Sidebar tools (collapse, search) sit at the top
// of the sidebar; the conversation uses the full height with a floating name pill top-left.
// Clicking the pill opens a details panel on the right (agent profile or channel members).
(function () {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const ic = (n, s) => (window.scIcon ? window.scIcon(n, s || 18) : '');
    const LS = {
        get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (_) { return d; } },
        set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
    };
    const api = (path) => fetch(path, { headers: { 'X-Session-Token': window.SESSION_TOKEN } }).then((r) => r.json()).catch(() => ({}));
    const isDm = (ch) => String(ch || '').startsWith('dm-');
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    const team = () => (window.scGetTeam ? window.scGetTeam() : {}) || {};
    const state = (h) => (window.scAgentState ? window.scAgentState(h) : 'offline');
    const STATE = { working: 'Working', available: 'Online', offline: 'Not running' };

    function tools() {
        const side = document.getElementById('channel-sidebar');
        if (!side || document.getElementById('sc-side-tools')) return;
        const bar = document.createElement('div');
        bar.id = 'sc-side-tools';
        bar.innerHTML = `
            <button type="button" class="sc-tool" data-t="collapse" aria-label="Hide sidebar" title="Hide sidebar">${ic('sidebar', 20)}</button>
            <button type="button" class="sc-tool" data-t="search" aria-label="Search" title="Search (${/Mac/.test(navigator.platform) ? '⌘' : 'Ctrl+'}K)">${ic('search', 20)}</button>`;
        side.insertBefore(bar, side.firstChild);
        bar.addEventListener('click', (e) => {
            const t = e.target.closest('[data-t]')?.dataset.t;
            if (t === 'collapse') window.scToggleDrawer && window.scToggleDrawer();
            if (t === 'search') document.getElementById('sc-search-btn')?.click();
        });
    }

    // The pane head floats over the messages: [expand+search when collapsed] [name pill] ... [members]
    function head() {
        const h = document.getElementById('sc-pane-head');
        if (!h || h.dataset.sc === '1') return;
        h.dataset.sc = '1';
        const icon = document.getElementById('sc-pane-icon');
        const title = document.getElementById('sc-pane-title');
        const pill = document.createElement('button');
        pill.type = 'button';
        pill.id = 'sc-pane-pill';
        pill.setAttribute('aria-label', 'Details');
        pill.appendChild(icon); pill.appendChild(title);
        pill.insertAdjacentHTML('beforeend', `<span class="sc-pill-chev">${ic('right', 16)}</span>`);
        const float = document.createElement('div');
        float.id = 'sc-float-tools';
        float.innerHTML = `
            <button type="button" class="sc-tool" data-t="expand" aria-label="Show sidebar" title="Show sidebar">${ic('sidebar', 20)}</button>
            <button type="button" class="sc-tool" data-t="search" aria-label="Search">${ic('search', 20)}</button>`;
        float.addEventListener('click', (e) => {
            const t = e.target.closest('[data-t]')?.dataset.t;
            if (t === 'expand') { e.stopPropagation(); window.scToggleDrawer && window.scToggleDrawer(); }
            if (t === 'search') document.getElementById('sc-search-btn')?.click();
        });
        h.insertBefore(pill, h.firstChild);
        h.insertBefore(float, pill);
        pill.addEventListener('click', () => toggleInfo());
    }

    // ---------------------------------------------------------------- details panel
    function panel() {
        let p = document.getElementById('sc-info');
        if (!p) {
            p = document.createElement('aside');
            p.id = 'sc-info';
            p.setAttribute('aria-label', 'Details');
            document.getElementById('sc-center')?.after(p);
            p.addEventListener('click', onPanelClick);
        }
        return p;
    }
    function isOpen() { return LS.get('scranton-info-open', '0') === '1'; }
    function toggleInfo(force) {
        const on = typeof force === 'boolean' ? force : !isOpen();
        LS.set('scranton-info-open', on ? '1' : '0');
        render();
    }
    window.scToggleInfo = toggleInfo;

    async function render() {
        const p = panel();
        const on = isOpen() && !document.body.classList.contains('sc-inbox-open');
        document.body.classList.toggle('sc-info-open', on);
        document.getElementById('sc-pane-pill')?.setAttribute('aria-expanded', String(on));
        if (!on) { p.innerHTML = ''; return; }
        const ch = window.activeChannel || 'general';
        const close = `<button type="button" class="sc-tool sc-info-x" data-i="close" aria-label="Close">${ic('close', 20)}</button>`;
        if (isDm(ch) && team()[ch.slice(3)]) {
            const h = ch.slice(3);
            const st = state(h);
            // Calm by default: who they are and what they did. Restart, Terminal and Settings live under ⋯.
            p.innerHTML = `${close}
                <button type="button" class="sc-tool sc-info-more" data-i="more" aria-label="More" title="More">${ic('more', 20)}</button>
                <div class="sc-info-hero">
                    <span class="sc-info-av">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span>
                    <h2>${esc(label(h))}</h2>
                    <p class="sc-info-st ${esc(st)}"><span></span>${STATE[st] || st}</p>
                    ${st === 'offline' ? `<div class="sc-info-actions"><button type="button" class="sc-btn primary" data-i="start">Start</button></div>` : ''}
                </div>
                <div class="sc-info-body" id="sc-info-body"><p class="sc-info-empty">Loading…</p></div>`;
            fill(h);
        } else {
            const members = (((window.scChannelMembers && window.scChannelMembers()) || {})[ch] || []).filter((m) => team()[m]);
            p.innerHTML = `${close}
                <div class="sc-info-hero">
                    <span class="sc-info-av sc-info-hash">#</span>
                    <h2>${esc(ch)}</h2>
                    <p class="sc-info-st">${members.length + 1} member${members.length ? 's' : ''}</p>
                    <div class="sc-info-actions"><button type="button" class="sc-btn" data-i="add">Add people</button></div>
                </div>
                <div class="sc-info-body"><div class="sc-info-list">
                    ${members.map((m) => `<button type="button" class="sc-info-row" data-dm="${esc(m)}"><span class="sc-info-rav">${window.scAvatarHtml ? window.scAvatarHtml(m) : ''}</span><span>${esc(label(m))}</span><em class="${esc(state(m))}">${STATE[state(m)] || ''}</em></button>`).join('') || '<p class="sc-info-empty">Only you so far.</p>'}
                </div></div>`;
        }
    }

    async function fill(h) {
        const body = document.getElementById('sc-info-body');
        if (!body) return;
        const r = await api(`/api/scranton/teammate/${encodeURIComponent(h)}`);
        // Only what they said: no join/leave lines, times as HH:MM
        const recent = (r.recent || []).filter((m) => m.type !== 'system' && !/^\S+ (?:disconnected|connected|joined|left)\b/i.test(String(m.text || '')));
        body.innerHTML = recent.length ? `<div class="sc-info-feed">${recent.map((m) => `
            <button type="button" class="sc-info-msg" data-ch="${esc(m.channel)}" data-msg="${esc(m.id)}">
                <span class="sc-info-meta">${m.channel && m.channel.startsWith('dm-') ? 'Direct message' : '#' + esc(m.channel)} · ${esc(String(m.time || '').slice(0, 5))}</span>
                <span class="sc-info-text">${esc(String(m.text || '').slice(0, 220).replace(/@([a-z0-9_-]+)/gi, (all, h) => (team()[h] ? '@' + label(h) : all)))}</span>
            </button>`).join('')}</div>` : '<p class="sc-info-empty">No messages yet.</p>';
    }

    const p_menu = () => document.querySelector('#sc-info .sc-info-menu');
    async function onPanelClick(e) {
        const t = e.target;
        if (!t.closest('[data-i="more"]')) p_menu()?.remove();
        const i = t.closest('[data-i]')?.dataset.i;
        const ch = window.activeChannel || 'general';
        if (i === 'close') return toggleInfo(false);
        if (i === 'more') {
            const b = t.closest('[data-i]');
            let m = p_menu();
            if (m) { m.remove(); return; }
            const st = state(ch.slice(3));
            m = document.createElement('div');
            m.className = 'sc-info-menu';
            m.innerHTML = `${st !== 'offline' ? `<button type="button" data-i="restart">${ic('refresh', 18)}<span>Restart</span></button>` : ''}
                <button type="button" data-i="settings">${ic('settings', 18)}<span>Settings</span></button>`;
            panel().appendChild(m);
            m.style.top = `${b.offsetTop + b.offsetHeight + 4}px`;
            return;
        }
        if (i === 'settings') return window.scOpenAgent && window.scOpenAgent(ch.slice(3));
        if (i === 'add') return document.getElementById('sc-members-btn')?.click();
        if (i === 'start' || i === 'restart') {
            const b = t.closest('[data-i]');
            if (i === 'start') { b.disabled = true; b.textContent = 'Starting…'; }
            await fetch(`/api/scranton/teammate/${encodeURIComponent(ch.slice(3))}`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN },
                body: JSON.stringify({ action: i }),
            }).catch(() => {});
            setTimeout(render, 4000);
            return;
        }
        const dm = t.closest('[data-dm]');
        if (dm && window.scOpenDm) return window.scOpenDm(dm.dataset.dm);
        const msg = t.closest('[data-msg]');
        if (msg) {
            const c = msg.dataset.ch;
            if (c !== window.activeChannel && typeof switchChannel === 'function') switchChannel(c);
            setTimeout(() => { location.hash = ''; location.hash = `#msg-${msg.dataset.msg}`; }, 150);
        }
    }

    // Empty conversation: say whose room this is and what to do, instead of a blank sheet.
    function renderEmpty() {
        const center = document.getElementById('sc-center');
        const list = document.getElementById('messages');
        if (!center || !list) return;
        const ch = window.activeChannel || 'general';
        const has = [...list.querySelectorAll('.message')].some((m) => m.offsetParent !== null && !m.classList.contains('join-msg'));
        let box = document.getElementById('sc-empty-room');
        const inboxOpen = !document.getElementById('sc-inbox')?.classList.contains('hidden');
        if (has || inboxOpen) { box?.remove(); return; }
        if (!box) { box = document.createElement('div'); box.id = 'sc-empty-room'; box.className = 'sc-empty'; center.appendChild(box); }
        const key = ch + '|' + Object.keys(team()).length;
        if (box.dataset.k === key) return;
        box.dataset.k = key;
        if (isDm(ch) && team()[ch.slice(3)]) {
            const h = ch.slice(3), t = team()[h] || {};
            box.innerHTML = `<span class="sc-empty-av">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span><h3>${esc(label(h))}</h3>
                ${t.role ? `<p>${esc(String(t.role).split(/[|｜:：]/)[0].trim().slice(0, 80))}</p>` : ''}<p class="sc-empty-hint">Ask anything. They start when you send.</p>`;
        } else {
            box.innerHTML = `<span class="sc-empty-av sc-empty-hash">#</span><h3>${esc(ch)}</h3><p class="sc-empty-hint">@ someone to give them a task.</p>`;
        }
    }

    function init() {
        tools(); head();
        setInterval(renderEmpty, 800);
        const title = document.getElementById('sc-pane-title');
        if (title) new MutationObserver(() => render()).observe(title, { childList: true, characterData: true, subtree: true });
        (window.scOnTeamChange || (window.scOnTeamChange = [])).push(() => { if (isOpen()) render(); });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && isOpen() && !window.scEscTaken) toggleInfo(false);
        });
        render();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();

    // ---------------------------------------------------------------- presence
    // Tell the server Lu is looking (at most once a minute). Back after a long break,
    // the project manager sends everything that needs her in one list.
    let lastPing = 0;
    function ping() {
        if (document.hidden || Date.now() - lastPing < 60000) return;
        lastPing = Date.now();
        fetch('/api/scranton/presence', { method: 'POST', headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {});
    }
    document.addEventListener('visibilitychange', ping);
    ['pointerdown', 'keydown'].forEach((ev) => document.addEventListener(ev, ping, { passive: true }));
    setTimeout(ping, 3000);
})();
