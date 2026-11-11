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
        if (isDm(c)) { box.innerHTML = ''; return; }
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const members = (((window.scChannelMembers && window.scChannelMembers()) || {})[c] || []).filter((h) => team[h]);
        const st = (h) => (window.scAgentState ? window.scAgentState(h) : 'offline');
        const open = (data.rows || []).filter((r) => r.state !== 'live');
        const live = (data.rows || []).filter((r) => r.state === 'live');
        const byWho = {};
        for (const r of open) (byWho[r.who && team[r.who] ? r.who : '_'] = byWho[r.who && team[r.who] ? r.who : '_'] || []).push(r);
        for (const k of Object.keys(byWho)) byWho[k].sort((a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state));
        const people = [...new Set([...members, ...Object.keys(byWho).filter((h) => h !== '_')])];
        const rank = (h) => (st(h) === 'working' ? 0 : 2) + (byWho[h] ? 0 : 1) + (st(h) === 'offline' ? 4 : 0);
        people.sort((a, b) => rank(a) - rank(b) || (byWho[b] || []).length - (byWho[a] || []).length);
        const busy = people.filter((h) => byWho[h] || st(h) === 'working');
        const free = people.filter((h) => !byWho[h] && st(h) === 'available');
        const off = people.filter((h) => !byWho[h] && st(h) !== 'working' && st(h) !== 'available');
        const askLi = (r) => `<li class="sc-board-row" data-state="${esc(r.state)}">
                <span class="sc-board-chip">${esc((data.states || {})[r.state] || r.state)}</span>
                <span class="sc-board-ask"><span class="sc-board-t">${esc(r.ask)}${r.due ? `<small> · 交 ${esc(r.due)}</small>` : ''}</span>${r.note ? `<small class="sc-board-note" title="${esc(r.note)}">${esc(r.note)}</small>` : ''}</span>
                ${r.link && /^https?:\/\//.test(r.link) ? `<a class="sc-board-link" href="${esc(r.link)}" target="_blank" rel="noopener" aria-label="Open link for ${esc(r.ask)}">Open</a>` : ''}
            </li>`;
        const stateLbl = (h) => ({ working: 'Working', available: 'Online' }[st(h)] || 'Not running');
        const person = (h) => `<div class="sc-who">
                <div class="sc-who-head"><span class="sc-who-av">${window.scAvatarHtml ? window.scAvatarHtml(h) : ''}</span>
                    <b>${esc(label(h))}</b><span class="sc-who-st" data-st="${esc(st(h))}">${stateLbl(h)}</span>
                    ${byWho[h] ? `<span class="sc-who-n">${byWho[h].length}</span>` : ''}</div>
                ${byWho[h] ? `<ul class="sc-board-list">${byWho[h].map(askLi).join('')}</ul>` : ''}
            </div>`;
        const names = (hs) => hs.map((h) => esc(label(h))).join('、');
        // Overview first (Lu, 11-11): how many in each step, waiting-on-you first; then who's free.
        const counts = {};
        for (const r of open) counts[r.state] = (counts[r.state] || 0) + 1;
        const tiles = STATE_ORDER.filter((k) => k !== 'live' && (counts[k] || k === 'waiting_lu'))
            .map((k) => `<div class="sc-ov-tile" data-state="${k}"><b>${counts[k] || 0}</b><span>${esc((data.states || {})[k] || k)}</span></div>`).join('');
        box.innerHTML = `<div class="sc-board-head"><h3>Who's on what</h3><span>${open.length ? open.length + ' open' : 'Nothing open'}</span></div>
            ${open.length ? `<div class="sc-ch-card sc-ov">
                <div class="sc-ov-tiles">${tiles}</div>
                <div class="sc-ov-foot"><span>${busy.length} busy</span><span>${free.length} free${free.length ? ': ' + names(free) : ''}</span>${live.length ? `<span>${live.length} live today</span>` : ''}</div>
            </div>` : ''}
            <div class="sc-ch-card sc-who-card">
                ${busy.map(person).join('')}
                ${byWho._ ? `<div class="sc-who"><div class="sc-who-head"><b>Not assigned</b><span class="sc-who-n">${byWho._.length}</span></div><ul class="sc-board-list">${byWho._.map(askLi).join('')}</ul></div>` : ''}
                ${free.length ? `<div class="sc-who sc-who-line"><span class="sc-who-st" data-st="available">Free</span>${names(free)}</div>` : ''}
                ${off.length ? `<div class="sc-who sc-who-line"><span class="sc-who-st">Not running</span>${names(off)}</div>` : ''}
                ${live.length ? `<div class="sc-who sc-who-line"><span class="sc-who-st">Live today</span>${live.map((r) => esc(r.ask)).join('、')}</div>` : ''}
            </div>`;
    }

    window.scBoardFill = fill;
    window.scBoardRefresh = load;
    let last = '';
    setInterval(() => { if (ch() !== last) { last = ch(); load(); } }, 300);
    setInterval(load, 20000);
    // working / online changes: repaint the list without refetching
    setInterval(() => { if (document.getElementById('sc-ch-board')) fill(); }, 5000);
})();
