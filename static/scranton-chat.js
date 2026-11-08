// Scranton chat layer (Buzz / Slack style):
// - thread replies leave the main stream; a summary ("N replies") sits under the root
// - threads open in a right-hand panel with tabs; replying there keeps agents in the thread
// - hover toolbar: react, reply in thread, copy link, forward, more
// - emoji reactions under messages
// Loaded after chat.js, channels.js, scranton.js and scranton-nav.js.

(function () {
    const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const me = () => (typeof username === 'string' ? username : 'Lu');
    const QUICK = ['👍', '❤️', '😂', '🎉', '👀', '✅', '🙏', '🔥'];

    const byId = new Map();          // id -> msg (as received, plus reactions)
    window.scMsgs = byId;            // read-only use elsewhere (who has not answered yet)
    const replies = new Map();       // rootId -> [msg]
    const openThreads = [];          // rootIds, newest last
    let activeThread = null;
    const seenReplyCount = new Map(); // rootId -> replies seen when the thread was last open

    function rootOf(msg) {
        let cur = msg, guard = 0;
        while (cur && cur.reply_to != null && guard++ < 50) {
            const parent = byId.get(Number(cur.reply_to));
            if (!parent) return Number(cur.reply_to);
            cur = parent;
        }
        return cur ? Number(cur.id) : null;
    }

    const findEl = (id, container) =>
        (container && container.querySelector && container.querySelector(`#message-${CSS.escape(String(id))}`))
        || document.getElementById(`message-${id}`);

    const labelOf = (n) => (window.scLabelOf ? window.scLabelOf(String(n).toLowerCase()) : n);
    const avatarOf = (n) => {
        if (String(n).toLowerCase() === me().toLowerCase()) {
            const el = document.getElementById('sc-me-avatar');
            return el ? el.innerHTML : esc(me().charAt(0));
        }
        return (window.scAvatarHtml && window.scAvatarHtml(String(n).toLowerCase())) || esc(String(n).charAt(0).toUpperCase());
    };

    // ------------------------------------------------------------------
    // Rendering helpers
    // ------------------------------------------------------------------
    function textHtml(msg) {
        try {
            const h = renderMarkdown(String(msg.text || ''));
            return typeof styleHashtags === 'function' ? styleHashtags(h) : h;
        } catch (_) { return esc(msg.text || ''); }
    }

    function reactionsHtml(msg) {
        const r = msg.reactions || {};
        const keys = Object.keys(r);
        if (!keys.length) return '';
        return keys.map((emo) => {
            const users = r[emo] || [];
            const mine = users.some((u) => String(u).toLowerCase() === me().toLowerCase());
            return `<button type="button" class="sc-reaction${mine ? ' mine' : ''}" data-emoji="${esc(emo)}" title="${esc(users.join(', '))}">${esc(emo)} <span>${users.length}</span></button>`;
        }).join('') + '<button type="button" class="sc-reaction sc-reaction-add" data-add="1" title="Add reaction">+</button>';
    }

    function paintReactions(msg, container) {
        const el = findEl(msg.id, container);
        const targets = [el, document.querySelector(`#sc-thread [data-mid="${msg.id}"]`)].filter(Boolean);
        for (const t of targets) {
            let box = t.querySelector(':scope .sc-reactions');
            if (!box) {
                box = document.createElement('div');
                box.className = 'sc-reactions';
                const anchor = t.querySelector('.chat-bubble, .sc-tmsg-body') || t;
                anchor.appendChild(box);
            }
            box.innerHTML = reactionsHtml(msg);
            box.dataset.mid = msg.id;
        }
    }

    function paintSummary(rootId, container) {
        const el = findEl(rootId, container);
        if (!el) return;
        const list = replies.get(rootId) || [];
        let box = el.querySelector('.sc-thread-summary');
        if (!list.length) { if (box) box.remove(); return; }
        if (!box) {
            box = document.createElement('button');
            box.type = 'button';
            box.className = 'sc-thread-summary';
            box.dataset.root = rootId;
            // under the bubble, not inside it
            const bubble = el.querySelector('.chat-bubble');
            if (bubble) {
                let col = bubble.parentElement.classList.contains('sc-bubble-col') ? bubble.parentElement : null;
                if (!col) {
                    col = document.createElement('div');
                    col.className = 'sc-bubble-col';
                    bubble.before(col);
                    col.appendChild(bubble);
                }
                col.appendChild(box);
            } else el.appendChild(box);
        }
        const people = [...new Set(list.map((m) => String(m.sender)))].slice(-3);
        const unread = list.length > (seenReplyCount.get(rootId) || 0)
            && list.some((m) => String(m.sender).toLowerCase() !== me().toLowerCase());
        box.innerHTML = `<span class="sc-ts-avatars">${people.map((p) => `<span class="sc-ts-av">${avatarOf(p)}</span>`).join('')}</span>`
            + `<span class="sc-ts-count">${list.length} ${list.length === 1 ? 'reply' : 'replies'}</span>`
            + (unread ? '<span class="sc-unread-dot"></span>' : '');
    }

    // ------------------------------------------------------------------
    // Message intake (wraps appendMessage)
    // ------------------------------------------------------------------
    if (typeof appendMessage === 'function') {
        const origAppend = appendMessage;
        appendMessage = function (msg, options) {
            const r = origAppend.apply(this, arguments);
            try { intake(msg, options && options.container); } catch (e) { console.warn('scranton-chat', e); }
            return r;
        };
    }

    function intake(msg, container) {
        if (!msg || msg.id == null) return;
        const id = Number(msg.id);
        byId.set(id, msg);
        const el = findEl(id, container);
        if (el && (msg.type || 'chat') === 'chat') {
            el.classList.add('sc-msg');
            addToolbar(el, id);
            relabel(el, msg);
            try { paintQuote(el, msg); paintStuck(el, msg); } catch (_) { /* never break rendering */ }
        }
        if (msg.reactions && Object.keys(msg.reactions).length) paintReactions(msg, container);
        if (msg.reply_to != null) {
            const root = rootOf(msg);
            if (root != null && root !== id) {
                if (el) el.classList.add('sc-in-thread');
                if (!replies.has(root)) replies.set(root, []);
                const list = replies.get(root);
                if (!list.some((m) => Number(m.id) === id)) list.push(msg);
                paintSummary(root, container);
                if (activeThread === root) { renderThread(); seenReplyCount.set(root, list.length); paintSummary(root, container); }
            }
        }
    }

    // Show teammates by name (项目经理), not by handle (pm); the handle stays in the tooltip.
    function relabel(el, msg) {
        const s = el.querySelector('.msg-sender');
        if (!s) return;
        const name = labelOf(msg.sender);
        if (name && name !== s.textContent) { s.textContent = name; s.title = `@${String(msg.sender).toLowerCase()}`; }
        polishText(el, '.msg-text .mention');
        shortTime(el.querySelector('.bubble-header .msg-time'));
    }
    // @pm → @项目经理 inside the text, as Buzz shows names in mention chips;
    // @lu → @Lu, marked so a mention of you stands out.
    function polishText(el, sel) {
        el.querySelectorAll(sel).forEach((m) => {
            const h = (m.dataset.handle || m.textContent.replace(/^@/, '')).trim();
            const isMe = h.toLowerCase() === me().toLowerCase();
            const lab = isMe ? me() : labelOf(h);
            if (lab && lab !== h) { m.dataset.handle = h; m.textContent = '@' + lab; m.title = '@' + h.toLowerCase(); }
            m.classList.toggle('sc-mention-me', isMe);
        });
    }
    // 22:19:50 → 22:19 (seconds stay in the tooltip)
    function shortTime(t) {
        if (!t || t.dataset.full) return;
        const s = t.textContent.trim();
        const m = s.match(/^(\d{1,2}:\d{2}):\d{2}$/);
        if (m) { t.dataset.full = s; t.title = s; t.textContent = m[1]; }
    }
    window.scOnTeamChange = window.scOnTeamChange || [];
    window.scOnTeamChange.push(() => {
        for (const [id, m] of byId) { const el = document.getElementById(`message-${id}`); if (el) relabel(el, m); }
        // portraits arrive with the team; summaries painted before that show initials
        for (const root of replies.keys()) paintSummary(root);
    });

    // live reactions
    if (typeof handleServerEvent === 'function') {
        const origHandle = handleServerEvent;
        handleServerEvent = function (event) {
            if (event && event.type === 'reaction') {
                const m = byId.get(Number(event.id));
                if (m) { m.reactions = event.reactions || {}; paintReactions(m); }
                return;
            }
            if (event && event.type === 'delete' && Array.isArray(event.ids)) {
                for (const did of event.ids) {
                    byId.delete(Number(did));
                    for (const [root, list] of replies) {
                        const i = list.findIndex((m) => Number(m.id) === Number(did));
                        if (i >= 0) { list.splice(i, 1); paintSummary(root); }
                    }
                    if (replies.has(Number(did))) closeThread(Number(did));
                }
            }
            const r = origHandle.apply(this, arguments);
            if (event && (event.type === 'delete' || event.type === 'clear') && activeThread != null) renderThread();
            return r;
        };
    }

    // ------------------------------------------------------------------
    // Hover toolbar + menus
    // ------------------------------------------------------------------
    const ri = (n) => (window.scIcon ? window.scIcon(n, 16) : '');
    const ICONS = { get reply() { return ri('reply'); }, get react() { return ri('emoji'); }, get thread() { return ri('thread'); }, get link() { return ri('link'); },
        get forward() { return ri('forward'); }, get more() { return ri('more'); } };

    function addToolbar(el, id) {
        if (el.querySelector('.sc-tools')) return;
        const bar = document.createElement('div');
        bar.className = 'sc-tools';
        bar.innerHTML = `<button type="button" data-act="react" title="Add reaction (E)">${ICONS.react}</button>`
            + `<button type="button" data-act="reply" title="Reply here (R)">${ICONS.reply}</button>`
            + `<button type="button" data-act="thread" title="Reply in thread (T)">${ICONS.thread}</button>`
            + `<button type="button" data-act="link" title="Copy link">${ICONS.link}</button>`
            + `<button type="button" data-act="forward" title="Forward message">${ICONS.forward}</button>`
            + `<button type="button" data-act="more" title="More">${ICONS.more}</button>`;
        bar.dataset.mid = id;
        el.appendChild(bar);
    }

    function closePops() { document.querySelectorAll('.sc-pop').forEach((p) => p.remove()); }

    function popAt(anchor, html, cls) {
        closePops();
        const pop = document.createElement('div');
        pop.className = `sc-pop ${cls || ''}`;
        pop.innerHTML = html;
        document.body.appendChild(pop);
        const r = anchor.getBoundingClientRect();
        const w = pop.offsetWidth, h = pop.offsetHeight;
        let left = Math.min(r.right - w, window.innerWidth - w - 8);
        left = Math.max(8, left);
        let top = r.bottom + 6;
        if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
        pop.style.left = `${left}px`;
        pop.style.top = `${top}px`;
        return pop;
    }

    function react(id, emoji) {
        if (window.ws && window.ws.readyState === WebSocket.OPEN) {
            window.ws.send(JSON.stringify({ type: 'react', id, emoji }));
        }
    }

    function linkFor(id) { return `${location.origin}${location.pathname}#msg-${id}`; }

    async function copyText(t, label) {
        try { await navigator.clipboard.writeText(t); toast(`${label} copied`); }
        catch (_) { toast('Copy failed'); }
    }

    function toast(text) {
        const t = document.createElement('div');
        t.className = 'sc-toast';
        t.textContent = text;
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 1600);
    }

    function openEmoji(anchor, id) {
        const pop = popAt(anchor, QUICK.map((e) => `<button type="button" class="sc-emoji" data-emoji="${e}">${e}</button>`).join(''), 'sc-emoji-pop');
        pop.addEventListener('click', (e) => {
            const b = e.target.closest('[data-emoji]');
            if (b) { react(id, b.dataset.emoji); closePops(); }
        });
    }

    function openForward(anchor, id) {
        const m = byId.get(id);
        if (!m) return;
        const chans = (window.channelList || []).filter((c) => !c.startsWith('dm-'));
        const dms = (window.channelList || []).filter((c) => c.startsWith('dm-'));
        const row = (c) => `<button type="button" class="sc-menu-item" data-ch="${esc(c)}">${c.startsWith('dm-') ? esc(labelOf(c.slice(3))) : '# ' + esc(c)}</button>`;
        const pop = popAt(anchor, `<div class="sc-menu-title">Forward to</div>${chans.map(row).join('')}${dms.length ? '<div class="sc-menu-sep"></div>' + dms.map(row).join('') : ''}`, 'sc-menu');
        pop.addEventListener('click', (e) => {
            const b = e.target.closest('[data-ch]');
            if (!b) return;
            const from = m.channel && m.channel.startsWith('dm-') ? 'a direct message' : `#${m.channel || 'general'}`;
            const quoted = String(m.text || '').split('\n').map((l) => `> ${l}`).join('\n');
            const text = `↪ Forwarded from ${labelOf(m.sender)} in ${from}:\n${quoted}`;
            if (window.ws && window.ws.readyState === WebSocket.OPEN) {
                window.ws.send(JSON.stringify({ type: 'message', text, sender: me(), channel: b.dataset.ch, attachments: [] }));
                toast('Forwarded');
            }
            closePops();
        });
    }

    function openMore(anchor, id) {
        const m = byId.get(id);
        if (!m) return;
        const items = [
            ['unread', 'Mark unread'],
            ['copy', 'Copy message'],
            ['link', 'Copy link'],
            ['forward', 'Forward message'],
            ['reply', 'Reply here'],
            ['thread', 'Reply in thread'],
            ['delete', 'Delete message', 'danger'],
        ];
        const pop = popAt(anchor, items.map(([k, label, cls]) =>
            `<button type="button" class="sc-menu-item ${cls || ''}" data-k="${k}">${esc(label)}</button>`).join(''), 'sc-menu');
        pop.addEventListener('click', (e) => {
            const b = e.target.closest('[data-k]');
            if (!b) return;
            const k = b.dataset.k;
            closePops();
            if (k === 'copy') copyText(String(m.text || ''), 'Message');
            if (k === 'link') copyText(linkFor(id), 'Link');
            if (k === 'forward') openForward(anchor, id);
            if (k === 'thread') openThread(rootOf(m) ?? id);
            if (k === 'reply') quoteReply(id);
            if (k === 'unread') {
                const ch = m.channel || 'general';
                if (window.channelUnread) window.channelUnread[ch] = (window.channelUnread[ch] || 0) + 1;
                if (window.scMarkUnread) window.scMarkUnread(m);
                if (typeof renderChannelSidebar === 'function') renderChannelSidebar();
                toast('Marked unread');
            }
            if (k === 'delete') {
                if (confirm('Delete this message?') && window.ws && window.ws.readyState === WebSocket.OPEN) {
                    window.ws.send(JSON.stringify({ type: 'delete', ids: [id] }));
                }
            }
        });
    }

    document.addEventListener('click', (e) => {
        const tool = e.target.closest('.sc-tools button');
        if (tool) {
            e.stopPropagation();
            const id = Number(tool.closest('.sc-tools').dataset.mid);
            const act = tool.dataset.act;
            const m = byId.get(id);
            if (act === 'react') openEmoji(tool, id);
            if (act === 'reply') quoteReply(id);
            if (act === 'thread') openThread(m ? (rootOf(m) ?? id) : id);
            if (act === 'link') copyText(linkFor(id), 'Link');
            if (act === 'forward') openForward(tool, id);
            if (act === 'more') openMore(tool, id);
            return;
        }
        const pill = e.target.closest('.sc-reaction');
        if (pill) {
            e.stopPropagation();
            const id = Number(pill.closest('.sc-reactions').dataset.mid);
            if (pill.dataset.add) openEmoji(pill, id); else react(id, pill.dataset.emoji);
            return;
        }
        const sum = e.target.closest('.sc-thread-summary');
        if (sum) { e.stopPropagation(); openThread(Number(sum.dataset.root)); return; }
        if (!e.target.closest('.sc-pop')) closePops();
    }, true);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePops(); });

    // ---- Reply here: quote a message in the main conversation (not a thread) ----
    // The quote travels in the text as a first line "> 项目经理: …", so agents reading
    // the channel see exactly what you're answering (e.g. "B" to "A, B or C?").
    let quoting = null;
    function quoteReply(id) {
        const m = byId.get(id);
        if (!m) return;
        const who = window.scLabelOf ? window.scLabelOf(String(m.sender)) : String(m.sender);
        // "@" in the quoted text is defused (zero-width space), so quoting "@dev fix it" doesn't wake dev again
        const snippet = String(m.text || '').replace(/^> .*\n/, '').replace(/\s+/g, ' ').trim().slice(0, 140).replace(/@/g, '@\u200b');
        quoting = { id, who, snippet, handle: String(m.sender) };
        let bar = document.getElementById('sc-quote');
        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'sc-quote';
            const row = document.getElementById('input-row');
            row?.parentElement?.insertBefore(bar, row);
        }
        bar.innerHTML = `<span class="sc-quote-ic">${ri('reply')}</span><span class="sc-quote-t"><b>${esc(who)}</b> ${esc(snippet)}</span>`
            + `<button type="button" class="sc-quote-x" aria-label="Cancel reply">${ri('close')}</button>`;
        bar.querySelector('.sc-quote-x').onclick = clearQuote;
        document.getElementById('input')?.focus();
    }
    function clearQuote() { quoting = null; document.getElementById('sc-quote')?.remove(); }
    window.scQuoteReply = quoteReply;
    window.scTakeQuote = () => { const q = quoting; clearQuote(); return q; };
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && quoting && document.activeElement?.id === 'input') clearQuote();
    });

    // Shortcuts on the message under the pointer: R reply here, T thread, E react
    let hovered = null;
    document.addEventListener('mouseover', (e) => { const m = e.target.closest?.('.message.sc-msg'); if (m) hovered = m; });
    document.addEventListener('keydown', (e) => {
        if (e.metaKey || e.ctrlKey || e.altKey) return;
        const a = document.activeElement;
        if (a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA' || a.isContentEditable)) return;
        if (!hovered || !hovered.matches(':hover')) return;
        const id = Number(hovered.dataset.id);
        if (!id && id !== 0) return;
        const k = e.key.toLowerCase();
        if (k === 'r') { e.preventDefault(); quoteReply(id); }
        if (k === 't') { e.preventDefault(); const m = byId.get(id); openThread(m ? (rootOf(m) ?? id) : id); }
        if (k === 'e') { e.preventDefault(); const b = hovered.querySelector('.sc-tools [data-act="react"]'); if (b) openEmoji(b, id); }
    });

    // Show a "> who: text" first line as a quote block above the message
    function paintQuote(el, msg) {
        const t = String(msg && msg.text || '');
        const mm = t.match(/^> ([^\n]{1,200})\n/);
        const body = el && el.querySelector('.msg-text');
        if (!mm || !body || body.dataset.scQuote) return;
        body.dataset.scQuote = '1';
        const line = mm[1];
        const html = body.innerHTML;
        const escLine = esc('> ' + line).replace(/&#39;/g, "'");
        let idx = html.indexOf(escLine);
        if (idx < 0) idx = html.indexOf(esc('> ' + line));
        if (idx >= 0) {
            let rest = html.slice(idx + escLine.length).replace(/^(<br\s*\/?>|\n)/, '');
            body.innerHTML = html.slice(0, idx) + rest;
        }
        const q = document.createElement('div');
        q.className = 'sc-quoted';
        const c = line.indexOf(': ');
        q.innerHTML = c > 0 ? `<b>${esc(line.slice(0, c))}</b> ${esc(line.slice(c + 2))}` : esc(line);
        body.parentElement.insertBefore(q, body);
    }
    window.scPaintQuote = paintQuote;

    // "my terminal is waiting on a question" → a button straight to that agent's terminal
    function paintStuck(el, msg) {
        // Every "I stopped…" post from a teammate gets a way to look at its terminal.
        if (!/^(I stopped|I hit an error|I can't read this yet)/i.test(String(msg.text || '').trim())) return;
        const col = el.querySelector('.chat-bubble');
        if (!col || col.querySelector('.sc-stuck-btn')) return;
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'sc-btn primary sc-stuck-btn';
        b.textContent = 'Open terminal';
        b.onclick = (e) => { e.stopPropagation(); window.scOpenAgent && window.scOpenAgent(String(msg.sender).replace(/-\d+$/, ''), 'terminal'); };
        col.appendChild(b);
    }
    // Touch screens have no hover: tap a message to show its toolbar.
    if (window.matchMedia('(hover: none)').matches) {
        document.addEventListener('click', (e) => {
            if (e.target.closest('.sc-tools, .sc-reaction, .sc-thread-summary, a, button')) return;
            const msg = e.target.closest('.message.sc-msg');
            document.querySelectorAll('.message.sc-tap').forEach((m) => { if (m !== msg) m.classList.remove('sc-tap'); });
            if (msg) msg.classList.toggle('sc-tap');
        });
    }

    // ------------------------------------------------------------------
    // Thread panel
    // ------------------------------------------------------------------
    function openThread(rootId) {
        if (rootId == null || !byId.has(rootId)) return;
        const i = openThreads.indexOf(rootId);
        if (i >= 0) openThreads.splice(i, 1);
        openThreads.push(rootId);
        while (openThreads.length > 4) openThreads.shift();
        activeThread = rootId;
        document.body.classList.add('sc-thread-open');
        renderThread();
        seenReplyCount.set(rootId, (replies.get(rootId) || []).length);
        paintSummary(rootId);
        setTimeout(() => document.getElementById('sc-thread-input')?.focus(), 30);
    }
    window.scOpenThread = openThread;

    function closeThread(rootId) {
        const i = openThreads.indexOf(rootId);
        if (i >= 0) openThreads.splice(i, 1);
        if (activeThread === rootId) activeThread = openThreads.length ? openThreads[openThreads.length - 1] : null;
        if (activeThread == null) document.body.classList.remove('sc-thread-open');
        renderThread();
    }

    function tmsgHtml(m) {
        const mine = String(m.sender).toLowerCase() === me().toLowerCase();
        return `<div class="sc-tmsg${mine ? ' self' : ''}" data-mid="${esc(m.id)}">`
            + `<span class="sc-tmsg-av">${avatarOf(m.sender)}</span>`
            + `<div class="sc-tmsg-body"><div class="sc-tmsg-head"><b>${esc(labelOf(m.sender))}</b><span>${esc(m.time || '')}</span></div>`
            + `<div class="sc-tmsg-text">${textHtml(m)}</div>`
            + (m.reactions && Object.keys(m.reactions).length ? `<div class="sc-reactions" data-mid="${esc(m.id)}">${reactionsHtml(m)}</div>` : '')
            + '</div></div>';
    }

    function renderThread() {
        const panel = document.getElementById('sc-thread');
        if (!panel) return;
        const tabs = panel.querySelector('.sc-thread-tabs');
        const body = panel.querySelector('.sc-thread-body');
        if (activeThread == null) { tabs.innerHTML = ''; body.innerHTML = ''; return; }
        tabs.innerHTML = openThreads.map((rid) => {
            const r = byId.get(rid) || {};
            const mine = String(r.sender || '').toLowerCase() === me().toLowerCase();
            const snippet = String(r.text || '').replace(/@[\w-]+/g, '').replace(/\s+/g, ' ').trim();
            const label = mine ? (snippet.slice(0, 18) || 'Your thread') : `@${labelOf(r.sender || '?')}`;
            return `<button type="button" class="sc-ttab${rid === activeThread ? ' active' : ''}" data-root="${rid}" title="${esc(String(r.text || '').slice(0, 120))}">`
                + `<span class="sc-ttab-label">${esc(label)}</span><span class="sc-ttab-x" data-close="${rid}" title="Close">✕</span></button>`;
        }).join('');
        const root = byId.get(activeThread);
        const list = replies.get(activeThread) || [];
        const where = root && root.channel && root.channel.startsWith('dm-') ? `Direct message with ${labelOf(root.channel.slice(3))}` : `#${(root && root.channel) || 'general'}`;
        body.innerHTML = (root ? `<div class="sc-thread-where">${esc(where)}</div>${tmsgHtml(root)}` : '')
            + `<div class="sc-thread-divider"><span>${list.length} ${list.length === 1 ? 'reply' : 'replies'}</span></div>`
            + list.map(tmsgHtml).join('');
        polishText(body, '.sc-tmsg-text .mention');
        body.querySelectorAll('.sc-tmsg-head > span').forEach(shortTime);
        body.scrollTop = body.scrollHeight;
        const input = document.getElementById('sc-thread-input');
        if (input) input.placeholder = `Reply in thread${root ? ' · @' + labelOf(root.sender) : ''}`;
    }

    function sendThreadReply() {
        const input = document.getElementById('sc-thread-input');
        const root = byId.get(activeThread);
        if (!input || !root) return;
        let text = window.scNormalizeMentions ? window.scNormalizeMentions(input.value.trim()) : input.value.trim();
        if (!text) return;
        // A reply without an @ goes to the teammate you're talking with in this thread:
        // the last teammate who replied, else the starter, else whoever the root @'d.
        if (!/(^|\s)@[\w-]+/.test(text)) {
            const team = (window.scGetTeam && window.scGetTeam()) || {};
            const isAgent = (n) => !!n && (!!team[n] || (typeof agentConfig !== 'undefined' && !!agentConfig[n]));
            const list = replies.get(Number(root.id)) || [];
            let target = [...list].reverse().map((m) => String(m.sender).toLowerCase()).find(isAgent);
            if (!target && isAgent(String(root.sender).toLowerCase())) target = String(root.sender).toLowerCase();
            if (!target) {
                const at = /(^|\s)@([\w-]+)/.exec(String(root.text || ''));
                if (at && isAgent(at[2].toLowerCase())) target = at[2].toLowerCase();
            }
            if (target) text = `@${target} ${text}`;
        }
        if (window.ws && window.ws.readyState === WebSocket.OPEN) {
            window.ws.send(JSON.stringify({ type: 'message', text, sender: me(), channel: root.channel || 'general', reply_to: Number(root.id), attachments: [] }));
            input.value = '';
            input.style.height = '';
        }
    }

    function initThreadPanel() {
        const panel = document.getElementById('sc-thread');
        if (!panel) return;
        panel.querySelector('.sc-thread-tabs').addEventListener('click', (e) => {
            const x = e.target.closest('[data-close]');
            if (x) { e.stopPropagation(); closeThread(Number(x.dataset.close)); return; }
            const t = e.target.closest('[data-root]');
            if (t) { activeThread = Number(t.dataset.root); renderThread(); }
        });
        panel.querySelector('.sc-thread-close').addEventListener('click', () => {
            openThreads.splice(0); activeThread = null;
            document.body.classList.remove('sc-thread-open'); renderThread();
        });
        const input = document.getElementById('sc-thread-input');
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendThreadReply(); }
        });
        input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; });
        document.getElementById('sc-thread-send').addEventListener('click', sendThreadReply);
    }

    // Links like /#msg-42 open the message (and its thread)
    function openFromHash() {
        const m = /^#msg-(\d+)$/.exec(location.hash || '');
        if (!m) return;
        const id = Number(m[1]);
        const msg = byId.get(id);
        if (!msg) return;
        const root = rootOf(msg);
        const ch = msg.channel || 'general';
        if (ch !== window.activeChannel && typeof switchChannel === 'function' && (window.channelList || []).includes(ch)) switchChannel(ch);
        setTimeout(() => {
            if (root != null && root !== id) openThread(root);
            else if (typeof scrollToMessage === 'function') scrollToMessage(id);
        }, 80);
    }
    window.addEventListener('hashchange', openFromHash);

    function init() {
        initThreadPanel();
        let tries = 0;
        const wait = setInterval(() => {   // after history has loaded
            if (byId.size || ++tries > 40) { clearInterval(wait); openFromHash(); }
        }, 250);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();

// Scranton: "@项目经理" typed by hand becomes "@pm" when sent, so it reaches them.
// Shared by the main composer and thread replies.
window.scNormalizeMentions = function (text) {
    const team = (window.scGetTeam && window.scGetTeam()) || {};
    if (!String(text).includes('@')) return text;
    const pairs = Object.entries(team).map(([h, t]) => [String(t.label || ''), h]).filter(([l]) => l)
        .sort((a, b) => b[0].length - a[0].length);
    let v = String(text);
    for (const [l, h] of pairs) v = v.split('@' + l).join('@' + h);
    return v;
};
(function () {
    if (typeof sendMessage !== 'function') return;
    const orig = sendMessage;
    sendMessage = function () {
        const input = document.getElementById('input');
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const q = window.scTakeQuote && input && input.value.trim() ? window.scTakeQuote() : null;
        if (q) {
            // the person you're answering gets it, even in a channel
            const dm = String(window.activeChannel || '').startsWith('dm-');
            const tag = !dm && team[q.handle] && !new RegExp('@(' + q.handle + '|' + String(team[q.handle].label || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')(?![\\w-])').test(input.value) ? `@${q.handle} ` : '';
            input.value = `> ${q.who}: ${q.snippet}\n${tag}${input.value}`;
        }
        if (input && input.value.includes('@')) {
            const v = window.scNormalizeMentions(input.value);
            input.value = v;
            // remember who you @, so the quick @ buttons and the @ list put them first
            try {
                const all = JSON.parse(localStorage.getItem('scranton-at-count') || '{}');
                const ch = all[window.activeChannel] = all[window.activeChannel] || {};
                const tot = all._all = all._all || {};
                for (const h of Object.keys(team)) {
                    if (new RegExp('@' + h.replace(/[-]/g, '\\-') + '(?![\\w-])').test(v)) { ch[h] = (ch[h] || 0) + 1; tot[h] = (tot[h] || 0) + 1; }
                }
                localStorage.setItem('scranton-at-count', JSON.stringify(all));
            } catch (_) { /* storage blocked */ }
        }
        const sent = input ? input.value : '';
        const r = orig.apply(this, arguments);
        try { suggestTracking(sent); } catch (_) { /* never block sending */ }
        return r;
    };

    // Several tasks in one message → offer to have the PM track them in Notion.
    function countTasks(text) {
        const lines = String(text).split('\n').map((l) => l.trim()).filter(Boolean);
        const items = lines.filter((l) => /^([-*•·]|\d+[.)、]|[一二三四五六七八九十]+[、.])\s*\S/.test(l));
        return items.length;
    }
    function suggestTracking(text) {
        const n = countTasks(text);
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        if (n < 3 || !team.pm || String(window.activeChannel || '').startsWith('dm-pm')) return;
        document.getElementById('sc-track')?.remove();
        const bar = document.createElement('div');
        bar.id = 'sc-track';
        bar.innerHTML = `<span>${n} tasks in that message</span>`
            + `<button type="button" data-a="track">Track them in Notion</button><button type="button" class="x" data-a="no" aria-label="No thanks">${window.scIcon ? window.scIcon('close', 16) : '✕'}</button>`;
        const row = document.getElementById('input-row');
        row?.parentElement?.insertBefore(bar, row);
        const t = setTimeout(() => bar.remove(), 20000);
        bar.onclick = (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (!a) return;
            clearTimeout(t); bar.remove();
            if (a === 'track' && window.ws && window.ws.readyState === WebSocket.OPEN) {
                const who = (window.scMe && window.scMe()) || 'Lu';
                window.ws.send(JSON.stringify({ type: 'message', sender: who, channel: window.activeChannel || 'general', attachments: [],
                    text: `@pm 把我上一条里的 ${n} 件事加进 Notion「Scranton tasks」跟踪（任务｜负责人｜状态｜消息链接），发我链接，之后状态有变就更新。` }));
            }
        };
    }
})();
