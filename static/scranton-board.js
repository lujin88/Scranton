// What Lu asked for (scranton_board.py), kept by the project manager.
// Lu, 11-11: no pill in the head. Hovering the channel pill says "21 open · 3 排队 · 10 在做 …";
// clicking it opens the channel overview on the right, with the list at the top.
(function () {
    'use strict';
    const STATE_ORDER = ['waiting_lu', 'blocked', 'doing', 'in_pr', 'waiting_qa', 'todo', 'later', 'live'];
    let data = { rows: [], summary: '', states: {} };

    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const ch = () => window.activeChannel || 'general';
    const isDm = (c) => String(c || '').startsWith('dm-');
    const label = (h) => { const t = (window.scGetTeam && window.scGetTeam()) || {}; return (t[h] && t[h].label) || h; };

    async function load() {
        const c = ch();
        if (isDm(c)) { data = { rows: [], summary: '', states: {} }; paint(); return; }
        try {
            const r = await fetch('/api/scranton/board?channel=' + encodeURIComponent(c), { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (!r.ok || ch() !== c) return;
            data = await r.json();
            // What Lu said here that nobody has taken yet (scranton_said.py).
            try {
                const s = await fetch('/api/scranton/said?channel=' + encodeURIComponent(c), { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
                data.said = s.ok ? await s.json() : null;
            } catch (_) { data.said = null; }
            if (ch() !== c) return;
            await Promise.all([loadClosing(), loadLessons()]);
            paint();
        } catch (_) { /* offline */ }
    }

    function paint() {
        document.getElementById('sc-board-btn')?.remove();   // the old head pill
        const pill = document.getElementById('sc-pane-pill');
        if (pill) {
            if (data.rows && data.rows.length && !isDm(ch())) { pill.dataset.tip = `Your asks: ${data.summary}`; pill.setAttribute('data-tip-always', ''); }
            else { delete pill.dataset.tip; pill.removeAttribute('data-tip-always'); }
        }
        fill();
    }

    // Under the channel setup: who's on what (Lu, 11-11: "底下就是谁在干活、谁没在干活").
    // One block per person with their open asks; free people are named so work can go to them.
    // ---- Close project (scranton_close.py): hand-over, chat saved, old files set aside, channel removed.
    let closing = null, armed = false;
    const closeable = () => !isDm(ch()) && ch() !== 'general';
    const post = (url, body) => fetch(url, { method: 'POST', headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then((r) => r.json().catch(() => ({})));
    async function loadClosing() {
        const c = ch();
        closing = null; armed = false;
        if (!closeable()) return;
        try {
            const r = await fetch(`/api/scranton/project/close?channel=${encodeURIComponent(c)}`, { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (r.ok && ch() === c) closing = await r.json();
        } catch (_) { /* offline */ }
    }
    const mb = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB');
    function closeCard() {
        if (!closing || !closing.closing) return '';
        const cl = closing.cleanup || { ok: [], refused: [] };
        const files = cl.ok.map((f) => `<li>${esc(f)}</li>`).join('');
        const refused = cl.refused.map((f) => `<li>${esc(f.path)} <small>· kept: ${esc(f.why)}</small></li>`).join('');
        return `<div class="sc-ch-card sc-close">
            <h4>Closing this project</h4>
            <ol class="sc-close-steps">
                <li class="${closing.handoff ? 'done' : ''}"><b>Hand-over note</b><span>${closing.handoff ? 'Written: ' + esc(closing.folder) + '/HANDOFF.md' : 'The project manager is writing it. This fills in by itself.'}</span></li>
                <li class="${cl.exists ? 'done' : ''}"><b>Old files to set aside</b><span>${cl.exists ? `${cl.ok.length} file${cl.ok.length === 1 ? '' : 's'} or folder${cl.ok.length === 1 ? '' : 's'}, ${mb(cl.bytes || 0)}. They are moved to ${esc(closing.folder)}/_to_delete, not deleted.` : 'The project manager is listing them.'}</span>
                    ${files ? `<details><summary>See the ${cl.ok.length}</summary><ul>${files}</ul></details>` : ''}
                    ${refused ? `<details><summary>${cl.refused.length} on the list will be left where they are</summary><ul>${refused}</ul></details>` : ''}</li>
                <li><b>Chat</b><span>${closing.messages} messages are saved to ${esc(closing.folder)}/chat.md, then this channel is removed.</span></li>
            </ol>
            <div class="sc-close-foot">
                <button type="button" class="sc-btn sm sc-close-cancel">Keep the project open</button>
                ${cl.ok.length ? `<button type="button" class="sc-btn sm sc-close-finish" data-clean="0">Close, leave files</button>` : ''}
                <button type="button" class="sc-btn sm sc-close-finish danger" data-clean="${cl.ok.length ? 1 : 0}" ${closing.handoff ? '' : 'data-nohandoff="1"'}>${armed ? 'Click again to remove the channel' : closing.handoff ? (cl.ok.length ? 'Close and set files aside' : 'Close project') : 'Close without a hand-over'}</button>
            </div>
        </div>`;
    }
    setInterval(() => { if (closing && closing.closing && !armed) loadClosing().then(fill); }, 15000);

    // What the team has learned here: her kept preferences for this project (scranton_lessons.py).
    let lessons = { kept: [], pending: [] }, lessonsOpen = false;
    async function loadLessons() {
        const c = ch();
        lessons = { kept: [], pending: [] };
        if (!closeable()) return;
        try {
            const r = await fetch(`/api/scranton/lessons?channel=${encodeURIComponent(c)}`, { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (r.ok && ch() === c) lessons = await r.json();
        } catch (_) { /* offline */ }
    }
    function lessonCard() {
        if (!closeable()) return '';
        const k = lessons.kept || [], p = lessons.pending || [];
        const head = `<button type="button" class="sc-lessons-toggle" aria-expanded="${lessonsOpen}"><span>Your preferences · ${k.length}</span>${p.length ? `<span class="sc-lessons-n">${p.length} to confirm</span>` : ''}</button>`;
        if (!lessonsOpen) return `<div class="sc-lessons">${head}</div>`;
        return `<div class="sc-lessons">${head}<div class="sc-ch-card">
            <p class="sc-lessons-note">Handed to every teammate who works here. Up to 15; a new one past that pushes the oldest out.</p>
            ${p.map((x) => `<div class="sc-lessons-item pending"><span>${esc(x.text)}</span><button type="button" class="sc-btn sm" data-lesson="drop" data-id="${x.id}">Drop</button><button type="button" class="sc-btn sm primary" data-lesson="keep" data-id="${x.id}">Keep</button></div>`).join('')}
            ${k.map((x, i) => `<div class="sc-lessons-item"><span>${i + 1}. ${esc(x.text)}</span><button type="button" class="sc-btn sm" data-lesson="remove" data-id="${x.id}">Remove</button></div>`).join('') || (p.length ? '' : '<p class="sc-lessons-note">None yet. They come from what you correct, once you confirm them; or add one yourself.</p>')}
            <form class="sc-lessons-add"><input type="text" maxlength="140" placeholder="Add one yourself, for example: titles sit in the same place on every slide" aria-label="Add a preference"><button type="submit" class="sc-btn sm">Add</button></form>
        </div></div>`;
    }
    document.addEventListener('click', (e) => {
        if (e.target.closest('#sc-ch-board .sc-lessons-toggle')) { lessonsOpen = !lessonsOpen; fill(); return; }
        const b = e.target.closest('#sc-ch-board [data-lesson]');
        if (b) { b.disabled = true; post('/api/scranton/lessons', { channel: ch(), action: b.dataset.lesson, id: Number(b.dataset.id) }).then((d) => { if (d && d.kept) lessons = d; fill(); if (window.scLoadAttention) window.scLoadAttention(); }); }
    });
    document.addEventListener('submit', (e) => {
        const f = e.target.closest && e.target.closest('#sc-ch-board .sc-lessons-add');
        if (!f) return;
        e.preventDefault();
        const v = f.querySelector('input').value.trim();
        if (v) post('/api/scranton/lessons', { channel: ch(), action: 'add', text: v }).then((d) => { if (d && d.kept) lessons = d; fill(); });
    });

    // Closed projects: one quiet line under the channel list; open it to bring one back.
    let closedOpen = false;
    async function loadClosed() {
        const box = document.getElementById('sc-closed');
        if (!box || !window.SESSION_TOKEN) return;
        let list = [];
        try {
            const r = await fetch('/api/scranton/projects/closed', { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (r.ok) list = (await r.json()).closed || [];
        } catch (_) { return; }
        box.hidden = !list.length;
        if (!list.length) return;
        const day = (t) => new Date(Number(t) * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
        box.innerHTML = `<button type="button" class="sc-closed-toggle" aria-expanded="${closedOpen}">Closed projects · ${list.length}</button>`
            + (closedOpen ? list.map((c) => `<div class="sc-closed-item"><span title="${esc(c.folder || '')}"># ${esc(c.channel)}<small>closed ${esc(day(c.at))}</small></span><button type="button" class="sc-btn sm" data-reopen="${esc(c.channel)}">Reopen</button></div>`).join('') : '');
    }
    document.addEventListener('click', (e) => {
        if (e.target.closest('.sc-closed-toggle')) { closedOpen = !closedOpen; loadClosed(); return; }
        const b = e.target.closest('[data-reopen]');
        if (b) { b.disabled = true; post('/api/scranton/project/reopen', { channel: b.dataset.reopen }).then(() => { loadClosed(); if (typeof switchChannel === 'function') setTimeout(() => switchChannel(b.dataset.reopen), 600); }); }
    });
    setTimeout(loadClosed, 2500);

    function fill() {
        const box = document.getElementById('sc-ch-board');
        if (!box) return;
        const c = ch();
        if (isDm(c)) { box.innerHTML = ''; box.dataset.html = ''; return; }
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const members = (((window.scChannelMembers && window.scChannelMembers()) || {})[c] || []).filter((h) => team[h]);
        const st = (h) => (window.scAgentState ? window.scAgentState(h) : 'offline');
        const allOpen = (data.rows || []).filter((r) => r.state !== 'live');
        const open = allOpen;
        const live = (data.rows || []).filter((r) => r.state === 'live');
        const byWho = {};
        for (const r of open.filter((x) => !filter || x.state === filter)) (byWho[r.who && team[r.who] ? r.who : '_'] = byWho[r.who && team[r.who] ? r.who : '_'] || []).push(r);
        for (const k of Object.keys(byWho)) byWho[k].sort((a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state));
        const people = [...new Set([...members, ...Object.keys(byWho).filter((h) => h !== '_')])];
        const rank = (h) => (st(h) === 'working' ? 0 : 2) + (byWho[h] ? 0 : 1) + (st(h) === 'offline' ? 4 : 0);
        people.sort((a, b) => rank(a) - rank(b) || (byWho[b] || []).length - (byWho[a] || []).length);
        const busy = people.filter((h) => byWho[h] || (!filter && st(h) === 'working'));
        const free = people.filter((h) => !byWho[h] && st(h) === 'available');
        const off = people.filter((h) => !byWho[h] && st(h) !== 'working' && st(h) !== 'available');
        // Rows nobody touched for 4 h may be out of date (Lu, 11-12: most were 17–20 h old).
        const staleH = (r) => { const h = Math.floor((Date.now() / 1000 - (r.at || 0)) / 3600); return h >= 4 ? h : 0; };
        const askLi = (r) => `<li class="sc-board-row" data-state="${esc(r.state)}" data-row="${r.id}" tabindex="0" role="button" aria-label="Open the chat for ${esc(r.ask)}">
                <span class="sc-board-chip">${esc((data.states || {})[r.state] || r.state)}</span>
                <span class="sc-board-ask"><span class="sc-board-t">${esc(r.ask)}${r.not_asked ? '<small> · not sent to you yet</small>' : ''}${r.due ? `<small> · 交 ${esc(r.due)}</small>` : ''}${staleH(r) ? `<small class="sc-board-stale"> · ${staleH(r)} h 没更新</small>` : ''}</span>${r.note ? `<small class="sc-board-note" title="${esc(r.note)}">${esc(r.note)}</small>` : ''}</span>
                ${r.link && /^https?:\/\//.test(r.link) ? `<a class="sc-board-link" href="${esc(r.link)}" target="_blank" rel="noopener" aria-label="Open link for ${esc(r.ask)}">Open</a>` : ''}
            </li>`;
        // "在做" on the board is what the PM wrote down; Working / Online is what the teammate is doing
        // right now. Online with work marked 在做 means it isn't on it at the moment: say so (Lu, 11-12).
        const doingNow = (h) => (byWho[h] || []).some((r) => r.state === 'doing');
        const stuck = (h) => { const d = String((window.scDoing || {})[h] || ''); return /^Stuck\?/.test(d) ? d : ''; };
        const stateLbl = (h) => stuck(h) ? stuck(h) : st(h) === 'working' ? 'Working'
            : st(h) === 'available' ? (doingNow(h) ? 'Idle, not on it right now' : 'Online') : 'Not running';
        const person = (h) => `<div class="sc-who">
                <div class="sc-who-head"><span class="sc-who-av">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span>
                    <b>${esc(label(h))}</b><span class="sc-who-st" data-st="${esc(st(h))}"${stuck(h) ? ' data-stuck' : st(h) !== 'working' && doingNow(h) ? ' data-idle' : ''}>${stateLbl(h)}</span>
                    ${byWho[h] ? `<span class="sc-who-n">${byWho[h].length}</span>` : ''}</div>
                ${byWho[h] ? `<ul class="sc-board-list">${byWho[h].map(askLi).join('')}</ul>` : ''}
            </div>`;
        const names = (hs) => hs.map((h) => esc(label(h))).join('、');
        // You said, not picked up yet (Lu, 11-18: "每次说完很多事情都没做"). Click one to open that message.
        const saidCard = () => {
            const o = (data.said && data.said.open) || [];
            if (!o.length) return '';
            const own = (t) => String(t || '').split('\n').filter((l) => !/^\s*>/.test(l)).join(' ').replace(/@[\w-]+/g, '').trim();
            return `<div class="sc-ch-card sc-who-card"><div class="sc-who"><div class="sc-who-head"><b>You said, not picked up yet</b><span class="sc-who-n">${o.length}</span></div>
                <ul class="sc-board-list">${o.slice(-12).reverse().map((it) => `<li class="sc-board-row sc-said-row" data-said="${it.id}" tabindex="0" role="button" aria-label="Open what you said">
                    <span class="sc-board-chip">${esc(String(it.at).slice(6))}</span>
                    <span class="sc-board-ask"><span class="sc-board-t">${esc(own(it.said).slice(0, 90))}</span></span></li>`).join('')}</ul></div></div>`;
        };
        // Overview first (Lu, 11-11): how many in each step, waiting-on-you first; then who's free.
        const counts = {};
        for (const r of open) counts[r.state] = (counts[r.state] || 0) + 1;
        const tiles = STATE_ORDER.filter((k) => k !== 'live' && (counts[k] || k === 'waiting_lu'))
            .map((k) => `<button type="button" class="sc-ov-tile${filter === k ? ' on' : ''}" data-state="${k}" aria-pressed="${filter === k}"><b>${counts[k] || 0}</b><span>${esc((data.states || {})[k] || k)}</span></button>`).join('');
        const html = `<div class="sc-board-head"><h3>Who's on what</h3><span>${data.paused ? 'Paused: no reminders, nobody woken' : open.length ? open.length + ' open' : 'Nothing open'}</span></div>
            <div class="sc-board-acts"><button type="button" class="sc-ch-edit sc-board-pause" data-paused="${data.paused ? 1 : 0}">${data.paused ? 'Resume project' : 'Pause project'}</button>
                ${closeable() && !(closing && closing.closing) ? '<button type="button" class="sc-ch-edit sc-board-close">Close project</button>' : ''}</div>
            ${closeCard()}
            ${lessonCard()}
            ${open.length ? `<div class="sc-ch-card sc-ov">
                <div class="sc-ov-tiles">${tiles}</div>
                <div class="sc-ov-foot"><span>${busy.length} busy</span><span>${free.length} free${free.length ? ': ' + names(free) : ''}</span>${live.length ? `<span>${live.length} live today</span>` : ''}</div>
            </div>` : ''}
            ${saidCard()}
            <div class="sc-ch-card sc-who-card">
                ${busy.map(person).join('')}
                ${byWho._ ? `<div class="sc-who"><div class="sc-who-head"><b>Not assigned</b><span class="sc-who-n">${byWho._.length}</span></div><ul class="sc-board-list">${byWho._.map(askLi).join('')}</ul></div>` : ''}
                ${filter ? `<button type="button" class="sc-who sc-who-line sc-ov-clear">Showing ${esc((data.states || {})[filter] || filter)} only · show all</button>` : ''}
                ${!filter && free.length ? `<div class="sc-who sc-who-line"><span class="sc-who-st" data-st="available">Free</span>${names(free)}</div>` : ''}
                ${!filter && off.length ? `<div class="sc-who sc-who-line"><span class="sc-who-st">Not running</span>${names(off)}</div>` : ''}
                ${!filter && live.length ? `<div class="sc-who sc-who-line"><span class="sc-who-st">Live today</span>${live.map((r) => esc(r.ask)).join('、')}</div>` : ''}
            </div>`;
        // Only touch the DOM when something changed: the 5 s refresh must not drop keyboard focus.
        if (box.dataset.html !== html) { box.dataset.html = html; box.innerHTML = html; }
    }

    // Click a row: open the message it's about (the question to Lu for 等你). Without one, the latest
    // message to Lu from the team in this channel since the row was made. Click a tile: show only that step;
    // 等你 with a single item goes straight to it (Lu, 11-11: "点过去直接跳到那个 chat").
    let filter = '';
    function target(r) {
        const msgs = window.scMsgs;
        if (r.msg && msgs && msgs.get(Number(r.msg))) return msgs.get(Number(r.msg));
        if (r.msg) return { id: Number(r.msg), channel: ch() };
        if (!msgs) return null;
        const me = String(window.username || 'Lu').toLowerCase();
        const since = Number(r.since || r.at || 0) - 600;
        let best = null;
        for (const m of msgs.values()) {
            if ((m.channel || 'general') !== ch() || String(m.sender || '').toLowerCase() === me) continue;
            if ((m.timestamp || 0) < since || !/@lu\b/i.test(String(m.text || ''))) continue;
            if (r.who && ![r.who, r.by, 'pm'].includes(String(m.sender || '').toLowerCase())) continue;
            if (!best || m.timestamp > best.timestamp) best = m;
        }
        return best;
    }
    function go(r) {
        const m = target(r);
        if (!m) { window.scToast && window.scToast('No message to open for this one yet'); return; }
        if (window.scCloseRightPanel) window.scCloseRightPanel();
        if (window.scFocusMessage) window.scFocusMessage(m);
    }
    document.addEventListener('click', (e) => {
        const said = e.target.closest('#sc-ch-board .sc-said-row');
        if (said) {
            if (window.scCloseRightPanel) window.scCloseRightPanel();
            if (window.scFocusMessage) window.scFocusMessage((window.scMsgs && window.scMsgs.get(Number(said.dataset.said))) || { id: Number(said.dataset.said), channel: ch() });
            return;
        }
        const tile = e.target.closest('#sc-ch-board .sc-ov-tile');
        if (tile) {
            const k = tile.dataset.state;
            const rows = (data.rows || []).filter((r) => r.state === k);
            if (k === 'waiting_lu' && rows.length === 1) { go(rows[0]); return; }
            filter = filter === k ? '' : k; fill(); return;
        }
        if (e.target.closest('#sc-ch-board .sc-ov-clear')) { filter = ''; fill(); return; }
        if (e.target.closest('#sc-ch-board .sc-board-close')) {
            post('/api/scranton/project/close', { channel: ch(), step: 'start' }).then((d) => { closing = d; load(); });
            return;
        }
        if (e.target.closest('#sc-ch-board .sc-close-cancel')) {
            post('/api/scranton/project/close', { channel: ch(), step: 'cancel' }).then((d) => { closing = d; armed = false; load(); });
            return;
        }
        const fin = e.target.closest('#sc-ch-board .sc-close-finish');
        if (fin) {
            if (fin.classList.contains('danger') && !armed) { armed = true; fill(); setTimeout(() => { if (armed) { armed = false; fill(); } }, 6000); return; }
            fin.disabled = true;
            post('/api/scranton/project/close', { channel: ch(), step: 'finish', clean: fin.dataset.clean === '1', without_handoff: fin.dataset.nohandoff === '1' }).then((d) => {
                armed = false;
                if (d && d.ok) {
                    if (window.scToast) window.scToast(`Closed. Saved in ${d.folder}`);
                    loadClosed();
                    if (typeof switchChannel === 'function') switchChannel('general');
                } else { if (window.scToast) window.scToast((d && d.error) || 'Could not close the project.'); loadClosing().then(fill); }
            });
            return;
        }
        const pb = e.target.closest('#sc-ch-board .sc-board-pause');
        if (pb) {
            fetch('/api/scranton/channel/pause', { method: 'POST', headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel: ch(), paused: pb.dataset.paused !== '1' }) }).then(load);
            return;
        }
        const li = e.target.closest('#sc-ch-board .sc-board-row');
        if (li && !e.target.closest('a')) { const r = (data.rows || []).find((x) => String(x.id) === li.dataset.row); if (r) go(r); }
    });
    document.addEventListener('keydown', (e) => {
        if ((e.key === 'Enter' || e.key === ' ') && e.target.matches && e.target.matches('#sc-ch-board .sc-board-row')) { e.preventDefault(); e.target.click(); }
    });

    window.scBoardFill = fill;
    window.scBoardRefresh = load;
    let last = '';
    setInterval(() => { if (ch() !== last) { last = ch(); filter = ''; load(); } }, 300);
    setInterval(load, 20000);
    // working / online changes: repaint the list without refetching
    setInterval(() => { if (document.getElementById('sc-ch-board')) fill(); }, 5000);
})();
