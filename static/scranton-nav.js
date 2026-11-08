// Scranton navigation: Inbox, Direct messages, collapsible sidebar, "me" chip.
// Loaded after chat.js, channels.js and scranton.js.

(function () {
    const LS = {
        get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (_) { return d; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
    };
    const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const me = () => (typeof username === 'string' ? username : 'Lu');
    const isDm = (ch) => typeof ch === 'string' && ch.startsWith('dm-');

    // ------------------------------------------------------------------
    // Inbox: agent messages that @mention me, reply to me, or arrive in a DM
    // ------------------------------------------------------------------
    const inbox = new Map();          // id -> msg
    const myMsgIds = new Set();
    // Read state uses message timestamps, not ids: ids restart at 0 when the
    // log is wiped, which would hide every new item behind an old high-water mark.
    const tsOf = (m) => Number(m && m.timestamp) || 0;
    const keyOf = (m) => `${m.id}@${tsOf(m)}`;
    let seenTs = parseFloat(LS.get('scranton-inbox-seen-ts', '0')) || 0;
    let readKeys;
    try { readKeys = new Set(JSON.parse(LS.get('scranton-inbox-read-keys', '[]') || '[]')); } catch (_) { readKeys = new Set(); }
    const forceUnread = new Set();
    const isUnread = (m) => forceUnread.has(keyOf(m)) || (tsOf(m) > seenTs && !readKeys.has(keyOf(m)));
    window.scMarkUnread = function (m) {
        const item = inbox.get(Number(m.id));
        if (!item) return;
        readKeys.delete(keyOf(item));
        forceUnread.add(keyOf(item));
        renderInboxBadge();
    };
    const pendingUnknown = [];   // messages from senders we couldn't classify yet

    function isAgentSender(sender) {
        const s = String(sender || '').toLowerCase();
        if (!s || s === 'system' || s === me().toLowerCase()) return false;
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        if (typeof agentConfig !== 'undefined' && agentConfig[s]) return true;
        return !!team[s] || !!team[s.replace(/-\d+$/, '')];
    }

    function mentionsMe(text) {
        const name = me().toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return new RegExp(`(^|[^\\w])@(${name}|lu)(?![\\w-])`, 'i').test(String(text || ''));
    }

    function consider(msg) {
        if (!msg || msg.id == null) return;
        // Work stopped because teammates handed off too many times in a row: Lu must see that.
        if (String(msg.sender || '').toLowerCase() === 'system' && /^Loop guard:/.test(String(msg.text || ''))) {
            inbox.set(Number(msg.id), { ...msg, _kinds: new Set(['mention']) });
            scheduleRender();
            return;
        }
        const type = msg.type || 'chat';
        if (!['chat', 'message', 'decision'].includes(type)) return;
        if (String(msg.sender || '').toLowerCase() === me().toLowerCase()) { myMsgIds.add(Number(msg.id)); return; }
        if (!isAgentSender(msg.sender)) {
            if (pendingUnknown.length < 1000) pendingUnknown.push(msg);
            return;
        }
        const kinds = new Set();
        if (mentionsMe(msg.text)) kinds.add('mention');
        if (isDm(msg.channel)) kinds.add('dm');
        if (msg.reply_to != null && myMsgIds.has(Number(msg.reply_to))) kinds.add('reply');
        if (kinds.size) {
            inbox.set(Number(msg.id), { ...msg, _kinds: kinds });
            scheduleRender();
        }
    }

    // Called when the team list arrives: classify messages that came in before it.
    function recheckPending() {
        const again = pendingUnknown.splice(0);
        for (const m of again) consider(m);
    }

    let renderPending = false;
    function scheduleRender() {
        if (renderPending) return;
        renderPending = true;
        requestAnimationFrame(() => { renderPending = false; renderInboxBadge(); if (inboxOpen()) renderInbox(); });
    }

    function unreadCount() {
        let n = 0;
        for (const m of inbox.values()) if (isUnread(m)) n++;
        return n;
    }

    function renderInboxBadge() {
        const b = document.getElementById('sc-inbox-badge');
        if (!b) return;
        const n = unreadCount();
        b.textContent = n > 99 ? '99+' : String(n);
        b.classList.toggle('hidden', n === 0);
        const row = document.getElementById('sc-inbox-row');
        if (row) row.classList.toggle('has-unread', n > 0);
    }

    const inboxOpen = () => !document.getElementById('sc-inbox')?.classList.contains('hidden');

    let filterKind = 'mention';  // default: things that tag Lu
    function relTime(m) {
        const ts = Number(m.timestamp) * (Number(m.timestamp) < 1e12 ? 1000 : 1);
        if (!ts) return m.time || '';
        const s = Math.max(0, (Date.now() - ts) / 1000);
        if (s < 60) return 'just now';
        if (s < 3600) { const n = Math.floor(s / 60); return `${n} minute${n > 1 ? 's' : ''} ago`; }
        if (s < 86400) { const n = Math.floor(s / 3600); return `${n} hour${n > 1 ? 's' : ''} ago`; }
        const n = Math.floor(s / 86400); return `${n} day${n > 1 ? 's' : ''} ago`;
    }

    function renderFromOptions() {
        const sel = document.getElementById('sc-inbox-from');
        if (!sel) return;
        const cur = sel.value;
        const senders = [...new Set([...inbox.values()].map((m) => String(m.sender).toLowerCase()))].sort();
        sel.innerHTML = '<option value="">Everyone</option>' + senders
            .map((n) => `<option value="${esc(n)}">${esc(window.scLabelOf ? window.scLabelOf(n) : n)}</option>`).join('');
        sel.value = senders.includes(cur) ? cur : '';
    }

    function renderInbox() {
        const list = document.getElementById('sc-inbox-list');
        if (!list) return;
        renderFromOptions();
        const from = document.getElementById('sc-inbox-from')?.value || '';
        const unreadOnly = !!document.getElementById('sc-inbox-unread')?.checked;
        const items = [...inbox.values()]
            .filter((m) => filterKind === 'all' || m._kinds.has(filterKind))
            .filter((m) => !from || String(m.sender).toLowerCase() === from)
            .filter((m) => !unreadOnly || isUnread(m))
            .sort((a, b) => b.id - a.id).slice(0, 300);
        if (!items.length) {
            list.innerHTML = `<div class="sc-empty">${window.scIcon ? window.scIcon('bell', 28) : ''}<h3>${inbox.size ? 'Nothing matches' : 'No activity yet'}</h3><p>${inbox.size
                ? 'Try another filter.'
                : 'Mentions, replies and direct messages show up here.'}</p></div>`;
            return;
        }
        list.innerHTML = '';
        for (const m of items) {
            const row = document.createElement('button');
            row.type = 'button';
            const unread = isUnread(m);
            row.className = 'sc-inbox-item' + (unread ? ' unread' : '');
            const where = isDm(m.channel) ? 'Direct message' : (m.channel || 'general');
            const sender = String(m.sender).toLowerCase();
            const label = window.scLabelOf ? window.scLabelOf(sender) : m.sender;
            const pic = window.scAvatarHtml ? window.scAvatarHtml(sender) : '';
            const text = String(m.text || '').replace(/\s+/g, ' ').trim();
            row.innerHTML = `<span class="sc-inbox-avatar">${pic}</span>`
                + `<span class="sc-inbox-body"><span class="sc-inbox-meta"><b>${esc(label)}</b> <span>${esc(where)}</span></span>`
                + `<span class="sc-inbox-text">${esc(text.length > 240 ? text.slice(0, 240) + '…' : text)}</span></span>`
                + `<span class="sc-inbox-side"><span class="sc-inbox-time">${esc(relTime(m))}</span>${unread ? '<span class="sc-unread-dot"></span>' : ''}</span>`;
            row.addEventListener('click', () => jumpTo(m));
            list.appendChild(row);
        }
    }

    function initInboxFilters() {
        document.querySelectorAll('#sc-inbox .sc-tab').forEach((t) => t.addEventListener('click', () => {
            filterKind = t.dataset.kind;
            document.querySelectorAll('#sc-inbox .sc-tab').forEach((x) => { x.classList.toggle('active', x === t); x.setAttribute('aria-selected', String(x === t)); });
            renderInbox();
        }));
        document.getElementById('sc-inbox-from')?.addEventListener('change', renderInbox);
        document.getElementById('sc-inbox-unread')?.addEventListener('change', renderInbox);
        setInterval(() => { if (inboxOpen()) renderInbox(); }, 60000);  // keep "x minutes ago" fresh
    }

    function jumpTo(m) {
        readKeys.add(keyOf(m));
        forceUnread.delete(keyOf(m));
        LS.set('scranton-inbox-read-keys', JSON.stringify([...readKeys].slice(-500)));
        renderInboxBadge();
        window.scCloseInbox();
        // 4: the channel may have been renamed or deleted since; don't open a ghost channel.
        let ch = m.channel || 'general';
        if (!window.channelList.includes(ch)) ch = 'general';
        if (ch !== window.activeChannel && typeof switchChannel === 'function') switchChannel(ch);
        setTimeout(() => { if (typeof scrollToMessage === 'function') scrollToMessage(m.id); }, 60);
        closeDrawer();
    }

    window.scOpenInbox = function () {
        document.getElementById('sc-inbox')?.classList.remove('hidden');
        document.getElementById('sc-inbox-row')?.classList.add('active');
        document.querySelectorAll('#channel-sidebar-list .channel-sidebar-row.active, #sc-dm-list .sc-side-row.active')
            .forEach((el) => el.classList.add('sc-dimmed'));
        renderInbox();
        closeDrawer();
    };
    window.scCloseInbox = function () {
        document.getElementById('sc-inbox')?.classList.add('hidden');
        document.getElementById('sc-inbox-row')?.classList.remove('active');
        document.querySelectorAll('.sc-dimmed').forEach((el) => el.classList.remove('sc-dimmed'));
    };
    window.scInboxMarkRead = function () {
        for (const m of inbox.values()) seenTs = Math.max(seenTs, tsOf(m));
        seenTs = Math.max(seenTs, Date.now() / 1000);
        LS.set('scranton-inbox-seen-ts', String(seenTs));
        readKeys.clear(); forceUnread.clear(); LS.set('scranton-inbox-read-keys', '[]');
        renderInboxBadge();
        renderInbox();
    };

    if (typeof appendMessage === 'function') {
        const origAppend = appendMessage;
        appendMessage = function (msg, options) {
            const r = origAppend.apply(this, arguments);
            try { consider(msg); addSelfAvatar(msg, options && options.container); } catch (_) { /* never break chat rendering */ }
            return r;
        };
    }

    // ------------------------------------------------------------------
    // Direct messages: one dm-<handle> channel per teammate
    // ------------------------------------------------------------------
    function teamHandles() {
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const names = new Set(Object.keys(team));
        if (typeof agentConfig !== 'undefined') {
            for (const [n, c] of Object.entries(agentConfig)) names.add((c && c.base && team[c.base]) ? c.base : n);
        }
        return [...names];
    }

    function openDm(handle) {
        const ch = `dm-${handle}`.slice(0, 20);
        window.scCloseInbox();
        closeDrawer();
        if (hiddenDms().includes(handle)) setHiddenDms(hiddenDms().filter((x) => x !== handle));
        if (window.channelList.includes(ch)) { if (ch !== window.activeChannel) switchChannel(ch); return; }
        if (!window.ws || window.ws.readyState !== WebSocket.OPEN) return;
        window.ws.send(JSON.stringify({ type: 'channel_create', name: ch }));
        let tries = 0;
        const wait = setInterval(() => {
            if (window.channelList.includes(ch) || ++tries > 30) {
                clearInterval(wait);
                if (window.channelList.includes(ch)) switchChannel(ch);
            }
        }, 100);
    }

    // Direct messages you've removed from the list (they come back when they message you)
    function hiddenDms() { try { return JSON.parse(LS.get('scranton-dm-hidden', '[]')) || []; } catch (_) { return []; } }
    function setHiddenDms(list) { LS.set('scranton-dm-hidden', JSON.stringify([...new Set(list)])); }
    window.scShowDm = (h) => { setHiddenDms(hiddenDms().filter((x) => x !== h)); renderDms(); };
    window.scHiddenDms = hiddenDms;

    function renderDms() {
        const list = document.getElementById('sc-dm-list');
        if (!list) return;
        list.innerHTML = '';
        const state = window.scAgentState || (() => 'offline');
        const order = { working: 0, pending: 1, available: 2, offline: 3 };
        const handles = teamHandles().sort((a, b) => (order[state(a)] - order[state(b)])
            || window.scLabelOf(a).localeCompare(window.scLabelOf(b)));
        const hidden = hiddenDms();
        for (const h of handles) {
            const ch = `dm-${h}`.slice(0, 20);
            const unreadNow = (window.channelUnread && window.channelUnread[ch]) || 0;
            if (hidden.includes(h) && !unreadNow && ch !== window.activeChannel) continue;   // a new message brings them back
            const row = document.createElement('button');
            row.type = 'button';
            row.className = `sc-side-row sc-dm-row ${state(h)}` + (ch === window.activeChannel && !inboxOpen() ? ' active' : '');
            row.title = `Direct message @${h}`;
            const unread = (window.channelUnread && window.channelUnread[ch]) || 0;
            row.innerHTML = `<span class="sc-dm-avatar">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}<span class="team-dot"></span></span>`
                + `<span class="sc-side-label">${esc(window.scLabelOf(h))}</span>`
                + (unread && ch !== window.activeChannel ? `<span class="sc-badge">${unread > 99 ? '99+' : unread}</span>` : '');
            const x = document.createElement('span');
            x.className = 'sc-dm-x';
            x.setAttribute('role', 'button');
            x.setAttribute('aria-label', `Remove ${window.scLabelOf(h)} from Direct messages`);
            x.title = 'Remove from list';
            x.innerHTML = window.scIcon ? window.scIcon('close', 14) : '×';
            x.addEventListener('click', (e) => { e.stopPropagation(); setHiddenDms([...hiddenDms(), h]); renderDms(); });
            row.appendChild(x);
            row.addEventListener('click', () => openDm(h));
            list.appendChild(row);
        }
    }

    // Keep dm-* channels out of the Channels list; refresh DMs alongside.
    if (typeof renderChannelSidebar === 'function') {
        const origSidebar = renderChannelSidebar;
        renderChannelSidebar = function () {
            origSidebar.apply(this, arguments);
            document.querySelectorAll('#channel-sidebar-list .channel-sidebar-row').forEach((row) => {
                if (isDm(row.dataset.channel)) row.remove();
                else if (inboxOpen() && row.classList.contains('active')) row.classList.add('sc-dimmed');
            });
            renderDms();
            updateTitle();
        };
    }
    if (typeof switchChannel === 'function') {
        const origSwitch = switchChannel;
        switchChannel = function (name) {
            window.scCloseInbox();
            const changed = name !== window.activeChannel;
            if (changed && window.scClearQuote) window.scClearQuote();   // a quote belongs to its conversation
            if (changed && window.scDraft) window.scDraft.save(window.activeChannel);
            const r = origSwitch.apply(this, arguments);
            if (changed && window.scDraft) window.scDraft.load(name);
            if (typeof renderChannelSidebar === 'function') renderChannelSidebar();
            updateTitle();
            // Back / swipe-back goes to the previous conversation instead of leaving Scranton.
            if (changed && !fromHistory) {
                try { history.pushState({ scChannel: name }, '', location.pathname + location.search); } catch (_) {}
            }
            return r;
        };
        let fromHistory = false;
        try { history.replaceState({ scChannel: window.activeChannel || 'general' }, '', location.href); } catch (_) {}
        window.addEventListener('popstate', (e) => {
            const ch = e.state && e.state.scChannel;
            if (!ch || !window.channelList || !window.channelList.includes(ch)) return;
            fromHistory = true;
            try { switchChannel(ch); } finally { fromHistory = false; }
        });
    }

    function updateTitle() {
        const ch = window.activeChannel || 'general';
        document.body.classList.toggle('sc-in-dm', isDm(ch));
        const pt = document.getElementById('sc-pane-title');
        const pi = document.getElementById('sc-pane-icon');
        if (pt) pt.textContent = isDm(ch) ? (window.scLabelOf ? window.scLabelOf(ch.slice(3)) : ch.slice(3)) : ch;
        if (pi) pi.innerHTML = isDm(ch) && window.scAvatarHtml ? window.scAvatarHtml(ch.slice(3)) : '#';
        const composer = document.getElementById('input');
        if (composer) {
            composer.placeholder = isDm(ch)
                ? `Message ${window.scLabelOf ? window.scLabelOf(ch.slice(3)) : ch.slice(3)} directly`
                : `Message #${ch} · @ to assign`;
        }
    }

    // ------------------------------------------------------------------
    // Collapsing: whole sidebar (desktop) and each section
    // ------------------------------------------------------------------
    window.scOpenDm = (h) => openDm(h);
    function closeDrawer() { document.body.classList.remove('sc-drawer-channels'); }

    function applyCollapsed() {
        document.body.classList.toggle('sc-sidebar-collapsed', LS.get('scranton-sidebar-collapsed', '0') === '1');
        for (const sec of ['channels', 'dms']) {
            const closed = LS.get(`scranton-section-${sec}`, 'open') === 'closed';
            document.querySelectorAll(`[data-section="${sec}"]`).forEach((el) => el.classList.toggle('sc-closed', closed));
        }
    }
    window.scToggleSection = function (sec) {
        const closed = LS.get(`scranton-section-${sec}`, 'open') === 'closed';
        LS.set(`scranton-section-${sec}`, closed ? 'open' : 'closed');
        applyCollapsed();
    };
    // Replace the phone-only menu button behaviour: on wide screens it collapses the sidebar.
    const origToggleDrawer = window.scToggleDrawer;
    window.scToggleDrawer = function () {
        if (window.matchMedia('(max-width: 760px)').matches) return origToggleDrawer && origToggleDrawer();
        const collapsed = LS.get('scranton-sidebar-collapsed', '0') === '1';
        LS.set('scranton-sidebar-collapsed', collapsed ? '0' : '1');
        applyCollapsed();
    };

    // ------------------------------------------------------------------
    // Me: name + picture at the bottom of the sidebar
    // ------------------------------------------------------------------
    function myAvatarHtml() {
        const pic = LS.get('scranton-me-avatar', '');
        if (pic && pic.startsWith('data:image/')) return `<img src="${esc(pic)}" alt="">`;
        return `<span class="sc-me-initial">${esc(me().trim().charAt(0).toUpperCase() || '?')}</span>`;
    }
    function renderMe() {
        const a = document.getElementById('sc-me-avatar');
        const n = document.getElementById('sc-me-name');
        if (a) a.innerHTML = myAvatarHtml();
        if (n) n.textContent = me();
        document.querySelectorAll('.message.self .avatar').forEach((av) => { av.innerHTML = myAvatarHtml(); });
    }
    function addSelfAvatar(msg, container) {
        if (!msg || String(msg.sender || '').toLowerCase() !== me().toLowerCase()) return;
        // During history replay messages are built in a fragment that isn't in the page yet.
        const el = (container && container.querySelector && container.querySelector(`#message-${CSS.escape(String(msg.id))}`))
            || document.getElementById(`message-${msg.id}`);
        if (!el || el.querySelector('.avatar-wrap')) return;
        const wrap = document.createElement('div');
        wrap.className = 'avatar-wrap sc-self-avatar';
        wrap.innerHTML = `<div class="avatar">${myAvatarHtml()}</div>`;
        const bubble = el.querySelector('.chat-bubble');
        if (bubble) el.insertBefore(wrap, bubble);
    }
    // Your photo lives on the Mac (data/me-avatar.txt, not in git) so the phone sees it too.
    function saveAvatarToServer(url) {
        fetch('/api/scranton/me/avatar', { method: 'POST', headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' },
            body: JSON.stringify({ data: url || '' }) }).catch(() => {});
    }
    window.scSaveAvatar = saveAvatarToServer;
    async function loadAvatarFromServer() {
        try {
            const r = await fetch('/api/scranton/me/avatar', { headers: { 'X-Session-Token': window.SESSION_TOKEN } }).then((x) => x.json());
            const cur = LS.get('scranton-me-avatar', '');
            if (r.data && r.data !== cur) { LS.set('scranton-me-avatar', r.data); renderMe(); }
            else if (!r.data && cur) saveAvatarToServer(cur);   // first run: keep the one this browser had
        } catch (_) { /* server restarting */ }
    }
    window.scLoadAvatar = loadAvatarFromServer;

    function pickAvatar(file) {
        if (!file || !/^image\/(png|jpeg|webp)$/.test(file.type)) return;
        const img = new Image();
        const url = URL.createObjectURL(file);
        img.onload = () => {
            const size = 128;
            const c = document.createElement('canvas');
            c.width = c.height = size;
            const s = Math.min(img.width, img.height);
            c.getContext('2d').drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
            const url = c.toDataURL('image/jpeg', 0.85);
            LS.set('scranton-me-avatar', url);
            saveAvatarToServer(url);
            URL.revokeObjectURL(url);
            renderMe();
        };
        img.src = url;
    }

    function editName() {
        const n = document.getElementById('sc-me-name');
        if (!n || n.querySelector('input')) return;
        const input = document.createElement('input');
        input.className = 'sc-me-input';
        input.value = me();
        input.maxLength = 20;
        input.setAttribute('aria-label', 'Your name');
        n.textContent = '';
        n.appendChild(input);
        input.focus(); input.select();
        let done = false;
        const finish = (save) => {
            if (done) return; done = true;
            const v = input.value.trim();
            if (save && v && v !== me() && window.ws && window.ws.readyState === WebSocket.OPEN) {
                window.ws.send(JSON.stringify({ type: 'update_settings', data: { username: v } }));
            }
            n.textContent = save && v ? v : me();
        };
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); finish(true); }
            if (e.key === 'Escape') { e.preventDefault(); finish(false); }
        });
        input.addEventListener('blur', () => finish(true));
    }

    function initMe() {
        const btn = document.getElementById('sc-me');
        const file = document.getElementById('sc-me-file');
        if (!btn || !file) return;
        // The chip opens the account menu (scranton-menu.js); these are its actions.
        window.scChangePicture = () => file.click();
        window.scRename = editName;
        window.scMyAvatarHtml = myAvatarHtml;
        window.scRenderMe = renderMe;
        loadAvatarFromServer();
        window.scMe = me;
        file.addEventListener('change', () => { pickAvatar(file.files && file.files[0]); file.value = ''; });
        renderMe();
        // username arrives from the server after connect; refresh when settings change
        let last = me();
        setInterval(() => { if (me() !== last) { last = me(); renderMe(); renderInbox(); } }, 1000);
    }

    // "+" next to Direct messages: bring back someone you removed (or open any teammate)
    function initDmAdd() {
        const btn = document.getElementById('sc-dm-add');
        if (!btn) return;
        let pop = null;
        const close = () => { pop?.remove(); pop = null; };
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (pop) { close(); return; }
            const hidden = hiddenDms();
            const team = Object.keys((window.scGetTeam && window.scGetTeam()) || {});
            const list = hidden.length ? hidden : team;
            pop = document.createElement('div');
            pop.id = 'sc-dm-pop';
            pop.innerHTML = `<div class="sc-dm-pop-h">${hidden.length ? 'Removed from your list' : 'Start a direct message'}</div>`
                + list.map((h) => `<button type="button" data-h="${esc(h)}"><span class="sc-dm-avatar">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span><span>${esc(window.scLabelOf(h))}</span></button>`).join('');
            document.body.appendChild(pop);
            const r = btn.getBoundingClientRect();
            pop.style.left = `${r.left}px`; pop.style.top = `${r.bottom + 6}px`;
            pop.addEventListener('click', (ev) => {
                const h = ev.target.closest('[data-h]')?.dataset.h;
                if (!h) return;
                close(); window.scShowDm(h); openDm(h);
            });
        });
        document.addEventListener('mousedown', (e) => { if (pop && !pop.contains(e.target) && e.target !== btn && !btn.contains(e.target)) close(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
    }

    function init() {
        initDmAdd();
        applyCollapsed();
        initInboxFilters();
        initMe();
        renderDms();
        renderInboxBadge();
        updateTitle();
        (window.scOnTeamChange || []).push(renderDms, recheckPending);
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && inboxOpen()) window.scCloseInbox(); });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
