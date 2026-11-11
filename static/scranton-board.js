// What Lu asked for, pinned in the channel head (scranton_board.py). One pill: "Your asks · 5 open · 2 在 PR";
// click it for the list. The project manager keeps the rows; nothing here posts to chat.
(function () {
    'use strict';
    const STATE_ORDER = ['waiting_lu', 'blocked', 'doing', 'in_pr', 'waiting_qa', 'todo', 'live'];
    let data = { rows: [], summary: '', states: {} };
    let loadedFor = '';

    const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const ch = () => window.activeChannel || 'general';
    const isDm = (c) => String(c || '').startsWith('dm-');
    const label = (h) => { const t = (window.scGetTeam && window.scGetTeam()) || {}; return (t[h] && t[h].label) || h; };

    async function load(force) {
        const c = ch();
        if (isDm(c)) { data = { rows: [], summary: '', states: {} }; paint(); return; }
        if (!force && loadedFor === c && document.hidden) return;
        try {
            const r = await fetch('/api/scranton/board?channel=' + encodeURIComponent(c), { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (!r.ok) return;
            const j = await r.json();
            if (ch() !== c) return;
            data = j; loadedFor = c;
            paint();
        } catch (_) { /* offline */ }
    }

    function paint() {
        const head = document.getElementById('sc-pane-head');
        if (!head) return;
        let btn = document.getElementById('sc-board-btn');
        if (!data.rows || !data.rows.length || isDm(ch())) { if (btn) btn.remove(); closePanel(); return; }
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'sc-board-btn';
            btn.type = 'button';
            btn.setAttribute('aria-haspopup', 'dialog');
            btn.addEventListener('click', (e) => { e.stopPropagation(); togglePanel(); });
            const members = document.getElementById('sc-members-btn');
            if (members) head.insertBefore(btn, members); else head.appendChild(btn);
        }
        const waiting = data.rows.filter((r) => r.state === 'waiting_lu').length;
        btn.classList.toggle('sc-board-you', waiting > 0);
        btn.innerHTML = `<span class="sc-board-k">Your asks</span><span class="sc-board-s">${esc(data.summary)}</span>`;
        btn.setAttribute('aria-label', `Your asks: ${data.summary}`);
        const panel = document.getElementById('sc-board-panel');
        if (panel) renderPanel(panel);
    }

    function renderPanel(panel) {
        const rows = [...data.rows].sort((a, b) => STATE_ORDER.indexOf(a.state) - STATE_ORDER.indexOf(b.state) || (b.at || 0) - (a.at || 0));
        const when = (t) => { const d = new Date((t || 0) * 1000); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };
        panel.innerHTML = `<div class="sc-board-head"><h3>Your asks in #${esc(ch())}</h3><span>Kept by the project manager</span></div>
            <ul class="sc-board-list">${rows.map((r) => `
                <li class="sc-board-row" data-state="${esc(r.state)}">
                    <span class="sc-board-chip">${esc((data.states || {})[r.state] || r.state)}</span>
                    <div class="sc-board-main">
                        <div class="sc-board-ask">${esc(r.ask)}</div>
                        <div class="sc-board-meta">${[r.who ? esc(label(r.who)) : '', r.due ? '交 ' + esc(r.due) : '', r.note ? esc(r.note) : '', 'updated ' + when(r.at)].filter(Boolean).join(' · ')}</div>
                    </div>
                    ${r.link && /^https?:\/\//.test(r.link) ? `<a class="sc-board-link" href="${esc(r.link)}" target="_blank" rel="noopener" aria-label="Open link for ${esc(r.ask)}">Open</a>` : ''}
                </li>`).join('')}</ul>`;
    }

    function togglePanel() {
        if (document.getElementById('sc-board-panel')) { closePanel(); return; }
        const btn = document.getElementById('sc-board-btn');
        if (!btn) return;
        const panel = document.createElement('div');
        panel.id = 'sc-board-panel';
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Your asks');
        document.body.appendChild(panel);
        renderPanel(panel);
        const r = btn.getBoundingClientRect();
        panel.style.top = (r.bottom + 8) + 'px';
        panel.style.left = Math.max(8, Math.min(r.left, innerWidth - panel.offsetWidth - 8)) + 'px';
        btn.setAttribute('aria-expanded', 'true');
        setTimeout(() => document.addEventListener('click', outside, true), 0);
        document.addEventListener('keydown', esc_, true);
    }
    function outside(e) { const p = document.getElementById('sc-board-panel'); if (p && !p.contains(e.target) && e.target.id !== 'sc-board-btn') closePanel(); }
    function esc_(e) { if (e.key === 'Escape') { closePanel(); const b = document.getElementById('sc-board-btn'); if (b) b.focus(); } }
    function closePanel() {
        const p = document.getElementById('sc-board-panel');
        if (p) p.remove();
        const b = document.getElementById('sc-board-btn');
        if (b) b.setAttribute('aria-expanded', 'false');
        document.removeEventListener('click', outside, true);
        document.removeEventListener('keydown', esc_, true);
    }

    window.scBoardRefresh = () => load(true);
    let last = '';
    setInterval(() => { if (ch() !== last) { last = ch(); closePanel(); load(true); } }, 300);
    setInterval(() => load(false), 20000);
    // the members pill re-renders the head; keep ours in front of it
    new MutationObserver(() => { const b = document.getElementById('sc-board-btn'), m = document.getElementById('sc-members-btn');
        if (b && m && b.nextElementSibling !== m) m.before(b); }).observe(document.getElementById('sc-pane-head') || document.body, { childList: true });
})();
