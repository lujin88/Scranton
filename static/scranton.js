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
        available: 'Available',
        offline: 'Offline',
        pending: 'Starting',
    };
    let lastStatus = {};

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
        if (!names.length) {
            const empty = document.createElement('div');
            empty.className = 'team-empty';
            empty.textContent = 'No agents online. Start them on your Mac with ./scranton.sh start';
            list.appendChild(empty);
            return;
        }
        // Working first, then available, then the rest; stable by label inside a group.
        const order = { working: 0, pending: 1, available: 2, offline: 3 };
        names.sort((a, b) => {
            const d = order[agentState(a)] - order[agentState(b)];
            if (d) return d;
            return (agentConfig[a].label || a).localeCompare(agentConfig[b].label || b);
        });
        for (const name of names) {
            const cfg = agentConfig[name] || {};
            const state = agentState(name);
            const info = lastStatus[name] || {};
            const color = (typeof colorOverrides !== 'undefined' && colorOverrides[name]) || info.color || cfg.color || '#888';
            const role = (typeof _agentRoles !== 'undefined' && _agentRoles[name]) || info.role || '';

            const row = document.createElement('button');
            row.type = 'button';
            row.className = `team-row ${state}`;
            row.style.setProperty('--agent-color', color);
            row.title = `@${name}`;

            const avatar = document.createElement('span');
            avatar.className = 'team-avatar';
            avatar.textContent = (cfg.label || name).trim().charAt(0).toUpperCase();
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
            st.textContent = role ? `${STATE_TEXT[state]} · ${role}` : STATE_TEXT[state];
            text.append(nm, st);

            row.append(avatar, text);
            // Reuse agentchattr's popover (rename, role, color) anchored to the hidden pill.
            row.addEventListener('click', (e) => {
                e.stopPropagation();
                const pill = document.getElementById(`status-${name}`);
                if (pill) pill.click();
            });
            // Long-press / double-click inserts an @mention into the composer.
            row.addEventListener('dblclick', () => insertMention(name));
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
        btn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.8-3.5 3.4-5.5 6.5-5.5s5.7 2 6.5 5.5"/><circle cx="17" cy="9" r="2.5"/><path d="M16.5 14.6c2.6.3 4.4 2.1 5 5.4"/></svg><span class="sc-team-badge hidden"></span>';
        btn.addEventListener('click', (e) => { e.stopPropagation(); window.scToggleTeam(); });
        right.insertBefore(btn, right.firstChild);
    }

    function init() {
        // Channels always live in the sidebar.
        if (typeof setChannelSidebarMode === 'function') setChannelSidebarMode('sidebar', true);
        addTeamButton();
        renderTeam();

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

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
