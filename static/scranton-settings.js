// Scranton Settings: one window, left navigation (Account / Workspace), as Slack, Linear, hilos do.
//   Profile      photo (upload / remove), name, status
//   Agents       every AI teammate: what it runs on, status, start/stop; click → agent page
//                with tabs Overview · Role card · Activity · Settings (model, permissions, autostart)
//   Connections  Claude / ChatGPT / Cursor: signed in or not, Connect opens the official sign-in
//   Updates      check for a new version
(function () {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const api = (path, body) => fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
    }).then(async (r) => { const d = await r.json().catch(() => ({})); if (!r.ok && !d.error) d.error = `Error ${r.status}`; return d; });
    const team = () => (window.scGetTeam ? window.scGetTeam() : {}) || {};
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    const avatar = (h) => (window.scAvatarHtml ? window.scAvatarHtml(h) : '');
    const state = (h) => (window.scAgentState ? window.scAgentState(h) : 'offline');
    const me = () => (window.scMe ? window.scMe() : 'You');
    const ri = {   // Remix Icon paths (Apache-2.0)
        user: 'M4 22C4 17.5817 7.58172 14 12 14C16.4183 14 20 17.5817 20 22H18C18 18.6863 15.3137 16 12 16C8.68629 16 6 18.6863 6 22H4ZM12 13C8.685 13 6 10.315 6 7C6 3.685 8.685 1 12 1C15.315 1 18 3.685 18 7C18 10.315 15.315 13 12 13ZM12 11C14.21 11 16 9.21 16 7C16 4.79 14.21 3 12 3C9.79 3 8 4.79 8 7C8 9.21 9.79 11 12 11Z',
        robot: 'M13 4.05469V2H11V4.05469C6.50005 4.55225 3 8.36707 3 13V21H21V13C21 8.36707 17.5 4.55225 13 4.05469ZM19 19H5V13C5 9.13401 8.13401 6 12 6C15.866 6 19 9.13401 19 13V19ZM12 18C14.2091 18 16 16.2091 16 14C16 11.7909 14.2091 10 12 10C9.79086 10 8 11.7909 8 14C8 16.2091 9.79086 18 12 18ZM12 16C10.8954 16 10 15.1046 10 14C10 12.8954 10.8954 12 12 12C13.1046 12 14 12.8954 14 14C14 15.1046 13.1046 16 12 16Z',
        plug: 'M13 18V20H19V22H13C11.8954 22 11 21.1046 11 20V18H8C5.79086 18 4 16.2091 4 14V7C4 6.44772 4.44772 6 5 6H8V2H10V6H14V2H16V6H19C19.5523 6 20 6.44772 20 7V14C20 16.2091 18.2091 18 16 18H13ZM8 16H16C17.1046 16 18 15.1046 18 14V11H6V14C6 15.1046 6.89543 16 8 16ZM18 8H6V9H18V8ZM12 14.5C11.4477 14.5 11 14.0523 11 13.5C11 12.9477 11.4477 12.5 12 12.5C12.5523 12.5 13 12.9477 13 13.5C13 14.0523 12.5523 14.5 12 14.5Z',
        refresh: 'M5.46257 4.43262C7.21556 2.91688 9.5007 2 12 2C17.5228 2 22 6.47715 22 12C22 14.1361 21.3302 16.1158 20.1892 17.7406L17 12H20C20 7.58172 16.4183 4 12 4C9.84982 4 7.89777 4.84827 6.46023 6.22842L5.46257 4.43262ZM18.5374 19.5674C16.7844 21.0831 14.4993 22 12 22C6.47715 22 2 17.5228 2 12C2 9.86386 2.66979 7.88416 3.8108 6.25944L7 12H4C4 16.4183 7.58172 20 12 20C14.1502 20 16.1022 19.1517 17.5398 17.7716L18.5374 19.5674Z',
        chat: 'M6.45455 19L2 22.5V4C2 3.44772 2.44772 3 3 3H21C21.5523 3 22 3.44772 22 4V18C22 18.5523 21.5523 19 21 19H6.45455ZM5.76282 17H20V5H4V18.3851L5.76282 17Z',
        close: 'M11.9997 10.5865L16.9495 5.63672L18.3637 7.05093L13.4139 12.0007L18.3637 16.9504L16.9495 18.3646L11.9997 13.4149L7.04996 18.3646L5.63574 16.9504L10.5855 12.0007L5.63574 7.05093L7.04996 5.63672L11.9997 10.5865Z',
        back: 'M10.8284 12.0007L15.7782 16.9504L14.364 18.3646L8 12.0007L14.364 5.63672L15.7782 7.05093L10.8284 12.0007Z',
        right: 'M13.1717 12.0007L8.22192 7.05093L9.63614 5.63672L16.0001 12.0007L9.63614 18.3646L8.22192 16.9504L13.1717 12.0007Z',
    };
    const icon = (k, s = 18) => (window.scIcon ? window.scIcon({ chat: 'feedback' }[k] || k, s) : '');
    const STATUSES = [['online', 'Online'], ['away', 'Away'], ['dnd', 'Do not disturb']];
    const myStatus = () => { try { return localStorage.getItem('scranton-my-status') || 'online'; } catch (_) { return 'online'; } };
    const stText = (h) => ({ working: 'Working', available: 'Online' }[state(h)] || 'Not running');

    const NAV = [
        ['Account', [['profile', 'Profile', 'user']]],
        ['Workspace', [['agents', 'Agents', 'robot'], ['connections', 'Connections', 'plug'], ['updates', 'Updates', 'refresh']]],
    ];

    let root = null;
    let section = 'profile';
    let agentOpen = null;     // handle when an agent page is open
    let agentTab = 'overview';

    function open(sec, handle) {
        section = sec || 'profile';
        agentOpen = handle || null;
        agentTab = 'overview';
        if (!root) {
            root = document.createElement('div');
            root.id = 'sc-settings';
            root.innerHTML = `<div class="sc-st" role="dialog" aria-modal="true" aria-label="Settings">
                <nav class="sc-st-nav"><div class="sc-st-title">Settings</div><div class="sc-st-navlist"></div>
                    <button type="button" class="sc-st-feedback" data-a="feedback">${icon('chat', 16)}<span>Send feedback</span></button></nav>
                <section class="sc-st-main"><button type="button" class="sc-st-x" aria-label="Close">${icon('close')}</button><div class="sc-st-body"></div></section>
            </div>`;
            document.body.appendChild(root);
            root.addEventListener('click', onClick);
            root.addEventListener('change', onChange);

        }
        renderNav();
        render();
        root.querySelector('.sc-st-x').focus();
    }
    function close() { root?.remove(); root = null; }

    function renderNav() {
        root.querySelector('.sc-st-navlist').innerHTML = NAV.map(([g, items]) => `<div class="sc-st-group">${g}</div>`
            + items.map(([id, name, ic]) => `<button type="button" class="sc-st-item${id === section ? ' on' : ''}" data-nav="${id}">${icon(ic, 18)}<span>${name}</span></button>`).join('')).join('');
    }

    async function render() {
        const body = root.querySelector('.sc-st-body');
        if (section === 'profile') body.innerHTML = profileView();
        if (section === 'agents') body.innerHTML = agentOpen ? '<div class="sc-st-loading">Loading…</div>' : agentsView();
        if (section === 'connections') { body.innerHTML = '<div class="sc-st-loading">Checking sign-ins…</div>'; body.innerHTML = connectionsView(await api('/api/scranton/connections')); }
        if (section === 'updates') body.innerHTML = updatesView();
        if (section === 'agents' && agentOpen) {
            const p = await api(`/api/scranton/teammate/${encodeURIComponent(agentOpen)}`);
            if (root && section === 'agents' && agentOpen === p.handle) body.innerHTML = agentView(p);
        }
    }

    // ---------------------------------------------------------------- Profile
    function profileView() {
        const pic = window.scMyAvatarHtml ? window.scMyAvatarHtml() : '';
        let hasPic = false;
        try { hasPic = (localStorage.getItem('scranton-me-avatar') || '').startsWith('data:image/'); } catch (_) {}
        return `<header class="sc-st-head"><h2>Profile</h2><p>How you appear to your agents and in the chat.</p></header>
            <div class="sc-pf">
                <div class="sc-pf-fields">
                    <label class="sc-field"><span>Full name</span><input id="sc-pf-name" type="text" maxlength="20" value="${esc(me())}">
                        <small>Agents address you by this name and @-mention it when they need you.</small></label>
                    <label class="sc-field"><span>Status</span>
                        <span class="sc-select"><select id="sc-pf-status">${STATUSES.map(([v, l]) => `<option value="${v}"${v === myStatus() ? ' selected' : ''}>${l}</option>`).join('')}</select></span>
                        <small>Shown on your avatar.</small></label>
                </div>
                <div class="sc-pf-photo"><span class="sc-field-label">Profile photo</span>
                    <div class="sc-pf-pic">${pic}</div>
                    <button type="button" class="sc-btn" data-a="upload">Upload photo</button>
                    ${hasPic ? '<button type="button" class="sc-link" data-a="remove-photo">Remove photo</button>' : ''}
                </div>
            </div>
            <footer class="sc-st-foot"><span class="sc-st-saved" id="sc-pf-saved"></span><button type="button" class="sc-btn primary" data-a="save-profile">Save changes</button></footer>`;
    }

    // ---------------------------------------------------------------- Agents
    function agentsView() {
        const t = team();
        const names = Object.keys(t);
        const running = names.filter((h) => state(h) !== 'offline').length;
        return `<header class="sc-st-head"><h2>Agents</h2><p>${names.length} agents · ${running} running. Click one to see its role, activity and settings.</p></header>
            <div class="sc-tbl">
                <div class="sc-tbl-h"><span>Agent</span><span>Runs on</span><span>Status</span><span></span></div>
                ${names.map((h) => `<div class="sc-tbl-r" data-agent="${esc(h)}" role="button" tabindex="0">
                    <span class="sc-ag"><span class="sc-ag-av">${avatar(h)}</span><span class="sc-ag-txt"><b>${esc(label(h))}</b><small>${esc((t[h].role || '').split(':')[0])}</small></span></span>
                    <span class="sc-tbl-dim">${esc({ claude: 'Claude', codex: 'ChatGPT', cursor: 'Cursor' }[t[h].provider] || t[h].provider || '')}</span>
                    <span><span class="sc-pill ${esc(state(h))}">${stText(h)}</span></span>
                    <span class="sc-tbl-go">${state(h) === 'offline' ? `<button type="button" class="sc-btn sm" data-start="${esc(h)}">Start</button>` : ''}${icon('right', 18)}</span>
                </div>`).join('')}
            </div>
            <p class="sc-st-note">New agents are added in <code>config.toml</code> for now.</p>`;
    }

    function agentView(p) {
        const st = p.running ? state(p.handle) : 'offline';
        const tabs = [['overview', 'Overview'], ['card', 'Role card'], ['activity', 'Activity'], ['settings', 'Settings']];
        let content = '';
        if (agentTab === 'overview') {
            content = `<dl class="sc-dl">
                <dt>Role</dt><dd>${esc(p.role || '—')}</dd>
                <dt>Runs on</dt><dd>${esc(p.provider_name)} · ${esc(p.model || 'default model')}</dd>
                <dt>Permissions</dt><dd>${p.permissions === 'full' ? 'Full: never stops to ask' : 'Asks before acting'}</dd>
                <dt>Works in</dt><dd><code>${esc(p.folder)}</code>${p.worktree ? ' · own working copy' : ''}</dd>
                <dt>Channels</dt><dd>${p.channels.length ? p.channels.map((c) => `<span class="sc-chip">#${esc(c)}</span>`).join(' ') : 'None yet'}</dd>
                <dt>@handle</dt><dd><code>@${esc(p.handle)}</code></dd></dl>`;
        } else if (agentTab === 'card') {
            const md = p.role_card_text || '';
            content = md ? `<div class="sc-card-md">${window.marked ? sanitize(window.marked.parse(md)) : `<pre>${esc(md)}</pre>`}</div><p class="sc-st-note">From <code>${esc(p.role_card)}</code></p>`
                : '<p class="sc-st-note">No role card yet. It only gets its one-line role.</p>';
        } else if (agentTab === 'activity') {
            content = p.recent.length ? `<ul class="sc-act">${p.recent.map((m) => `<li><button type="button" data-msg="${Number(m.id)}" data-ch="${esc(m.channel || 'general')}">
                <span class="sc-act-meta">${String(m.channel || '').startsWith('dm-') ? 'Direct message' : '#' + esc(m.channel || 'general')} · ${esc(String(m.time || '').slice(0, 5))}</span>
                <span class="sc-act-text">${esc(String(m.text || '').slice(0, 220))}</span></button></li>`).join('')}</ul>`
                : '<p class="sc-st-note">Nothing yet. Messages from this agent will show up here.</p>';
        } else {
            const known = p.models.map(([v]) => v);
            const custom = p.model && !known.includes(p.model);
            content = `<div class="sc-form">
                <label class="sc-field"><span>Model</span>
                    <span class="sc-select"><select data-set="model">${p.models.map(([v, l]) => `<option value="${esc(v)}"${v === p.model ? ' selected' : ''}>${esc(l)}</option>`).join('')}
                        <option value="__other"${custom ? ' selected' : ''}>Other…</option></select></span>
                    <input type="text" class="sc-other" data-set-other="model" placeholder="Model name, e.g. gpt-5" value="${custom ? esc(p.model) : ''}"${custom ? '' : ' hidden'}>
                    <small>Default uses whatever ${esc(p.provider_name)} picks for your plan.</small></label>
                <label class="sc-field"><span>Permissions</span>
                    <span class="sc-select"><select data-set="permissions"><option value="full"${p.permissions === 'full' ? ' selected' : ''}>Full: never stops to ask</option>
                        <option value="ask"${p.permissions === 'ask' ? ' selected' : ''}>Ask before acting</option></select></span></label>
                <label class="sc-toggle"><input type="checkbox" data-set="autostart"${p.autostart ? ' checked' : ''}><span class="sc-switch"></span>
                    <span>Start with Scranton</span></label>
                <div class="sc-st-saved" id="sc-ag-saved"></div>
            </div>`;
        }
        return `<button type="button" class="sc-back" data-a="back">${icon('back', 18)}<span>All agents</span></button>
            <header class="sc-agh">
                <span class="sc-agh-av">${avatar(p.handle)}<span class="sc-dot ${esc(st)}"></span></span>
                <div class="sc-agh-txt"><h2>${esc(p.label)}</h2><p>${esc((p.role || '').split(':')[0])} · <span class="sc-pill ${esc(st)}">${stText(p.handle)}</span></p></div>
                <div class="sc-agh-act">
                    <button type="button" class="sc-btn" data-a="message">Message</button>
                    ${p.running ? `<button type="button" class="sc-btn" data-agent-act="restart">Restart</button><button type="button" class="sc-btn" data-agent-act="stop">Stop</button>`
                        : '<button type="button" class="sc-btn primary" data-agent-act="start">Start</button>'}
                </div>
            </header>
            <div class="sc-tabs" role="tablist">${tabs.map(([id, n]) => `<button type="button" role="tab" class="${id === agentTab ? 'on' : ''}" data-tab="${id}">${n}</button>`).join('')}</div>
            <div class="sc-tabbody">${content}</div>`;
    }
    function sanitize(html) {
        const t = document.createElement('template');
        t.innerHTML = html;
        t.content.querySelectorAll('script,style,iframe,object,embed,link,meta,form').forEach((n) => n.remove());
        t.content.querySelectorAll('*').forEach((n) => [...n.attributes].forEach((a) => {
            if (/^on/i.test(a.name) || (/^(href|src)$/i.test(a.name) && /^\s*javascript:/i.test(a.value))) n.removeAttribute(a.name);
        }));
        return t.innerHTML;
    }

    // ---------------------------------------------------------------- Connections
    function connectionsView(list) {
        if (!Array.isArray(list)) return '<p class="sc-st-note">Couldn\'t check. Is Scranton running?</p>';
        // Brand marks from Remix Icon's Logos set, on each brand's own colour
        const badge = { claude: ['claude', '#d97757', '#fff'], codex: ['openai', '#ffffff', '#000'], cursor: ['cursor-ai', '#000000', '#fff'] };
        return `<header class="sc-st-head"><h2>Connections</h2><p>Agents run on the apps you already pay for. Sign in once per app. No API keys.</p></header>
            <div class="sc-conn">${list.map((c) => {
                const [b, col, fg] = badge[c.id] || ['robot', '#444', '#fff'];
                const status = !c.installed ? ['missing', 'Not installed'] : c.connected === true ? ['ok', `Connected${c.account ? ' · ' + esc(c.account) : ''}`]
                    : c.connected === false ? ['off', c.account ? esc(c.account) : 'Not signed in'] : ['unknown', 'Installed'];
                const used = c.teammates.length ? `${c.teammates.length} agent${c.teammates.length === 1 ? '' : 's'}: ${c.teammates.map((h) => esc(label(h))).join(', ')}` : 'No agents use it yet';
                return `<div class="sc-conn-r">
                    <span class="sc-conn-logo" style="background:${col};color:${fg}">${icon(b, 22)}</span>
                    <span class="sc-conn-txt"><b>${esc(c.name)}</b><small>${esc(c.plan)} · ${used}</small></span>
                    <span class="sc-pill ${status[0]}">${status[1]}</span>
                    ${c.installed ? `<button type="button" class="sc-btn${c.connected === true ? '' : ' primary'}" data-connect="${esc(c.id)}">${c.connected === true ? 'Sign in again' : 'Connect'}</button>`
                        : '<a class="sc-btn" href="https://github.com/lujin88/Scranton#install-on-a-mac" target="_blank" rel="noopener">How to install</a>'}
                </div>`;
            }).join('')}</div>
            <p class="sc-st-note" id="sc-conn-note">Connect opens the app's own sign-in on your Mac (a Terminal window plus your browser).</p>`;
    }

    // ---------------------------------------------------------------- Updates
    function updatesView() {
        return `<header class="sc-st-head"><h2>Updates</h2><p>Scranton checks GitHub every hour. When there's a new version, a card appears bottom-left.</p></header>
            <button type="button" class="sc-btn primary" data-a="check-update">Check now</button>`;
    }

    // ---------------------------------------------------------------- events
    async function onClick(e) {
        if (e.target === root) { close(); return; }
        const t = e.target;
        if (t.closest('.sc-st-x')) { close(); return; }
        const nav = t.closest('[data-nav]');
        if (nav) { section = nav.dataset.nav; agentOpen = null; renderNav(); render(); return; }
        const a = t.closest('[data-a]')?.dataset.a;
        if (a === 'feedback') { close(); window.scSendFeedback && window.scSendFeedback(); return; }
        if (a === 'upload') { window.scChangePicture && window.scChangePicture(); waitForPicture(); return; }
        if (a === 'remove-photo') { try { localStorage.removeItem('scranton-me-avatar'); } catch (_) {} window.scSaveAvatar && window.scSaveAvatar(''); window.scRenderMe && window.scRenderMe(); render(); return; }
        if (a === 'save-profile') { saveProfile(); return; }
        if (a === 'back') { agentOpen = null; render(); return; }
        if (a === 'message') { const h = agentOpen; close(); window.scOpenDm && window.scOpenDm(h); return; }
        if (a === 'check-update') { window.scCheckUpdate && window.scCheckUpdate(); return; }
        const tab = t.closest('[data-tab]');
        if (tab) { agentTab = tab.dataset.tab; render(); return; }
        const start = t.closest('[data-start]');
        if (start) { e.stopPropagation(); start.textContent = 'Starting…'; start.disabled = true; const r = await api(`/api/scranton/teammate/${encodeURIComponent(start.dataset.start)}`, { action: 'start' }); if (r.error) start.textContent = 'Can\'t start'; return; }
        const act = t.closest('[data-agent-act]');
        if (act) {
            act.disabled = true; act.textContent = { start: 'Starting…', stop: 'Stopping…', restart: 'Restarting…' }[act.dataset.agentAct];
            const r = await api(`/api/scranton/teammate/${encodeURIComponent(agentOpen)}`, { action: act.dataset.agentAct });
            if (r.error) { act.textContent = 'Failed'; act.title = r.error; flash('sc-ag-saved', r.error); }
            setTimeout(() => render(), 2500);
            return;
        }
        const row = t.closest('[data-agent]');
        if (row) { agentOpen = row.dataset.agent; agentTab = 'overview'; render(); return; }
        const conn = t.closest('[data-connect]');
        if (conn) {
            const r = await api(`/api/scranton/connections/${conn.dataset.connect}/login`, {});
            const note = root.querySelector('#sc-conn-note');
            if (note) note.textContent = r.ok ? `A Terminal window opened on your Mac. ${r.hint} Then come back and press Check again.` : r.error;
            conn.textContent = 'Check again'; conn.dataset.connect = ''; conn.onclick = () => render();
            return;
        }
        const msg = t.closest('[data-msg]');
        if (msg) {
            close();
            const ch = msg.dataset.ch;
            if (ch !== window.activeChannel && typeof switchChannel === 'function' && (window.channelList || []).includes(ch)) switchChannel(ch);
            setTimeout(() => { location.hash = ''; location.hash = `#msg-${msg.dataset.msg}`; }, 150);
        }
    }

    async function onChange(e) {
        const sel = e.target.closest('[data-set]');
        const other = e.target.closest('[data-set-other]');
        if (!sel && !other) return;
        let key, value;
        if (other) { key = other.dataset.setOther; value = other.value.trim(); }
        else {
            key = sel.dataset.set;
            value = sel.type === 'checkbox' ? sel.checked : sel.value;
            if (value === '__other') { const o = root.querySelector('.sc-other'); o.hidden = false; o.focus(); return; }
            if (key === 'model') { const o = root.querySelector('.sc-other'); if (o) { o.hidden = true; o.value = ''; } }
        }
        const r = await api(`/api/scranton/teammate/${encodeURIComponent(agentOpen)}`, { action: 'set', key, value });
        flash('sc-ag-saved', r.error ? r.error : r.restart_needed ? 'Saved. Restart the agent to use it.' : 'Saved.');
    }

    function saveProfile() {
        const name = root.querySelector('#sc-pf-name')?.value.trim();
        const st = root.querySelector('#sc-pf-status')?.value;
        if (name && name !== me() && window.ws && window.ws.readyState === WebSocket.OPEN) {
            window.ws.send(JSON.stringify({ type: 'update_settings', data: { username: name } }));
        }
        if (st) { try { localStorage.setItem('scranton-my-status', st); } catch (_) {} window.scPaintStatus && window.scPaintStatus(); }
        flash('sc-pf-saved', 'Saved.');
    }
    function waitForPicture() {
        let before = '';
        try { before = localStorage.getItem('scranton-me-avatar') || ''; } catch (_) {}
        const t0 = Date.now();
        const iv = setInterval(() => {
            let now = '';
            try { now = localStorage.getItem('scranton-me-avatar') || ''; } catch (_) {}
            if (!root || Date.now() - t0 > 120000) { clearInterval(iv); return; }
            if (now !== before) { clearInterval(iv); if (section === 'profile') render(); }
        }, 400);
    }
    function flash(id, text) {
        const el = root && root.querySelector('#' + id);
        if (!el) return;
        el.textContent = text;
        clearTimeout(el._t);
        el._t = setTimeout(() => { el.textContent = ''; }, 4000);
    }

    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && root) close(); });
    window.scOpenSettings = (sec, handle) => open(sec, handle);
    window.scOpenAgent = (h) => open('agents', h);
})();
