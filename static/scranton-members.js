// Scranton: channel members. Header shows who's in the channel; click to add/remove.
// Drag a teammate from Direct messages onto a channel (sidebar row or the open channel) to add them.
// Added teammates who aren't running are started by the server.
(function () {
    const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const MIME = 'application/x-scranton-teammate';
    let members = {};   // channel -> [handle]

    const team = () => (window.scGetTeam ? window.scGetTeam() : {}) || {};
    const label = (h) => (window.scLabelOf ? window.scLabelOf(h) : h);
    const avatar = (h) => (window.scAvatarHtml ? window.scAvatarHtml(h) : '');
    const state = (h) => (window.scAgentState ? window.scAgentState(h) : 'offline');
    const isDm = (ch) => String(ch || '').startsWith('dm-');
    const current = () => window.activeChannel || 'general';

    function send(channel, add, remove) {
        if (!window.ws || window.ws.readyState !== WebSocket.OPEN) return false;
        window.ws.send(JSON.stringify({ type: 'members_update', channel, add: add || [], remove: remove || [] }));
        return true;
    }

    // ---- header: avatar stack + count ---------------------------------
    function renderHead() {
        const head = document.getElementById('sc-pane-head');
        if (!head) return;
        let btn = document.getElementById('sc-members-btn');
        const ch = current();
        if (isDm(ch)) { if (btn) btn.remove(); return; }
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'sc-members-btn';
            btn.type = 'button';
            btn.addEventListener('click', (e) => { e.stopPropagation(); togglePanel(); });
            head.appendChild(btn);
        }
        const list = (members[ch] || []).filter((h) => team()[h]);
        btn.title = list.length ? `${list.length} teammates in #${ch}. Add or remove` : `Add teammates to #${ch}`;
        btn.setAttribute('aria-label', btn.title);
        btn.innerHTML = list.length
            ? `<span class="sc-mb-stack">${list.slice(0, 4).map((h) => `<span class="sc-mb-av ${esc(state(h))}">${avatar(h)}</span>`).join('')}</span><span class="sc-mb-count">${list.length}</span>`
            : `<span class="sc-mb-add">+ Add teammates</span>`;
        if (panelOpen()) renderPanel();
    }

    // ---- panel ----------------------------------------------------------
    const panelOpen = () => !!document.getElementById('sc-members-panel');
    function closePanel() { document.getElementById('sc-members-panel')?.remove(); }
    function togglePanel() { panelOpen() ? closePanel() : renderPanel(); }

    function stateText(h) {
        const s = state(h);
        return s === 'working' ? 'Working' : s === 'available' ? 'Online' : 'Not running';
    }

    function renderPanel() {
        const ch = current();
        const all = Object.keys(team());
        const inCh = (members[ch] || []).filter((h) => team()[h]);
        const others = all.filter((h) => !inCh.includes(h));
        let p = document.getElementById('sc-members-panel');
        if (!p) {
            p = document.createElement('div');
            p.id = 'sc-members-panel';
            p.setAttribute('role', 'dialog');
            p.addEventListener('click', onPanelClick);
            document.body.appendChild(p);
        }
        const row = (h, inside) => `<li class="sc-mp-row">
                <span class="sc-mp-av ${esc(state(h))}">${avatar(h)}<span class="team-dot"></span></span>
                <span class="sc-mp-who"><b>${esc(label(h))}</b><small>${esc(stateText(h))}</small></span>
                ${inside
                    ? `<button type="button" class="sc-mp-btn" data-remove="${esc(h)}" aria-label="Remove ${esc(label(h))} from #${esc(ch)}">Remove</button>`
                    : `<button type="button" class="sc-mp-btn add" data-add="${esc(h)}" aria-label="Add ${esc(label(h))} to #${esc(ch)}">Add</button>`}
            </li>`;
        p.innerHTML = `
            <div class="sc-mp-head"><b>#${esc(ch)}</b><span>${inCh.length} teammate${inCh.length === 1 ? '' : 's'}</span>
                ${others.length ? `<button type="button" class="sc-mp-all" data-addall="1">Add everyone</button>` : ''}</div>
            <ul class="sc-mp-list">${inCh.map((h) => row(h, true)).join('') || '<li class="sc-mp-empty">Nobody yet. Add teammates below, or drag them here from Direct messages.</li>'}</ul>
            ${others.length ? `<div class="sc-mp-sub">Add to this channel</div><ul class="sc-mp-list">${others.map((h) => row(h, false)).join('')}</ul>` : ''}
            <p class="sc-mp-note">Added teammates start automatically. @-mentioning someone here also adds them.</p>`;
        const btn = document.getElementById('sc-members-btn');
        if (btn) {
            const r = btn.getBoundingClientRect();
            p.style.top = `${r.bottom + 6}px`;
            p.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
        }
    }

    function onPanelClick(e) {
        e.stopPropagation();
        const ch = current();
        const b = e.target.closest('button');
        if (!b) return;
        if (b.dataset.add) send(ch, [b.dataset.add]);
        if (b.dataset.remove) send(ch, [], [b.dataset.remove]);
        if (b.dataset.addall) send(ch, Object.keys(team()).filter((h) => !(members[ch] || []).includes(h)));
    }

    // ---- drag & drop: teammate → channel ---------------------------------
    function makeDraggable() {
        document.querySelectorAll('#sc-dm-list .sc-dm-row').forEach((row) => {
            if (row.dataset.scDrag) return;
            const h = (row.title.match(/@([\w-]+)/) || [])[1];
            if (!h) return;
            row.dataset.scDrag = '1';
            row.dataset.handle = h;
            row.draggable = true;
            row.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData(MIME, h);
                e.dataTransfer.setData('text/plain', `@${h}`);
                e.dataTransfer.effectAllowed = 'copy';
                document.body.classList.add('sc-dragging-teammate');
            });
            row.addEventListener('dragend', () => {
                document.body.classList.remove('sc-dragging-teammate');
                document.querySelectorAll('.sc-drop-over').forEach((el) => el.classList.remove('sc-drop-over'));
            });
        });
    }

    function dropTarget(e) {
        const row = e.target.closest && e.target.closest('.channel-sidebar-row[data-channel]');
        if (row) return { el: row, ch: row.dataset.channel };
        const pane = e.target.closest && e.target.closest('#sc-center');
        if (pane && !isDm(current())) return { el: pane, ch: current() };
        return null;
    }
    const isTeammateDrag = (e) => Array.from(e.dataTransfer?.types || []).includes(MIME);

    document.addEventListener('dragover', (e) => {
        if (!isTeammateDrag(e)) return;
        const t = dropTarget(e);
        document.querySelectorAll('.sc-drop-over').forEach((el) => { if (!t || el !== t.el) el.classList.remove('sc-drop-over'); });
        if (!t || isDm(t.ch)) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        t.el.classList.add('sc-drop-over');
    }, true);

    document.addEventListener('drop', (e) => {
        if (!isTeammateDrag(e)) return;
        e.preventDefault();
        e.stopPropagation();   // not a file upload
        document.body.classList.remove('sc-dragging-teammate');
        document.querySelectorAll('.sc-drop-over').forEach((el) => el.classList.remove('sc-drop-over'));
        const t = dropTarget(e);
        const h = e.dataTransfer.getData(MIME);
        if (t && h && !isDm(t.ch)) send(t.ch, [h]);
    }, true);

    // ---- wiring --------------------------------------------------------------
    if (typeof handleServerEvent === 'function') {
        const orig = handleServerEvent;
        handleServerEvent = function (event) {
            const r = orig.apply(this, arguments);
            if (event && event.type === 'settings' && event.data && event.data.channel_members) {
                members = event.data.channel_members || {};
                renderHead();
            }
            return r;
        };
    }
    window.scChannelMembers = () => members;

    function init() {
        document.addEventListener('click', (e) => { if (panelOpen() && !e.target.closest('#sc-members-panel')) closePanel(); });
        document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePanel(); });
        window.addEventListener('resize', closePanel);
        (window.scOnTeamChange || []).push(renderHead, makeDraggable);
        // channel switches and DM list re-renders
        const obs = new MutationObserver(() => { makeDraggable(); });
        const dm = document.getElementById('sc-dm-list');
        if (dm) obs.observe(dm, { childList: true });
        const title = document.getElementById('sc-pane-title');
        if (title) new MutationObserver(() => { closePanel(); renderHead(); }).observe(title, { childList: true, characterData: true, subtree: true });
        setInterval(renderHead, 5000);   // status dots
        renderHead(); makeDraggable();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
