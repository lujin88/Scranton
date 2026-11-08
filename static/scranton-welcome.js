// Scranton: first-time welcome. A short checklist that ticks itself off from what has
// really happened (apps connected, profile set, first task given), shown in place of the
// conversation until it's done or hidden. "Get started" in the sidebar brings it back.
(function () {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const ic = (n, s) => (window.scIcon ? window.scIcon(n, s || 18) : '');
    const LS = {
        get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (_) { return d; } },
        set: (k, v) => { try { localStorage.setItem(k, v); } catch (_) { /* private mode */ } },
    };
    const team = () => (window.scGetTeam ? window.scGetTeam() : {}) || {};
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    const PM = 'pm';
    // The first project channel in the sidebar (not #general), else general.
    const projectChannel = () => {
        const names = Array.from(document.querySelectorAll('#channel-list [data-channel], .channel-sidebar-row[data-channel]'))
            .map((el) => el.dataset.channel).filter((n) => n && n !== 'general' && !n.startsWith('dm-'));
        return names[0] || 'general';
    };

    let connected = null;   // null = not checked yet
    async function checkConnections() {
        try {
            const r = await fetch('/api/scranton/connections', { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            const list = await r.json();
            connected = Array.isArray(list) && list.some((c) => c.connected === true);
        } catch (_) { connected = false; }
    }

    function steps() {
        const hasPic = (LS.get('scranton-me-avatar', '') || '').startsWith('data:image/');
        const myName = String((window.scMe && window.scMe()) || '');
        const pmHandle = team()[PM] ? PM : Object.keys(team())[0];
        // Ticked from what really happened, so it's the same on the phone as on the Mac.
        const pmAnswered = !!pmHandle && Array.from((window.scMsgs && window.scMsgs.values()) || [])
            .some((m) => m && m.channel === `dm-${pmHandle}` && String(m.sender || '').split('-')[0] === pmHandle);
        const pm = team()[PM] ? PM : Object.keys(team())[0];
        return [
            { id: 'apps', icon: 'plug', title: 'Connect your apps', text: 'Claude, ChatGPT or Cursor. Your plans, no API keys.',
                done: connected === true, go: () => window.scOpenSettings && window.scOpenSettings('connections') },
            { id: 'me', icon: 'user-smile', title: 'Add your name and photo', text: 'So your agents know who they work for.',
                done: hasPic || (myName && !/^(user|you)$/i.test(myName)), go: () => { window.scOpenSettings && window.scOpenSettings('profile'); } },
            { id: 'meet', icon: 'chat-smile', title: `Say hi to ${esc(pm ? label(pm) : 'your project manager')}`, text: 'Your project manager plans the work and hands it to the team.',
                done: pmAnswered, go: () => { close(); pm && window.scOpenDm && window.scOpenDm(pm); } },
            { id: 'task', icon: 'task', title: 'Give the first task', text: `In #${projectChannel()}, @ someone and say what you need.`,
                done: LS.get('scranton-welcome-task', '') === '1', go: () => {
                    close();
                    if (typeof switchChannel === 'function') switchChannel(projectChannel());
                    setTimeout(() => {
                        const input = document.getElementById('input');
                        if (input && pm) { input.value = `@${label(pm)} `; input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
                    }, 200);
                } },
            { id: 'phone', icon: 'phone', title: 'Open it on your phone', text: 'Through Tailscale, only from your own devices.',
                done: LS.get('scranton-welcome-phone', '') === '1', go: () => { LS.set('scranton-welcome-phone', '1'); window.open('https://github.com/lujin88/Scranton#phone-access-with-tailscale', '_blank', 'noopener'); render(); } },
        ];
    }

    function section() {
        let s = document.getElementById('sc-welcome');
        if (!s) {
            s = document.createElement('section');
            s.id = 'sc-welcome';
            s.className = 'hidden';
            s.setAttribute('aria-label', 'Get started');
            document.getElementById('sc-center')?.appendChild(s);
            s.addEventListener('click', onClick);
        }
        return s;
    }

    function render() {
        const list = steps();
        const done = list.filter((x) => x.done).length;
        renderSideRow(done, list.length);
        const s = section();
        if (s.classList.contains('hidden')) return;
        s.innerHTML = `
            <div class="sc-wl">
                <img class="sc-wl-logo" src="/static/scranton-icon.png" alt="">
                <h1>Welcome to Scranton</h1>
                <p class="sc-wl-sub">Your company of one. You decide; your agents plan, build, check and report back here.</p>
                <div class="sc-wl-list">
                    ${list.map((x) => `<button type="button" class="sc-wl-step${x.done ? ' done' : ''}" data-step="${x.id}">
                        <span class="sc-wl-ic">${ic(x.icon, 20)}</span>
                        <span class="sc-wl-t"><b>${x.title}</b><small>${x.text}</small></span>
                        <span class="sc-wl-state">${x.done ? ic('check-fill', 20) : ic('right', 18)}</span>
                    </button>`).join('')}
                </div>
                <p class="sc-wl-rule">Agents can change anything in their project folders. The real stop is on GitHub: protect <code>main</code> so design PRs need your approval.</p>
                <div class="sc-wl-also">${(window.scMoreTools || []).map((t) => t.url
                    ? `<a href="${esc(t.url)}" target="_blank" rel="noopener">${ic(t.icon, 16)}<span><b>${esc(t.name)}</b> · ${esc(t.what)}</span></a>`
                    : `<span class="soon">${ic(t.icon, 16)}<span><b>${esc(t.name)}</b> · ${esc(t.what)} · soon</span></span>`).join('')}</div>
                <div class="sc-wl-foot"><span>${done} of ${list.length} done</span><button type="button" class="sc-wl-hide" data-a="hide">${done === list.length ? 'Done' : 'Hide'}</button></div>
            </div>`;
    }

    function renderSideRow(done, total) {
        let row = document.getElementById('sc-start-row');
        // "Hide" only stops it opening by itself; the sidebar row stays until every step is done.
        if (done >= total) { row?.remove(); return; }
        if (!row) {
            row = document.createElement('button');
            row.id = 'sc-start-row';
            row.type = 'button';
            row.className = 'sc-side-row';
            row.onclick = () => open();
            document.getElementById('sc-inbox-row')?.after(row);
        }
        row.innerHTML = `${ic('rocket', 18)}<span class="sc-side-label">Get started</span><span class="sc-start-count">${done}/${total}</span>`;
    }

    function open() {
        if (window.scCloseInbox) window.scCloseInbox();
        document.getElementById('sc-report')?.classList.add('hidden');
        document.body.classList.remove('sc-report-open');
        section().classList.remove('hidden');
        document.body.classList.add('sc-welcome-open');
        const f = document.querySelector('#app > footer, footer'); if (f) f.inert = true;   // the composer is behind it
        checkConnections().then(render);
        render();
    }
    function close() {
        section().classList.add('hidden');
        document.body.classList.remove('sc-welcome-open');
        const f = document.querySelector('#app > footer, footer'); if (f) f.inert = false;
    }
    window.scOpenWelcome = open;

    function onClick(e) {
        const step = e.target.closest('[data-step]');
        if (step) { const x = steps().find((s) => s.id === step.dataset.step); if (x) x.go(); return; }
        if (e.target.closest('[data-a="hide"]')) {
            const all = steps().every((x) => x.done);
            if (!all) LS.set('scranton-welcome-hidden', '1');
            close(); render();
        }
    }

    // "Give the first task" ticks itself when you send a message that @s someone
    if (typeof sendMessage === 'function') {
        const orig = sendMessage;
        sendMessage = function () {
            const v = document.getElementById('input')?.value || '';
            if (/@\S/.test(v)) { LS.set('scranton-welcome-task', '1'); setTimeout(render, 50); }
            return orig.apply(this, arguments);
        };
    }

    async function init() {
        section();
        await checkConnections();
        const list = steps();
        const allDone = list.every((x) => x.done);
        if (!allDone && LS.get('scranton-welcome-hidden', '') !== '1' && LS.get('scranton-welcome-seen', '') !== '1') {
            LS.set('scranton-welcome-seen', '1');   // opens by itself once; after that from "Get started"
            open();
        } else {
            render();
        }
        // channel switches close it
        const title = document.getElementById('sc-pane-title');
        if (title) new MutationObserver(() => close()).observe(title, { childList: true, characterData: true, subtree: true });
        (window.scOnTeamChange || []).push(render);
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && document.body.classList.contains('sc-welcome-open') && !window.scEscTaken) close(); });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 300));
    else setTimeout(init, 300);
})();
