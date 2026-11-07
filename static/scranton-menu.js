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
    const svg = (k) => (window.scIcon ? window.scIcon({ picture: 'image', rename: 'edit', feedback: 'feedback', update: 'refresh' }[k] || k, 18) : '');

    // Your status: shown on your avatar (sidebar and menu). Kept on this device.
    const STATUSES = [['online', 'Online'], ['away', 'Away'], ['dnd', 'Do not disturb']];
    function myStatus() {
        try { const v = localStorage.getItem('scranton-my-status'); return STATUSES.some(([k]) => k === v) ? v : 'online'; } catch (_) { return 'online'; }
    }
    function setStatus(v) {
        try { localStorage.setItem('scranton-my-status', v); } catch (_) { /* private mode */ }
        paintStatus();
    }
    function paintStatus() {
        const st = myStatus();
        document.querySelectorAll('#sc-me .sc-me-dot').forEach((d) => { d.className = `sc-me-dot ${st}`; });
        const chip = document.getElementById('sc-me');
    }

    function openProfile() {
        const pic = window.scMyAvatarHtml ? window.scMyAvatarHtml() : '';
        const d = openDialog('Edit profile', `
            <div class="sc-prof">
                <button type="button" class="sc-prof-av" data-a="picture" aria-label="Change picture">${pic}<span>Change</span></button>
                <label class="sc-prof-field"><span>Name</span><input id="sc-prof-name" type="text" maxlength="20" value="${esc(me())}"></label>
            </div>
            <div class="sc-prof-actions"><button type="button" class="sc-set-actions-btn" data-a="cancel">Cancel</button>
                <button type="button" class="sc-set-primary" data-a="save">Save</button></div>`, 'sc-prof-dlg');
        const input = d.querySelector('#sc-prof-name');
        input.focus(); input.select();
        const save = () => {
            const v = input.value.trim();
            if (v && v !== me() && window.ws && window.ws.readyState === WebSocket.OPEN) {
                window.ws.send(JSON.stringify({ type: 'update_settings', data: { username: v } }));
            }
            d.remove();
        };
        input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
        d.addEventListener('click', (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (a === 'picture') {
                window.scChangePicture && window.scChangePicture();
                const t0 = Date.now();
                const iv = setInterval(() => {   // show the new picture once it's been picked
                    const av = d.querySelector('.sc-prof-av');
                    if (!document.body.contains(d) || Date.now() - t0 > 60000) { clearInterval(iv); return; }
                    const now = window.scMyAvatarHtml ? window.scMyAvatarHtml() : '';
                    if (av && !av.innerHTML.startsWith(now)) av.innerHTML = now + '<span>Change</span>';
                }, 500);
            }
            if (a === 'cancel') d.remove();
            if (a === 'save') save();
        });
    }

    // ------------------------------------------------------------------
    // Account menu
    // ------------------------------------------------------------------
    let menu = null;
    function closeMenu() {
        if (!menu) return;
        menu.remove(); menu = null;
        document.getElementById('sc-me')?.setAttribute('aria-expanded', 'false');
    }
    // Grok-style: flat list, rows with a value and › open a submenu to the right.
    function row(a, ic, text, extra) {
        return `<button type="button" role="menuitem" data-a="${a}"${extra ? ' aria-haspopup="menu"' : ''}>${ic}<span>${text}</span>${extra || ''}</button>`;
    }
    function openMenu() {
        const chip = document.getElementById('sc-me');
        if (!chip) return;
        closeMenu();
        const pic = window.scMyAvatarHtml ? window.scMyAvatarHtml() : '';
        menu = document.createElement('div');
        menu.id = 'sc-account-menu';
        menu.setAttribute('role', 'menu');
        const st = myStatus();
        const stLabel = (STATUSES.find(([k]) => k === st) || STATUSES[0])[1];
        const chev = window.scIcon ? window.scIcon('right', 16) : '›';
        menu.innerHTML = `
            <div class="sc-am-head"><span class="sc-am-av">${pic}<span class="sc-me-dot ${st}"></span></span><span class="sc-am-name">${esc(me())}</span></div>
            ${row('status', `<span class="sc-am-dot ${st}"></span>`, 'Status', `<em>${stLabel}</em><i class="sc-am-chev">${chev}</i>`)}
            ${row('settings', svg('settings'), 'Settings')}
            ${row('update', svg('update'), 'Check for updates')}
            <hr>
            ${row('support', svg('support'), 'Support', `<i class="sc-am-chev">${chev}</i>`)}`;
        document.body.appendChild(menu);
        const r = chip.getBoundingClientRect();
        menu.style.left = `${Math.max(8, r.left)}px`;
        menu.style.bottom = `${Math.max(8, window.innerHeight - r.top + 6)}px`;
        chip.setAttribute('aria-expanded', 'true');
        menu.querySelector('button')?.focus();

        let sub = null;
        const closeSub = () => { sub?.remove(); sub = null; menu?.querySelectorAll('[aria-expanded]').forEach((b) => b.removeAttribute('aria-expanded')); };
        function openSub(btn) {
            if (sub && sub.dataset.for === btn.dataset.a) return;
            closeSub();
            sub = document.createElement('div');
            sub.className = 'sc-am-sub'; sub.dataset.for = btn.dataset.a; sub.setAttribute('role', 'menu');
            if (btn.dataset.a === 'status') {
                const cur = myStatus();
                sub.innerHTML = STATUSES.map(([v, l]) => `<button type="button" role="menuitemradio" aria-checked="${v === cur}" data-s="${v}"><span class="sc-am-dot ${v}"></span><span>${l}</span>${v === cur ? (window.scIcon ? window.scIcon('check', 16) : '') : ''}</button>`).join('');
            } else {
                sub.innerHTML = `<button type="button" role="menuitem" data-a="feedback">${svg('mail')}<span>Send feedback</span></button>
                    <button type="button" role="menuitem" data-a="shortcuts">${svg('keyboard')}<span>Keyboard shortcuts</span></button>`;
            }
            menu.appendChild(sub);
            const br = btn.getBoundingClientRect(), mr = menu.getBoundingClientRect();
            sub.style.left = `${mr.width - 4}px`;
            sub.style.top = `${br.top - mr.top - 8}px`;
            btn.setAttribute('aria-expanded', 'true');
        }
        menu.addEventListener('mouseover', (e) => {
            const b = e.target.closest('#sc-account-menu > button');
            if (!b) return;
            if (b.hasAttribute('aria-haspopup')) openSub(b); else closeSub();
        });
        menu.addEventListener('click', (e) => {
            const s2 = e.target.closest('[data-s]');
            if (s2) {
                setStatus(s2.dataset.s); closeMenu(); return;
            }
            const b = e.target.closest('[data-a]');
            if (!b) return;
            if (b.hasAttribute('aria-haspopup')) { openSub(b); sub?.querySelector('button')?.focus(); return; }
            const a = b.dataset.a;
            closeMenu();
            if (a === 'settings') window.scOpenSettings('profile');
            if (a === 'update') window.scCheckUpdate && window.scCheckUpdate();
            if (a === 'feedback') sendFeedback();
            if (a === 'shortcuts') openShortcuts();
        });
        menu.addEventListener('keydown', (e) => {
            const inSub = sub && sub.contains(document.activeElement);
            const items = [...(inSub ? sub : menu).querySelectorAll(inSub ? 'button' : ':scope > button')];
            const i = items.indexOf(document.activeElement);
            if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
            if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
            if (e.key === 'ArrowRight' && !inSub && document.activeElement?.hasAttribute('aria-haspopup')) {
                e.preventDefault(); openSub(document.activeElement); sub?.querySelector('button')?.focus();
            }
            if (e.key === 'ArrowLeft' && inSub) {
                e.preventDefault(); const owner = menu.querySelector(`[data-a="${sub.dataset.for}"]`); closeSub(); owner?.focus();
            }
        });
    }
    function openShortcuts() {
        const k = isMac ? '⌘' : 'Ctrl+';
        const rows = [[`${k}K`, 'Search'], [`${k}U`, 'Upload files'], ['Enter', 'Send'], ['Shift+Enter', 'New line'],
            ['R (on a message)', 'Reply here'], ['T (on a message)', 'Reply in thread'], ['E (on a message)', 'Add reaction'],
            ['Alt+↑ / Alt+↓', 'Move the selected channel'], ['Delete', 'Delete the selected channel'], ['Esc', 'Close']];
        openDialog('Keyboard shortcuts', `<dl class="sc-keys">${rows.map(([key, what]) => `<dt>${what}</dt><dd><kbd>${esc(key)}</kbd></dd>`).join('')}</dl>`);
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
        get search() { return window.scIcon ? window.scIcon('search', 18) : ''; },
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
        // Grow out of the top-bar search field (as Slack / Linear do) instead of a separate box
        const place = () => {
            const btn = document.getElementById('sc-search-btn');
            const dlg = d.querySelector('.sc-search-dlg');
            if (!btn || !dlg || window.matchMedia('(max-width: 760px)').matches) return;
            const r = btn.getBoundingClientRect();
            const w = Math.min(Math.max(r.width + 120, 640), window.innerWidth - 32);
            const left = Math.min(Math.max(16, r.left + r.width / 2 - w / 2), window.innerWidth - w - 16);
            dlg.style.left = `${left}px`; dlg.style.top = `${Math.max(4, r.top - 6)}px`; dlg.style.width = `${w}px`;
        };
        place();
        window.addEventListener('resize', place);
        const input = d.querySelector('#sc-search-input');
        const out = d.querySelector('#sc-search-results');
        const count = d.querySelector('#sc-search-count');
        const clear = d.querySelector('.sc-sq-clear');
        let filter = 'all', hits = [], seq = 0, timer = null, active = 0;
        const close = () => { d.remove(); window.removeEventListener('resize', place); };
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
            if (q && filter === 'messages' && !g.messages.length) html = '<div class="sc-sr-empty">No messages match.</div>';
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
        window.scSendFeedback = sendFeedback;
        window.scPaintStatus = paintStatus;
        paintStatus();
        window.scOpenSearch = openSearch;
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
