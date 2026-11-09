// Scranton: Report — what got done this week, measured. No invented numbers:
// "time you'd have spent" only shows when you set your own estimate.
(function () {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const ic = (n, s) => (window.scIcon ? window.scIcon(n, s || 18) : '');
    const api = (path, body) => fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
    }).then((r) => r.json());
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    let days = 7;

    function section() {
        let s = document.getElementById('sc-report');
        if (!s) {
            s = document.createElement('section');
            s.id = 'sc-report';
            s.className = 'hidden';
            s.setAttribute('aria-label', 'Report');
            document.getElementById('sc-center')?.appendChild(s);
            s.addEventListener('click', onClick);
            s.addEventListener('change', onChange);
        }
        return s;
    }

    function sideRow() {
        if (document.getElementById('sc-report-row')) return;
        const row = document.createElement('button');
        row.id = 'sc-report-row';
        row.type = 'button';
        row.className = 'sc-side-row';
        row.innerHTML = `${ic('chart', 18)}<span class="sc-side-label">Report</span>`;
        row.onclick = () => open();
        const after = document.getElementById('sc-inbox-row');
        after?.after(row);
    }

    const ago = (t) => {
        const m = Math.round((Date.now() / 1000 - t) / 60);
        return m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : `${Math.round(m / 1440)} d`;
    };

    let renderSeq = 0;
    async function render() {
        const s = section();
        s.innerHTML = '<div class="sc-rp"><p class="sc-rp-muted">Loading…</p></div>';
        const seq = ++renderSeq, want = days;
        let r;
        try { r = await api(`/api/scranton/report?days=${days}`); } catch (_) { r = null; }
        // A slower answer for the other period must not replace the one you picked last.
        if (seq !== renderSeq || want !== days) return;
        if (!r || r.error) {
            s.innerHTML = '<div class="sc-rp"><p class="sc-rp-muted">Couldn\'t load the report. Is Scranton running? <button type="button" class="sc-btn" id="sc-rp-retry">Try again</button></p></div>';
            s.querySelector('#sc-rp-retry')?.addEventListener('click', render);
            return;
        }
        const c = r.counts || {};
        const w = r.waiting || {};
        const maxH = Math.max(1, ...(r.work || []).map((x) => x.hours));
        const anyHours = (r.work || []).some((x) => x.hours > 0);   // all 0 h: empty bars are noise
        s.innerHTML = `<div class="sc-rp">
            <header class="sc-rp-head">
                <h1>Report</h1>
                <div class="sc-rp-range" role="tablist">${[[7, 'This week'], [30, '30 days']].map(([d, l]) => `<button type="button" role="tab" data-days="${d}" aria-selected="${days === d}">${l}</button>`).join('')}</div>
            </header>

            <div class="sc-rp-stats">
                <div><b>${c.merged ?? 0}</b><span>PRs merged</span></div>
                <div><b>${c.prs ?? 0}</b><span>PRs in chat</span></div>
                <div><b>${c.agent_hours ?? 0} h</b><span>Agent busy time</span></div>
                <div><b>${w.avg_minutes == null ? '–' : w.avg_minutes < 60 ? w.avg_minutes + ' min' : Math.round(w.avg_minutes / 6) / 10 + ' h'}</b><span>Your average answer time</span></div>
            </div>

            <h2>Tokens: what gets re-read, and what to change</h2>
            <div id="sc-rp-tokens"><p class="sc-rp-muted">Counting tokens…</p></div>

            <h2>Pull requests</h2>
            ${(r.shipped || []).length ? `<div class="sc-rp-list">${r.shipped.map((p) => `<a class="sc-rp-row" href="${esc(p.url)}" target="_blank" rel="noopener">
                <span class="sc-rp-ic">${ic('git-pr', 18)}</span>
                <span class="sc-rp-t"><b>${esc(p.title || p.url.replace(/^https:\/\/github\.com\//, ''))}</b><small>${esc(p.url.replace(/^https:\/\/github\.com\//, ''))}${p.by ? ' · ' + esc(label(p.by)) : ''}</small></span>
                <span class="sc-rp-tag ${p.merged ? 'ok' : ''}"${p.checked === false ? ' title="Not checked on GitHub, taken from the chat"' : ''}>${p.merged ? 'Merged' : 'Open'}${p.checked === false ? '?' : ''}</span></a>`).join('')}</div>
               ${c.unverified ? `<p class="sc-rp-muted">${c.unverified === (r.shipped || []).length ? 'GitHub couldn\'t be reached, so' : `For ${c.unverified} of these`} "Merged" is taken from the chat, not checked on GitHub (marked ?).</p>` : ''}`
                : '<p class="sc-rp-muted">No pull requests in this period yet. They show up here when an agent posts a PR link.</p>'}

            <h2>Who worked</h2>
            ${(r.work || []).length ? `<div class="sc-rp-list">${r.work.map((x) => `<div class="sc-rp-row static">
                <span class="sc-rp-av">${window.scAvatarHtml ? window.scAvatarHtml(x.agent) : ''}</span>
                <span class="sc-rp-t"><b>${esc(label(x.agent))}</b><small>${x.replies} message${x.replies === 1 ? '' : 's'}</small></span>
                ${anyHours ? `<span class="sc-rp-bar"><i style="width:${Math.round((x.hours / maxH) * 100)}%"></i></span>
                <span class="sc-rp-num">${x.hours} h</span>` : ''}</div>`).join('')}</div>
                <p class="sc-rp-note">Hours are measured from when each agent's terminal was busy. Busy isn't always productive: a stuck agent counts too.</p>`
                : '<p class="sc-rp-muted">No agent work measured yet. Scranton starts counting from now on.</p>'}

            <h2>Waiting on you</h2>
            ${(w.open || []).length ? `<div class="sc-rp-list">${w.open.map((o) => `<button type="button" class="sc-rp-row" data-msg="${esc(o.id)}" data-ch="${esc(o.channel)}">
                <span class="sc-rp-ic">${ic('hourglass', 18)}</span>
                <span class="sc-rp-t"><b>${esc(label(o.by))} · #${esc(o.channel)}</b><small>${esc(o.text)}</small></span>
                <span class="sc-rp-num">${ago(o.since)}</span></button>`).join('')}</div>`
                : '<p class="sc-rp-muted">Nothing open. Everything an agent @-ed you about has an answer.</p>'}

            <h2>Your estimate</h2>
            <div class="sc-rp-est">
                <label>One merged PR used to take me <input type="number" id="sc-rp-hours" min="0.25" max="40" step="0.25" value="${r.settings && r.settings.minutes_per_pr ? r.settings.minutes_per_pr / 60 : ''}" placeholder="–"> hours</label>
                ${r.estimate ? `<p>By your estimate, this period's ${c.merged} merged PRs would have taken you about <b>${r.estimate.hours} h</b>.</p>` : '<p class="sc-rp-muted">Optional. Scranton doesn\'t guess this for you.</p>'}
            </div>
        </div>`;
        renderTokens();
    }

    // Tokens: read from the apps' own logs on this Mac; can take a few seconds, so it fills in after.
    const fmtTok = (n) => n >= 1e9 ? (n / 1e9).toFixed(1) + ' B' : n >= 1e6 ? (n / 1e6).toFixed(1) + ' M' : n >= 1e3 ? Math.round(n / 1e3) + ' K' : String(n);
    async function renderTokens() {
        const box = document.getElementById('sc-rp-tokens');
        if (!box) return;
        const want = days;
        let t;
        try { t = await api(`/api/scranton/report/tokens?days=${days}`); } catch (_) { t = null; }
        if (want !== days || !box.isConnected) return;
        if (t && t.pending) {
            // first read of the logs runs on the server in the background; check back
            box.innerHTML = '<p class="sc-rp-muted">Reading Claude Code and Codex logs on this Mac… the first time takes a minute.</p>';
            setTimeout(renderTokens, 4000);
            return;
        }
        if (!t || !t.available) {
            box.innerHTML = '<p class="sc-rp-muted">No token data found for this period. Scranton reads it from Claude Code and Codex on this Mac.</p>';
            return;
        }
        const maxA = Math.max(1, ...t.agents.map((a) => a.tokens));
        const pct = (n) => Math.round((100 * n) / Math.max(1, t.total));
        const acts = t.top_actions || [], heavy = t.top_sessions || [];
        box.innerHTML = `
            <p class="sc-rp-sum">${fmtTok(t.total)} tokens · <b>${pct(t.cached)}%</b> of it agents re-reading what's already in their session. So what matters is what sits in a session and gets re-read on every reply:</p>
            ${acts.length ? `<h3 class="sc-rp-h3">Done most, and what to change</h3>
            <div class="sc-rp-list">${acts.map((x, i) => `<div class="sc-rp-row static sc-rp-act">
                <span class="sc-rp-rank">${i + 1}</span>
                <span class="sc-rp-t"><b><code>${esc(x.what)}</code> <span class="sc-rp-times">× ${x.times}</span></b>
                    <small>${x.agents.map((a) => esc(label(a))).join(', ')} · about ${fmtTok(x.tokens)} re-read</small>
                    ${x.advice ? `<span class="sc-rp-advice">${esc(x.advice)}</span>` : ''}</span></div>`).join('')}</div>` : ''}
            ${heavy.length ? `<h3 class="sc-rp-h3">Heaviest sessions: what they kept re-reading</h3>
            <div class="sc-rp-sessions">${heavy.map((x) => `<div class="sc-rp-sess">
                <div class="sc-rp-sess-h"><span class="sc-rp-av">${window.scAvatarHtml ? window.scAvatarHtml(x.agent) : ''}</span>
                    <span class="sc-rp-t"><b>${esc(label(x.agent))}</b><small>${x.replies} replies over ${x.hours} h · ${fmtTok(x.tokens)} (${x.share}% of all)</small></span></div>
                <div class="sc-rp-mix">${x.mix.map((m) => `<div class="sc-rp-mixrow"><span>${esc(m.what)}</span>
                    <span class="sc-rp-bar"><i style="width:${m.share}%"></i></span><span class="sc-rp-num">${m.share}%</span></div>`).join('')}</div>
                ${x.repeats.length ? `<p class="sc-rp-reps">Repeated: ${x.repeats.map((r) => `<code>${esc(r.what)}</code> × ${r.times}`).join(' · ')}</p>` : ''}
                ${x.advice.length ? `<ul class="sc-rp-tips">${x.advice.map((v) => `<li>${esc(v)}</li>`).join('')}</ul>` : ''}
            </div>`).join('')}</div>` : ''}
            <details class="sc-rp-more"><summary>By teammate</summary>
            <div class="sc-rp-list">${t.agents.slice(0, 12).map((x) => `<div class="sc-rp-row static">
                <span class="sc-rp-av">${window.scAvatarHtml ? window.scAvatarHtml(x.agent) : ''}</span>
                <span class="sc-rp-t"><b>${esc(label(x.agent))}</b><small>${pct(x.tokens)}% · re-reading ${Math.round((100 * x.cached) / Math.max(1, x.tokens))}%</small></span>
                <span class="sc-rp-bar"><i style="width:${Math.round((x.tokens / maxA) * 100)}%"></i></span>
                <span class="sc-rp-num">${fmtTok(x.tokens)}</span></div>`).join('')}</div></details>
            <p class="sc-rp-note">From Claude Code and Codex logs on this Mac, the ${heavy.length ? 'eight heaviest sessions' : 'sessions'} of this period. "Re-read" weighs each thing by its size and by how many replies came after it, so the numbers are estimates.${t.not_counted.length ? ` Cursor keeps no token log, so ${t.not_counted.map((a) => esc(label(a))).join(', ')} ${t.not_counted.length === 1 ? 'isn\'t' : 'aren\'t'} counted.` : ''}${t.unassigned ? ` ${fmtTok(t.unassigned)} more came from sessions that never posted in Scranton (for example ones you ran yourself) and is left out.` : ''}</p>`;
    }

    function open() {
        if (window.scCloseInbox) window.scCloseInbox();
        if (window.scCloseRightPanel) window.scCloseRightPanel();
        document.getElementById('sc-welcome')?.classList.add('hidden');
        section().classList.remove('hidden');
        document.getElementById('sc-report-row')?.classList.add('active');
        document.body.classList.add('sc-report-open');
        render();
    }
    function close() {
        section().classList.add('hidden');
        document.getElementById('sc-report-row')?.classList.remove('active');
        document.body.classList.remove('sc-report-open');
    }
    window.scOpenReport = open;

    async function onClick(e) {
        const d = e.target.closest('[data-days]');
        if (d) { days = Number(d.dataset.days); render(); return; }
        const m = e.target.closest('[data-msg]');
        if (m) {
            close();
            if (m.dataset.ch !== window.activeChannel && typeof switchChannel === 'function') switchChannel(m.dataset.ch);
            setTimeout(() => { location.hash = ''; location.hash = `#msg-${m.dataset.msg}`; }, 150);
        }
    }
    async function onChange(e) {
        if (e.target.id === 'sc-rp-hours') {
            const raw = e.target.value.trim();
            const h = parseFloat(raw);
            // Empty clears it; anything else must be a real number of hours, or nothing changes.
            if (raw && !(h >= 0.25 && h <= 40)) {
                e.target.setAttribute('aria-invalid', 'true');
                if (window.scToast) window.scToast('Use a number between 0.25 and 40 hours');
                return;
            }
            e.target.removeAttribute('aria-invalid');
            const r = await api('/api/scranton/report/settings', { minutes_per_pr: raw ? Math.round(h * 60) : null });
            if (r && r.error) { if (window.scToast) window.scToast(r.error); return; }
            if (window.scToast) window.scToast(raw ? 'Saved' : 'Cleared');
            render();
        }
    }

    function init() {
        sideRow(); section();
        const title = document.getElementById('sc-pane-title');
        if (title) new MutationObserver(() => close()).observe(title, { childList: true, characterData: true, subtree: true });
        document.getElementById('sc-inbox-row')?.addEventListener('click', close);
        document.getElementById('sc-start-row')?.addEventListener('click', close);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 400));
    else setTimeout(init, 400);
})();
