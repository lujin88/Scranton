// Scranton banners: "update available" and "teammates stopped — resume?"
(function () {
    const esc = (v) => String(v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const LS = {
        get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch (_) { return d; } },
        set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
    };
    const api = (path, body) => fetch(path, {
        method: body ? 'POST' : 'GET',
        headers: { 'X-Session-Token': window.SESSION_TOKEN, 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
    }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
    const labelOf = (n) => (window.scLabelOf ? window.scLabelOf(n) : n);

    function bar() {
        let el = document.getElementById('sc-banners');
        if (!el) {
            el = document.createElement('div');
            el.id = 'sc-banners';
            document.body.appendChild(el);
        }
        return el;
    }

    function banner(id, html, kind) {
        let b = document.getElementById(id);
        if (!b) {
            b = document.createElement('div');
            b.id = id;
            b.className = `sc-card ${kind || ''}`;
            bar().appendChild(b);
        }
        b.innerHTML = html;
        return b;
    }
    const drop = (id) => document.getElementById(id)?.remove();

    // --- update ---------------------------------------------------------
    function showFailed(msg) {
        if (!msg) { drop('sc-update-failed'); return; }
        const b = banner('sc-update-failed',
            `<button type="button" class="sc-card-x" data-a="ok" aria-label="Close">✕</button>`
            + `<div class="sc-card-title">Update didn't work</div><div class="sc-card-sub">${esc(msg)}</div>`, 'warn');
        b.onclick = async (e) => {
            if (e.target.closest('[data-a]')) { try { await api('/api/scranton/update/failed/dismiss', {}); } catch (_) {} drop('sc-update-failed'); }
        };
    }

    function showUpdate(u) {
        showFailed(u && u.failed);
        if (!u || !u.behind) { drop('sc-update'); return; }
        const key = `${u.behind}:${u.subject}`;
        if (LS.get('scranton-update-later', '') === key) return;
        const b = banner('sc-update',
            `<button type="button" class="sc-card-x" data-a="later" aria-label="Later">✕</button>`
            + `<div class="sc-card-title">Ready to update!</div>`
            + `<div class="sc-card-sub">${u.behind} change${u.behind > 1 ? 's' : ''}${u.subject ? ' · ' + esc(u.subject) : ''}</div>`
            + `<button type="button" class="sc-card-btn" data-a="update">Update now</button>`, 'info');
        b.onclick = async (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (a === 'later') { LS.set('scranton-update-later', key); drop('sc-update'); }
            if (a === 'update') {
                b.innerHTML = '<div class="sc-card-title">Updating…</div><div class="sc-card-sub">Your teammates keep working. This page reloads when Scranton is back.</div>';
                try {
                    const r = await api('/api/scranton/update/apply', {});
                    if (!r.ok) {
                        b.innerHTML = `<button type="button" class="sc-card-x" data-a="later" aria-label="Close">✕</button><div class="sc-card-title">Update didn't run</div><div class="sc-card-sub">${esc(r.error || 'unknown error')}</div>`;
                        return;
                    }
                    waitAndReload();
                } catch (_) { waitAndReload(); }
            }
        };
    }

    function waitAndReload() {
        let tries = 0;
        const t0 = Date.now();
        const tick = setInterval(async () => {
            tries++;
            if (Date.now() - t0 < 6000) return;   // give the old server time to go down
            try {
                await fetch('/', { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error(); });
                clearInterval(tick);
                location.reload();
            } catch (_) {
                if (tries > 120) {
                    clearInterval(tick);
                    banner('sc-update', '<div class="sc-card-title">Scranton isn\'t back yet</div><div class="sc-card-sub">On the Mac, open the Scranton app (or run ./scranton.sh start).</div>', 'warn');
                }
            }
        }, 1000);
    }

    // --- resume -----------------------------------------------------------
    function showStopped(names) {
        if (!names || !names.length) { drop('sc-resume'); return; }
        const list = names.map((n) => `<b>${esc(labelOf(n))}</b>`).join(', ');
        const b = banner('sc-resume',
            `<button type="button" class="sc-card-x" data-a="dismiss" aria-label="Not now">✕</button>`
            + `<div class="sc-card-title">${names.length > 1 ? 'Teammates stopped' : 'A teammate stopped'}</div>`
            + `<div class="sc-card-sub">${list}</div>`
            + `<button type="button" class="sc-card-btn" data-a="resume">Resume ${names.length > 1 ? 'all' : ''}</button>`, 'warn');
        b.onclick = async (e) => {
            const a = e.target.closest('[data-a]')?.dataset.a;
            if (!a) return;
            try {
                if (a === 'resume') {
                    await api('/api/scranton/resume', { names });
                    b.innerHTML = '<div class="sc-card-title">Starting…</div><div class="sc-card-sub">They show as Available in a few seconds.</div>';
                    setTimeout(() => drop('sc-resume'), 6000);
                } else {
                    await api('/api/scranton/resume/dismiss', { names });
                    drop('sc-resume');
                }
            } catch (_) {
                const sub = b.querySelector('.sc-card-sub'); if (sub) sub.textContent = 'Couldn\'t reach Scranton. Is it running?';
            }
        };
    }

    async function poll() {
        try {
            const s = await api('/api/scranton/status');
            showUpdate(s.update);
            showStopped(s.stopped);
        } catch (_) { /* server restarting */ }
    }

    window.scCheckUpdate = async function () {
        try {
            const u = await api('/api/scranton/update/check', {});
            LS.set('scranton-update-later', '');   // asked by hand: show it even if dismissed before
            showUpdate(u);
            if (u.error) note(`Couldn't check: ${u.error}`);
            else if (!u.behind) note('Scranton is up to date.');
        } catch (_) { note('Couldn\'t reach Scranton.'); }
    };
    function note(text) {
        const b = banner('sc-update-note', `<div class="sc-card-sub">${esc(text)}</div>`, 'info');
        setTimeout(() => drop('sc-update-note'), 4000);
        return b;
    }

    function init() {
        poll();
        setInterval(poll, 60 * 1000);
        // after a reconnect (Mac woke up, server restarted) check right away
        document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
