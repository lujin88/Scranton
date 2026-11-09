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
    // "Mark as unread" survives a reload (it used to live in memory only).
    let forceUnread;
    try { forceUnread = new Set(JSON.parse(LS.get('scranton-inbox-unread-keys', '[]') || '[]')); } catch (_) { forceUnread = new Set(); }
    // The Activity number = asks still waiting on you, nothing else (Lu, 11-09):
    //  - an ask is a question for you (option card / decision) or a PR for you to merge;
    //  - it's done when you answer it (pick an option, reply to it, or @ them in that channel
    //    afterwards), when the PR is merged or closed, or when you mark it done;
    //  - plain messages are listed but never counted (their channel shows them as unread);
    //  - only asks put to you (@Lu at the start, or a DM); older than 12 hours: dropped from the count. "Remind me" brings one back.
    const repliedTo = new Set();          // ids you replied to directly
    const myLastInThread = new Map();     // thread parent id -> id of your latest message in it
    const OPT_LINE = /(^|\n)\s*[A-H]\s*[.、:：)]/g;
    const isQuestion = (m) => (m.type === 'decision' && Array.isArray((m.metadata || {}).choices) && m.metadata.choices.length > 0)
        || (String(m.text || '').match(OPT_LINE) || []).length >= 2;
    // "Please merge #93": done once GitHub says merged (or closed). Lu doesn't report back.
    const PR_RE = /https:\/\/github\.com\/[\w.-]+\/[\w.-]+\/pull\/\d+/g;
    const prUrls = (m) => [...new Set(String(m.text || '').match(PR_RE) || [])];
    // url -> OPEN | MERGED | CLOSED. Merged/closed never change back, so they're kept across reloads:
    // otherwise every reload counted all of today's merged PRs as "Merge on GitHub" until GitHub answered.
    const prState = (() => { try { return JSON.parse(LS.get('scranton-pr-final', '{}')) || {}; } catch (_) { return {}; } })();
    const savePrFinal = () => {
        const keep = Object.entries(prState).filter(([, st]) => st === 'MERGED' || st === 'CLOSED').slice(-400);
        LS.set('scranton-pr-final', JSON.stringify(Object.fromEntries(keep)));
    };
    // "可以合 / 合并 / merge", not any 合 (合适, 合作, 综合 aren't asks to merge).
    const MERGE_RE = /可以合|请合|去合|合并|合进|合一下|合吧|合了吗|\bmerge/i;
    // A PR handed to you to merge (not a question with options that happens to link one):
    // only GitHub can say it's done. Replying in the chat doesn't merge it (Lu, 11-09: #117 and #94
    // showed "Answered" while still open).
    const isPrAsk = (m) => prUrls(m).length > 0 && MERGE_RE.test(String(m.text || '')) && !isQuestion(m);
    const isAsk = (m) => isQuestion(m) || isPrAsk(m);
    // The PM often asks again about the same PR: only the latest ask counts and is listed.
    const prNewest = new Map();   // PR url -> id of the latest ask to merge it
    const prRepeat = (m) => isPrAsk(m) && prUrls(m).every((u) => (prNewest.get(u) || 0) > Number(m.id));
    // For the notification sound: an ask addressed to you (mention, DM, or a reply to you), not yet done.
    window.scIsAskForMe = (m) => {
        if (!m || !isAgentSender(m.sender) || !['chat', 'message', 'decision'].includes(m.type || 'chat')) return false;
        return addressedToMe(m) && isAsk(m) && !answered(m);
    };
    const prDone = (m) => { const u = prUrls(m); return u.length > 0 && u.every((x) => prState[x] === 'MERGED' || prState[x] === 'CLOSED'); };
    async function refreshPrs() {
        // Also when hidden: the Mac app's Dock badge counts these while its window is in the back.
        // (Cheap: the server keeps open PRs for 3 min and merged ones for a day.)
        // Only PRs that could still count (recent, not marked done), newest first, all of them in
        // batches of 20. (Before: the first 20 found, which were old ones, so today's never got checked.)
        const want = new Set();
        const now = Date.now() / 1000;
        for (const m of [...inbox.values()].sort((a, b) => b.id - a.id)) {
            if (readKeys.has(keyOf(m)) || now - tsOf(m) > STALE_S) continue;
            for (const u of prUrls(m)) if (prState[u] !== 'MERGED' && prState[u] !== 'CLOSED') want.add(u);
        }
        const all = [...want];
        let changed = false;
        for (let i = 0; i < all.length; i += 20) {
            try {
                const q = all.slice(i, i + 20).map((u) => 'u=' + encodeURIComponent(u)).join('&');
                const r = await fetch('/api/scranton/pr-state?' + q, { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
                if (!r.ok) break;
                const got = await r.json();
                for (const [u, st] of Object.entries(got)) if (st && prState[u] !== st) { prState[u] = st; changed = true; }
            } catch (_) { break; }   /* offline: try again next round */
        }
        if (changed) { savePrFinal(); scheduleRender(); }
    }
    // Ask soon after a PR link shows up or Activity opens (at page load the history may not be in yet,
    // so a single check 3 s in found nothing and the next one was 2 minutes later), then every minute.
    let prTimer = null;
    const refreshPrsSoon = () => { clearTimeout(prTimer); prTimer = setTimeout(refreshPrs, 800); };
    window.scRefreshPrs = refreshPrsSoon;
    setInterval(refreshPrs, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshPrsSoon(); });
    // You talked to them after it, in the same channel (e.g. "@pm B" typed in the channel instead of
    // clicking): counts as dealt with. The PM re-asks anything still open when you're back.
    const myLastToIn = new Map();   // "channel|handle" -> id of your latest message there @mentioning them
    const answered = (m) => !!(prDone(m) || (!isPrAsk(m) && ((m.type === 'decision' && (m.metadata || {}).resolved)
        || repliedTo.has(Number(m.id))
        || (m.reply_to != null && (myLastInThread.get(Number(m.reply_to)) || 0) > Number(m.id))
        || (myLastToIn.get(`${m.channel || 'general'}|${String(m.sender || '').toLowerCase().replace(/-\d+$/, '')}`) || 0) > Number(m.id))));
    // Older than 12 hours: no longer counted. Overnight questions come back in the PM's
    // "Lu is back" list, so the count doesn't carry yesterday around.
    const STALE_S = 12 * 3600;
    const isUnread = (m) => {
        const k = keyOf(m);
        if (forceUnread.has(k)) return true;
        if (readKeys.has(k) || answered(m) || prRepeat(m)) return false;
        if (Date.now() / 1000 - tsOf(m) > STALE_S) return false;
        // Only asks count (Lu, 11-09: "我只需要关注我的 event", 52 when 2 really needed her):
        // a question for you, or a PR for you to merge. Everything else is just listed;
        // unread messages are already counted on their channel in the sidebar.
        if (!isAsk(m)) return false;
        // ...and only when it's actually put to you: @Lu, or a DM. A question one teammate asks
        // another in your thread isn't yours; the PM brings anything for you to you (Lu, 11-09).
        if (!addressedToMe(m)) return false;
        return tsOf(m) > seenTs;
    };
    // Deleted or cleared messages leave Activity too (they used to keep counting for 12 h).
    window.scInboxRemove = (ids) => {
        let hit = false;
        for (const id of ids || []) hit = inbox.delete(Number(id)) || hit;
        if (hit) scheduleRender();
    };
    window.scInboxClear = (channel) => {
        for (const [id, m] of inbox) if (!channel || (m.channel || 'general') === channel) inbox.delete(id);
        scheduleRender();
    };
    window.scInboxUpdate = (m) => {   // a decision answered (server message_update)
        const item = m && inbox.get(Number(m.id));
        if (item) { inbox.set(Number(m.id), { ...item, ...m, _kinds: item._kinds }); scheduleRender(); }
    };
    const saveRead = () => {
        LS.set('scranton-inbox-read-keys', JSON.stringify([...readKeys].slice(-500)));
        LS.set('scranton-inbox-unread-keys', JSON.stringify([...forceUnread].slice(-200)));
    };
    // One place that changes an item's read state: the row's dot, the message's "Mark as unread",
    // clicking the row, and seeing the message in its conversation all go through here.
    function setRead(m, read) {
        const k = keyOf(m);
        if (read) { readKeys.add(k); forceUnread.delete(k); } else { readKeys.delete(k); forceUnread.add(k); }
        saveRead();
        renderInboxBadge();
        if (inboxOpen()) renderInbox();
    }
    window.scMarkUnread = function (m) {
        const item = inbox.get(Number(m.id));
        if (item) setRead(item, false);
    };
    const pendingUnknown = [];   // messages from senders we couldn't classify yet

    function isAgentSender(sender) {
        const s = String(sender || '').toLowerCase();
        if (!s || s === 'system' || s === me().toLowerCase()) return false;
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        if (typeof agentConfig !== 'undefined' && agentConfig[s]) return true;
        return !!team[s] || !!team[s.replace(/-\d+$/, '')];
    }

    // Put to you: a DM, or @Lu among the names the message opens with ("@Lu …", "@Lu @pm …").
    // An @Lu further down ("…then send it to @Lu") is talk about you, not to you.
    function addressedToMe(m) {
        if (isDm(m.channel)) return true;
        return mentionsMe(leadOf(m.text));
    }
    const leadOf = (text) => (/^\s*(?:@[\w-]+[\s,，、]*)+/.exec(String(text || '')) || [''])[0];

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
        if (String(msg.sender || '').toLowerCase() === me().toLowerCase()) {
            myMsgIds.add(Number(msg.id));
            // only messages in the channel itself: an answer inside one card's thread says nothing about the others
            if (msg.reply_to == null) for (const h of String(msg.text || '').matchAll(/@([\w-]+)/g)) {
                const key = `${msg.channel || 'general'}|${h[1].toLowerCase().replace(/-\d+$/, '')}`;
                myLastToIn.set(key, Math.max(myLastToIn.get(key) || 0, Number(msg.id)));
            }
            if (msg.reply_to != null) {
                const p = Number(msg.reply_to);
                repliedTo.add(p);
                myLastInThread.set(p, Math.max(myLastInThread.get(p) || 0, Number(msg.id)));
                scheduleRender();
            }
            return;
        }
        if (!isAgentSender(msg.sender)) {
            if (pendingUnknown.length < 1000) pendingUnknown.push(msg);
            return;
        }
        const kinds = new Set();
        // Only when the message opens with @Lu, like the "needs you" count. "@Lu" further down is talk
        // about you, often "静默时段不 @Lu" (Lu, 11-09: why are these under Mentions?). They stay in All.
        if (mentionsMe(leadOf(msg.text))) kinds.add('mention');
        else if (mentionsMe(msg.text)) kinds.add('about');
        if (isDm(msg.channel)) kinds.add('dm');
        if (msg.reply_to != null && myMsgIds.has(Number(msg.reply_to))) kinds.add('reply');
        if (kinds.size) {
            inbox.set(Number(msg.id), { ...msg, _kinds: kinds });
            if (isPrAsk(msg)) for (const u of prUrls(msg)) prNewest.set(u, Math.max(prNewest.get(u) || 0, Number(msg.id)));
            scheduleRender();
            if (PR_RE.test(String(msg.text || ''))) { PR_RE.lastIndex = 0; refreshPrsSoon(); }
        }
    }

    // The page opens with only the newest messages of each channel, so Activity gets its own list:
    // everything from the last 7 days that's to you, a reply to you, a DM, or yours (Lu, 11-10).
    window.scAfterHistory = async () => {
        try {
            const r = await fetch('/api/scranton/inbox-feed?days=7', { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (!r.ok) return;
            const { messages } = await r.json();
            for (const m of messages || []) consider(m);
        } catch (_) { /* offline: Activity shows what the page has */ }
    };

    // Called when the team list arrives: classify messages that came in before it.
    function recheckPending() {
        const again = pendingUnknown.splice(0);
        for (const m of again) consider(m);
    }

    let renderPending = false;
    function scheduleRender() {
        if (renderPending) return;
        renderPending = true;
        const run = () => { renderPending = false; renderInboxBadge(); if (inboxOpen()) renderInbox(); };
        // A hidden page (the Mac app's window in the back, a background tab) gets no animation frames,
        // so the count, and the Dock badge read from it, would stay stale until you looked.
        if (document.hidden) setTimeout(run, 50); else requestAnimationFrame(run);
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
        paintMarkAll();
    }

    const inboxOpen = () => !document.getElementById('sc-inbox')?.classList.contains('hidden');
    function paintMarkAll() { /* the button lives in the list now and is drawn only when something needs you */ }

    let filterKind = 'mention';  // default: Mentions (Lu, 11-09). Asks count only when they @ you, so they're all here
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
        // One "Show" control instead of a toggle plus a sort: needs-you first (default), newest first,
        // or only what still needs you. The choice is remembered.
        // each tab says how many things in it need you
        document.querySelectorAll('#sc-inbox .sc-tab').forEach((t) => {
            const k = t.dataset.kind;
            const n = [...inbox.values()].filter((m) => (k === 'all' || m._kinds.has(k)) && isUnread(m)).length;
            let b = t.querySelector('.sc-tab-n');
            if (!b) { b = document.createElement('span'); b.className = 'sc-tab-n'; t.appendChild(b); }
            b.textContent = n ? String(n) : '';
        });
        const sortSel = document.getElementById('sc-inbox-sort');
        const mode = sortSel ? sortSel.value : 'needs';
        const items = [...inbox.values()]
            .filter((m) => !prRepeat(m))
            .filter((m) => filterKind === 'all' || m._kinds.has(filterKind))
            .filter((m) => !from || String(m.sender).toLowerCase() === from)
            .filter((m) => mode !== 'only' || isUnread(m))
            .sort((a, b) => (mode === 'needs' ? (isUnread(b) - isUnread(a)) : 0) || (b.id - a.id)).slice(0, 300);
        if (!items.length) {
            list.innerHTML = `<div class="sc-empty">${window.scIcon ? window.scIcon('bell', 28) : ''}<h3>${inbox.size ? 'Nothing matches' : 'No activity yet'}</h3><p>${inbox.size
                ? 'Try another filter.'
                : 'Mentions, replies and direct messages show up here.'}</p></div>`;
            return;
        }
        list.innerHTML = '';
        const needN = items.filter(isUnread).length;
        let doneHead = false;
        // "Mark all as read" sits with the count it clears (right above the list), not in the page header.
        const totalN = unreadCount();
        if (totalN) {
            const label = needN ? `Needs you · ${needN}` : `Nothing here needs you · ${totalN} in other tabs`;
            list.insertAdjacentHTML('beforeend', `<div class="sc-inbox-group sc-inbox-group-top"><span>${label}</span>`
                + `<button type="button" class="sc-inbox-markall" data-tip="Mark everything that needs you as done (⇧Esc)">${window.scIcon ? window.scIcon('check-double', 14) : ''}Mark all done</button></div>`);
            list.querySelector('.sc-inbox-markall').addEventListener('click', () => window.scInboxMarkRead());
        }
        for (const m of items) {
            if (mode === 'needs' && needN && !doneHead && !isUnread(m)) {
                doneHead = true;
                list.insertAdjacentHTML('beforeend', '<div class="sc-inbox-group">Everything else</div>');
            }
            const row = document.createElement('button');
            row.type = 'button';
            const unread = isUnread(m);
            row.className = 'sc-inbox-item' + (unread ? ' unread' : '');
            const where = isDm(m.channel) ? 'Direct message' : (m.channel || 'general');
            const sender = String(m.sender).toLowerCase();
            const label = window.scLabelOf ? window.scLabelOf(sender) : m.sender;
            const pic = window.scAvatarHtml ? window.scAvatarHtml(sender) : '';
            const text = String(m.text || '').replace(/\s+/g, ' ').trim();
            const forMe = addressedToMe(m);
            const q = forMe && isQuestion(m);
            const done = answered(m);
            const chosen = m.type === 'decision' && (m.metadata || {}).resolved ? String(m.metadata.chosen || '') : '';
            const prs = prUrls(m);
            const prClosed = prs.length && prs.every((u) => prState[u] === 'CLOSED');
            const status = forMe && (isPrAsk(m) || (prs.length && prDone(m))) ? (prDone(m)
                    ? `<span class="sc-inbox-status done">${window.scIcon ? window.scIcon('check', 14) : ''}${prClosed ? 'Closed on GitHub' : 'Merged on GitHub'}</span>`
                    : `<span class="sc-inbox-status todo">Merge on GitHub</span>`)
                : !q ? ''
                : done ? `<span class="sc-inbox-status done">${window.scIcon ? window.scIcon('check', 14) : ''}Answered${chosen ? ': ' + esc(chosen.length > 40 ? chosen.slice(0, 40) + '…' : chosen) : ''}</span>`
                : `<span class="sc-inbox-status todo">Needs your answer</span>`;
            row.innerHTML = `<span class="sc-inbox-avatar">${pic}</span>`
                + `<span class="sc-inbox-body"><span class="sc-inbox-meta"><b>${esc(label)}</b> <span>${esc(where)}</span></span>`
                + `<span class="sc-inbox-text">${esc(text.length > 240 ? text.slice(0, 240) + '…' : text)}</span>${status}</span>`
                + `<span class="sc-inbox-side"><span class="sc-inbox-time">${esc(relTime(m))}</span>`
                + `<span class="sc-read-toggle" role="button" tabindex="0" data-tip="${unread ? 'Mark as done' : 'Remind me'}" aria-label="${unread ? 'Mark as done' : 'Remind me'}"><span class="sc-unread-dot"></span></span></span>`;
            const tog = row.querySelector('.sc-read-toggle');
            const flip = (e) => { e.stopPropagation(); e.preventDefault(); setRead(m, isUnread(m)); };
            tog.addEventListener('click', flip);
            tog.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') flip(e); });
            row.addEventListener('click', () => jumpTo(m));
            row.addEventListener('contextmenu', (e) => { e.preventDefault(); rowMenu(e, m); });
            list.appendChild(row);
        }
    }

    // Right-click a row: the two things you'd want without opening it.
    function rowMenu(e, m) {
        document.querySelectorAll('.sc-inbox-menu').forEach((x) => x.remove());
        const unread = isUnread(m);
        const menu = document.createElement('div');
        menu.className = 'sc-inbox-menu sc-pop sc-menu';
        menu.setAttribute('role', 'menu');
        menu.innerHTML = `<button type="button" class="sc-menu-item" role="menuitem" data-k="read">${unread ? 'Mark as done' : 'Remind me (needs me)'}</button>`
            + '<button type="button" class="sc-menu-item" role="menuitem" data-k="open">Open in conversation</button>';
        document.body.appendChild(menu);
        const w = menu.offsetWidth, h = menu.offsetHeight;
        menu.style.left = Math.min(e.clientX, innerWidth - w - 8) + 'px';
        menu.style.top = Math.min(e.clientY, innerHeight - h - 8) + 'px';
        const close = () => { menu.remove(); document.removeEventListener('pointerdown', away, true); };
        const away = (ev) => { if (!menu.contains(ev.target)) close(); };
        document.addEventListener('pointerdown', away, true);
        menu.addEventListener('click', (ev) => {
            const k = ev.target.closest('[data-k]')?.dataset.k;
            if (!k) return;
            close();
            if (k === 'read') setRead(m, unread);
            if (k === 'open') jumpTo(m);
        });
        menu.querySelector('button').focus();
        const row = e.target && e.target.closest ? e.target.closest('.sc-inbox-item') : null;
        menu.addEventListener('keydown', (ev) => {
            if (ev.key !== 'Escape') return;
            ev.stopPropagation(); ev.preventDefault();   // close the menu, not the whole Activity panel
            close(); row?.focus();
        });
    }

    function initInboxFilters() {
        document.querySelectorAll('#sc-inbox .sc-tab').forEach((t) => t.addEventListener('click', () => {
            filterKind = t.dataset.kind;
            document.querySelectorAll('#sc-inbox .sc-tab').forEach((x) => { x.classList.toggle('active', x === t); x.setAttribute('aria-selected', String(x === t)); });
            renderInbox();
        }));
        document.getElementById('sc-inbox-from')?.addEventListener('change', renderInbox);
        const sortSel = document.getElementById('sc-inbox-sort');
        if (sortSel) {
            sortSel.value = LS.get('scranton-inbox-sort', 'needs');
            if (!sortSel.value) sortSel.value = 'needs';
            sortSel.addEventListener('change', () => { LS.set('scranton-inbox-sort', sortSel.value); renderInbox(); });
        }
        setInterval(() => { if (inboxOpen()) renderInbox(); }, 60000);  // keep "x minutes ago" fresh
    }

    function jumpTo(m) {
        setRead(m, true);
        window.scCloseInbox();
        // 4: the channel may have been renamed or deleted since; don't open a ghost channel.
        let ch = m.channel || 'general';
        if (!window.channelList.includes(ch)) ch = 'general';
        if (ch !== window.activeChannel && typeof switchChannel === 'function') switchChannel(ch);
        if (window.scFocusMessage) window.scFocusMessage(m);
        else setTimeout(() => { if (typeof scrollToMessage === 'function') scrollToMessage(m.id); }, 60);
        closeDrawer();
    }

    window.scOpenInbox = function () {
        if (window.scCloseRightPanel) window.scCloseRightPanel();
        document.getElementById('sc-inbox')?.classList.remove('hidden');
        document.body.classList.add('sc-inbox-open');
        refreshPrsSoon();
        document.getElementById('sc-inbox-row')?.classList.add('active');
        document.querySelectorAll('#channel-sidebar-list .channel-sidebar-row.active, #sc-dm-list .sc-side-row.active')
            .forEach((el) => el.classList.add('sc-dimmed'));
        renderInbox();
        closeDrawer();
    };
    window.scCloseInbox = function () {
        document.getElementById('sc-inbox')?.classList.add('hidden');
        document.body.classList.remove('sc-inbox-open');
        document.getElementById('sc-inbox-row')?.classList.remove('active');
        document.querySelectorAll('.sc-dimmed').forEach((el) => el.classList.remove('sc-dimmed'));
    };
    window.scInboxMarkRead = function () {
        const n = unreadCount();
        if (!n) return;
        const before = { seenTs, read: [...readKeys], unread: [...forceUnread] };
        // Message times only: they're the server's clock. Mixing in this device's clock hid
        // asks that arrived in the next few seconds when the iPad ran ahead.
        for (const m of inbox.values()) seenTs = Math.max(seenTs, tsOf(m));
        LS.set('scranton-inbox-seen-ts', String(seenTs));
        readKeys.clear(); forceUnread.clear(); saveRead();
        renderInboxBadge();
        renderInbox();
        // Easy to hit by accident and it touches every tab, so it can be undone.
        if (window.scToast) window.scToast(`Marked ${n} done`, { label: 'Undo', run: () => {
            seenTs = before.seenTs; LS.set('scranton-inbox-seen-ts', String(seenTs));
            readKeys = new Set(before.read); forceUnread = new Set(before.unread); saveRead();
            renderInboxBadge(); if (inboxOpen()) renderInbox();
        } });
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

    // Direct messages: drag to put them in your own order (kept on this device).
    const DM_MIME = 'application/x-scranton-dm';
    const dmOrder = () => { try { return JSON.parse(LS.get('scranton-dm-order', '[]')) || []; } catch (_) { return []; } };
    document.addEventListener('dragover', (e) => {
        if (![...(e.dataTransfer?.types || [])].includes(DM_MIME)) return;
        const row = e.target.closest && e.target.closest('#sc-dm-list .sc-dm-row');
        document.querySelectorAll('#sc-dm-list .sc-drop-before, #sc-dm-list .sc-drop-after').forEach((r) => r.classList.remove('sc-drop-before', 'sc-drop-after'));
        if (!row) return;
        e.preventDefault();
        const r = row.getBoundingClientRect();
        row.classList.add(e.clientY < r.top + r.height / 2 ? 'sc-drop-before' : 'sc-drop-after');
    }, true);
    document.addEventListener('drop', (e) => {
        if (![...(e.dataTransfer?.types || [])].includes(DM_MIME)) return;
        e.preventDefault(); e.stopPropagation();
        const h = e.dataTransfer.getData(DM_MIME);
        const row = e.target.closest && e.target.closest('#sc-dm-list .sc-dm-row');
        if (!row || !h || row.dataset.h === h) { renderDms(); return; }
        const before = e.clientY < row.getBoundingClientRect().top + row.getBoundingClientRect().height / 2;
        const shown = [...document.querySelectorAll('#sc-dm-list .sc-dm-row')].map((r) => r.dataset.h).filter((x) => x !== h);
        shown.splice(shown.indexOf(row.dataset.h) + (before ? 0 : 1), 0, h);
        // keep people not shown right now in the order too, after the ones on screen
        LS.set('scranton-dm-order', JSON.stringify([...shown, ...dmOrder().filter((x) => !shown.includes(x))]));
        renderDms();
    }, true);

    function renderDms() {
        const list = document.getElementById('sc-dm-list');
        if (!list) return;
        list.innerHTML = '';
        const state = window.scAgentState || (() => 'offline');
        const order = { working: 0, pending: 1, available: 2, offline: 3 };
        const handles = teamHandles().sort((a, b) => (order[state(a)] - order[state(b)])
            || window.scLabelOf(a).localeCompare(window.scLabelOf(b)));
        const hidden = hiddenDms();
        // Like Slack: only people you've actually talked to (most recent first), plus the
        // one open right now. "+" starts a new one; a new message brings someone back.
        const recent = (h) => dmActivity[`dm-${h}`.slice(0, 20)] || 0;
        handles.sort((a, b) => recent(b) - recent(a));
        // Once you've dragged them into an order, that order holds; new people go at the end.
        const mine = dmOrder();
        if (mine.length) {
            const at = (h) => { const i = mine.indexOf(h); return i < 0 ? 1e6 : i; };
            handles.sort((a, b) => at(a) - at(b));
        }
        let shown = 0;
        for (const h of handles) {
            const ch = `dm-${h}`.slice(0, 20);
            const unreadNow = (window.channelUnread && window.channelUnread[ch]) || 0;
            if (hidden.includes(h) && !unreadNow && ch !== window.activeChannel) continue;
            if (!recent(h) && !unreadNow && ch !== window.activeChannel) continue;
            shown++;
            const row = document.createElement('button');
            row.type = 'button';
            row.className = `sc-side-row sc-dm-row ${state(h)}` + (ch === window.activeChannel && !inboxOpen() ? ' active' : '');
            row.dataset.h = h;
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
            row.draggable = true;
            row.addEventListener('dragstart', (e) => { e.dataTransfer.setData(DM_MIME, h); e.dataTransfer.effectAllowed = 'move'; row.classList.add('sc-dragging'); });
            row.addEventListener('dragend', () => { row.classList.remove('sc-dragging'); list.querySelectorAll('.sc-drop-before, .sc-drop-after').forEach((r) => r.classList.remove('sc-drop-before', 'sc-drop-after')); });
            list.appendChild(row);
        }
        if (!shown) {
            const hint = document.createElement('button');
            hint.type = 'button'; hint.className = 'sc-side-row sc-dm-empty';
            hint.innerHTML = `<span class="sc-dm-avatar">${window.scIcon ? window.scIcon('add', 16) : '+'}</span><span class="sc-side-label">Message a teammate</span>`;
            hint.addEventListener('click', (e) => { e.stopPropagation(); document.getElementById('sc-dm-add')?.click(); });
            list.appendChild(hint);
        }
    }

    // When each DM last had a message (server), kept fresh from live messages.
    let dmActivity = {};
    async function loadDmActivity() {
        try {
            const r = await fetch('/api/scranton/dm-activity', { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (r.ok) { dmActivity = await r.json(); renderDms(); }
        } catch (_) { /* offline: keep what we have */ }
    }
    window.scNoteDmMessage = (msg) => {
        const ch = String(msg && msg.channel || '');
        if (!ch.startsWith('dm-') || (msg.type && msg.type !== 'chat') || msg.sender === 'system') return;
        const t = Number(msg.timestamp) || Date.now() / 1000;
        if ((dmActivity[ch] || 0) >= t) return;
        dmActivity[ch] = t;
        renderDms();   // most recent first, so a new message moves that person up
    };
    window.scReloadDmActivity = loadDmActivity;
    loadDmActivity();

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
            if (window.scUpdateComposerHint) window.scUpdateComposerHint();
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
            const data = c.toDataURL('image/jpeg', 0.85);
            LS.set('scranton-me-avatar', data);
            saveAvatarToServer(data);
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
            const team = Object.keys((window.scGetTeam && window.scGetTeam()) || {});
            const inList = new Set(Array.from(document.querySelectorAll('#sc-dm-list .sc-dm-row')).map((r) => r.dataset.h));
            const list = team.filter((h) => !inList.has(h)).sort((a, b) => window.scLabelOf(a).localeCompare(window.scLabelOf(b)));
            pop = document.createElement('div');
            pop.id = 'sc-dm-pop';
            pop.innerHTML = `<div class="sc-dm-pop-h">${list.length ? 'Start a direct message' : 'Everyone is already in your list'}</div>`
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
