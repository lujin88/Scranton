// Scranton: Report — what got done this week, measured. No invented numbers:
// "time you'd have spent" only shows when you set your own estimate.
(function () {
    const PR_SHOWN = 5;   // pull requests listed before "Show more"
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const ic = (n, s) => (window.scIcon ? window.scIcon(n, s || 18) : '');
    const api = (path, body) => fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
    }).then((r) => r.json());
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    // "Claude · Opus", "ChatGPT · default model", "Cursor · Grok 4.6": which app and model a teammate runs on
    const runsOn = (h) => {
        const a = (window.scGetTeam ? window.scGetTeam() : {})[h] || {};
        const app = { claude: 'Claude', codex: 'ChatGPT', agent: 'Cursor', 'cursor-agent': 'Cursor', agy: 'Gemini', gemini: 'Gemini', grok: 'Grok' }[String(a.provider || a.command || '').toLowerCase()] || '';
        const m = String(a.model_name || '');
        return [app, m && m !== app ? m : (app ? 'default model' : '')].filter(Boolean).join(' · ');
    };
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
            <div id="sc-rp-trend"></div>
            <div id="sc-rp-tokens"><p class="sc-rp-muted">Counting tokens…</p></div>

            <h2>Pull requests</h2>
            ${(r.shipped || []).length ? `<div class="sc-rp-list" id="sc-rp-prs">${r.shipped.map((p, i) => `<a class="sc-rp-row${i >= PR_SHOWN ? ' sc-rp-more' : ''}" href="${esc(p.url)}" target="_blank" rel="noopener"${i >= PR_SHOWN ? ' hidden' : ''}>
                <span class="sc-rp-ic">${ic('git-pr', 18)}</span>
                <span class="sc-rp-t"><b>${esc(p.title || p.url.replace(/^https:\/\/github\.com\//, ''))}</b><small>${esc(p.url.replace(/^https:\/\/github\.com\//, ''))}${p.by ? ' · ' + esc(label(p.by)) : ''}</small></span>
                <span class="sc-rp-tag ${p.merged ? 'ok' : ''}"${p.checked === false ? ' title="Not checked on GitHub, taken from the chat"' : ''}>${p.merged ? 'Merged' : 'Open'}${p.checked === false ? '?' : ''}</span></a>`).join('')}</div>
               ${r.shipped.length > PR_SHOWN ? `<button type="button" class="sc-btn sm sc-rp-showmore" id="sc-rp-prs-more">Show ${r.shipped.length - PR_SHOWN} more</button>` : ''}
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
        renderTrend();
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
            <div id="sc-rp-props"></div>
            ${heavy.length ? `<h3 class="sc-rp-h3">Heaviest sessions: what they kept re-reading</h3>
            <div class="sc-rp-sessions">${heavy.map((x) => `<div class="sc-rp-sess">
                <div class="sc-rp-sess-h"><span class="sc-rp-av">${window.scAvatarHtml ? window.scAvatarHtml(x.agent) : ''}</span>
                    <span class="sc-rp-t"><b>${esc(label(x.agent))}${runsOn(x.agent) ? ` <span class="sc-rp-app">${esc(runsOn(x.agent))}</span>` : ''}</b><small>Its longest session: ${x.replies} replies over ${x.hours} h · ${fmtTok(x.tokens)} (${x.share}% of all)${x.more ? ` · plus ${x.more} more long session${x.more > 1 ? 's' : ''}` : ''}</small></span></div>
                <div class="sc-rp-mix">${x.mix.map((m) => `<div class="sc-rp-mixrow"><span>${esc(m.what)}</span>
                    <span class="sc-rp-bar"><i style="width:${m.share}%"></i></span><span class="sc-rp-num">${m.share}%</span></div>`).join('')}</div>
                ${x.repeats.length ? `<p class="sc-rp-reps">Repeated: ${x.repeats.map((r) => `<code>${esc(r.what)}</code> × ${r.times}`).join(' · ')}</p>` : ''}
                ${x.advice.length ? `<ul class="sc-rp-tips">${x.advice.map((v) => `<li>${esc(v)}</li>`).join('')}</ul>` : ''}
            </div>`).join('')}</div>` : ''}
            <details class="sc-rp-more"><summary>By teammate</summary>
            <div class="sc-rp-list">${t.agents.slice(0, 12).map((x) => `<div class="sc-rp-row static">
                <span class="sc-rp-av">${window.scAvatarHtml ? window.scAvatarHtml(x.agent) : ''}</span>
                <span class="sc-rp-t"><b>${esc(label(x.agent))}${runsOn(x.agent) ? ` <span class="sc-rp-app">${esc(runsOn(x.agent))}</span>` : ''}</b><small>${pct(x.tokens)}% · re-reading ${Math.round((100 * x.cached) / Math.max(1, x.tokens))}%</small></span>
                <span class="sc-rp-bar"><i style="width:${Math.round((x.tokens / maxA) * 100)}%"></i></span>
                <span class="sc-rp-num">${fmtTok(x.tokens)}</span></div>`).join('')}</div></details>
            <p class="sc-rp-note">From Claude Code and Codex logs on this Mac, the ${heavy.length ? 'eight heaviest sessions' : 'sessions'} of this period. "Re-read" weighs each thing by its size and by how many replies came after it, so the numbers are estimates.${t.not_counted.length ? ` Cursor keeps no token log, so ${t.not_counted.map((a) => esc(label(a))).join(', ')} ${t.not_counted.length === 1 ? 'isn\'t' : 'aren\'t'} counted.` : ''}${t.unassigned ? ` ${fmtTok(t.unassigned)} more came from sessions that never posted in Scranton (for example ones you ran yourself) and is left out.` : ''}</p>`;
        renderProposals(t);
    }

    // ---------------------------------------------------------------- what changed (Lu, 11-10)
    // "选完了得让我看到改进，否则我什么都看不到": every change you picked stays here with the numbers
    // before and after it, worked out again each time the Report opens.
    const TITLES = { 'fresh-sessions': 'Fresh sessions on', 'only-new-chat': 'Read only new chat',
        'files-once': 'Stop reopening the same files', 'short-output': 'Keep command output short' };
    const dayOf = (ms) => { const d = new Date(ms); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
    const today = () => dayOf(Date.now());
    const avg = (xs) => { const v = xs.filter((x) => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
    function compare(series, at) {
        const d0 = dayOf(at), now = today();
        // days the team actually worked (an idle Saturday would make "before" look good)
        const busy = (d) => (d.calls || 0) >= 50 || (d.wakes || 0) >= 50;
        const before = series.filter((d) => d.day < d0 && busy(d)).slice(-3);
        const full = series.filter((d) => d.day > d0 && d.day < now);      // whole days after it
        const after = full.length ? full : series.filter((d) => d.day === now && d.day > d0);
        const partial = !full.length;
        const m = (rows, k) => avg(rows.map((r) => r[k]));
        return { partial, n: full.length, before: before.length,
            ctx: [m(before, 'ctx_k'), m(after, 'ctx_k')],
            wakes: [m(before, 'wakes'), partial ? null : m(after, 'wakes')],
            tokens: [m(before, 'tokens'), partial ? null : m(after, 'tokens')] };
    }
    const delta = (a, b) => (a && b != null ? Math.round((100 * (b - a)) / a) : null);
    const cell = (label, [a, b], fmt) => {
        if (!a) return '';
        if (b == null) return `<span class="sc-rp-cmp"><small>${label}</small><span><b>${fmt(a)}</b> → <i>tomorrow</i></span></span>`;
        const d = delta(a, b);
        return `<span class="sc-rp-cmp"><small>${label}</small><span><b>${fmt(a)} → ${fmt(b)}</b>${d != null ? ` <em class="${d <= 0 ? 'good' : 'bad'}">${d > 0 ? '+' : ''}${d}%</em>` : ''}</span></span>`;
    };
    async function migrateLocalPicks() {
        // picks made before 11-10 sit in this browser's localStorage: hand them to the server once
        const got = picks(), items = Object.entries(got).filter(([, g]) => g && typeof g === 'object' && g.key && g.key !== 'C')
            .map(([id, g]) => ({ id, key: g.key, at: g.at, title: TITLES[id] || id, merge_only: true }));
        if (!items.length || localStorage.getItem(PROP_KEY + '-sent') === '1') return;
        try { await api('/api/scranton/report/changes', { items }); localStorage.setItem(PROP_KEY + '-sent', '1'); } catch (_) { /* next time */ }
    }
    async function renderTrend() {
        const box = document.getElementById('sc-rp-trend');
        if (!box) return;
        await migrateLocalPicks();
        let tr;
        try { tr = await api('/api/scranton/report/trend?days=14'); } catch (_) { tr = null; }
        if (!box.isConnected || !tr || !Array.isArray(tr.days)) return;
        const series = tr.days, changes = (tr.changes || []).slice().reverse();
        const k = (n) => `${Math.round(n)}k`;
        const per = (n) => `${Math.round(n)}/day`;
        const tok = (n) => fmtTok(n) + '/day';
        const fmtDate = (ms) => new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
        const rows = changes.map((c) => {
            const r = compare(series, c.at);
            const note = r.before ? (r.partial ? 'Today so far; daily totals show tomorrow.' : `${r.n} full day${r.n > 1 ? 's' : ''} after vs ${r.before} before.`) : 'No numbers from before it.';
            return `<div class="sc-rp-row static sc-rp-change">
                <span class="sc-rp-t"><b>${esc(c.title)}</b><small>${fmtDate(c.at)}${c.by && c.by !== 'Lu' ? ` · ${esc(c.by)}` : ''} · ${note}</small></span>
                <span class="sc-rp-cmps">${cell('Re-read per reply', r.ctx, k)}${cell('Wake-ups', r.wakes, per)}${cell('Tokens', r.tokens, tok)}</span>
            </div>`;
        }).join('');
        const max = Math.max(1, ...series.map((d) => d.tokens));
        const marks = new Set(changes.map((c) => dayOf(c.at)));
        box.innerHTML = `${changes.length ? `<h3 class="sc-rp-h3">What changed since you picked</h3><div class="sc-rp-list">${rows}</div>` : ''}
            <details class="sc-rp-more"><summary>Day by day (14 days)</summary>
            <div class="sc-rp-list">${series.slice().reverse().map((d) => `<div class="sc-rp-row static sc-rp-day">
                <span class="sc-rp-t"><b>${new Date(d.day + 'T12:00').toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })}${marks.has(d.day) ? ' <span class="sc-rp-app">change</span>' : ''}</b>
                <small>${d.ctx_k != null ? `${d.ctx_k}k re-read per reply · ` : ''}${d.wakes} wake-ups${d.pm_wakes ? ` (${d.pm_wakes} by the project manager)` : ''}${d.day === today() ? ' · so far' : ''}</small></span>
                <span class="sc-rp-bar"><i style="width:${Math.round((d.tokens / max) * 100)}%"></i></span>
                <span class="sc-rp-num">${d.tokens ? fmtTok(d.tokens) : ''}</span></div>`).join('')}</div></details>`;
    }

    // ---------------------------------------------------------------- proposals
    // Lu, 11-09: "suggestions at the bottom, as A/B/C I can agree to or not". Each one comes from
    // this period's numbers. Picking an option does it: a Scranton setting is changed right away;
    // a change to how agents work goes to @harness (who owns the rules) as a request.
    const PROP_KEY = 'scranton-report-picks';
    const picks = () => { try { return JSON.parse(localStorage.getItem(PROP_KEY) || '{}'); } catch (_) { return {}; } };
    const ACT_RULES = [
        [/^chat_read/, 'only-new-chat', 'Read only new chat',
            'Agents re-read chat they already saw', 'read chat with since_id (only what is new since they last read), and read a thread only when they are in it'],
        [/^(Read|Edit|Write) /, 'files-once', 'Stop reopening the same files',
            'The same files are opened again and again', 'read a file once per task, only the part they need (offset/limit), and put what they always need in their role card'],
        [/./, 'short-output', 'Keep command output short',
            'The same commands run many times, and their output stays in memory', 'keep command output short (| tail -40, --quiet) and not re-run a command to check something that did not change'],
    ];
    async function proposals(t) {
        const out = [];
        const reread = Math.round((100 * t.cached) / Math.max(1, t.total));
        let ho = null;
        try { ho = await api('/api/scranton/handover'); } catch (_) { ho = null; }
        if (ho && !ho.enabled && reread >= 70) {
            out.push({ id: 'fresh-sessions', title: 'Turn on Fresh sessions',
                why: `${reread}% of all tokens are agents re-reading their own long sessions, and Fresh sessions is off.`,
                options: [
                    { key: 'A', text: 'Turn on: start fresh every 4 hours or 40 messages', rec: true, act: { type: 'handover', hours: 4, wakes: 40 } },
                    { key: 'B', text: 'Turn on, gentler: every 8 hours or 80 messages', act: { type: 'handover', hours: 8, wakes: 80 } },
                    { key: 'C', text: 'Not now', act: { type: 'none' } }] });
        }
        const seen = new Set();
        for (const a of (t.top_actions || [])) {
            if (/\(other\)$/.test(a.what)) continue;   // nothing specific to ask for
            // chat_read already returns only what's new (11-10): its cost is long sessions and too
            // many wake-ups, which "@ only who acts" and Fresh sessions by size already address.
            if (/^chat_read/.test(a.what)) continue;
            const r = ACT_RULES.find(([re]) => re.test(a.what));
            if (!r || seen.has(r[1])) continue;
            seen.add(r[1]);
            const who = a.agents.map((x) => '@' + x).join(' ');
            const rule = r[4];
            out.push({ id: r[1], title: r[2],
                why: `${r[3]}: \`${a.what}\` ran ${a.times} times (${a.agents.map(label).join(', ')}), about ${fmtTok(a.tokens)} re-read.`,
                options: [
                    { key: 'A', text: 'Add it to every agent\'s rules (Harness manager opens the PR)', rec: true,
                      act: { type: 'ask', text: `@harness Lu agreed (Report → Tokens): add a rule for every agent: ${rule}. Reason: \`${a.what}\` ran ${a.times} times this period, about ${fmtTok(a.tokens)} tokens re-read. Open a PR in harness-core; it's not a design change.` } },
                    { key: 'B', text: `Only for ${a.agents.map(label).join(', ')}`,
                      act: { type: 'ask', text: `@harness Lu agreed (Report → Tokens): add to the role card of ${who}: ${rule}. Reason: \`${a.what}\` ran ${a.times} times this period, about ${fmtTok(a.tokens)} tokens re-read. Open a PR in harness-core.` } },
                    { key: 'C', text: 'Leave it as it is', act: { type: 'none' } }] });
            if (out.length >= 3) break;
        }
        return out.slice(0, 3);
    }
    async function renderProposals(t) {
        const box = document.getElementById('sc-rp-props');
        if (!box) return;
        const list = await proposals(t);
        if (!box.isConnected || !list.length) return;
        // Once you've picked, it's done: the card goes away. It can come back after a week if the
        // numbers still say so.
        const got = picks();
        // picked on another device (the phone, the Mac app) counts too
        try { for (const c of (await api('/api/scranton/report/changes')).changes || []) if (!got[c.id] || got[c.id].at < c.at) got[c.id] = c; } catch (_) { /* local only */ }
        const open = list.filter((p) => { const g = got[p.id]; return !g || (typeof g === 'object' && Date.now() - g.at > 7 * 86400e3); });
        if (!open.length) { box.innerHTML = ''; return; }
        box.innerHTML = `<h3 class="sc-rp-h3">Suggestions: pick one</h3><div class="sc-choices sc-rp-props">${open.map((p) => {
            const picked = null;
            return `<div class="sc-choice-card${picked ? ' done' : ''}" data-prop="${esc(p.id)}">
                <div class="sc-choice-q">${esc(p.title)}</div>
                <p class="sc-rp-why">${esc(p.why)}</p>
                ${p.options.map((o) => `<button type="button" class="sc-choice${picked === o.key ? ' on' : ''}" data-opt="${o.key}"${picked ? ' disabled' : ''}>
                    <span class="sc-choice-key">${o.key}</span><span>${esc(o.text)}${o.rec ? ' <span class="sc-rec">推荐</span>' : ''}</span></button>`).join('')}
            </div>`;
        }).join('')}</div>`;
        box.onclick = async (e) => {
            const card = e.target.closest('[data-prop]');
            if (!card) return;
            const p = list.find((x) => x.id === card.dataset.prop);
            const b = e.target.closest('[data-opt]');
            if (!b || b.disabled) return;
            const o = p.options.find((x) => x.key === b.dataset.opt);
            let ok = true;
            if (o.act.type === 'handover') {
                const r = await api('/api/scranton/handover', { enabled: true, hours: o.act.hours, wakes: o.act.wakes }).catch(() => null);
                ok = !!(r && !r.error);
                if (ok && window.scToast) window.scToast(`Fresh sessions on: every ${o.act.hours} h or ${o.act.wakes} messages`);
            } else if (o.act.type === 'ask') {
                ok = !!(window.ws && window.ws.readyState === WebSocket.OPEN);
                if (ok) {
                    window.ws.send(JSON.stringify({ type: 'message', text: o.act.text, sender: (typeof username === 'string' ? username : 'Lu'), channel: 'general', attachments: [] }));
                    if (window.scToast) window.scToast('Sent to Harness manager in #general');
                }
            }
            if (!ok) { if (window.scToast) window.scToast("Couldn't do that. Is Scranton running?"); return; }
            const a = picks(); a[p.id] = { key: o.key, at: Date.now() }; localStorage.setItem(PROP_KEY, JSON.stringify(a));
            if (o.key !== 'C' && o.act.type !== 'none') api('/api/scranton/report/changes', { items: [{ id: p.id, key: o.key, at: Date.now(), title: TITLES[p.id] || p.title }] }).then(renderTrend).catch(() => {});
            card.classList.add('sc-gone');
            setTimeout(() => renderProposals(t), 260);
        };
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
        if (e.target.closest('#sc-rp-prs-more')) {
            // Lu, 11-09: five is enough at a glance; the rest one click away.
            document.querySelectorAll('#sc-rp-prs .sc-rp-more').forEach((a) => { a.hidden = false; });
            e.target.closest('#sc-rp-prs-more').remove();
            return;
        }
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
