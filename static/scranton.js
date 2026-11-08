// Scranton layer on top of agentchattr's UI.
// - channels always in the left sidebar (Slack/Buzz layout)
// - right "Team" panel: every agent with a live status line
// - phone: sidebar and team panel become slide-in drawers
// Loaded after chat.js so it can wrap buildStatusPills/updateStatus.

(function () {
    // agentchattr's first-run tour points at controls Scranton hides. Skip it.
    try { localStorage.setItem('help_seen', '1'); } catch (_) { /* private mode */ }

    const STATE_TEXT = {
        working: 'Working',
        available: 'Online',
        offline: 'Not running',
        pending: 'Starting',
    };
    let lastStatus = {};
    let scTeam = {};   // from /api/scranton/team: label, role, provider, avatar per config entry

    function baseOf(name) {
        const cfg = (typeof agentConfig !== 'undefined' && agentConfig[name]) || {};
        if (cfg.base && scTeam[cfg.base]) return cfg.base;
        if (scTeam[name]) return name;
        const stripped = name.replace(/-\d+$/, '');
        return scTeam[stripped] ? stripped : name;
    }

    function labelOf(name) {
        if (name === 'grok') return '幕僚长 (Grok)';   // Grok Bot, posting through scranton.sh grok
        const c = (typeof agentConfig !== 'undefined' && agentConfig[name]) || scTeam[baseOf(name)] || {};
        return c.label || name;
    }

    function escAttr(v) {
        return String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    function avatarHtml(name) {
        if (name === 'grok') return '<span class="sc-grok-av" aria-hidden="true">G</span>';
        const t = scTeam[baseOf(name)];
        // Server only returns /static/avatars/<plain file name>; escape anyway.
        if (t && t.avatar && /^\/static\/avatars\/[^/]+$/.test(t.avatar)) return `<img src="${escAttr(t.avatar)}" alt="" loading="lazy">`;
        if (t && t.provider && typeof BRAND_AVATARS !== 'undefined' && BRAND_AVATARS[t.provider]) return BRAND_AVATARS[t.provider];
        return '';
    }

    async function loadTeam() {
        try {
            const r = await fetch('/api/scranton/team', { headers: { 'X-Session-Token': SESSION_TOKEN } });
            if (r.ok) scTeam = await r.json();
        } catch (_) { /* server restarting */ }
        renderTeam();
        refreshMessageAvatars();
    }

    function refreshMessageAvatars() {
        document.querySelectorAll('.avatar-wrap[data-agent]').forEach((wrap) => {
            const html = avatarHtml(wrap.dataset.agent || '');
            const av = wrap.querySelector('.avatar');
            if (html && av && av.dataset.sc !== '1') { av.innerHTML = html; av.dataset.sc = '1'; }
        });
    }

    // Messages: use the teammate's portrait (or its CLI's icon) instead of a generic person.
    if (typeof getAvatarSvg === 'function') {
        const origAvatar = getAvatarSvg;
        getAvatarSvg = function (sender) {
            return avatarHtml(String(sender || '').toLowerCase()) || origAvatar.apply(this, arguments);
        };
    }

    function agentState(name) {
        const pill = document.getElementById(`status-${name}`);
        if (!pill) return 'offline';
        for (const s of ['working', 'pending', 'available', 'offline']) {
            if (pill.classList.contains(s)) return s;
        }
        return 'offline';
    }

    function renderTeam() {
        const list = document.getElementById('team-list');
        if (!list || typeof agentConfig === 'undefined') return;
        list.innerHTML = '';
        const names = Object.keys(agentConfig);
        const covered = new Set(names.map(baseOf));
        for (const key of Object.keys(scTeam)) if (!covered.has(key)) names.push(key);
        if (!names.length) {
            const empty = document.createElement('div');
            empty.className = 'team-empty';
            empty.textContent = 'No agents running. Start one in Settings → Agents.';
            list.appendChild(empty);
            return;
        }
        // Working first, then available, then the rest; stable by label inside a group.
        const order = { working: 0, pending: 1, available: 2, offline: 3 };
        names.sort((a, b) => {
            const d = order[agentState(a)] - order[agentState(b)];
            if (d) return d;
            return labelOf(a).localeCompare(labelOf(b));
        });
        for (const name of names) {
            const t = scTeam[baseOf(name)] || {};
            const cfg = agentConfig[name] || { label: t.label };
            const state = agentState(name);
            const info = lastStatus[name] || {};
            const color = (typeof colorOverrides !== 'undefined' && colorOverrides[name]) || info.color || cfg.color || '#888';
            const role = (typeof _agentRoles !== 'undefined' && _agentRoles[name]) || info.role || t.role || '';

            const row = document.createElement('button');
            row.type = 'button';
            row.className = `team-row ${state}`;
            row.style.setProperty('--agent-color', color);
            row.title = state === 'offline' && !agentConfig[name]
                ? `@${name} · not running (./scranton.sh start ${name})`
                : `@${name}`;

            const avatar = document.createElement('span');
            avatar.className = 'team-avatar';
            const pic = avatarHtml(name);
            if (pic) { avatar.innerHTML = pic; avatar.classList.add('has-pic'); }
            else avatar.textContent = (cfg.label || name).trim().charAt(0).toUpperCase();
            const dot = document.createElement('span');
            dot.className = 'team-dot';
            avatar.appendChild(dot);

            const text = document.createElement('span');
            text.className = 'team-text';
            const nm = document.createElement('span');
            nm.className = 'team-name';
            nm.textContent = cfg.label || name;
            const st = document.createElement('span');
            st.className = 'team-state';
            const roleShort = role.split(/[:：]/)[0];
            st.textContent = `@${name} · ${STATE_TEXT[state]}`;
            if (roleShort && roleShort !== (cfg.label || name)) st.textContent += ` · ${roleShort}`;
            text.append(nm, st);

            row.append(avatar, text);
            // Reuse agentchattr's popover (rename, role, color) anchored to the hidden pill.
            // Click: put "@name " in the composer (the most common action).
            row.addEventListener('click', (e) => { e.stopPropagation(); insertMention(name); });
            // Gear: rename / role / colour (agentchattr's popover), placed next to this row.
            if (document.getElementById(`status-${name}`)) {
                const gear = document.createElement('span');
                gear.className = 'team-edit';
                gear.title = 'Name, role, colour';
                gear.setAttribute('role', 'button');
                gear.textContent = '⋯';
                gear.addEventListener('click', (e) => {
                    e.stopPropagation();
                    document.getElementById(`status-${name}`).click();
                    const pop = document.querySelector('.pill-popover');
                    if (pop) {
                        const r = row.getBoundingClientRect();
                        const w = 280;
                        let left = r.left - w - 8;
                        if (left < 12) left = Math.max(12, Math.min(r.left, window.innerWidth - w - 12));
                        pop.style.left = `${left}px`;
                        pop.style.top = `${Math.max(12, Math.min(r.top, window.innerHeight - 320))}px`;
                        pop.style.transform = 'none';
                    }
                });
                row.appendChild(gear);
            }
            list.appendChild(row);
        }
        updateWorkingCount();
    }

    function insertMention(name) {
        const input = document.getElementById('input');
        if (!input) return;
        const sep = input.value && !input.value.endsWith(' ') ? ' ' : '';
        input.value = `${input.value}${sep}@${name} `;
        input.focus();
        closeDrawers();
    }

    function updateWorkingCount() {
        const btn = document.getElementById('sc-team-btn');
        if (!btn || typeof agentConfig === 'undefined') return;
        const n = Object.keys(agentConfig).filter((a) => agentState(a) === 'working').length;
        const badge = btn.querySelector('.sc-team-badge');
        badge.textContent = n ? String(n) : '';
        badge.classList.toggle('hidden', !n);
    }

    // --- wrap agentchattr's status functions ---
    if (typeof buildStatusPills === 'function') {
        const origBuild = buildStatusPills;
        buildStatusPills = function () { origBuild.apply(this, arguments); renderTeam(); };
    }
    if (typeof updateStatus === 'function') {
        const origUpdate = updateStatus;
        updateStatus = function (data) {
            origUpdate.apply(this, arguments);
            if (data && typeof data === 'object') {
                for (const [k, v] of Object.entries(data)) if (k !== 'paused') lastStatus[k] = v;
            }
            renderTeam();
        };
    }

    // --- drawers (phone) ---
    function closeDrawers() {
        document.body.classList.remove('sc-drawer-channels', 'sc-drawer-team');
    }
    window.scToggleDrawer = function () {
        const on = !document.body.classList.contains('sc-drawer-channels');
        closeDrawers();
        document.body.classList.toggle('sc-drawer-channels', on);
    };
    window.scToggleTeam = function () {
        const on = !document.body.classList.contains('sc-drawer-team');
        closeDrawers();
        document.body.classList.toggle('sc-drawer-team', on);
    };

    function addTeamButton() {
        const right = document.querySelector('.header-right');
        if (!right || document.getElementById('sc-team-btn')) return;
        const btn = document.createElement('button');
        btn.id = 'sc-team-btn';
        btn.className = 'settings-btn sc-team-btn';
        btn.title = 'Team';
        btn.setAttribute('aria-label', 'Team');
        btn.innerHTML = (window.scIcon ? window.scIcon('team', 18) : '') + '<span class="sc-team-badge hidden"></span>';
        btn.addEventListener('click', (e) => { e.stopPropagation(); window.scToggleTeam(); });
        right.insertBefore(btn, right.firstChild);
    }

    // "+" at the start of the composer's bottom row: upload files (drag-and-drop and ⌘V paste work too)
    function addAttachButton(chips) {
        if (!chips || document.getElementById('sc-attach-btn')) return;
        const btn = document.createElement('button');
        btn.id = 'sc-attach-btn';
        btn.type = 'button';
        btn.title = 'Attach files (or drag them in, or paste with ⌘V)';
        btn.setAttribute('aria-label', 'Attach files');
        btn.innerHTML = window.scIcon ? window.scIcon('add', 18) : '+';
        const file = document.createElement('input');
        file.type = 'file'; file.multiple = true; file.hidden = true; file.id = 'sc-attach-file';
        let pop = null;
        const close = () => { if (pop) { pop.remove(); pop = null; btn.setAttribute('aria-expanded', 'false'); } };
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (pop) { close(); return; }
            pop = document.createElement('div');
            pop.id = 'sc-attach-menu';
            const mac = /Mac|iPhone|iPad/.test(navigator.platform);
            pop.innerHTML = `<button type="button" data-a="files">${window.scIcon ? window.scIcon('attach', 18) : ''}<span>Upload files</span><kbd>${mac ? '⌘' : 'Ctrl+'}U</kbd></button>`;
            document.body.appendChild(pop);
            const r = btn.getBoundingClientRect();
            pop.style.left = `${r.left}px`;
            pop.style.bottom = `${window.innerHeight - r.top + 8}px`;
            btn.setAttribute('aria-expanded', 'true');
            pop.addEventListener('click', (ev) => {
                const a = ev.target.closest('[data-a]')?.dataset.a;
                if (!a) return;
                close();
                file.click();
            });
        });
        document.addEventListener('click', (e) => { if (pop && !pop.contains(e.target)) close(); });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') close();
            if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'u') { e.preventDefault(); close(); file.click(); }
        });
        file.addEventListener('change', async () => {
            const files = Array.from(file.files || []);
            file.value = '';
            if (files.length && typeof uploadFiles === 'function') await uploadFiles(files, false);
            document.getElementById('input')?.focus();
        });
        chips.insertBefore(btn, chips.firstChild);
        chips.appendChild(file);
    }

    // Shortcuts (Settings → Shortcuts): messages Lu sends often, one click from the composer.
    // Picking one puts it in the box so she can check or edit it, then Enter sends.
    function addShortcutButton(chips) {
        if (!chips || document.getElementById('sc-shortcut-btn')) return;
        const btn = makeShortcutButton(() => document.getElementById('input'));
        btn.id = 'sc-shortcut-btn';
        const attach = document.getElementById('sc-attach-btn');
        if (attach) attach.after(btn); else chips.insertBefore(btn, chips.firstChild);
    }

    // A ⚡ button that fills `getInput()` with a saved message. Used by the main box and threads.
    let shortcutPop = null;
    const closeShortcuts = () => { if (shortcutPop) { shortcutPop._btn?.setAttribute('aria-expanded', 'false'); shortcutPop.remove(); shortcutPop = null; } };
    document.addEventListener('click', (e) => { if (shortcutPop && !shortcutPop.contains(e.target)) closeShortcuts(); });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeShortcuts(); });
    function makeShortcutButton(getInput) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'sc-shortcut-btn';
        btn.title = 'Shortcuts';
        btn.setAttribute('aria-label', 'Shortcuts');
        btn.setAttribute('aria-haspopup', 'menu');
        btn.innerHTML = window.scIcon ? window.scIcon('flashlight', 18) : '⚡';
        btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (shortcutPop && shortcutPop._btn === btn) { closeShortcuts(); return; }
            closeShortcuts();
            const items = await fetch('/api/scranton/shortcuts', { headers: { 'X-Session-Token': window.SESSION_TOKEN } })
                .then((r) => r.json()).catch(() => []);
            const pop = document.createElement('div');
            pop.id = 'sc-shortcut-menu';
            pop.setAttribute('role', 'menu');
            pop._btn = btn;
            const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
            pop.innerHTML = (Array.isArray(items) ? items : []).map((it, i) =>
                `<button type="button" role="menuitem" data-i="${i}"><span>${esc(it.label)}</span></button>`).join('')
                + `<button type="button" role="menuitem" data-edit="1" class="sc-sc-edit">${window.scIcon ? window.scIcon('edit', 16) : ''}<span>Edit shortcuts</span></button>`;
            document.body.appendChild(pop);
            shortcutPop = pop;
            const r = btn.getBoundingClientRect();
            pop.style.left = `${Math.min(r.left, window.innerWidth - pop.offsetWidth - 8)}px`;
            pop.style.bottom = `${window.innerHeight - r.top + 8}px`;
            btn.setAttribute('aria-expanded', 'true');
            pop.addEventListener('click', (ev) => {
                const b = ev.target.closest('button');
                if (!b) return;
                closeShortcuts();
                if (b.dataset.edit) { window.scOpenSettings && window.scOpenSettings('shortcuts'); return; }
                const it = items[+b.dataset.i];
                const input = getInput();
                if (!it || !input) return;
                input.value = input.value.trim() ? `${input.value.trim()}\n${it.text}` : it.text;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
                input.setSelectionRange(input.value.length, input.value.length);
            });
        });
        return btn;
    }
    window.scMakeShortcutButton = makeShortcutButton;

    function init() {
        // Channels always live in the sidebar.
        if (typeof setChannelSidebarMode === 'function') setChannelSidebarMode('sidebar', true);
        addTeamButton();
        // The @ quick-chips set who this channel's messages go to, so they live
        // inside the composer card (bottom row), not floating above it.
        const chips = document.getElementById('mention-toggles-row');
        const row = document.getElementById('input-row');
        if (chips && row && chips.parentElement !== row) row.appendChild(chips);
        // Files waiting to be sent sit inside the composer card, above the text (as in Grok Bot).
        const atts = document.getElementById('attachments');
        if (atts && row && atts.parentElement !== row) row.prepend(atts);
        addAttachButton(chips);
        addShortcutButton(chips);
        renderTeam();
        loadTeam();

        // Tap outside a drawer closes it; picking a channel closes the channel drawer.
        document.addEventListener('click', (e) => {
            const body = document.body;
            if (!body.classList.contains('sc-drawer-channels') && !body.classList.contains('sc-drawer-team')) return;
            if (e.target.closest('#channel-sidebar, #team-panel, #sc-menu-btn, #sc-team-btn, .pill-popover')) {
                if (e.target.closest('.channel-sidebar-row') && !e.target.closest('.channel-sidebar-row-actions')) closeDrawers();
                return;
            }
            closeDrawers();
        });
    }

    // A tab left open across an update keeps running the old code in memory; the server
    // reconnects quietly, so nothing tells you. Compare builds and reload when they differ:
    // right away if you're not in the middle of something, else ask with a toast.
    let buildAsked = false;
    async function checkBuild() {
        const mine = window.__SC_BUILD__;
        if (!mine) return;
        let now = null;
        try {
            const r = await fetch('/api/scranton/build', { headers: { 'X-Session-Token': SESSION_TOKEN }, cache: 'no-store' });
            if (r.ok) now = (await r.json()).build;
        } catch (_) { return; }
        if (!now || now === mine) return;
        const typing = ['input', 'sc-thread-input'].some((id) => { const el = document.getElementById(id); return el && el.value.trim(); });
        const busy = typing || document.querySelector('#sc-settings, .sc-modal-open, [aria-modal="true"]:not([hidden])');
        if (!busy) { location.reload(); return; }
        if (buildAsked) return;
        buildAsked = true;
        const t = document.createElement('div');
        t.className = 'sc-update-toast'; t.setAttribute('role', 'status');
        t.innerHTML = '<span>Scranton was updated.</span><button type="button" class="sc-btn primary sm">Reload</button>';
        t.querySelector('button').onclick = () => location.reload();
        document.body.appendChild(t);
    }
    window.scCheckBuild = checkBuild;
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') checkBuild(); });
    setInterval(checkBuild, 120000);

    // Shared with scranton-nav.js
    window.scGetTeam = () => scTeam;
    window.scReloadTeam = () => loadTeam();
    window.scAvatarHtml = avatarHtml;
    window.scAgentState = agentState;
    window.scLabelOf = labelOf;
    window.scOnTeamChange = [];
    const _origRender = renderTeam;
    renderTeam = function () { _origRender(); for (const f of window.scOnTeamChange) { try { f(); } catch (_) {} } };

    if (typeof handleServerEvent === 'function') {
        const origEv = handleServerEvent;
        handleServerEvent = function (event) {
            if (event && event.type === 'scranton_team_changed') { loadTeam(); return; }
            if (event && event.type === 'scranton_doing') {
                window.scDoing = window.scDoing || {};
                window.scDoing[String(event.agent).replace(/-\d+$/, '')] = event.text || '';
                if (window.scRenderWorking) window.scRenderWorking();
                return;
            }
            return origEv.apply(this, arguments);
        };
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
