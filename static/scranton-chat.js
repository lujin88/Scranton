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
            // Built fresh (not copied from the sidebar, which can still show the default "U")
            if (window.scMyAvatarHtml) return window.scMyAvatarHtml();
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
        if (el && String(msg.sender) === 'system') { try { paintPause(el, msg); } catch (_) {} }
        const kind = msg.type || 'chat';
        // Everything someone said can be reacted to, replied to in a thread, copied: chats and every
        // card (decision, job, rule, summary). Only status lines (joined, left, session phases) can't.
        const statusLine = kind === 'join' || kind === 'leave' || kind === 'system' || kind.startsWith('session_');
        if (el && !statusLine && String(msg.sender) !== 'system') {
            el.classList.add('sc-msg');
            addToolbar(el, id);
            try { relabel(el, msg); paintQuote(el, msg); paintStuck(el, msg); if (kind === 'chat' || kind === 'decision') paintChoices(el, msg); } catch (_) { /* never break rendering */ }
        }
        if (msg.reactions && Object.keys(msg.reactions).length) paintReactions(msg, container);
        if (msg.reply_to != null) {
            // an answer to an option card: show it as picked
            try { const c = findEl(Number(msg.reply_to), container)?.querySelector('.sc-choices'); if (c && c._paint) c._paint(); } catch (_) {}
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
            // Your name changed and your past messages moved with it: redraw them as yours.
            if (event && event.type === 'scranton_reload') { setTimeout(() => location.reload(), 300); return; }
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

    // In a thread the same bar, minus "Reply in thread" (you're already in it); quoting goes
    // into the thread's reply box.
    function addToolbar(el, id, inThread) {
        if (el.querySelector('.sc-tools')) return;
        el.tabIndex = 0;   // keyboard users reach a message with Tab; its actions show while it's focused
        const bar = document.createElement('div');
        bar.className = 'sc-tools';
        bar.innerHTML = `<button type="button" data-act="react" title="Add reaction (E)">${ICONS.react}</button>`
            + (inThread ? `<button type="button" data-act="tquote" title="Quote in your reply">${ICONS.reply}</button>`
                : `<button type="button" data-act="thread" title="Reply in thread (T)">${ICONS.reply}</button>`)
            + `<button type="button" data-act="more" title="More">${ICONS.more}</button>`;
        if (inThread) bar.dataset.thread = '1';
        bar.querySelectorAll('button').forEach((b) => b.setAttribute('aria-label', b.title.replace(/ \(.\)$/, '')));
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


    async function copyText(t, label) {
        try { await navigator.clipboard.writeText(t); toast(`${label} copied`); }
        catch (_) { toast('Copy failed'); }
    }

    window.scToast = (text, action) => toast(text, action);

    // Unsent text is kept per conversation: switching away or reloading doesn't lose it.
    window.scDraft = (() => {
        const KEY = 'scranton-drafts';
        const all = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (_) { return {}; } };
        const put = (o) => { try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (_) { /* storage blocked */ } };
        const box = () => document.getElementById('input');
        return {
            save(ch) { const i = box(); if (!i || !ch) return; const o = all(); if (i.value.trim()) o[ch] = i.value; else delete o[ch]; put(o); },
            load(ch) { const i = box(); if (!i) return; i.value = all()[ch] || ''; i.dispatchEvent(new Event('input', { bubbles: true })); },
            clear(ch) { const o = all(); delete o[ch]; put(o); },
        };
    })();
    {
        let t = null;
        document.addEventListener('input', (e) => {
            if (!e.target || e.target.id !== 'input') return;
            clearTimeout(t); t = setTimeout(() => window.scDraft.save(window.activeChannel), 400);
            // the quick @ chips light up for whoever is @'d in the box
            const v = e.target.value;
            document.querySelectorAll('#mention-toggles .mention-toggle').forEach((b) => {
                const words = [b.dataset.agent, b.textContent.replace(/^@/, '')].map((x) => String(x).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
                b.classList.toggle('active', new RegExp('(^|\\s)@(' + words.join('|') + ')(?![\\w-])').test(v));
            });
        });
        setTimeout(() => { const i = document.getElementById('input'); if (i && !i.value) window.scDraft.load(window.activeChannel); }, 1500);
    }
    // toast(text) or toast(text, { label: 'Undo', run }) - with an action it stays 5 s and is clickable.
    function toast(text, action) {
        document.querySelectorAll('.sc-toast.sc-toast-act').forEach((x) => x.remove());
        const t = document.createElement('div');
        t.className = 'sc-toast' + (action ? ' sc-toast-act' : '');
        t.setAttribute('role', 'status');
        const span = document.createElement('span');
        span.textContent = text;
        t.appendChild(span);
        if (action) {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = action.label || 'Undo';
            b.addEventListener('click', () => { t.remove(); action.run(); });
            t.appendChild(b);
        }
        document.body.appendChild(t);
        setTimeout(() => t.remove(), action ? 5000 : 1600);
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

    function openMore(anchor, id, inThread) {
        const m = byId.get(id);
        if (!m) return;
        const items = [
            ['copy', 'Copy text'],
            ...(inThread ? [] : [['quote', 'Quote in channel']]),   // also R
            ['forward', 'Forward to another channel'],
            ...(inThread ? [] : [['unread', 'Mark as unread']]),   // unread is per conversation, not per reply
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
            if (k === 'quote') quoteReply(id);
            if (k === 'forward') openForward(anchor, id);
            if (k === 'unread') {
                const ch = m.channel || 'general';
                if (window.channelUnread) window.channelUnread[ch] = (window.channelUnread[ch] || 0) + 1;
                if (window.scMarkUnread) window.scMarkUnread(m);
                if (typeof renderChannelSidebar === 'function') renderChannelSidebar();
                toast('Marked unread');
            }
            if (k === 'delete') {
                if (confirm((() => { const n = [...byId.values()].filter((x) => x && x.reply_to != null && Number(x.reply_to) === Number(id)).length; return n ? `Delete this message and its ${n} repl${n === 1 ? 'y' : 'ies'}? This can't be undone.` : 'Delete this message? This can\'t be undone.'; })()) && window.ws && window.ws.readyState === WebSocket.OPEN) {
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
            if (act === 'forward') openForward(tool, id);
            if (act === 'more') openMore(tool, id, !!tool.closest('.sc-tools').dataset.thread);
            if (act === 'tquote') threadQuote(id);
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
    // Quote inside a thread: the same bar above the thread's reply box as in the main box;
    // the quote goes out as the same "> who: text" first line.
    let tquoting = null;
    function threadQuote(id) {
        const m = byId.get(id);
        if (!m) return;
        const who = window.scLabelOf ? window.scLabelOf(String(m.sender)) : String(m.sender);
        const snippet = String(m.text || '').replace(/^> .*\n/, '').replace(/\s+/g, ' ').trim().slice(0, 140).replace(/@/g, '@\u200b');
        tquoting = { id, who, snippet };
        let bar = document.getElementById('sc-tquote');
        const compose = document.querySelector('#sc-thread .sc-thread-compose');
        if (!bar && compose) {
            bar = document.createElement('div');
            bar.id = 'sc-tquote';
            compose.parentElement.insertBefore(bar, compose);
        }
        if (bar) {
            bar.innerHTML = `<span class="sc-quote-ic">${ri('reply')}</span><span class="sc-quote-t"><b>${esc(who)}</b> ${esc(snippet)}</span>`
                + `<button type="button" class="sc-quote-x" aria-label="Cancel quote">${ri('close')}</button>`;
            bar.querySelector('.sc-quote-x').onclick = clearThreadQuote;
        }
        document.getElementById('sc-thread-input')?.focus();
    }
    function clearThreadQuote() { tquoting = null; document.getElementById('sc-tquote')?.remove(); }
    function clearQuote() { quoting = null; document.getElementById('sc-quote')?.remove(); }
    window.scQuoteReply = quoteReply;
    window.scClearQuote = clearQuote;
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
        // The focused message (keyboard) first, else the one under the pointer.
        const focused = a && a.closest && a.closest('.message.sc-msg');
        const target = focused || (hovered && hovered.matches(':hover') ? hovered : null);
        if (!target) return;
        hovered = target;
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
        const body = el && el.querySelector('.msg-text, .sc-tmsg-text');
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
    // Options typed by an agent ("A. 就这 6 人" / "B) …" on their own lines) become a card you
    // click, like Grok's. Each question in a message gets its own card. A click answers in the
    // thread: "@pm 1A：就这 6 人，建一个群".
    const OPT_RE = /^\s*(?:[-*•]\s*)?([A-H])\s*[.)、:：]\s*(.+?)\s*$/;
    const chosenStore = {
        all() { try { return JSON.parse(localStorage.getItem('scranton-chosen') || '{}'); } catch (_) { return {}; } },
        get(id, q) { return (this.all()[id] || {})[q]; },
        set(id, q, v) { const a = this.all(); (a[id] = a[id] || {})[q] = v; try { localStorage.setItem('scranton-chosen', JSON.stringify(a)); } catch (_) {} },
    };
    function parseChoices(text) {
        const lines = String(text || '').split('\n');
        const blocks = [];
        let cur = null;
        lines.forEach((line, i) => {
            const m = OPT_RE.exec(line);
            const expect = cur ? String.fromCharCode(65 + cur.options.length) : 'A';
            if (m && m[1] === expect) {
                if (!cur) {
                    // the question: the nearest non-empty line above, without list markers
                    let q = '';
                    for (let j = i - 1; j >= 0 && !q; j--) q = lines[j].trim();
                    const num = /^(\d+)[.)、]/.exec(q);
                    cur = { question: q.replace(/^\d+[.)、]\s*/, '').replace(/[*_`]/g, ''), num: num ? num[1] : '', options: [] };
                }
                cur.options.push({ key: m[1], text: m[2].replace(/[*_`]/g, '') });
            } else if (cur && line.trim()) {
                if (cur.options.length >= 2) blocks.push(cur);
                cur = null;
                const m2 = OPT_RE.exec(line);
                if (m2 && m2[1] === 'A') {   // a new question's A right after the last option
                    let q = lines[i - 1] ? lines[i - 1].trim() : '';
                    cur = { question: q, num: '', options: [{ key: 'A', text: m2[2] }] };
                }
            }
        });
        if (cur && cur.options.length >= 2) blocks.push(cur);
        return blocks;
    }
    // The option cards need the team list; if it arrives after the messages, paint them then.
    (window.scOnTeamChange = window.scOnTeamChange || []).push(() => {
        document.querySelectorAll('#messages .message.sc-msg').forEach((el) => {
            if (el.querySelector('.sc-choices')) return;
            const m = byId.get(Number(el.dataset.id));
            if (m) { try { paintChoices(el, m); } catch (_) { /* never break rendering */ } }
        });
    });
    // What you're typing in a card's "Something else" row survives the card being redrawn
    // (a thread is redrawn on every new reply; before, the text and focus vanished mid-typing).
    const otherDraft = new Map();   // "msgId:q" -> text
    let otherFocus = null;          // "msgId:q" of the row you're typing in
    function paintChoices(el, msg) {
        const sender = String(msg.sender || '').split('-')[0];
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        if (!team[sender] || el.querySelector('.sc-choices')) return;
        // One kind of option card everywhere (Grok Bot): options written as "A. …" lines in the text,
        // or a decision message's choices (chat_send(choices=[…])). Same card in the channel and in threads.
        const meta = msg.metadata || {};
        const isDecision = msg.type === 'decision' && Array.isArray(meta.choices) && meta.choices.length;
        const blocks = isDecision
            ? [{ question: '', num: '', options: meta.choices.map((c, i) => ({ key: String.fromCharCode(65 + i), raw: String(c),
                // agents sometimes write "A. …" inside the choice itself; the row already shows the letter
                text: String(c).replace(/^\s*[A-H]\s*[.)、:：]\s*/, '') })) }]
            : parseChoices(msg.text);
        if (!blocks.length) return;
        const col = el.querySelector('.chat-bubble, .sc-tmsg-body');
        if (!col) return;
        const textEl = col.querySelector('.msg-text, .sc-tmsg-text');
        const wrap = document.createElement('div');
        wrap.className = 'sc-choices';
        // What you already answered, from your replies in its thread (so the phone shows it too)
        const typedOwn = {};   // question -> what you typed in "Something else"
        const fromReplies = (qi) => {
            if (isDecision && meta.resolved) {
                if (meta.other) { typedOwn[qi] = String(meta.chosen || ''); return String.fromCharCode(65 + blocks[0].options.length); }
                const i = meta.choices.indexOf(meta.chosen);
                return i >= 0 ? String.fromCharCode(65 + i) : null;
            }
            const mine = String(me()).toLowerCase();
            const root = rootOf(msg);
            const otherKey = String.fromCharCode(65 + blocks[qi].options.length);
            for (const r of byId.values()) {
                if (!r || String(r.sender || '').toLowerCase() !== mine) continue;
                const direct = Number(r.reply_to) === Number(msg.id);
                // a card inside a thread is answered in that same thread, after the card
                const sameThread = root != null && Number(r.reply_to) === Number(root) && Number(r.id) > Number(msg.id);
                if (!direct && !sameThread) continue;
                const m = /^@\S+\s+(\d*)([A-H])：(.*)$/s.exec(String(r.text || ''));
                if (!m || (blocks.length > 1 && Number(m[1]) !== Number(blocks[qi].num || qi + 1))) continue;
                const opt = blocks[qi].options.find((o) => o.key === m[2]);
                // in a shared thread, make sure it answers this card: same option text, or the typed row
                if (!direct && !(opt ? opt.text.trim() === m[3].trim() : m[2] === otherKey)) continue;
                typedOwn[qi] = m[3];
                return m[2];
            }
            return null;
        };
        // A decision is answered through the server, which records it on the card (sessions wait on that)
        // and posts "@agent B：text" in its thread.
        const answerDecision = (choice, other) => fetch(`/api/messages/${msg.id}/resolve_decision`, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN },
            body: JSON.stringify(other ? { choice, other: true } : { choice }),
        }).then((r) => { if (!r.ok) { chosenStore.set(msg.id, 0, null); paint(); toast('Couldn\'t send your answer'); } })
          .catch(() => { chosenStore.set(msg.id, 0, null); paint(); toast('Couldn\'t send your answer'); });
        const paint = () => {
            wrap.innerHTML = blocks.map((b, qi) => {
                const fromServer = fromReplies(qi);   // also fills in what you typed, after a reload or repaint
                const picked = (isDecision && meta.resolved) ? fromServer : (chosenStore.get(msg.id, qi) || fromServer);
                if (picked) {
                    const o = b.options.find((x) => x.key === picked);
                    const txt = o ? o.text : (typedOwn[qi] || '');
                    return `<div class="sc-choice-card done" data-q="${qi}">
                        ${b.question ? `<div class="sc-choice-q">${b.num ? esc(b.num) + '. ' : ''}${esc(b.question)}</div>` : ''}
                        <div class="sc-choice on" aria-label="Your answer"><span class="sc-choice-key">${esc(picked)}</span><span>${o && window.scOptionHtml ? window.scOptionHtml(txt) : esc(txt)}</span></div>
                    </div>`;
                }
                return `<div class="sc-choice-card" data-q="${qi}">
                    ${b.question ? `<div class="sc-choice-q">${b.num ? esc(b.num) + '. ' : ''}${esc(b.question)}</div>` : ''}
                    ${b.options.map((o) => `<button type="button" class="sc-choice${picked === o.key ? ' on' : ''}" data-k="${esc(o.key)}"${picked ? ' disabled' : ''}>
                        <span class="sc-choice-key">${esc(o.key)}</span><span>${window.scOptionHtml ? window.scOptionHtml(o.text) : esc(o.text)}</span></button>`).join('')}
                    ${(() => {
                        // the last row: your own answer, typed right here (Grok Bot's "Something else")
                        const k = String.fromCharCode(65 + b.options.length);
                        const mine = picked === k;
                        const draft = otherDraft.get(`${msg.id}:${qi}`) || '';
                        return `<label class="sc-choice sc-choice-other${mine ? ' on' : ''}${!picked && draft ? ' has-text' : ''}"><span class="sc-choice-key">${k}</span>
                            <input type="text" data-other="${k}" placeholder="Something else" aria-label="Your own answer" maxlength="500"
                                value="${mine ? esc(typedOwn[qi] || '') : esc(draft)}"${picked ? ' disabled' : ''}>`
                            + (picked ? '' : `<button type="button" class="sc-choice-send" data-send aria-label="Send your answer" data-tip="Send (Enter)">${window.scIcon ? window.scIcon('send', 16) : '→'}</button>`)
                            + '</label>';
                    })()}
                </div>`;
            }).join('');
            // put the cursor back if you were typing here when it was redrawn
            if (otherFocus && otherFocus.startsWith(`${msg.id}:`)) {
                const qi = otherFocus.split(':')[1];
                const inp = wrap.querySelector(`[data-q="${qi}"] [data-other]`);
                if (inp && !inp.disabled) requestAnimationFrame(() => { if (inp.isConnected) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); } });
            }
        };
        paint();
        wrap._paint = paint;
        wrap.addEventListener('input', (e) => {
            const inp = e.target.closest?.('[data-other]');
            if (!inp) return;
            const key = `${msg.id}:${inp.closest('[data-q]').dataset.q}`;
            if (inp.value) otherDraft.set(key, inp.value); else otherDraft.delete(key);
            inp.closest('.sc-choice-other')?.classList.toggle('has-text', !!inp.value.trim());
        });
        wrap.addEventListener('focusin', (e) => { const inp = e.target.closest?.('[data-other]'); if (inp) otherFocus = `${msg.id}:${inp.closest('[data-q]').dataset.q}`; });
        wrap.addEventListener('focusout', (e) => {
            const inp = e.target.closest?.('[data-other]');
            // a redraw also blurs; only forget when focus really went elsewhere
            if (inp) setTimeout(() => { if (!document.activeElement?.closest?.('.sc-choice-other')) otherFocus = null; }, 0);
        });
        wrap.addEventListener('click', (e) => {
            const btn = e.target.closest?.('[data-send]');
            if (!btn) return;
            e.preventDefault(); e.stopPropagation();
            submitOther(btn.closest('.sc-choice-other').querySelector('[data-other]'));
        }, true);
        wrap.addEventListener('keydown', (e) => {
            const inp = e.target.closest?.('[data-other]');
            if (!inp || e.key !== 'Enter' || e.isComposing || e.keyCode === 229 || e.shiftKey) return;
            e.preventDefault(); e.stopPropagation();
            submitOther(inp);
        });
        function submitOther(inp) {
            if (!inp) return;
            const v = inp.value.trim();
            if (!v) { inp.focus(); return; }
            if (!isDecision && (!window.ws || window.ws.readyState !== WebSocket.OPEN)) { toast('Not connected. Your answer has not been sent.'); return; }
            const qi = Number(inp.closest('[data-q]').dataset.q);
            const block = blocks[qi], k = inp.dataset.other;
            const tag = blocks.length > 1 || block.num ? `${block.num || qi + 1}${k}` : k;
            if (isDecision) answerDecision(v, true);
            else {
                const root = rootOf(msg) ?? Number(msg.id);
                window.ws.send(JSON.stringify({ type: 'message', text: `@${sender} ${tag}：${v}`, sender: me(),
                    channel: msg.channel || 'general', reply_to: Number(root), attachments: [] }));
            }
            typedOwn[qi] = v;
            otherDraft.delete(`${msg.id}:${qi}`);
            otherFocus = null;
            chosenStore.set(msg.id, qi, k);
            paint();
            toast(`Answered ${tag}`);
        }
        wrap.addEventListener('click', (e) => {
            const own = e.target.closest('[data-own]');
            if (own) {
                e.stopPropagation();
                const qi = Number(own.closest('[data-q]').dataset.q);
                const block = blocks[qi];
                const tag = blocks.length > 1 || block.num ? `${block.num || qi + 1}` : '';
                window.scAnswerOwn(msg, tag);
                return;
            }
            if (e.target.closest('.sc-choice-other')) { e.stopPropagation(); return; }   // typing, not picking
            const b = e.target.closest('.sc-choice');
            if (!b || b.disabled) return;
            e.stopPropagation();
            const qi = Number(b.closest('[data-q]').dataset.q);
            const block = blocks[qi];
            const opt = block.options.find((o) => o.key === b.dataset.k);
            if (!opt || !window.ws || window.ws.readyState !== WebSocket.OPEN) return;
            const tag = blocks.length > 1 || block.num ? `${block.num || qi + 1}${opt.key}` : opt.key;
            if (isDecision) answerDecision(opt.raw || opt.text, false);
            else {
                const root = rootOf(msg) ?? Number(msg.id);
                window.ws.send(JSON.stringify({ type: 'message', text: `@${sender} ${tag}：${opt.text}`, sender: me(),
                    channel: msg.channel || 'general', reply_to: Number(root), attachments: [] }));
            }
            chosenStore.set(msg.id, qi, opt.key);
            paint();
            toast(`Answered ${tag}`);
        });
        // The questions and options are in the cards now: hide those lines in the text so
        // nothing shows twice. Anything else in the message stays.
        const norm = (t) => String(t || '').replace(/[*_`]/g, '').replace(/^\s*(?:\d+|[A-H])\s*[.)、:：]\s*/, '').replace(/\s+/g, ' ').trim();
        const known = new Set();
        // A decision's text often repeats its options as "A. …" lines, worded a bit differently: drop those too.
        const optLetter = (raw) => {
            const m = /^\s*([A-H])\s*[.)、:：]/.exec(String(raw || ''));
            return !!(m && isDecision && m[1].charCodeAt(0) - 65 < blocks[0].options.length);
        };
        blocks.forEach((b) => { if (b.question) known.add(norm(b.question)); b.options.forEach((o) => known.add(norm(o.text))); });
        const ownText = (n) => {
            const c = n.cloneNode(true);
            c.querySelectorAll('ul, ol').forEach((x) => x.remove());
            c.querySelectorAll('br').forEach((x) => x.replaceWith('\n'));   // a detached copy has no layout, so no innerText lines
            return c.textContent;
        };
        // Plain text with line breaks (no paragraphs): hide the whole text when it's only the question and options.
        const mt = textEl;
        if (mt && !mt.querySelector('p, li')) {
            const lines = ownText(mt).split('\n').map(norm).filter(Boolean);
            const raws = ownText(mt).split('\n').filter((l) => l.trim());
            if (lines.length && lines.every((l) => known.has(l))) mt.classList.add('sc-opt-line');
            else if (lines.some((l) => known.has(l)) || raws.some(optLetter)) {
                // Question plus option lines in one block: keep the question, drop the option lines.
                const parts = mt.innerHTML.split(/<br\s*\/?>|\n/);
                const tmp = document.createElement('div');
                const keep = parts.filter((h) => { tmp.innerHTML = h; const t = norm(tmp.textContent); return !t || !(known.has(t) || optLetter(tmp.textContent)); });
                if (keep.length < parts.length) mt.innerHTML = keep.join('<br>').replace(/(<br>)+$/, '');
            }
        }
        el.querySelectorAll('.msg-text li, .msg-text p, .sc-tmsg-text li, .sc-tmsg-text p').forEach((n) => {
            const lines = ownText(n).split('\n').map(norm).filter(Boolean);
            if (lines.length && lines.every((l) => known.has(l))) n.classList.add('sc-opt-line');
        });
        if (textEl) textEl.after(wrap); else col.appendChild(wrap);
    }
    window.scPaintChoices = paintChoices;
    // A card changed on the server (a decision answered elsewhere): draw it again.
    window.scRepaintChoices = (m) => {
        if (!m || m.id == null) return;
        byId.set(Number(m.id), m);
        if (window.scInboxUpdate) window.scInboxUpdate(m);
        const el = findEl(Number(m.id));
        if (el) { el.querySelector('.sc-choices')?.remove(); try { paintChoices(el, m); } catch (_) { /* never break */ } }
        if (activeThread != null) renderThread();
    };

    // Loop guard. In the conversation the notice is a one-line note; the decision is a card
    // docked above the message box (Higgsfield / Cofounder pattern), shown only while the
    // server says this channel is paused. Any message from you also lets them go on.
    const PAUSE_RE = /passed this back and forth (\d+) times, so I paused them/i;
    let pausedChannels = new Set();
    const keptPaused = new Set();   // channels where you chose "Keep paused" for this pause
    const pauseHops = new Map();    // channel -> hand-offs, from the latest notice
    function paintPause(el, msg) {
        const m = PAUSE_RE.exec(String(msg.text || ''));
        if (!m || el.classList.contains('sc-pause-note')) return;
        pauseHops.set(msg.channel || 'general', Number(m[1]));
        el.classList.add('sc-pause-note');
        el.innerHTML = `<span class="msg-text">${window.scIcon ? window.scIcon('hourglass', 14) : ''} Agents paused after ${Number(m[1])} hand-offs without you</span>`;
    }
    window.scSetPaused = (list) => {
        if (!Array.isArray(list)) return;
        const now = new Set(list);
        for (const ch of keptPaused) if (!now.has(ch)) keptPaused.delete(ch);   // that pause is over
        pausedChannels = now;
        renderPauseDock();
    };
    function renderPauseDock() {
        const ch = window.activeChannel || 'general';
        const show = pausedChannels.has(ch) && !keptPaused.has(ch);
        let dock = document.getElementById('sc-pause-dock');
        updateComposerHint(show);
        if (!show) { dock?.remove(); return; }
        if (!dock) {
            dock = document.createElement('div');
            dock.id = 'sc-pause-dock';
            dock.setAttribute('role', 'status');
            const row = document.getElementById('input-row');
            row?.parentElement?.insertBefore(dock, row);
            dock.addEventListener('click', (e) => {
                const a = e.target.closest('[data-pa]')?.dataset.pa;
                const c = window.activeChannel || 'general';
                if (a === 'go' && window.ws && window.ws.readyState === WebSocket.OPEN) {
                    window.ws.send(JSON.stringify({ type: 'message', text: '/continue', sender: me(), channel: c, attachments: [] }));
                    e.target.closest('[data-pa]').disabled = true;
                }
                if (a === 'keep') { keptPaused.add(c); renderPauseDock(); }
                if (a === 'see') { const r = lastAgentThread(c); if (r != null) openThread(Number(r)); }
            });
        }
        const n = pauseHops.get(ch);
        const where = lastAgentThread(ch);
        // Say what happened, what each button does, and where to look (approval-card pattern:
        // the outcome is on the button, the decision is recorded in the conversation).
        dock.innerHTML = `<span class="sc-pd-ic">${window.scIcon ? window.scIcon('hourglass', 16) : ''}</span>
            <div class="sc-pd-body">
                <b>The agents paused and are waiting for you</b>
                <small>They handed this back and forth${n ? ` ${n} times` : ''} without you. Continue, and they pick up where they stopped. Or reply in the thread to steer them first.</small>
                <div class="sc-pd-actions">
                    <button type="button" class="sc-btn primary sm" data-pa="go">Let them continue</button>
                    ${where != null ? '<button type="button" class="sc-btn sm" data-pa="see">Open the thread</button>' : ''}
                    <button type="button" class="sc-pd-link" data-pa="keep">Not now</button>
                </div>
            </div>`;
    }
    // The newest thread an agent wrote in, here: where the back-and-forth happened.
    function lastAgentThread(ch) {
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        let best = null;
        for (const m of byId.values()) {
            if (!m || (m.channel || 'general') !== ch || !team[String(m.sender || '').split('-')[0].toLowerCase()]) continue;
            if (!best || Number(m.id) > Number(best.id)) best = m;
        }
        return best ? (rootOf(best) ?? Number(best.id)) : null;
    }
    window.scRenderPauseDock = renderPauseDock;
    // While paused, the empty message box suggests /continue; Tab types it (like ChatGPT).
    function updateComposerHint(paused) {
        const input = document.getElementById('input');
        if (!input) return;
        if (paused === undefined) paused = pausedChannels.has(window.activeChannel || 'general') && !keptPaused.has(window.activeChannel || 'general');
        if (!input.placeholder.startsWith('/continue')) input.dataset.scBasePh = input.placeholder;
        input.dataset.scSuggest = paused ? '/continue' : '';
        input.placeholder = paused ? '/continue   (Tab) let the agents go on' : (input.dataset.scBasePh || input.placeholder);
    }
    window.scUpdateComposerHint = () => renderPauseDock();
    document.addEventListener('keydown', (e) => {
        const input = document.getElementById('input');
        if (e.key !== 'Tab' || e.shiftKey || document.activeElement !== input) return;
        if (input.value || !input.dataset.scSuggest) return;
        e.preventDefault();
        input.value = input.dataset.scSuggest;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }, true);

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
        // The right panel shows one thing: this thread replaces details or another thread.
        openThreads.splice(0, openThreads.length, rootId);
        if (activeThread !== rootId && typeof clearThreadQuote === 'function') clearThreadQuote();
        activeThread = rootId;
        if (infoTab != null && window.scToggleInfo) { infoTab = null; window.scToggleInfo(false); }
        infoActive = false;
        document.body.classList.add('sc-thread-open');
        renderThread();
        seenReplyCount.set(rootId, (replies.get(rootId) || []).length);
        paintSummary(rootId);
        setTimeout(() => document.getElementById('sc-thread-input')?.focus(), 30);
    }
    window.scOpenThread = openThread;
    // Take me to a message (Activity, links): a reply opens its thread with that reply in view
    // and the reply box ready; a channel message scrolls into view. Waits for the channel to load.
    window.scFocusMessage = (m) => {
        const id = Number(m.id), root = m.reply_to != null ? Number(m.reply_to) : null;
        let tries = 0;
        const step = () => {
            const known = byId.get(id) || (root != null && byId.get(root));
            if (!known && tries++ < 40) { setTimeout(step, 100); return; }
            const r = root != null ? (rootOf(byId.get(id) || m) ?? root) : null;
            if (r != null && byId.has(r)) {
                openThread(r);
                setTimeout(() => {
                    const el = document.querySelector(`#sc-thread .sc-tmsg[data-mid="${id}"]`);
                    if (el) { el.scrollIntoView({ block: 'center' }); el.classList.add('sc-flash'); setTimeout(() => el.classList.remove('sc-flash'), 1800); }
                    document.querySelector(`.message[data-id="${r}"]`)?.scrollIntoView({ block: 'center' });
                }, 80);
                return;
            }
            if (typeof scrollToMessage === 'function') scrollToMessage(id);
        };
        step();
    };
    // The agent you're talking to in the open thread: who started it, else the last agent to reply.
    window.scThreadAgent = () => {
        if (activeThread == null) return '';
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const base = (x) => String(x || '').split('-')[0].toLowerCase();
        const root = byId.get(activeThread);
        if (root && team[base(root.sender)]) return base(root.sender);
        const r = [...(replies.get(activeThread) || [])].reverse().find((m) => team[base(m.sender)]);
        return r ? base(r.sender) : '';
    };
    // "None of these" / "Change my answer": open the thread with "@agent 2：" typed, so you
    // write your own answer (or a different one) in your words. Agents read it like a click.
    window.scAnswerOwn = (msgOrId, tag) => {
        const msg = typeof msgOrId === 'object' ? msgOrId : byId.get(Number(msgOrId));
        if (!msg) return;
        const root = rootOf(msg) ?? Number(msg.id);
        openThread(Number(root));
        const sender = String(msg.sender || '').split('-')[0];
        setTimeout(() => {
            const t = document.getElementById('sc-thread-input');
            if (!t) return;
            t.value = window.scShowLabels(`@${sender} `) + (tag ? tag + '：' : '');
            t.dispatchEvent(new Event('input', { bubbles: true }));
            t.focus();
            t.setSelectionRange(t.value.length, t.value.length);
        }, 60);
    };
    // Close whatever the right panel shows (also when you leave the channel for Activity or Report).
    window.scCloseRightPanel = () => {
        openThreads.splice(0); activeThread = null;
        if (infoTab != null && window.scToggleInfo) window.scToggleInfo(false);
        document.body.classList.remove('sc-thread-open'); renderThread();
    };

    function closeThread(rootId) {
        const i = openThreads.indexOf(rootId);
        if (i >= 0) openThreads.splice(i, 1);
        if (activeThread === rootId) activeThread = openThreads.length ? openThreads[openThreads.length - 1] : null;
        if (activeThread == null && infoTab == null) document.body.classList.remove('sc-thread-open');
        renderThread();
    }

    function tmsgHtml(m) {
        const mine = String(m.sender).toLowerCase() === me().toLowerCase();
        return `<div class="sc-tmsg${mine ? ' self' : ''}" data-mid="${esc(m.id)}">`
            + `<span class="sc-tmsg-av">${avatarOf(m.sender)}</span>`
            + `<div class="sc-tmsg-body"><div class="sc-tmsg-head"><b>${esc(labelOf(m.sender))}</b><span>${esc(m.time || '')}</span></div>`
            + (() => {
                // a "> who: text" first line is a quote: show it as a quote block, not as text
                const q = /^> ([^\n]{1,200})\n/.exec(String(m.text || ''));
                if (!q) return `<div class="sc-tmsg-text">${textHtml(m)}</div>`;
                const c = q[1].indexOf(': ');
                const quoted = c > 0 ? `<b>${esc(q[1].slice(0, c))}</b> ${esc(q[1].slice(c + 2))}` : esc(q[1]);
                return `<div class="sc-quoted">${quoted}</div><div class="sc-tmsg-text" data-sc-quote="1">${textHtml({ ...m, text: String(m.text).slice(q[0].length) })}</div>`;
            })()
            + (Array.isArray(m.attachments) && m.attachments.length && typeof attachmentMarkup === 'function'
                ? `<div class="msg-attachments sc-tmsg-att">${m.attachments.map((a) => attachmentMarkup(a)).join('')}</div>` : '')
            + (m.reactions && Object.keys(m.reactions).length ? `<div class="sc-reactions" data-mid="${esc(m.id)}">${reactionsHtml(m)}</div>` : '')
            + '</div></div>';
    }

    // The right panel holds threads and, as its first tab, the channel / person details
    // (opened from the name pill). One panel, never two columns.
    let infoTab = null;      // label of the details tab, or null when it isn't open
    let infoActive = false;
    window.scRightPanel = {
        info(on, label) {
            if (on) { infoTab = label; infoActive = true; openThreads.splice(0); activeThread = null; }
            else { infoTab = null; infoActive = false; }
            document.body.classList.toggle('sc-thread-open', activeThread != null || infoTab != null);
            renderThread();
        },
        showInfo() { if (infoTab != null) { infoActive = true; renderThread(); } },
        isShowingInfo() { return infoTab != null && infoActive; },
    };

    function renderThread() {
        const panel = document.getElementById('sc-thread');
        if (!panel) return;
        const tabs = panel.querySelector('.sc-thread-tabs');
        const body = panel.querySelector('.sc-thread-body');
        if (activeThread == null) infoActive = infoTab != null;
        panel.classList.toggle('sc-info-active', infoActive);
        renderThreadChips();
        renderThreadAtts();
        // A title for what's showing (no tabs): "# channel" for details, "Thread" + where for a thread.
        if (activeThread == null) {
            tabs.innerHTML = infoTab != null ? `<div class="sc-rp-title"><b>${esc(infoTab)}</b></div>` : '';
            body.innerHTML = '';
            return;
        }
        {
            const r = byId.get(activeThread) || {};
            const w = r.channel && r.channel.startsWith('dm-') ? `with ${labelOf(r.channel.slice(3))}` : `#${r.channel || 'general'}`;
            tabs.innerHTML = `<div class="sc-rp-title"><b>Thread</b><span>${esc(w)}</span></div>`;
        }
        const root = byId.get(activeThread);
        const list = replies.get(activeThread) || [];
        const prevTop = body.scrollTop, prevAtBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
        body.innerHTML = (root ? tmsgHtml(root) : '')
            + `<div class="sc-thread-divider"><span>${list.length} ${list.length === 1 ? 'reply' : 'replies'}</span></div>`
            + list.map(tmsgHtml).join('');
        polishText(body, '.sc-tmsg-text .mention');
        body.querySelectorAll('.sc-tmsg-head > span').forEach(shortTime);
        body.querySelectorAll('.sc-tmsg[data-mid]').forEach((el) => {
            addToolbar(el, Number(el.dataset.mid), true);
            try { paintQuote(el, byId.get(Number(el.dataset.mid))); } catch (_) { /* never break the thread */ }
            try { const tm = byId.get(Number(el.dataset.mid)); if (tm) paintChoices(el, tm); } catch (_) { /* never break the thread */ }
        });
        // Opening a thread starts at the newest reply; a new reply while you read doesn't move you
        // (it does if you were already at the bottom, or the reply is yours).
        const tKey = String(activeThread);
        const last = list[list.length - 1] || {};
        const lastSender = String(last.sender || '').toLowerCase();
        const lastIsAnswer = /^@\S+\s+\d*[A-H]：/.test(String(last.text || ''));   // an option you clicked
        const sameThread = body.dataset.thread === tKey;
        const prevCount = sameThread ? Number(body.dataset.count || 0) : list.length;
        // Opening a thread starts at the bottom. After that nothing moves you: if you were at the
        // bottom you stay there; if you were reading higher up (and replied from there), new replies,
        // yours included, add to the ↓ count instead. An option you clicked never moves you.
        if (!sameThread || (prevAtBottom && !lastIsAnswer)) {
            body.scrollTop = body.scrollHeight;
            threadUnread = 0;
        } else {
            body.scrollTop = prevTop;
            threadUnread += Math.max(0, list.length - prevCount);
        }
        body.dataset.thread = tKey;
        body.dataset.count = String(list.length);
        paintThreadDown(panel, body);
        const input = document.getElementById('sc-thread-input');
        if (input) input.placeholder = `Reply in thread${root ? ' · @' + labelOf(root.sender) : ''}`;
    }

    // ↓ button in the thread: same look as the main one, shows how many replies are below you.
    var threadUnread = 0;
    function paintThreadDown(panel, body) {
        let btn = panel.querySelector('.sc-tdown');
        if (!btn) {
            btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'sc-tdown';
            btn.setAttribute('aria-label', 'Jump to latest reply');
            btn.innerHTML = '<span class="sc-tdown-n"></span><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M13 16.17L18.36 10.81L19.78 12.22L12 20L4.22 12.22L5.64 10.81L11 16.17V4H13V16.17Z"/></svg>';
            btn.addEventListener('click', () => { body.scrollTo({ top: body.scrollHeight, behavior: 'smooth' }); });
            panel.appendChild(btn);
        }
        if (!body.dataset.tdownBound) {
            body.dataset.tdownBound = '1';
            body.addEventListener('scroll', () => {
                if (body.scrollHeight - body.scrollTop - body.clientHeight < 40) { threadUnread = 0; }
                paintThreadDown(panel, body);
            }, { passive: true });
        }
        const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 40;
        const show = activeThread != null && !infoActive && !atBottom && threadUnread > 0;
        btn.classList.toggle('sc-on', show);
        btn.querySelector('.sc-tdown-n').textContent = threadUnread > 0 ? String(threadUnread) : '';
        const compose = panel.querySelector('.sc-thread-compose, #sc-thread-compose');
        const br = body.getBoundingClientRect(), pr = panel.getBoundingClientRect();
        btn.style.bottom = Math.max(16, pr.bottom - br.bottom + 16) + 'px';
        void compose;
    }

    // Files waiting to go with the thread reply (same cards as the main box).
    // One list per thread: files added in thread A never ride along with a reply in thread B.
    var threadAttsBy = new Map();   // var: renderThread can run before this line on start-up
    var threadUploads = 0;
    function attsFor(root) {
        if (!threadAttsBy) threadAttsBy = new Map();
        if (!threadAttsBy.has(root)) threadAttsBy.set(root, []);
        return threadAttsBy.get(root);
    }
    function renderThreadAtts() {
        const box = document.getElementById('sc-thread-atts');
        if (!box || typeof createAttachmentPreview !== 'function') return;
        box.innerHTML = '';
        const list = attsFor(activeThread);
        list.forEach((a, i) => box.appendChild(createAttachmentPreview(a, () => { list.splice(i, 1); renderThreadAtts(); })));
    }
    async function addThreadFiles(files) {
        const root = activeThread;
        if (root == null) return;
        threadUploads++;
        try {
            for (const f of files) {
                try { attsFor(root).push(await uploadAttachment(f)); }
                catch (err) { window.scToast ? window.scToast(err.message || 'Upload failed') : alert(err.message); }
                if (root === activeThread) renderThreadAtts();
            }
        } finally { threadUploads--; }
    }
    window.scAddThreadFiles = addThreadFiles;
    window.scThreadHasFiles = () => [...threadAttsBy.values()].some((l) => l.length) || threadUploads > 0;
    // @ chips under the reply box: who's in this thread (they're who you'd answer).
    function renderThreadChips() {
        const wrap = document.querySelector('#sc-thread .sc-thread-chips');
        const root = byId.get(activeThread);
        if (!wrap) return;
        wrap.innerHTML = '';
        if (!root) return;
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const people = [];
        const add = (n) => { n = String(n || '').toLowerCase().replace(/-\d+$/, ''); if (team[n] && !people.includes(n)) people.push(n); };
        [...(replies.get(Number(root.id)) || [])].reverse().forEach((m) => add(m.sender));
        add(root.sender);
        (String(root.text || '').match(/@([\w-]+)/g) || []).forEach((t) => add(t.slice(1)));
        for (const h of people.slice(0, 3)) {
            const b = document.createElement('button');
            b.type = 'button'; b.className = 'mention-toggle'; b.textContent = '@' + labelOf(h);
            b.onclick = () => {
                const input = document.getElementById('sc-thread-input');
                const tag = '@' + labelOf(h) + ' ';
                if (input.value.includes(tag)) input.value = input.value.replace(tag, '');
                else input.value = tag + input.value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
            };
            b.dataset.tag = '@' + labelOf(h) + ' ';
            wrap.appendChild(b);
        }
        markThreadChips();
    }
    function markThreadChips() {
        const v = (document.getElementById('sc-thread-input') || {}).value || '';
        document.querySelectorAll('#sc-thread .sc-thread-chips .mention-toggle').forEach((b) => b.classList.toggle('active', v.includes(b.dataset.tag)));
    }
    window.scRenderThreadChips = renderThreadChips;

    function sendThreadReply() {
        const input = document.getElementById('sc-thread-input');
        const root = byId.get(activeThread);
        if (!input || !root) return;
        let text = window.scNormalizeMentions ? window.scNormalizeMentions(input.value.trim()) : input.value.trim();
        if (threadUploads > 0) { window.scToast && window.scToast('Still uploading…'); return; }
        const atts = attsFor(Number(root.id));
        if (!text && !atts.length) return;
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
        if (tquoting) text = `> ${tquoting.who}: ${tquoting.snippet}\n${text}`;
        if (window.ws && window.ws.readyState === WebSocket.OPEN) {
            window.ws.send(JSON.stringify({ type: 'message', text, sender: me(), channel: root.channel || 'general', reply_to: Number(root.id), attachments: atts.slice() }));
            clearThreadQuote();
            input.value = '';
            input.style.height = '';
            atts.splice(0); renderThreadAtts();
        }
    }

    // @ list for any message box (used by the thread reply box; the main box has chat.js's own).
    function attachMentions(box) {
        if (!box || box._scMentions) return;
        box._scMentions = true;
        let menu = null, items = [], index = 0, start = -1;
        const close = () => { menu?.remove(); menu = null; start = -1; };
        const usage = () => { try { return JSON.parse(localStorage.getItem('scranton-at-count') || '{}')._all || {}; } catch (_) { return {}; } };
        function pick(i) {
            const it = items[i];
            if (!it || start < 0) return;
            const cur = box.selectionStart;
            box.value = box.value.slice(0, start) + `@${it.label} ` + box.value.slice(cur);
            const pos = start + it.label.length + 2;
            box.setSelectionRange(pos, pos);
            close();
            box.dispatchEvent(new Event('input', { bubbles: true }));
            box.focus();
        }
        function update() {
            const cur = box.selectionStart, text = box.value.slice(0, cur);
            const m = /(^|\s)@([^\s@]{0,20})$/.exec(text);
            if (!m) { close(); return; }
            start = cur - m[2].length - 1;
            const q = m[2].toLowerCase();
            const team = (window.scGetTeam && window.scGetTeam()) || {};
            const used = usage();
            items = Object.keys(team).map((h) => ({ h, label: labelOf(h) }))
                .filter((x) => !q || x.h.includes(q) || String(x.label).toLowerCase().includes(q))
                .sort((a, b) => {
                    const sa = a.h.startsWith(q) || String(a.label).toLowerCase().startsWith(q) ? 1 : 0;
                    const sb = b.h.startsWith(q) || String(b.label).toLowerCase().startsWith(q) ? 1 : 0;
                    return (sb - sa) || ((used[b.h] || 0) - (used[a.h] || 0));
                }).slice(0, 8);
            if (!items.length) { close(); return; }
            index = 0;
            if (!menu) {
                menu = document.createElement('div');
                menu.className = 'sc-pop sc-tmention';
                menu.setAttribute('role', 'listbox');
                document.body.appendChild(menu);
                menu.addEventListener('mousedown', (e) => {
                    const b = e.target.closest('[data-i]');
                    if (b) { e.preventDefault(); pick(+b.dataset.i); }
                });
            }
            paint();
            const r = box.getBoundingClientRect();
            menu.style.left = `${Math.max(8, Math.min(r.left, window.innerWidth - 268))}px`;
            menu.style.bottom = `${window.innerHeight - r.top + 8}px`;
        }
        function paint() {
            menu.innerHTML = items.map((x, i) => `<button type="button" role="option" aria-selected="${i === index}" class="sc-menu-item${i === index ? ' active' : ''}" data-i="${i}">
                <span class="sc-tm-av">${avatarOf(x.h)}</span><span>${esc(x.label)}</span>${window.mentionMetaHtml ? window.mentionMetaHtml(x.h, window.scAgentState ? window.scAgentState(x.h) : '') : ''}</button>`).join('');
        }
        box.addEventListener('keydown', (e) => {
            if (!menu) return;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault(); e.stopImmediatePropagation();
                index = (index + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length; paint();
            } else if ((e.key === 'Enter' || e.key === 'Tab') && !e.isComposing) {
                e.preventDefault(); e.stopImmediatePropagation(); pick(index);
            } else if (e.key === 'Escape') {
                e.preventDefault(); e.stopImmediatePropagation(); close();
            }
        });
        box.addEventListener('input', update);
        box.addEventListener('click', update);
        box.addEventListener('blur', () => setTimeout(close, 150));
    }
    window.scAttachMentions = attachMentions;

    function initThreadPanel() {
        const panel = document.getElementById('sc-thread');
        if (!panel) return;
        panel.querySelector('.sc-thread-tabs').addEventListener('click', (e) => {
            if (e.target.closest('[data-close-info]')) { e.stopPropagation(); window.scToggleInfo && window.scToggleInfo(false); return; }
            const x = e.target.closest('[data-close]');
            if (x) { e.stopPropagation(); closeThread(Number(x.dataset.close)); return; }
            if (e.target.closest('[data-info]')) { infoActive = true; renderThread(); return; }
            const t = e.target.closest('[data-root]');
            if (t) { activeThread = Number(t.dataset.root); infoActive = false; renderThread(); }
        });
        panel.querySelector('.sc-thread-close').addEventListener('click', () => window.scCloseRightPanel());
        const input = document.getElementById('sc-thread-input');
        attachMentions(input);   // first, so Enter/Tab pick a name while the list is open
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); sendThreadReply(); }
        });
        // ⚡ shortcuts, same as under the main message box
        const send = document.getElementById('sc-thread-send');
        if (send && window.scMakeShortcutButton && !panel.querySelector('.sc-shortcut-btn')) {
            document.getElementById('sc-thread-attach').after(window.scMakeShortcutButton(() => document.getElementById('sc-thread-input')));
        }
        input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 160) + 'px'; markThreadChips(); });
        const attach = document.getElementById('sc-thread-attach'), file = document.getElementById('sc-thread-file');
        if (attach && file) {
            attach.innerHTML = window.scIcon ? window.scIcon('add', 18) : '+';
            attach.addEventListener('click', () => file.click());
            file.addEventListener('change', () => { addThreadFiles(Array.from(file.files || [])); file.value = ''; });
        }
        input.addEventListener('paste', (e) => {
            const files = Array.from(e.clipboardData?.files || []);
            // stop it here, or the page-wide paste handler uploads the same files to the main box too
            if (files.length) { e.preventDefault(); e.stopPropagation(); addThreadFiles(files); }
        });
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
// The other way round, for anything we put into a message box: "@pm" shows as "@项目经理",
// the same name you see everywhere else. Sending turns it back.
window.scShowLabels = function (text) {
    const team = (window.scGetTeam && window.scGetTeam()) || {};
    return String(text ?? '').replace(/@([A-Za-z0-9_-]+)(?![\w-])/g, (all, h) => {
        const t = team[h.toLowerCase()] || team[h];
        return t && t.label ? '@' + t.label : all;
    });
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
        if (input && !input.value.trim() && window.scDraft) window.scDraft.clear(window.activeChannel);
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
