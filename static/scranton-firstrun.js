// Scranton: on first launch, ask once how much agents may do without asking.
// Saved as the team default (a teammate's own setting in Settings → Agents still wins);
// it applies when an agent next starts.
(function () {
    'use strict';
    const H = () => ({ 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN });
    const OPTS = [
        ['ask', 'Ask me first', 'Before running commands or changing files, an agent stops and waits. You answer it from Scranton.'],
        ['full', 'Full access', "Agents run commands and edit or delete files in their project folders without asking. Faster, but nothing stops a mistake before it happens."],
    ];

    async function maybeAsk() {
        let st = null;
        try { const r = await fetch('/api/scranton/team-permissions', { headers: H() }); if (r.ok) st = await r.json(); } catch (_) { return; }
        if (!st || st.asked || document.getElementById('sc-perm-ask')) return;
        let pick = st.permissions;
        const wrap = document.createElement('div');
        wrap.id = 'sc-perm-ask';
        wrap.innerHTML = `<div class="sc-perm-dlg" role="dialog" aria-modal="true" aria-labelledby="sc-perm-h">
            <h2 id="sc-perm-h">How much can your agents do on their own?</h2>
            <p class="sc-perm-sub">This is for the whole team. You can change it later per teammate in Settings → Agents.</p>
            <div class="sc-perm-opts" role="radiogroup">${OPTS.map(([v, t, d]) => `
                <button type="button" role="radio" class="sc-perm-opt" data-v="${v}" aria-checked="${v === pick}">
                    <span class="sc-perm-dot"></span><span><b>${t}</b><small>${d}</small></span></button>`).join('')}</div>
            <div class="sc-perm-foot"><span>Applies when an agent next starts.</span><button type="button" class="sc-btn primary" data-a="save">Continue</button></div>
        </div>`;
        document.body.appendChild(wrap);
        const release = window.scModal ? window.scModal(wrap.querySelector('.sc-perm-dlg')) : null;
        wrap.addEventListener('click', async (e) => {
            const o = e.target.closest('[data-v]');
            if (o) { pick = o.dataset.v; wrap.querySelectorAll('[data-v]').forEach((b) => b.setAttribute('aria-checked', String(b.dataset.v === pick))); return; }
            if (!e.target.closest('[data-a="save"]')) return;
            const r = await fetch('/api/scranton/team-permissions', { method: 'POST', headers: H(), body: JSON.stringify({ permissions: pick }) }).catch(() => null);
            if (!r || !r.ok) { window.scToast && window.scToast("Couldn't save. Is Scranton running?"); return; }
            if (typeof release === 'function') release();
            wrap.remove();
            if (document.getElementById('app')) document.getElementById('app').inert = false;
        });
        wrap.querySelector(`[data-v="${pick}"]`)?.focus();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(maybeAsk, 800));
    else setTimeout(maybeAsk, 800);
})();
