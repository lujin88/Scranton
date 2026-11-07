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
        update: '<path d="M21 12a9 9 0 1 1-2.6-6.4"/><path d="M21 3v6h-6"/>',
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
            <button type="button" role="menuitem" data-a="update">${svg('update')}<span>Check for updates</span></button>
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
            if (a === 'update') window.scCheckUpdate && window.scCheckUpdate();
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
                <li><b>Updates</b> Scranton checks GitHub every hour; a card bottom-left says when a new version is ready. Check now: your avatar → Check for updates. Teammates keep working while it updates.</li>
                <li><b>Someone stopped</b> A card bottom-left lists them. <i>Resume</i> starts them again.</li>
                <li><b>On your phone</b> Open the same address through Tailscale.</li>
            </ul>`, 'sc-help-dlg');
    }

    // ------------------------------------------------------------------
    // Search (⌘K): people, channels and messages, grouped; keyboard first
    // ------------------------------------------------------------------
    const ico = {
        search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
        hash: '<span class="sc-sr-hash">#</span>',
    };
    function openSearch() {
        document.getElementById('sc-dialog')?.remove();
        const d = document.createElement('div');
        d.id = 'sc-dialog';
        d.innerHTML = `<div class="sc-dlg sc-search-dlg" role="dialog" aria-modal="true" aria-label="Search">
            <div class="sc-sq">${ico.search}<input id="sc-search-input" type="text" placeholder="Search messages, people and channels" autocomplete="off" spellcheck="false" aria-label="Search">
                <button type="button" class="sc-sq-clear" hidden aria-label="Clear">Clear</button></div>
            <div class="sc-sf" role="tablist">
                <button type="button" data-f="all" class="on">All</button><button type="button" data-f="messages">Messages</button>
                <button type="button" data-f="people">People</button><button type="button" data-f="channels">Channels</button></div>
            <div id="sc-search-results" role="listbox"></div>
            <div class="sc-sfoot"><span id="sc-search-count"></span><span class="sc-keys"><kbd>↑</kbd><kbd>↓</kbd> Navigate <kbd>↵</kbd> Open <kbd>esc</kbd> Close</span></div>
        </div>`;
        document.body.appendChild(d);
        const input = d.querySelector('#sc-search-input');
        const out = d.querySelector('#sc-search-results');
        const count = d.querySelector('#sc-search-count');
        const clear = d.querySelector('.sc-sq-clear');
        let filter = 'all', hits = [], seq = 0, timer = null, active = 0;
        const close = () => d.remove();
        d.addEventListener('click', (e) => { if (e.target === d) close(); });

        const team = () => (window.scGetTeam ? window.scGetTeam() : {}) || {};
        const avatar = (h) => (window.scAvatarHtml ? window.scAvatarHtml(h) : '');
        const stateOf = (h) => (window.scAgentState ? window.scAgentState(h) : 'offline');
        const channels = () => (window.channelList || []).filter((c) => !String(c).startsWith('dm-'));
        const mark = (text, q) => {
            const s = String(text || '').replace(/\s+/g, ' ');
            if (!q) return esc(s.slice(0, 160));
            const i = s.toLowerCase().indexOf(q.toLowerCase());
            const start = Math.max(0, i - 40);
            const cut = (start ? '…' : '') + s.slice(start, start + 170);
            const j = cut.toLowerCase().indexOf(q.toLowerCase());
            if (j < 0) return esc(cut);
            return esc(cut.slice(0, j)) + '<mark>' + esc(cut.slice(j, j + q.length)) + '</mark>' + esc(cut.slice(j + q.length));
        };

        function items(q) {
            const ql = q.toLowerCase();
            const people = Object.keys(team()).filter((h) => !q || h.includes(ql) || labelOf(h).toLowerCase().includes(ql))
                .map((h) => ({ kind: 'person', h }));
            const chans = channels().filter((c) => !q || c.includes(ql)).map((c) => ({ kind: 'channel', c }));
            const msgs = q ? hits.map((m) => ({ kind: 'message', m })) : [];
            return {
                people: filter === 'all' || filter === 'people' ? people.slice(0, q ? 5 : 6) : [],
                channels: filter === 'all' || filter === 'channels' ? chans.slice(0, q ? 5 : 8) : [],
                messages: filter === 'all' || filter === 'messages' ? msgs : [],
            };
        }

        function row(it, q, idx) {
            if (it.kind === 'person') {
                const st = stateOf(it.h);
                return `<button type="button" class="sc-sr" data-i="${idx}"><span class="sc-sr-av">${avatar(it.h)}<span class="sc-sr-dot ${esc(st)}"></span></span>
                    <span class="sc-sr-main"><span class="sc-sr-title">${mark(labelOf(it.h), q)}</span><span class="sc-sr-meta">@${esc(it.h)} · ${st === 'working' ? 'Working' : st === 'available' ? 'Online' : 'Not running'}</span></span>
                    <span class="sc-sr-go">Message</span></button>`;
            }
            if (it.kind === 'channel') {
                const n = ((window.scChannelMembers && window.scChannelMembers()[it.c]) || []).length;
                return `<button type="button" class="sc-sr" data-i="${idx}"><span class="sc-sr-av sc-sr-icon">${ico.hash}</span>
                    <span class="sc-sr-main"><span class="sc-sr-title">${mark(it.c, q)}</span><span class="sc-sr-meta">${n ? `${n} teammate${n === 1 ? '' : 's'}` : 'Channel'}</span></span>
                    <span class="sc-sr-go">Open</span></button>`;
            }
            const m = it.m;
            const ch = String(m.channel || 'general');
            const where = ch.startsWith('dm-') ? `DM with ${esc(labelOf(ch.slice(3)))}` : `#${esc(ch)}`;
            return `<button type="button" class="sc-sr sc-sr-msg" data-i="${idx}"><span class="sc-sr-av">${avatar(m.sender) || `<span class="sc-sr-initial">${esc(String(m.sender || '?').charAt(0).toUpperCase())}</span>`}</span>
                <span class="sc-sr-main"><span class="sc-sr-meta"><b>${esc(labelOf(m.sender))}</b> · ${where} · ${esc(String(m.time || '').slice(0, 5))}</span>
                <span class="sc-sr-text">${mark(m.text, q)}</span></span></button>`;
        }

        let flat = [];
        function render() {
            const q = input.value.trim();
            clear.hidden = !q;
            const g = items(q);
            flat = [...g.people, ...g.channels, ...g.messages];
            let idx = 0, html = '';
            const group = (title, list) => {
                if (!list.length) return;
                html += `<div class="sc-sg">${title}</div>` + list.map((it) => row(it, q, idx++)).join('');
            };
            group(q ? 'People' : 'Teammates', g.people);
            group('Channels', g.channels);
            group('Messages', g.messages);
            if (!flat.length) html = `<div class="sc-sr-empty">${q ? `Nothing matches “${esc(q)}”.` : 'No teammates or channels yet.'}</div>`;
            if (q && filter !== 'people' && filter !== 'channels' && !g.messages.length && flat.length) html += '<div class="sc-sr-none">No messages match.</div>';
            out.innerHTML = html;
            const msgCount = g.messages.length;
            count.textContent = q ? `${flat.length} result${flat.length === 1 ? '' : 's'}${msgCount >= 40 ? ' (newest 40 messages)' : ''}` : 'Type to search every channel';
            active = Math.min(active, Math.max(0, flat.length - 1));
            highlight();
        }
        function highlight() {
            out.querySelectorAll('.sc-sr').forEach((b) => b.classList.toggle('on', Number(b.dataset.i) === active));
            out.querySelector('.sc-sr.on')?.scrollIntoView({ block: 'nearest' });
        }
        function openItem(i) {
            const it = flat[i];
            if (!it) return;
            close();
            if (window.scCloseInbox) window.scCloseInbox();
            if (it.kind === 'person') { window.scOpenDm && window.scOpenDm(it.h); return; }
            const ch = it.kind === 'channel' ? it.c : String(it.m.channel || 'general');
            if (ch !== window.activeChannel && typeof switchChannel === 'function' && (window.channelList || []).includes(ch)) switchChannel(ch);
            if (it.kind === 'message') setTimeout(() => { location.hash = ''; location.hash = `#msg-${Number(it.m.id)}`; }, 150);
        }
        async function fetchHits() {
            const q = input.value.trim();
            const mine = ++seq;
            if (!q) { hits = []; render(); return; }
            try { hits = await fetch(`/api/scranton/search?q=${encodeURIComponent(q)}&limit=40`, { headers: { 'X-Session-Token': window.SESSION_TOKEN } }).then((r) => r.json()); }
            catch (_) { hits = []; }
            if (mine === seq) render();
        }

        input.addEventListener('input', () => { active = 0; render(); clearTimeout(timer); timer = setTimeout(fetchHits, 160); });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); active = Math.min(active + 1, flat.length - 1); highlight(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); active = Math.max(active - 1, 0); highlight(); }
            else if (e.key === 'Enter') { e.preventDefault(); openItem(active); }
            else if (e.key === 'Escape') { e.preventDefault(); close(); }
        });
        out.addEventListener('mousemove', (e) => { const b = e.target.closest('.sc-sr'); if (b && Number(b.dataset.i) !== active) { active = Number(b.dataset.i); highlight(); } });
        out.addEventListener('click', (e) => { const b = e.target.closest('.sc-sr'); if (b) openItem(Number(b.dataset.i)); });
        clear.addEventListener('click', () => { input.value = ''; hits = []; render(); input.focus(); });
        d.querySelector('.sc-sf').addEventListener('click', (e) => {
            const b = e.target.closest('[data-f]'); if (!b) return;
            filter = b.dataset.f; active = 0;
            d.querySelectorAll('.sc-sf button').forEach((x) => x.classList.toggle('on', x === b));
            render(); input.focus();
        });
        render();
        input.focus();
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
