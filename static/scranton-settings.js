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
        ['Workspace', [['agents', 'Agents', 'robot'], ['connections', 'Connections', 'plug']]],
    ];

    let root = null;
    let section = 'profile';
    let agentOpen = null;     // handle when an agent page is open
    let agentTab = 'overview';
    let editing = false;
    let newOpts = null;
    let pickingAvatar = false;

    function open(sec, handle, tab) {
        section = sec || 'profile';
        agentOpen = handle || null;
        agentTab = tab || 'overview';
        if (!root) {
            root = document.createElement('div');
            root.id = 'sc-settings';
            root.innerHTML = `<div class="sc-st" role="dialog" aria-modal="true" aria-label="Settings">
                <nav class="sc-st-nav"><div class="sc-st-title">Settings</div><div class="sc-st-navlist"></div></nav>
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
        if (section === 'agents' && agentOpen === '__new') {
            body.innerHTML = '<div class="sc-st-loading">Loading…</div>';
            newOpts = await api('/api/scranton/agents/new');
            if (root && agentOpen === '__new') body.innerHTML = addView(newOpts);
            return;
        }
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
        return `<header class="sc-st-head sc-st-head-row"><div><h2>Agents</h2><p>${names.length} agents · ${running} running</p></div>
                <button type="button" class="sc-btn primary" data-a="add-agent">${icon('add', 16)}<span>Add agent</span></button></header>
            <div class="sc-tbl">
                <div class="sc-tbl-h"><span>Agent</span><span>Runs on</span><span>Status</span><span></span></div>
                ${names.map((h) => `<div class="sc-tbl-r" data-agent="${esc(h)}" role="button" tabindex="0">
                    <span class="sc-ag"><span class="sc-ag-av">${avatar(h)}</span><span class="sc-ag-txt"><b>${esc(label(h))}</b><small>${esc((t[h].role || '').split(':')[0])}</small></span></span>
                    <span class="sc-tbl-dim">${esc({ claude: 'Claude', codex: 'ChatGPT', cursor: 'Cursor' }[t[h].provider] || t[h].provider || '')}</span>
                    <span><span class="sc-pill ${esc(state(h))}">${stText(h)}</span></span>
                    <span class="sc-tbl-go">${state(h) === 'offline' ? `<button type="button" class="sc-btn sm" data-start="${esc(h)}">Start</button>` : ''}${icon('right', 18)}</span>
                </div>`).join('')}
            </div>
`;
    }

    function addView(o) {
        const provs = [['claude', 'Claude'], ['codex', 'ChatGPT'], ['cursor', 'Cursor']];
        return `<button type="button" class="sc-back" data-a="back">${icon('back', 18)}<span>All agents</span></button>
            <header class="sc-st-head"><h2>Add agent</h2><p>It starts right away and joins the channels you pick.</p></header>
            <div class="sc-form wide">
                <div class="sc-row2">
                    <label class="sc-field"><span>Name</span><input type="text" id="sc-new-label" maxlength="40" placeholder="e.g. 数据分析师"></label>
                    <label class="sc-field"><span>@handle</span><input type="text" id="sc-new-handle" maxlength="20" placeholder="e.g. data"><small>How you @ it. Lowercase letters, numbers, dashes.</small></label>
                </div>
                <div class="sc-field"><span>Runs on</span><div class="sc-seg" role="radiogroup">${provs.map(([v, l], i) => `<label><input type="radio" name="sc-new-prov" value="${v}"${i === 0 ? ' checked' : ''}><span>${l}</span></label>`).join('')}</div></div>
                <label class="sc-field"><span>Model</span><span class="sc-select"><select id="sc-new-model">${modelOptions(o.models.claude, '')}</select></span></label>
                <label class="sc-field"><span>Role</span><textarea id="sc-new-role" rows="3" maxlength="300" placeholder="What it does, in one or two sentences."></textarea></label>
                <label class="sc-field"><span>Works in</span><span class="sc-select"><select id="sc-new-cwd">${o.folders.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join('')}</select></span></label>
                <div class="sc-field"><span>Picture</span><div class="sc-av-grid">${o.avatars.map((f, i) => `<button type="button" class="sc-av-pick${i === 0 ? ' on' : ''}" data-av="${esc(f)}" aria-label="${esc(f)}"><img src="/static/avatars/${esc(f)}" alt=""></button>`).join('')}</div></div>
                <div class="sc-field"><span>Channels</span><div class="sc-ch-picks">${o.channels.map((c) => `<label class="sc-ch-pick"><input type="checkbox" value="${esc(c)}"${c === 'lu-portfolio' ? ' checked' : ''}><span>#${esc(c)}</span></label>`).join('')}</div></div>
                <div class="sc-edit-actions"><span class="sc-st-saved err" id="sc-new-err"></span>
                    <button type="button" class="sc-btn" data-a="back">Cancel</button><button type="button" class="sc-btn primary" data-a="add-save">Add agent</button></div>
            </div>`;
    }

    function agentView(p) {
        const st = p.running ? state(p.handle) : 'offline';
        const tabs = [['overview', 'Identity'], ['terminal', 'Terminal'], ['card', 'Role card'], ['activity', 'Activity'], ['settings', 'Settings']];
        let content = '';
        if (agentTab === 'overview' && editing) {
            const inCh = new Set(p.channels);
            const chans = (window.channelList || []).filter((c) => !String(c).startsWith('dm-'));
            content = `<div class="sc-form wide">
                <label class="sc-field"><span>Name</span><input type="text" id="sc-ed-label" maxlength="40" value="${esc(p.label)}"></label>
                <label class="sc-field"><span>Role</span><textarea id="sc-ed-role" rows="3" maxlength="300">${esc(p.role)}</textarea>
                    <small>One or two sentences. Added to every task this agent gets.</small></label>
                <div class="sc-field"><span>Picture</span><div class="sc-av-grid">${p.avatars.map((f) => `<button type="button" class="sc-av-pick${f === p.avatar ? ' on' : ''}" data-av="${esc(f)}" aria-label="${esc(f)}"><img src="/static/avatars/${esc(f)}" alt=""></button>`).join('')}</div></div>
                <div class="sc-field"><span>Channels</span><div class="sc-ch-picks">${chans.map((c) => `<label class="sc-ch-pick"><input type="checkbox" value="${esc(c)}"${inCh.has(c) ? ' checked' : ''}><span>#${esc(c)}</span></label>`).join('')}</div></div>
                <div class="sc-edit-actions"><span class="sc-st-saved" id="sc-ag-saved"></span>
                    <button type="button" class="sc-btn" data-a="edit-cancel">Cancel</button><button type="button" class="sc-btn primary" data-a="edit-save">Save</button></div>
            </div>`;
        } else if (agentTab === 'overview') {
            const provs = [['claude', 'Claude', 'claude'], ['codex', 'ChatGPT', 'openai'], ['cursor', 'Cursor', 'cursor-ai']];
            const cur = provs.find((x) => x[0] === p.provider) || provs[0];
            const known = p.models.map(([v]) => v);
            const modelLabel = (p.models.find(([v]) => v === p.model) || [p.model, p.model || 'Default'])[1];
            const inCh = new Set(p.channels);
            const chans = (window.channelList || []).filter((c) => !String(c).startsWith('dm-'));
            content = `
            <div class="sc-id-card">
                <div class="sc-id-row"><span>Runs on</span>
                    <span class="sc-pick"><span class="sc-pick-logo ${cur[0]}">${icon(cur[2], 16)}</span><span>${esc(cur[1])}</span>${icon('chevron-down', 16)}
                        <select data-set="provider" aria-label="Runs on">${provs.map(([v, l]) => `<option value="${v}"${v === cur[0] ? ' selected' : ''}>${l}</option>`).join('')}</select></span></div>
                <div class="sc-id-row"><span>Model</span>
                    <span class="sc-pick"><span class="sc-pick-logo ${cur[0]}">${icon(cur[2], 16)}</span><span>${esc(p.model ? modelLabel : 'Default')}</span>${icon('chevron-down', 16)}
                        <select data-set="model" aria-label="Model">${modelOptions(p.models, p.model)}${p.model && !known.includes(p.model) ? `<option value="${esc(p.model)}" selected>${esc(p.model)}</option>` : ''}</select></span></div>
                ${p.efforts.length ? `<div class="sc-id-row"><span>Thinking</span>
                    <span class="sc-pick"><span>${esc(p.effort ? p.effort[0].toUpperCase() + p.effort.slice(1) : 'Automatic')}</span>${icon('chevron-down', 16)}
                        <select data-set="effort" aria-label="Thinking"><option value="">Automatic</option>${p.efforts.map((x) => `<option value="${x}"${x === p.effort ? ' selected' : ''}>${x[0].toUpperCase() + x.slice(1)}</option>`).join('')}</select></span></div>` : ''}
            </div>
            <div class="sc-st-saved" id="sc-ag-saved"></div>
            <label class="sc-field sc-id-instr"><span>Instructions</span>
                <textarea data-set-text="role" rows="4" maxlength="300" placeholder="What this agent does, in one or two sentences.">${esc(p.role)}</textarea>
                <small>Added to every task it gets. Its full rules are in the Role card tab.</small></label>
            <div class="sc-id-card">
                <div class="sc-id-row"><span>Name</span><input type="text" class="sc-id-input" data-set-text="label" maxlength="40" value="${esc(p.label)}"></div>
                <div class="sc-id-row top"><span>Channels</span><div class="sc-ch-picks">${chans.map((c) => `<label class="sc-ch-pick"><input type="checkbox" data-channel="${esc(c)}"${inCh.has(c) ? ' checked' : ''}><span>#${esc(c)}</span></label>`).join('')}</div></div>
                <div class="sc-id-row"><span>Works in</span><code>${esc(p.folder)}</code></div>
                <div class="sc-id-row"><span>@handle</span><code>@${esc(p.handle)}</code></div>
            </div>`;
        } else if (agentTab === 'terminal') {
            content = `<p class="sc-st-note sc-term-note">What ${esc(p.label)}'s terminal shows right now. If it's waiting on a question, answer with the keys below.</p>
                <pre class="sc-term" id="sc-term">Loading…</pre>
                <div class="sc-term-keys">${['Enter', 'Escape', 'Up', 'Down', '1', '2', '3', 'y', 'n'].map((k) => `<button type="button" class="sc-btn sm" data-key="${k}">${{ Escape: 'Esc', Up: '↑', Down: '↓' }[k] || k}</button>`).join('')}</div>`;
            setTimeout(() => pollScreen(p.handle), 0);
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
                    <span class="sc-select"><select data-set="model">${modelOptions(p.models, p.model)}
                        <option value="__other"${custom ? ' selected' : ''}>Other…</option></select></span>
                    <input type="text" class="sc-other" data-set-other="model" placeholder="Model name, e.g. gpt-5" value="${custom ? esc(p.model) : ''}"${custom ? '' : ' hidden'}>
                    <small>Default lets ${esc(p.provider_name)} pick. “Latest” follows new releases; a pinned version stays put. Models your plan doesn't include fail when the agent starts.</small></label>
                <label class="sc-field"><span>Permissions</span>
                    <span class="sc-select"><select data-set="permissions"><option value="full"${p.permissions === 'full' ? ' selected' : ''}>Full: never stops to ask</option>
                        <option value="ask"${p.permissions === 'ask' ? ' selected' : ''}>Ask before acting</option></select></span></label>
                <label class="sc-toggle"><input type="checkbox" data-set="autostart"${p.autostart ? ' checked' : ''}><span class="sc-switch"></span>
                    <span>Start with Scranton</span></label>
                <div class="sc-st-saved" id="sc-ag-saved"></div>
            </div>
            ${p.handle === 'help' ? '' : `<div class="sc-danger"><div><b>Delete agent</b><small>Stops ${esc(p.label)} and removes it from Scranton. Its messages stay in the chat.</small></div>
                <button type="button" class="sc-btn danger" data-a="delete-agent">Delete</button></div>`}`;
        }
        return `<button type="button" class="sc-back" data-a="back">${icon('back', 18)}<span>All agents</span></button>
            <header class="sc-agh">
                <button type="button" class="sc-agh-av" data-a="pick-avatar" aria-label="Change picture" title="Change picture">${avatar(p.handle)}<span class="sc-dot ${esc(st)}"></span><span class="sc-agh-edit">${icon('edit', 14)}</span></button>
                <div class="sc-agh-txt"><h2>${esc(p.label)}</h2><p>${esc((p.role || '').split(':')[0])} · <span class="sc-pill ${esc(st)}">${stText(p.handle)}</span></p></div>
                <div class="sc-agh-act">
                    <button type="button" class="sc-btn" data-a="message">Message</button>
                    ${p.running ? `<button type="button" class="sc-btn" data-agent-act="restart">Restart</button><button type="button" class="sc-btn" data-agent-act="stop">Stop</button>`
                        : '<button type="button" class="sc-btn primary" data-agent-act="start">Start</button>'}
                </div>
            </header>
            ${pickingAvatar ? `<div class="sc-av-pop"><div class="sc-av-grid">${p.avatars.map((f) => `<button type="button" class="sc-av-pick${f === p.avatar ? ' on' : ''}" data-av-set="${esc(f)}" aria-label="${esc(f)}"><img src="/static/avatars/${esc(f)}" alt=""></button>`).join('')}</div></div>` : ''}
            <div class="sc-tabs" role="tablist">${tabs.map(([id, n]) => `<button type="button" role="tab" class="${id === agentTab ? 'on' : ''}" data-tab="${id}">${n}</button>`).join('')}</div>
            <div class="sc-tabbody">${content}</div>`;
    }
    // Grouped model list: Default, then "Always the newest", "Pinned version", …
    function modelOptions(models, current) {
        const groups = [];
        for (const [v, l, g] of models) {
            let grp = groups.find((x) => x.name === (g || ''));
            if (!grp) groups.push(grp = { name: g || '', items: [] });
            grp.items.push(`<option value="${esc(v)}"${v === current ? ' selected' : ''}>${esc(l)}</option>`);
        }
        return groups.map((g) => g.name ? `<optgroup label="${esc(g.name)}">${g.items.join('')}</optgroup>` : g.items.join('')).join('');
    }
    let screenTimer = null;
    async function pollScreen(h) {
        clearTimeout(screenTimer);
        const pre = root && root.querySelector('#sc-term');
        if (!pre || agentOpen !== h || agentTab !== 'terminal') return;
        const r = await api(`/api/scranton/teammate/${encodeURIComponent(h)}/screen`);
        const atBottom = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
        pre.textContent = r.running ? (r.text || '(empty)') : 'Not running.';
        if (atBottom) pre.scrollTop = pre.scrollHeight;
        screenTimer = setTimeout(() => pollScreen(h), 1500);
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
            <div class="sc-conn-hd"><span>Default model</span></div>
            <div class="sc-conn">${list.map((c) => {
                const [b, col, fg] = badge[c.id] || ['robot', '#444', '#fff'];
                const status = !c.installed ? ['missing', 'Not installed'] : c.connected === true ? ['ok', 'Connected']
                    : c.connected === false ? ['off', 'Not signed in'] : ['unknown', 'Installed'];
                const n = c.teammates.length;
                const models = (c.models || []).map((m) => m[0] === '' ? ['', 'App default', m[2] || ''] : m);
                return `<div class="sc-conn-r">
                    <span class="sc-conn-logo" style="background:${col};color:${fg}">${icon(b, 22)}</span>
                    <span class="sc-conn-txt"><b>${esc(c.name)} <span class="sc-pill ${status[0]}"${c.account ? ` title="${esc(c.account)}"` : ''}>${status[1]}</span></b><small>${esc(c.plan)} · ${n} agent${n === 1 ? '' : 's'}</small></span>
                    ${c.installed ? `<select data-default="${esc(c.id)}" aria-label="${esc(c.name)} default model">${modelOptions(models, c.default_model || '')}</select>` : '<span></span>'}
                    ${c.installed ? `<button type="button" class="sc-btn${c.connected === true ? '' : ' primary'}" data-connect="${esc(c.id)}">${c.connected === true ? 'Switch account' : 'Connect'}</button>`
                        : '<a class="sc-btn" href="https://github.com/lujin88/Scranton#install-on-a-mac" target="_blank" rel="noopener">How to install</a>'}
                </div>`;
            }).join('')}</div>
            <p class="sc-st-note" id="sc-conn-note">Default model is for agents that don't pick their own. It applies the next time they start.</p>`;
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
        if (a === 'back') { agentOpen = null; editing = false; pickingAvatar = false; render(); return; }
        if (a === 'edit') { editing = true; render(); return; }
        if (a === 'pick-avatar') { pickingAvatar = !pickingAvatar; render(); return; }
        const avSet = t.closest('[data-av-set]');
        if (avSet) {
            const r = await api(`/api/scranton/teammate/${encodeURIComponent(agentOpen)}`, { action: 'set', key: 'avatar', value: avSet.dataset.avSet });
            pickingAvatar = false;
            if (!r.error) { window.scReloadTeam && window.scReloadTeam(); }
            setTimeout(render, 300); return;
        }
        if (a === 'add-agent') { agentOpen = '__new'; render(); return; }
        if (a === 'add-save') { addAgent(); return; }
        if (a === 'delete-agent') {
            const b = t.closest('[data-a]');
            if (!b.dataset.sure) { b.dataset.sure = '1'; b.textContent = 'Click again to delete'; setTimeout(() => { if (b.isConnected) { delete b.dataset.sure; b.textContent = 'Delete'; } }, 4000); return; }
            b.disabled = true; b.textContent = 'Deleting…';
            const r = await api('/api/scranton/agents', { action: 'delete', name: agentOpen });
            if (r.error) { b.textContent = 'Delete'; b.disabled = false; flash('sc-ag-saved', r.error); return; }
            agentOpen = null; window.scReloadTeam && window.scReloadTeam(); setTimeout(render, 400); return;
        }
        if (a === 'edit-cancel') { editing = false; render(); return; }
        if (a === 'edit-save') { saveAgent(); return; }
        const av = t.closest('[data-av]');
        if (av) { root.querySelectorAll('.sc-av-pick').forEach((b) => b.classList.toggle('on', b === av)); return; }
        if (a === 'message') { const h = agentOpen; close(); window.scOpenDm && window.scOpenDm(h); return; }
        if (a === 'check-update') { window.scCheckUpdate && window.scCheckUpdate(); return; }
        const key = t.closest('[data-key]');
        if (key) { await api(`/api/scranton/teammate/${encodeURIComponent(agentOpen)}/keys`, { key: key.dataset.key }); setTimeout(() => pollScreen(agentOpen), 300); return; }
        const tab = t.closest('[data-tab]');
        if (tab) { agentTab = tab.dataset.tab; editing = false; render(); return; }
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
        if (row) { agentOpen = row.dataset.agent; agentTab = 'overview'; editing = false; render(); return; }
        const conn = t.closest('[data-connect]');
        if (conn) {
            const r = await api(`/api/scranton/connections/${conn.dataset.connect}/login`, {});
            const note = root.querySelector('#sc-conn-note');
            if (note) note.textContent = r.ok ? `A Terminal window opened on your Mac. ${r.hint} Then come back and press Check again.` : r.error;
            conn.textContent = 'Check again'; conn.removeAttribute('data-connect'); conn.onclick = () => render();
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

    async function addAgent() {
        const val = (id) => (root.querySelector(id)?.value || '').trim();
        const btn = root.querySelector('[data-a="add-save"]');
        const err = root.querySelector('#sc-new-err');
        const body = {
            action: 'add', label: val('#sc-new-label'), handle: val('#sc-new-handle').toLowerCase(),
            provider: root.querySelector('input[name="sc-new-prov"]:checked')?.value || 'claude',
            model: root.querySelector('#sc-new-model')?.value || '', role: val('#sc-new-role'), cwd: val('#sc-new-cwd'),
            avatar: root.querySelector('.sc-av-pick.on')?.dataset.av || '',
            channels: Array.from(root.querySelectorAll('.sc-ch-pick input')).filter((i) => i.checked).map((i) => i.value),
        };
        if (!body.label || !body.handle) { err.textContent = 'Give it a name and an @handle.'; return; }
        btn.disabled = true; btn.textContent = 'Adding…';
        const r = await api('/api/scranton/agents', body);
        if (r.error) { err.textContent = r.error; btn.disabled = false; btn.textContent = 'Add agent'; return; }
        window.scReloadTeam && window.scReloadTeam();
        agentOpen = r.agent.handle; agentTab = 'overview';
        setTimeout(render, 600);
    }

    async function saveAgent() {
        const h = agentOpen;
        const btn = root.querySelector('[data-a="edit-save"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
        const post = (key, value) => api(`/api/scranton/teammate/${encodeURIComponent(h)}`, { action: 'set', key, value });
        const errors = [];
        for (const [key, value] of [['label', root.querySelector('#sc-ed-label').value], ['role', root.querySelector('#sc-ed-role').value],
            ['avatar', root.querySelector('.sc-av-pick.on')?.dataset.av || '']]) {
            const r = await post(key, value);
            if (r.error) errors.push(r.error);
        }
        // channels
        const want = Array.from(root.querySelectorAll('.sc-ch-pick input')).filter((i) => i.checked).map((i) => i.value);
        const members = (window.scChannelMembers && window.scChannelMembers()) || {};
        for (const c of Array.from(root.querySelectorAll('.sc-ch-pick input')).map((i) => i.value)) {
            const isIn = (members[c] || []).includes(h);
            const should = want.includes(c);
            if (isIn !== should && window.ws && window.ws.readyState === WebSocket.OPEN) {
                window.ws.send(JSON.stringify({ type: 'members_update', channel: c, add: should ? [h] : [], remove: should ? [] : [h] }));
            }
        }
        if (errors.length) { if (btn) { btn.disabled = false; btn.textContent = 'Save'; } flash('sc-ag-saved', errors[0]); return; }
        editing = false;
        if (window.scReloadTeam) window.scReloadTeam();
        setTimeout(render, 300);
    }

    async function onChange(e) {
        if (e.target.name === 'sc-new-prov' && newOpts) {
            const sel = root.querySelector('#sc-new-model');
            if (sel) sel.innerHTML = modelOptions(newOpts.models[e.target.value] || [['', 'Default', '']], '');
            return;
        }
        if (e.target.id && e.target.id.startsWith('sc-new-')) return;
        const def = e.target.closest('select[data-default]');
        if (def) {
            const r = await api(`/api/scranton/connections/${encodeURIComponent(def.dataset.default)}/default`, { model: def.value });
            const note = root.querySelector('#sc-conn-note');
            if (note) note.textContent = r.ok ? 'Saved. Agents pick it up the next time they start.' : (r.error || 'Couldn\'t save.');
            return;
        }
        const chk = e.target.closest('input[data-channel]');
        if (chk && agentOpen && window.ws && window.ws.readyState === WebSocket.OPEN) {
            window.ws.send(JSON.stringify({ type: 'members_update', channel: chk.dataset.channel, add: chk.checked ? [agentOpen] : [], remove: chk.checked ? [] : [agentOpen] }));
            flash('sc-ag-saved', 'Saved.');
            return;
        }
        const txt = e.target.closest('[data-set-text]');
        if (txt) {
            const r = await api(`/api/scranton/teammate/${encodeURIComponent(agentOpen)}`, { action: 'set', key: txt.dataset.setText, value: txt.value });
            flash('sc-ag-saved', r.error ? r.error : 'Saved.');
            if (!r.error && txt.dataset.setText === 'label') { window.scReloadTeam && window.scReloadTeam(); const h = root.querySelector('.sc-agh-txt h2'); if (h) h.textContent = txt.value.trim(); }
            return;
        }
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
        if (!r.error && ['provider', 'model', 'effort'].includes(key) && agentTab === 'overview') {
            if (key === 'provider') window.scReloadTeam && window.scReloadTeam();
            await render();
        }
        flash('sc-ag-saved', r.error ? r.error : r.restart_needed ? 'Saved. Press Restart (top right) to use it.' : 'Saved. Used the next time it starts.');
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
    window.scOpenAgent = (h, tab) => open('agents', h, tab);
})();
