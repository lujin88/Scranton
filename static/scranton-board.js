// What Lu asked for (scranton_board.py), kept by the project manager.
// Lu, 11-11: no pill in the head. Hovering the channel pill says "21 open · 3 排队 · 10 在做 …";
// clicking it opens the channel overview on the right, with the list at the top.
(function () {
    'use strict';
    const STATE_ORDER = ['waiting_lu', 'blocked', 'doing', 'in_pr', 'waiting_qa', 'todo', 'live'];
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
                <span class="sc-board-ask"><span class="sc-board-t">${esc(r.ask)}${r.due ? `<small> · 交 ${esc(r.due)}</small>` : ''}${staleH(r) ? `<small class="sc-board-stale"> · ${staleH(r)} h 没更新</small>` : ''}</span>${r.note ? `<small class="sc-board-note" title="${esc(r.note)}">${esc(r.note)}</small>` : ''}</span>
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
        // Overview first (Lu, 11-11): how many in each step, waiting-on-you first; then who's free.
        const counts = {};
        for (const r of open) counts[r.state] = (counts[r.state] || 0) + 1;
        const tiles = STATE_ORDER.filter((k) => k !== 'live' && (counts[k] || k === 'waiting_lu'))
            .map((k) => `<button type="button" class="sc-ov-tile${filter === k ? ' on' : ''}" data-state="${k}" aria-pressed="${filter === k}"><b>${counts[k] || 0}</b><span>${esc((data.states || {})[k] || k)}</span></button>`).join('');
        const html = `<div class="sc-board-head"><h3>Who's on what</h3><span>${open.length ? open.length + ' open' : 'Nothing open'}</span></div>
            ${open.length ? `<div class="sc-ch-card sc-ov">
                <div class="sc-ov-tiles">${tiles}</div>
                <div class="sc-ov-foot"><span>${busy.length} busy</span><span>${free.length} free${free.length ? ': ' + names(free) : ''}</span>${live.length ? `<span>${live.length} live today</span>` : ''}</div>
            </div>` : ''}
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
        const tile = e.target.closest('#sc-ch-board .sc-ov-tile');
        if (tile) {
            const k = tile.dataset.state;
            const rows = (data.rows || []).filter((r) => r.state === k);
            if (k === 'waiting_lu' && rows.length === 1) { go(rows[0]); return; }
            filter = filter === k ? '' : k; fill(); return;
        }
        if (e.target.closest('#sc-ch-board .sc-ov-clear')) { filter = ''; fill(); return; }
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
