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
    let lastSeen = parseInt(LS.get('scranton-inbox-seen', '0'), 10) || 0;
    const readIds = new Set(JSON.parse(LS.get('scranton-inbox-read', '[]') || '[]'));
    const isUnread = (id) => id > lastSeen && !readIds.has(id);

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
        const type = msg.type || 'chat';
        if (type !== 'chat' && type !== 'message' && type !== undefined && type !== 'decision') return;
        if (String(msg.sender || '').toLowerCase() === me().toLowerCase()) { myMsgIds.add(Number(msg.id)); return; }
        if (!isAgentSender(msg.sender)) return;
        const toMe = mentionsMe(msg.text)
            || isDm(msg.channel)
            || (msg.reply_to != null && myMsgIds.has(Number(msg.reply_to)));
        if (toMe) {
            inbox.set(Number(msg.id), msg);
            scheduleRender();
        }
    }

    let renderPending = false;
    function scheduleRender() {
        if (renderPending) return;
        renderPending = true;
        requestAnimationFrame(() => { renderPending = false; renderInboxBadge(); if (inboxOpen()) renderInbox(); });
    }

    function unreadCount() {
        let n = 0;
        for (const id of inbox.keys()) if (isUnread(id)) n++;
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

    function renderInbox() {
        const list = document.getElementById('sc-inbox-list');
        if (!list) return;
        const items = [...inbox.values()].sort((a, b) => b.id - a.id).slice(0, 200);
        if (!items.length) {
            list.innerHTML = '<div class="sc-inbox-empty">Nothing yet. When a teammate @mentions you, replies to you, or writes in a direct message, it shows up here.</div>';
            return;
        }
        list.innerHTML = '';
        for (const m of items) {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'sc-inbox-item' + (isUnread(Number(m.id)) ? ' unread' : '');
            const where = isDm(m.channel) ? 'Direct message' : `#${m.channel || 'general'}`;
            const label = window.scLabelOf ? window.scLabelOf(String(m.sender).toLowerCase()) : m.sender;
            const pic = window.scAvatarHtml ? window.scAvatarHtml(String(m.sender).toLowerCase()) : '';
            const text = String(m.text || '').replace(/\s+/g, ' ').trim();
            row.innerHTML = `<span class="sc-inbox-avatar">${pic}</span>`
                + `<span class="sc-inbox-body"><span class="sc-inbox-meta"><b>${esc(label)}</b> <span>${esc(where)}</span> <span>${esc(m.time || '')}</span></span>`
                + `<span class="sc-inbox-text">${esc(text.length > 280 ? text.slice(0, 280) + '…' : text)}</span></span>`;
            row.addEventListener('click', () => jumpTo(m));
            list.appendChild(row);
        }
    }

    function jumpTo(m) {
        readIds.add(Number(m.id));
        LS.set('scranton-inbox-read', JSON.stringify([...readIds].filter((id) => id > lastSeen).slice(-500)));
        renderInboxBadge();
        window.scCloseInbox();
        const ch = m.channel || 'general';
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
        for (const id of inbox.keys()) lastSeen = Math.max(lastSeen, id);
        LS.set('scranton-inbox-seen', String(lastSeen));
        readIds.clear(); LS.set('scranton-inbox-read', '[]');
        renderInboxBadge();
        renderInbox();
    };

    if (typeof appendMessage === 'function') {
        const origAppend = appendMessage;
        appendMessage = function (msg) {
            const r = origAppend.apply(this, arguments);
            try { consider(msg); addSelfAvatar(msg); } catch (_) { /* never break chat rendering */ }
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

    function renderDms() {
        const list = document.getElementById('sc-dm-list');
        if (!list) return;
        list.innerHTML = '';
        const state = window.scAgentState || (() => 'offline');
        const order = { working: 0, pending: 1, available: 2, offline: 3 };
        const handles = teamHandles().sort((a, b) => (order[state(a)] - order[state(b)])
            || window.scLabelOf(a).localeCompare(window.scLabelOf(b)));
        for (const h of handles) {
            const ch = `dm-${h}`.slice(0, 20);
            const row = document.createElement('button');
            row.type = 'button';
            row.className = `sc-side-row sc-dm-row ${state(h)}` + (ch === window.activeChannel && !inboxOpen() ? ' active' : '');
            row.title = `Direct message @${h}`;
            const unread = (window.channelUnread && window.channelUnread[ch]) || 0;
            row.innerHTML = `<span class="sc-dm-avatar">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}<span class="team-dot"></span></span>`
                + `<span class="sc-side-label">${esc(window.scLabelOf(h))}</span>`
                + (unread && ch !== window.activeChannel ? `<span class="sc-badge">${unread > 99 ? '99+' : unread}</span>` : '');
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
        };
    }
    if (typeof switchChannel === 'function') {
        const origSwitch = switchChannel;
        switchChannel = function (name) {
            window.scCloseInbox();
            const r = origSwitch.apply(this, arguments);
            if (typeof renderChannelSidebar === 'function') renderChannelSidebar();
            updateTitle();
            return r;
        };
    }

    function updateTitle() {
        const ch = window.activeChannel || 'general';
        document.body.classList.toggle('sc-in-dm', isDm(ch));
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
    function addSelfAvatar(msg) {
        if (!msg || String(msg.sender || '').toLowerCase() !== me().toLowerCase()) return;
        const el = document.getElementById(`message-${msg.id}`);
        if (!el || el.querySelector('.avatar-wrap')) return;
        const wrap = document.createElement('div');
        wrap.className = 'avatar-wrap sc-self-avatar';
        wrap.innerHTML = `<div class="avatar">${myAvatarHtml()}</div>`;
        const bubble = el.querySelector('.chat-bubble');
        if (bubble) el.insertBefore(wrap, bubble);
    }
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
            LS.set('scranton-me-avatar', c.toDataURL('image/jpeg', 0.85));
            URL.revokeObjectURL(url);
            renderMe();
        };
        img.src = url;
    }

    function initMe() {
        const btn = document.getElementById('sc-me');
        const file = document.getElementById('sc-me-file');
        if (!btn || !file) return;
        btn.addEventListener('click', (e) => {
            // Click the picture to change it; click the name to open Settings (name lives there).
            if (e.target.closest('#sc-me-avatar')) file.click();
            else document.getElementById('settings-toggle')?.click();
        });
        file.addEventListener('change', () => { pickAvatar(file.files && file.files[0]); file.value = ''; });
        renderMe();
        // username arrives from the server after connect; refresh when settings change
        let last = me();
        setInterval(() => { if (me() !== last) { last = me(); renderMe(); renderInbox(); } }, 1000);
    }

    function init() {
        applyCollapsed();
        initMe();
        renderDms();
        renderInboxBadge();
        updateTitle();
        (window.scOnTeamChange || []).push(renderDms);
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && inboxOpen()) window.scCloseInbox(); });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
