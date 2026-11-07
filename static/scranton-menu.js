// Scranton: account menu (bottom-left avatar), Search (top bar, ⌘K), Settings and Help dialogs.
(function () {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const api = (path) => fetch(path, { headers: { 'X-Session-Token': window.SESSION_TOKEN } })
        .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    const labelOf = (n) => (window.scLabelOf ? window.scLabelOf(n) : n);
    const me = () => (window.scMe ? window.scMe() : (window.username || 'You'));
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
    const icon = {
        picture: '<path d="M4 5h16v14H4z"/><circle cx="9" cy="10" r="2"/><path d="M20 16l-5-5-9 8"/>',
        rename: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
        settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
        help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.7M12 17h.01"/>',
        feedback: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    };
    const svg = (k) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${icon[k]}</svg>`;

    // ------------------------------------------------------------------
    // Account menu
    // ------------------------------------------------------------------
    let menu = null;
    function closeMenu() {
        if (!menu) return;
        menu.remove(); menu = null;
        document.getElementById('sc-me')?.setAttribute('aria-expanded', 'false');
    }
    function openMenu() {
        const chip = document.getElementById('sc-me');
        if (!chip) return;
        closeMenu();
        const pic = window.scMyAvatarHtml ? window.scMyAvatarHtml() : '';
        menu = document.createElement('div');
        menu.id = 'sc-account-menu';
        menu.setAttribute('role', 'menu');
        menu.innerHTML = `
            <div class="sc-am-head"><span class="sc-am-av">${pic}<span class="sc-me-dot"></span></span>
                <div><div class="sc-am-name">${esc(me())}</div><span class="sc-am-status">Online</span></div></div>
            <button type="button" role="menuitem" data-a="picture">${svg('picture')}<span>Change picture</span></button>
            <button type="button" role="menuitem" data-a="rename">${svg('rename')}<span>Change name</span></button>
            <hr>
            <button type="button" role="menuitem" data-a="settings">${svg('settings')}<span>Settings</span></button>
            <button type="button" role="menuitem" data-a="help">${svg('help')}<span>Help</span></button>
            <hr>
            <button type="button" role="menuitem" data-a="feedback">${svg('feedback')}<span>Send feedback</span></button>`;
        document.body.appendChild(menu);
        const r = chip.getBoundingClientRect();
        menu.style.left = `${Math.max(8, r.left)}px`;
        menu.style.bottom = `${Math.max(8, window.innerHeight - r.top + 6)}px`;
        chip.setAttribute('aria-expanded', 'true');
        menu.querySelector('button')?.focus();
        menu.addEventListener('click', (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (!a) return;
            closeMenu();
            if (a === 'picture') window.scChangePicture && window.scChangePicture();
            if (a === 'rename') window.scRename && window.scRename();
            if (a === 'settings') openSettings();
            if (a === 'help') openHelp();
            if (a === 'feedback') sendFeedback();
        });
        menu.addEventListener('keydown', (e) => {
            const items = [...menu.querySelectorAll('button')];
            const i = items.indexOf(document.activeElement);
            if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
            if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
        });
    }
    function sendFeedback() {
        const team = window.scGetTeam ? window.scGetTeam() : {};
        if (team.help && window.scOpenDm) { window.scOpenDm('help'); setTimeout(() => document.getElementById('input')?.focus(), 300); }
        else openDialog('Send feedback', '<p>The Help teammate isn\'t set up, so there\'s nobody to collect feedback yet. Add <code>[agents.help]</code> back to <code>config.toml</code>.</p>');
    }

    // ------------------------------------------------------------------
    // Dialogs
    // ------------------------------------------------------------------
    function openDialog(title, bodyHtml, cls) {
        document.getElementById('sc-dialog')?.remove();
        const d = document.createElement('div');
        d.id = 'sc-dialog';
        d.innerHTML = `<div class="sc-dlg ${cls || ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
            <div class="sc-dlg-head"><h2>${esc(title)}</h2><button type="button" class="sc-dlg-x" aria-label="Close">✕</button></div>
            <div class="sc-dlg-body">${bodyHtml}</div></div>`;
        document.body.appendChild(d);
        const close = () => d.remove();
        d.addEventListener('click', (e) => { if (e.target === d || e.target.closest('.sc-dlg-x')) close(); });
        d.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
        d.querySelector('.sc-dlg-x').focus();
        return d;
    }

    function openSettings() {
        const team = window.scGetTeam ? window.scGetTeam() : {};
        const rows = Object.entries(team).map(([name, t]) => {
            const st = window.scAgentState ? window.scAgentState(name) : '';
            const av = window.scAvatarHtml ? window.scAvatarHtml(name) : '';
            return `<li class="sc-set-row"><span class="sc-set-av">${av}</span>
                <span class="sc-set-who"><b>${esc(t.label || name)}</b><small>${esc(t.role || '')}</small></span>
                <span class="sc-set-tool">${esc(t.provider || '')}</span>
                <span class="sc-set-state ${esc(st)}">${esc(st === 'offline' || !st ? 'Not running' : st === 'working' ? 'Working' : 'Online')}</span></li>`;
        }).join('');
        openDialog('Settings', `
            <section><h3>You</h3>
                <div class="sc-set-me"><span class="sc-set-av big">${window.scMyAvatarHtml ? window.scMyAvatarHtml() : ''}</span>
                <div><b>${esc(me())}</b><div class="sc-set-actions">
                    <button type="button" data-a="picture">Change picture</button><button type="button" data-a="rename">Change name</button></div></div></div>
            </section>
            <section><h3>Team <small>${Object.keys(team).length}</small></h3>
                <ul class="sc-set-list">${rows || '<li class="sc-set-empty">No teammates yet.</li>'}</ul>
                <p class="sc-set-note">Adding or importing teammates from here is coming next. For now they live in <code>config.toml</code>.</p>
            </section>
            <section><h3>Feedback</h3>
                <p class="sc-set-note">Something odd or missing? Tell the Help teammate. It turns your note into a GitHub issue for the Harness manager.</p>
                <button type="button" class="sc-set-primary" data-a="feedback">Send feedback</button>
            </section>`, 'sc-settings').addEventListener('click', (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (!a) return;
            document.getElementById('sc-dialog')?.remove();
            if (a === 'picture') window.scChangePicture && window.scChangePicture();
            if (a === 'rename') window.scRename && window.scRename();
            if (a === 'feedback') sendFeedback();
        });
    }

    function openHelp() {
        const k = isMac ? '⌘K' : 'Ctrl K';
        openDialog('Help', `
            <ul class="sc-help">
                <li><b>Give someone work</b> Type <code>@</code> and their name in a channel. Only the people you @ start working.</li>
                <li><b>Talk one-to-one</b> Open someone under <i>Direct messages</i>. No @ needed there.</li>
                <li><b>Threads</b> Hover a message → 💬 to reply in a thread on the right. Teammates answer inside the thread.</li>
                <li><b>Activity</b> Everything that @mentions you, newest first. Start here when you come back.</li>
                <li><b>Search</b> Press <kbd>${k}</kbd> to find any message in any channel.</li>
                <li><b>Updates</b> A card bottom-left says when a new version is ready. Teammates keep working while it updates.</li>
                <li><b>Someone stopped</b> A card bottom-left lists them. <i>Resume</i> starts them again.</li>
                <li><b>On your phone</b> Open the same address through Tailscale.</li>
            </ul>`, 'sc-help-dlg');
    }

    // ------------------------------------------------------------------
    // Search
    // ------------------------------------------------------------------
    function openSearch() {
        const d = openDialog('Search', `<input id="sc-search-input" type="search" placeholder="Search messages and people" autocomplete="off" aria-label="Search">
            <div id="sc-search-results" role="listbox"></div>`, 'sc-search-dlg');
        const input = d.querySelector('#sc-search-input');
        const out = d.querySelector('#sc-search-results');
        input.focus();
        let timer = null, seq = 0;
        const run = async () => {
            const q = input.value.trim();
            const mine = ++seq;
            if (!q) { out.innerHTML = ''; return; }
            let hits = [];
            try { hits = await api(`/api/scranton/search?q=${encodeURIComponent(q)}&limit=40`); } catch (_) { /* server restarting */ }
            if (mine !== seq) return;   // a newer search is on the way
            const ql = q.toLowerCase();
            const mark = (t) => {
                const s = String(t || '').replace(/\s+/g, ' ');
                const i = s.toLowerCase().indexOf(ql);
                const start = Math.max(0, i - 40);
                const cut = (start ? '…' : '') + s.slice(start, start + 160);
                if (i < 0) return esc(cut);
                const j = cut.toLowerCase().indexOf(ql);
                return esc(cut.slice(0, j)) + '<mark>' + esc(cut.slice(j, j + q.length)) + '</mark>' + esc(cut.slice(j + q.length));
            };
            out.innerHTML = hits.length ? hits.map((m) => `<button type="button" class="sc-sr" data-id="${Number(m.id)}" data-ch="${esc(m.channel || 'general')}">
                <span class="sc-sr-meta"><b>${esc(labelOf(m.sender))}</b> · ${esc(String(m.channel || 'general').startsWith('dm-') ? 'DM' : '#' + (m.channel || 'general'))} · ${esc(m.time || '')}</span>
                <span class="sc-sr-text">${mark(m.text)}</span></button>`).join('')
                : '<div class="sc-sr-empty">No messages match.</div>';
        };
        input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(run, 180); });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { const first = out.querySelector('.sc-sr'); if (first) { e.preventDefault(); first.click(); } }
            if (e.key === 'ArrowDown') { const first = out.querySelector('.sc-sr'); if (first) { e.preventDefault(); first.focus(); } }
        });
        out.addEventListener('keydown', (e) => {
            const items = [...out.querySelectorAll('.sc-sr')];
            const i = items.indexOf(document.activeElement);
            if (e.key === 'ArrowDown' && i >= 0) { e.preventDefault(); items[Math.min(i + 1, items.length - 1)].focus(); }
            if (e.key === 'ArrowUp' && i >= 0) { e.preventDefault(); (i === 0 ? input : items[i - 1]).focus(); }
        });
        out.addEventListener('click', (e) => {
            const b = e.target.closest('.sc-sr');
            if (!b) return;
            d.remove();
            const ch = b.dataset.ch;
            if (window.scCloseInbox) window.scCloseInbox();
            if (ch !== window.activeChannel && typeof switchChannel === 'function' && (window.channelList || []).includes(ch)) switchChannel(ch);
            // Wait for the channel to render, then open the message (and its thread).
            setTimeout(() => { location.hash = ''; location.hash = `#msg-${b.dataset.id}`; }, 150);
        });
    }

    function init() {
        const chip = document.getElementById('sc-me');
        chip?.addEventListener('click', (e) => { e.stopPropagation(); menu ? closeMenu() : openMenu(); });
        document.addEventListener('click', (e) => { if (menu && !menu.contains(e.target)) closeMenu(); });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && menu) { closeMenu(); chip?.focus(); }
            if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openSearch(); }
        });
        window.addEventListener('resize', closeMenu);
        const kbd = document.getElementById('sc-search-kbd');
        if (kbd && !isMac) kbd.textContent = 'Ctrl K';
        document.getElementById('sc-search-btn')?.addEventListener('click', openSearch);
        window.scOpenSettings = openSettings;
        window.scOpenSearch = openSearch;
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
