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
            <button type="button" class="sc-tool" data-t="expand" aria-label="${window.matchMedia('(max-width: 760px)').matches ? 'Back' : 'Show sidebar'}" title="${window.matchMedia('(max-width: 760px)').matches ? 'Back' : 'Show sidebar'}">${ic(window.matchMedia('(max-width: 760px)').matches ? 'back' : 'sidebar', window.matchMedia('(max-width: 760px)').matches ? 24 : 20)}</button>
            <button type="button" class="sc-tool" data-t="search" aria-label="Search">${ic('search', 20)}</button>
            <button type="button" class="sc-rail-me" data-t="me" aria-label="You: status, settings, updates" aria-haspopup="menu"></button>`;
        float.addEventListener('click', (e) => {
            const t = e.target.closest('[data-t]')?.dataset.t;
            if (t === 'expand') { e.stopPropagation(); window.scToggleDrawer && window.scToggleDrawer(); }
            if (t === 'search') document.getElementById('sc-search-btn')?.click();
            if (t === 'me') { e.stopPropagation(); window.scToggleAccountMenu && window.scToggleAccountMenu(e.target.closest('[data-t]')); }
        });
        const paintMe = () => {
            const b = float.querySelector('.sc-rail-me');
            // the picture plus your status dot, same as in the full sidebar
            if (b && window.scMyAvatarHtml) { b.innerHTML = `<span class="sc-rail-pic">${window.scMyAvatarHtml()}</span><span class="sc-me-dot"></span>`; window.scPaintStatus && window.scPaintStatus(); }
        };
        paintMe(); setTimeout(paintMe, 1500);
        (window.scOnTeamChange || []).push(paintMe);
        h.insertBefore(pill, h.firstChild);
        h.insertBefore(float, pill);
        // Details open behind a thread tab: bring them to the front instead of closing them.
        // The pill toggles this channel's details in the right panel (replacing a thread).
        pill.addEventListener('click', () => {
            const rp = window.scRightPanel;
            infoTab = 'about';
            if (isOpen() && rp && !rp.isShowingInfo()) toggleInfo(true); else toggleInfo();
        });
    }

    // ---------------------------------------------------------------- details panel
    function panel() {
        let p = document.getElementById('sc-info');
        if (!p) {
            p = document.createElement('aside');
            p.id = 'sc-info';
            p.setAttribute('aria-label', 'Details');
            // Lives inside the right panel (with the threads), under its tabs.
            const tp = document.getElementById('sc-thread');
            const head = tp && tp.querySelector('.sc-thread-head');
            if (head) head.after(p); else document.getElementById('sc-center')?.after(p);
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
        // Don't rebuild under someone typing (status changes re-render the panel every few seconds).
        if (document.getElementById('sc-ch-edit')) return;
        if (document.activeElement && document.activeElement.closest && document.activeElement.closest('#sc-info select')) return;
        const p = panel();
        const on = isOpen() && !document.body.classList.contains('sc-inbox-open');
        document.body.classList.toggle('sc-info-open', on);
        document.getElementById('sc-pane-pill')?.setAttribute('aria-expanded', String(on));
        const ch = window.activeChannel || 'general';
        if (window.scRightPanel) window.scRightPanel.info(on, isDm(ch) && team()[ch.slice(3)] ? label(ch.slice(3)) : `# ${ch}`);
        if (!on) { p.innerHTML = ''; return; }
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
                <div class="sc-info-tabs" role="tablist">${INFO_TABS.map(([k, n]) => `<button type="button" role="tab" data-itab="${k}" aria-selected="${k === agTab}">${n}</button>`).join('')}</div>
                <div class="sc-info-body" id="sc-info-body"><p class="sc-info-empty">Loading…</p></div>`;
            fill(h);
        } else {
            // Slack's channel details: About (name, topic, description, started, files) | Members
            const members = (((window.scChannelMembers && window.scChannelMembers()) || {})[ch] || []).filter((m) => team()[m]);
            const tab = 'about';
            p.innerHTML = `${close}
                <div class="sc-info-body" id="sc-ch-body"></div>`;
            const body = p.querySelector('#sc-ch-body');
            if (tab === 'members') {
                body.innerHTML = `<button type="button" class="sc-info-row sc-ch-addrow" data-i="add"><span class="sc-info-rav sc-ch-plus">${ic('add', 18)}</span><span>Add people</span></button>
                    <div class="sc-info-list">
                    ${members.map((m) => `<button type="button" class="sc-info-row" data-dm="${esc(m)}"><span class="sc-info-rav">${window.scAvatarHtml ? window.scAvatarHtml(m) : ''}</span><span>${esc(label(m))}</span><em class="${esc(state(m))}">${STATE[state(m)] || ''}</em></button>`).join('') || '<p class="sc-info-empty">Only you so far.</p>'}
                    </div>`;
            } else {
                body.innerHTML = '<p class="sc-info-empty">Loading…</p>';
                fillAbout(ch);
            }
        }
    }

    let infoTab = 'about';
    let aboutData = null;
    let aboutStale = false;
    function fmtDate(ts) { try { return new Date(ts * 1000).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }); } catch (_) { return ''; } }
    function fmtSize(n) { return !Number.isFinite(n) ? '' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`; }
    async function fillAbout(ch, editing) {
        const body = document.getElementById('sc-ch-body');
        if (!body) return;
        // Fetch once per channel; refresh after a save or a channel switch (not on every status tick).
        if (!editing && (!aboutData || aboutData.name !== ch || aboutStale)) {
            const got = await api(`/api/scranton/channel/${encodeURIComponent(ch)}/about`);
            if (got && got.name === ch) { aboutData = got; aboutStale = false; }
        }
        if ((window.activeChannel || 'general') !== ch || !document.getElementById('sc-ch-body')) return;
        if (!editing && document.getElementById('sc-ch-edit')) return;   // an edit started while we were fetching
        const d = (aboutData && aboutData.name === ch) ? aboutData : {};
        const row = (key, title, value, empty, canEdit = true) => editing === key
            ? `<div class="sc-ch-row editing"><div class="sc-ch-rt">${title}</div>
                ${key === 'description' ? `<textarea id="sc-ch-edit" rows="4" maxlength="1000">${esc(value)}</textarea>` : `<input id="sc-ch-edit" value="${esc(value)}" maxlength="${key === 'name' ? 20 : 250}">`}
                <div class="sc-ch-editbar"><button type="button" class="sc-btn sm" data-i="edit-cancel">Cancel</button><button type="button" class="sc-btn primary sm" data-i="edit-save" data-key="${key}">Save</button></div></div>`
            : `<div class="sc-ch-row"><div class="sc-ch-rt">${title}${canEdit ? `<button type="button" class="sc-ch-edit" data-i="edit" data-key="${key}">Edit</button>` : ''}</div>
                <div class="sc-ch-rv${value ? '' : ' empty'}">${value ? esc(value) : empty}</div></div>`;
        const files = (d.files || []).slice(0, 10);
        body.innerHTML = `<div class="sc-ch-card">
                ${row('name', 'Channel name', '#' + ch, '', ch !== 'general')}
                ${row('topic', 'Topic', d.topic || '', 'Add a topic: what this channel is for right now')}
                ${row('description', 'Description', d.description || '', 'Add a description')}
                ${d.started ? `<div class="sc-ch-row"><div class="sc-ch-rt">Started</div><div class="sc-ch-rv">${esc(fmtDate(d.started))}</div></div>` : ''}
                ${(() => { const ms = (((window.scChannelMembers && window.scChannelMembers()) || {})[ch] || []).filter((m) => team()[m]);
                    return `<button type="button" class="sc-ch-row sc-ch-members" data-i="members"><div class="sc-ch-rt">Members<span class="sc-ch-edit" data-i="add-people">Edit</span></div>
                        <div class="sc-ch-avs">${ms.slice(0, 6).map((m) => `<span class="sc-ch-av">${window.scAvatarHtml ? window.scAvatarHtml(m) : ''}</span>`).join('')}<em>${ms.length + 1} with you</em></div></button>`; })()}
            </div>
            <div id="sc-ch-board"></div>
            <h3 class="sc-ch-sub">Files</h3>
            ${files.length ? `<div class="sc-ch-card sc-ch-files">${files.map((f) => `<a class="sc-ch-file" href="${esc(f.url)}" target="_blank" rel="noopener">
                <span class="sc-pend-ic" aria-hidden="true"><i></i><i></i><i></i></span>
                <span class="sc-ch-fi"><b>${esc(f.name)}</b><small>${esc([label(String(f.by || '').toLowerCase()), f.time ? fmtDate(f.time) : '', fmtSize(f.size)].filter(Boolean).join(' · '))}</small></span></a>`).join('')}</div>`
                : '<p class="sc-info-empty">No files shared here yet.</p>'}`;
        if (window.scBoardFill) window.scBoardFill();   // Your asks (scranton-board.js) at the top
        const ed = document.getElementById('sc-ch-edit');
        if (ed) { ed.focus(); if (editing === 'name') ed.value = ch; ed.select && ed.select(); }
    }

    document.addEventListener('keydown', (e) => {
        const ed = e.target && e.target.id === 'sc-ch-edit' ? e.target : null;
        if (!ed) return;
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); document.querySelector('#sc-info [data-i="edit-cancel"]')?.click(); }
        if (e.key === 'Enter' && (ed.tagName === 'INPUT' || e.metaKey || e.ctrlKey)) { e.preventDefault(); document.querySelector('#sc-info [data-i="edit-save"]')?.click(); }
    }, true);

    // The same three things as the agent's Settings page (Lu, 11-10: switch the model right here)
    const INFO_TABS = [['identity', 'Identity'], ['terminal', 'Terminal'], ['activity', 'Activity']];
    let agTab = 'identity';
    let termTimer = null;
    const opts = (list, cur) => {
        const groups = [];
        for (const [v, l, g] of list || []) {
            let grp = groups.find((x) => x.name === (g || ''));
            if (!grp) groups.push(grp = { name: g || '', items: [] });
            grp.items.push(`<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(l)}</option>`);
        }
        return groups.map((g) => (g.name ? `<optgroup label="${esc(g.name)}">${g.items.join('')}</optgroup>` : g.items.join(''))).join('');
    };
    const PROVS = [['claude', 'Claude'], ['codex', 'ChatGPT'], ['cursor', 'Cursor'], ['gemini', 'Gemini']];
    const EFFS = { '': 'Automatic', low: 'Low', medium: 'Medium', high: 'High', xhigh: 'Extra high', max: 'Max' };
    async function pollTerm(h) {
        clearTimeout(termTimer);
        const pre = document.getElementById('sc-info-term');
        if (!pre || agTab !== 'terminal') return;
        const r = await api(`/api/scranton/teammate/${encodeURIComponent(h)}/screen`);
        const now = document.getElementById('sc-info-term');
        if (!now) return;
        now.textContent = r.running ? (r.text || '(empty)') : 'Not running.';
        termTimer = setTimeout(() => pollTerm(h), 2000);
    }
    async function fill(h) {
        const body = document.getElementById('sc-info-body');
        if (!body) return;
        document.querySelectorAll('#sc-info [data-itab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.itab === agTab)));
        const r = await api(`/api/scranton/teammate/${encodeURIComponent(h)}`);
        if (!document.getElementById('sc-info-body')) return;
        if (agTab === 'identity') {
            const efforts = r.efforts || [];
            body.innerHTML = `<div class="sc-info-card" data-h="${esc(h)}">
                <label class="sc-info-row"><span>Runs on</span><span class="sc-info-sel"><select data-qset="provider">${PROVS.map(([v, l]) => `<option value="${v}"${v === r.provider ? ' selected' : ''}>${l}</option>`).join('')}</select>${ic('chevron-down', 16)}</span></label>
                <label class="sc-info-row"><span>Model</span><span class="sc-info-sel"><select data-qset="model">${opts(r.models, r.model || '')}</select>${ic('chevron-down', 16)}</span></label>
                ${efforts.length ? `<label class="sc-info-row"><span>Thinking</span><span class="sc-info-sel"><select data-qset="effort">${['', ...efforts].map((e) => `<option value="${e}"${e === (r.effort || '') ? ' selected' : ''}>${EFFS[e] || e}</option>`).join('')}</select>${ic('chevron-down', 16)}</span></label>` : ''}
            </div>
            <p class="sc-info-note" id="sc-info-saved" role="status">Takes effect when it restarts.</p>
            <button type="button" class="sc-btn sm sc-info-all" data-i="settings">All settings</button>`;
            return;
        }
        if (agTab === 'terminal') {
            body.innerHTML = `<div class="sc-term-live sc-info-termlive" id="sc-info-termlive"></div>
                <div class="sc-term-keys sc-term-touch">${['Enter', 'Escape', 'Up', 'Down'].map((k) => `<button type="button" class="sc-btn sm" data-ikey="${k}">${{ Escape: 'Esc', Up: '↑', Down: '↓' }[k] || k}</button>`).join('')}</div>
                <p class="sc-info-note" id="sc-info-saved" role="status"></p>`;
            const el = document.getElementById('sc-info-termlive');
            if (el && window.scTerm) window.scTerm(el, h);
            return;
        }
        // Only what they said: no join/leave lines, times as HH:MM
        const recent = (r.recent || []).filter((m) => m.type !== 'system' && !/^\S+ (?:disconnected|connected|joined|left)\b/i.test(String(m.text || '')));
        body.innerHTML = recent.length ? `<div class="sc-info-feed">${recent.map((m) => `
            <button type="button" class="sc-info-msg" data-ch="${esc(m.channel)}" data-msg="${esc(m.id)}">
                <span class="sc-info-meta">${m.channel && m.channel.startsWith('dm-') ? 'Direct message' : '#' + esc(m.channel)} · ${esc(String(m.time || '').slice(0, 5))}</span>
                <span class="sc-info-text">${esc(String(m.text || '').slice(0, 220).replace(/@([a-z0-9_-]+)/gi, (all, h) => (team()[h] ? '@' + label(h) : all)))}</span>
            </button>`).join('')}</div>` : '<p class="sc-info-empty">No messages yet.</p>';
    }

    document.addEventListener('change', async (e) => {
        const sel = e.target.closest && e.target.closest('#sc-info select[data-qset]');
        if (!sel) return;
        const h = sel.closest('[data-h]').dataset.h;
        const r = await fetch(`/api/scranton/teammate/${encodeURIComponent(h)}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN },
            body: JSON.stringify({ action: 'set', key: sel.dataset.qset, value: sel.value }),
        }).then((x) => x.json()).catch(() => ({ error: "Couldn't save" }));
        const n = document.getElementById('sc-info-saved');
        if (n) n.textContent = r.error ? r.error : (state(h) === 'offline' ? 'Saved.' : 'Saved. Restart it (⋯ → Restart) to use this now.');
        window.scReloadTeam && window.scReloadTeam();
        if (!r.error && sel.dataset.qset === 'provider') { sel.blur(); fill(h); }
    });

    const p_menu = () => document.querySelector('#sc-info .sc-info-menu');
    async function onPanelClick(e) {
        const t = e.target;
        if (!t.closest('[data-i="more"]')) p_menu()?.remove();
        const i = t.closest('[data-i]')?.dataset.i;
        const ch = window.activeChannel || 'general';
        if (i === 'close') return toggleInfo(false);
        if (i === 'add-people') return window.scAddPeople ? window.scAddPeople() : document.getElementById('sc-members-btn')?.click();
        if (i === 'members') return document.getElementById('sc-members-btn')?.click();
        if (i === 'edit') return fillAbout(ch, t.closest('[data-key]').dataset.key);
        if (i === 'edit-cancel') return fillAbout(ch);
        if (i === 'edit-save') {
            const key = t.closest('[data-key]').dataset.key;
            const v = (document.getElementById('sc-ch-edit') || {}).value || '';
            const ed = document.getElementById('sc-ch-edit');
            if (key === 'name') {
                const nn = v.trim().toLowerCase().replace(/^#/, '');
                if (nn === ch) return fillAbout(ch);
                // Same rule as the server: lowercase letters, digits, - and _, up to 20.
                if (!/^[a-z0-9][a-z0-9_-]{0,19}$/.test(nn) || nn.startsWith('dm-')) {
                    window.scToast && window.scToast('Use lowercase letters, numbers, - or _ (up to 20).'); ed?.focus(); return;
                }
                if ((window.channelList || []).includes(nn)) { window.scToast && window.scToast(`#${nn} already exists.`); ed?.focus(); return; }
                if (window.ws && window.ws.readyState === WebSocket.OPEN) {
                    window.ws.send(JSON.stringify({ type: 'channel_rename', old_name: ch, new_name: nn }));
                }
                ed?.remove();   // the panel follows the rename when the server confirms it
                return;
            }
            const r = await fetch(`/api/scranton/channel/${encodeURIComponent(ch)}/about`, {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN },
                body: JSON.stringify({ [key]: v }),
            }).catch(() => null);
            if (!r || !r.ok) { window.scToast && window.scToast("Couldn't save. Is Scranton running?"); return; }
            aboutStale = true;
            ed?.remove();
            return fillAbout(ch);
        }
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
        const tab = t.closest('[data-itab]');
        if (tab) { agTab = tab.dataset.itab; return fill(ch.slice(3)); }
        const key = t.closest('[data-ikey]');
        const post = (path, body) => fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN }, body: JSON.stringify(body) }).then((r) => r.json()).catch(() => ({ error: 'Scranton isn\'t answering' }));
        if (key) {
            const r = await post(`/api/scranton/teammate/${encodeURIComponent(ch.slice(3))}/keys`, { key: key.dataset.ikey });
            const n = document.getElementById('sc-info-saved'); if (n) n.textContent = r.error ? `Didn't reach the terminal: ${r.error}` : '';
            setTimeout(() => pollTerm(ch.slice(3)), 400);
            return;
        }
        if (t.closest('[data-iopen]')) {
            const r = await post(`/api/scranton/teammate/${encodeURIComponent(ch.slice(3))}/open-terminal`, {});
            const n = document.getElementById('sc-info-saved'); if (n) n.textContent = r.error || 'Opened in Terminal. Close that window when you\'re done; it keeps running.';
            return;
        }
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
            box.innerHTML = `<span class="sc-empty-av sc-empty-hash">#</span><h3>${esc(ch)}</h3><p class="sc-empty-hint">@ someone to give them a task.</p>${ch !== 'general' && !ch.startsWith('dm-') && !((((window.scChannelMembers && window.scChannelMembers()) || {})[ch] || []).length) ? `<button type="button" class="sc-btn primary sc-empty-add" onclick="window.scAddPeople && window.scAddPeople()">${window.scIcon ? window.scIcon('add', 16) : '+'}Add people</button>` : ''}`;
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

    // ---------------------------------------------------------------- resizable side panels
    // Drag the left edge of the thread or details panel. The width is remembered.
    function makeResizable(panel, key, cssVar) {
        if (!panel || panel.querySelector(':scope > .sc-resize')) return;
        const saved = Number(LS.get(key, '0'));
        if (saved) document.documentElement.style.setProperty(cssVar, saved + 'px');
        const h = document.createElement('div');
        h.className = 'sc-resize';
        h.setAttribute('role', 'separator');
        h.setAttribute('aria-orientation', 'vertical');
        h.setAttribute('aria-label', 'Resize panel');
        h.tabIndex = 0;
        panel.prepend(h);
        const clamp = (w) => Math.round(Math.max(300, Math.min(w, Math.min(900, window.innerWidth * 0.6))));
        const set = (w) => { w = clamp(w); document.documentElement.style.setProperty(cssVar, w + 'px'); LS.set(key, String(w)); };
        h.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            h.setPointerCapture(e.pointerId);
            document.body.classList.add('sc-resizing');
            const right = panel.getBoundingClientRect().right;
            const move = (ev) => set(right - ev.clientX);
            const up = () => { h.removeEventListener('pointermove', move); document.body.classList.remove('sc-resizing'); };
            h.addEventListener('pointermove', move);
            h.addEventListener('pointerup', up, { once: true });
            h.addEventListener('pointercancel', up, { once: true });
        });
        h.addEventListener('dblclick', () => { document.documentElement.style.removeProperty(cssVar); LS.set(key, '0'); });
        h.addEventListener('keydown', (e) => {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            e.preventDefault();
            set(panel.getBoundingClientRect().width + (e.key === 'ArrowLeft' ? 24 : -24));
        });
    }
    function initResize() {
        makeResizable(document.getElementById('sc-thread'), 'scranton-thread-w', '--sc-thread-w');
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(initResize, 500));
    else setTimeout(initResize, 500);
})();
