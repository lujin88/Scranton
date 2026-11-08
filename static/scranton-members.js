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

    function start(names, channel, btn) {
        if (!window.ws || window.ws.readyState !== WebSocket.OPEN) return;
        window.ws.send(JSON.stringify({ type: 'start_agents', names, channel }));
        if (btn) {
            btn.dataset.starting = '1';
            btn.innerHTML = '<span class="sc-start-dot on"></span>Starting…';
            setTimeout(() => { delete btn.dataset.starting; renderHead(); }, 20000);
        }
    }

    // ---- header: avatar stack + count ---------------------------------
    function renderHead() {
        const head = document.getElementById('sc-pane-head');
        if (!head) return;
        let btn = document.getElementById('sc-members-btn');
        const ch = current();
        if (isDm(ch)) {
            // DM with someone who isn't running: offer to start them
            const h = ch.slice(3);
            if (team()[h] && state(h) === 'offline') {
                if (!btn) {
                    btn = document.createElement('button');
                    btn.id = 'sc-members-btn';
                    btn.type = 'button';
                    head.appendChild(btn);
                }
                btn.className = 'sc-start-btn';
                btn.onclick = (e) => { e.stopPropagation(); start([h], ch, btn); };
                if (!btn.dataset.starting) btn.innerHTML = `<span class="sc-start-dot"></span>Not running · <b>Start</b>`;
                btn.title = `Start ${label(h)}`;
            } else if (btn) btn.remove();
            return;
        }
        if (btn && btn.classList.contains('sc-start-btn')) { btn.remove(); btn = null; }
        if (!btn) {
            btn = document.createElement('button');
            btn.id = 'sc-members-btn';
            btn.type = 'button';
            head.appendChild(btn);
        }
        btn.onclick = (e) => { e.stopPropagation(); togglePanel(); };
        const list = (members[ch] || []).filter((h) => team()[h]);
        const total = list.length + 1;   // you're in every channel
        const meAv = `<span class="sc-mb-av me">${window.scMyAvatarHtml ? window.scMyAvatarHtml() : ''}</span>`;
        btn.title = `${total} people in #${ch} (you and ${list.length} teammate${list.length === 1 ? '' : 's'}). Add or remove`;
        btn.setAttribute('aria-label', btn.title);
        btn.innerHTML = `<span class="sc-mb-stack">${meAv}${list.slice(0, 3).map((h) => `<span class="sc-mb-av ${esc(state(h))}">${avatar(h)}</span>`).join('')}</span><span class="sc-mb-count">${total}</span>`;
        if (panelOpen()) renderPanel();
    }

    // ---- panel ----------------------------------------------------------
    const panelOpen = () => !!document.getElementById('sc-members-panel');
    function closePanel(apply) {
        const p = document.getElementById('sc-members-panel');
        if (!p) return;
        if (apply) applyDraft();
        p.remove();
        draft = null; order = null; draftCh = null;
    }
    function togglePanel() { panelOpen() ? closePanel(true) : renderPanel(); }

    function stateText(h) {
        const s = state(h);
        return s === 'working' ? 'Working' : s === 'available' ? 'Online' : 'Not running';
    }

    // The panel edits a draft: tick people in or out, then Done applies it once.
    // Order is fixed while it's open (members first, then everyone else), so nothing jumps.
    let draft = null;          // Set of handles that should be in the channel
    let order = null;          // handles in display order, frozen while open
    let draftCh = null;

    function renderPanel() {
        const ch = current();
        const all = Object.keys(team());
        const inCh = (members[ch] || []).filter((h) => team()[h]);
        if (!draft || draftCh !== ch) {
            draft = new Set(inCh);
            draftCh = ch;
            order = [...inCh, ...all.filter((h) => !inCh.includes(h))];
        }
        let p = document.getElementById('sc-members-panel');
        if (!p) {
            p = document.createElement('div');
            p.id = 'sc-members-panel';
            p.setAttribute('role', 'dialog');
            p.setAttribute('aria-label', `Members of #${ch}`);
            p.addEventListener('click', onPanelClick);
            p.addEventListener('change', onPanelChange);
            document.body.appendChild(p);
        }
        const scroll = p.querySelector('.sc-mp-list')?.scrollTop || 0;
        const adds = [...draft].filter((h) => !inCh.includes(h));
        const removes = inCh.filter((h) => !draft.has(h));
        const changes = adds.length + removes.length;
        const offline = inCh.filter((h) => state(h) === 'offline');
        p.innerHTML = `
            <div class="sc-mp-head">
                <div class="sc-mp-title"><b>#${esc(ch)}</b><span>${draft.size + 1} people · ${all.filter((h) => state(h) !== 'offline').length} running</span></div>
                <button type="button" class="sc-mp-link" data-selectall="1">${draft.size === all.length ? 'Clear all' : 'Select all'}</button>
            </div>
            <ul class="sc-mp-list">
                <li><div class="sc-mp-row on me">
                    <span class="sc-mp-check locked" aria-hidden="true">${window.scIcon ? window.scIcon('check', 16) : ''}</span>
                    <span class="sc-mp-av me">${window.scMyAvatarHtml ? window.scMyAvatarHtml() : ''}<span class="team-dot"></span></span>
                    <span class="sc-mp-who"><b>${esc(window.scMe ? window.scMe() : 'You')} <em>you</em></b><small>Always in every channel</small></span>
                </div></li>${order.filter((h) => team()[h]).map((h) => `
                <li><label class="sc-mp-row${draft.has(h) ? ' on' : ''}">
                    <input type="checkbox" value="${esc(h)}"${draft.has(h) ? ' checked' : ''}>
                    <span class="sc-mp-check" aria-hidden="true">${window.scIcon ? window.scIcon('check', 16) : ''}</span>
                    <span class="sc-mp-av ${esc(state(h))}">${avatar(h)}<span class="team-dot"></span></span>
                    <span class="sc-mp-who"><b>${esc(label(h))}</b>${state(h) === 'offline' ? '' : `<small>${esc(stateText(h))}</small>`}</span>
                    ${inCh.includes(h) && draft.has(h) && state(h) === 'offline' ? `<button type="button" class="sc-mp-btn start" data-start="${esc(h)}">Start</button>` : ''}
                </label></li>`).join('')}</ul>
            <div class="sc-mp-foot">
                ${offline.length ? `<button type="button" class="sc-mp-link" data-startall="1">Start ${offline.length} not running</button>` : '<span></span>'}
                <span class="sc-mp-actions">
                    <button type="button" class="sc-mp-btn" data-cancel="1">Cancel</button>
                    <button type="button" class="sc-mp-btn primary" data-done="1"${changes ? '' : ' disabled'}>${changes ? `Done · ${adds.length ? `+${adds.length}` : ''}${adds.length && removes.length ? ' ' : ''}${removes.length ? `−${removes.length}` : ''}` : 'Done'}</button>
                </span>
            </div>
`;
        const list = p.querySelector('.sc-mp-list');
        if (list) list.scrollTop = scroll;
        const btn = document.getElementById('sc-members-btn');
        if (btn) {
            const r = btn.getBoundingClientRect();
            p.style.top = `${r.bottom + 6}px`;
            p.style.right = `${Math.max(8, window.innerWidth - r.right)}px`;
        }
    }

    function applyDraft() {
        const ch = draftCh;
        if (!draft || !ch) return;
        const inCh = (members[ch] || []).filter((h) => team()[h]);
        const add = [...draft].filter((h) => !inCh.includes(h));
        const remove = inCh.filter((h) => !draft.has(h));
        if (add.length || remove.length) send(ch, add, remove);
    }

    function onPanelChange(e) {
        const cb = e.target.closest('input[type="checkbox"]');
        if (!cb) return;
        if (cb.checked) draft.add(cb.value); else draft.delete(cb.value);
        renderPanel();
    }

    function onPanelClick(e) {
        e.stopPropagation();
        const b = e.target.closest('button');
        if (!b) return;
        e.preventDefault();   // buttons inside <label> must not toggle the checkbox
        const ch = current();
        if (b.dataset.selectall) {
            const all = Object.keys(team());
            draft = draft.size === all.length ? new Set() : new Set(all);
            renderPanel();
        }
        if (b.dataset.start) { start([b.dataset.start], ch); b.textContent = 'Starting…'; b.disabled = true; }
        if (b.dataset.startall) { start((members[ch] || []).filter((h) => state(h) === 'offline'), ch); b.textContent = 'Starting…'; b.disabled = true; }
        if (b.dataset.cancel) closePanel(false);
        if (b.dataset.done) closePanel(true);
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

    // "项目经理 is working…" above the composer while a teammate in this channel is busy
    // "项目经理 is working…" sits at the end of the conversation, like a reply on its way.
    function renderWorking() {
        const ch = current();
        const list = document.getElementById('messages');
        if (!list) return;
        const who = isDm(ch) ? [ch.slice(3)] : (members[ch] || []);
        const busy = who.filter((h) => team()[h] && state(h) === 'working');
        const key = busy.join(',');
        let row = document.getElementById('sc-working');
        if (!busy.length) { row?.remove(); return; }
        const atBottom = list.parentElement ? (list.parentElement.scrollHeight - list.parentElement.scrollTop - list.parentElement.clientHeight < 80) : false;
        if (!row) {
            row = document.createElement('div');
            row.id = 'sc-working';
            row.setAttribute('aria-live', 'polite');
        }
        const doing = busy.length === 1 ? ((window.scDoing || {})[busy[0]] || '') : '';
        if (row.dataset.k !== key + '|' + doing) {
            row.dataset.k = key + '|' + doing;
            const text = `${busy.map((h) => label(h)).join('、')} ${busy.length > 1 ? 'are' : 'is'} working` + (doing ? ` · ${doing}` : '');
            row.innerHTML = `<span class="sc-working-av">${busy.slice(0, 3).map((h) => `<span>${avatar(h)}</span>`).join('')}</span>
                <span class="sc-working-bubble"><span class="sc-dots"><i></i><i></i><i></i></span><span>${esc(text)}…</span></span>`;
        }
        if (list.lastElementChild !== row) {
            list.appendChild(row);
            if (atBottom && list.parentElement) list.parentElement.scrollTop = list.parentElement.scrollHeight;
        }
    }

    window.scRenderWorking = () => renderWorking();

    // "项目经理 hasn't answered yet (12 min)": you @'d someone here, they're not working,
    // and nothing came back. Quiet hint with a way to look at their terminal.
    function renderNoReply() {
        const ch = current();
        const list = document.getElementById('messages');
        const msgs = window.scMsgs;
        if (!list || !msgs) return;
        const me = String((window.scMe && window.scMe()) || window.username || '').toLowerCase();
        const mine = [...msgs.values()].filter((m) => (m.channel || 'general') === ch).sort((a, b) => a.id - b.id);
        const waiting = [];
        for (const h of Object.keys(team())) {
            let asked = null;
            for (const m of mine) {
                const who = String(m.sender || '').toLowerCase();
                if (who === me && (isDm(ch) ? ch.slice(3) === h : new RegExp('@' + h + '(?![\\w-])').test(String(m.text || '')))) asked = m;
                else if (asked && (who === h || who.startsWith(h + '-'))) asked = null;
            }
            if (!asked || state(h) === 'working') continue;
            const mins = Math.floor((Date.now() / 1000 - Number(asked.timestamp || 0)) / 60);
            if (mins >= 10 && mins < 24 * 60) waiting.push([h, mins]);
        }
        let row = document.getElementById('sc-noreply');
        if (!waiting.length) { row?.remove(); return; }
        if (!row) { row = document.createElement('div'); row.id = 'sc-noreply'; }
        const key = waiting.map(([h, m]) => h + m).join(',');
        if (row.dataset.k !== key) {
            row.dataset.k = key;
            row.innerHTML = waiting.map(([h, m]) => `<span>${esc(label(h))} hasn't answered yet · ${m < 60 ? m + ' min' : Math.floor(m / 60) + ' h'}`
                + ` <button type="button" data-term="${esc(h)}">${state(h) === 'offline' ? 'Start' : 'Open terminal'}</button></span>`).join('');
            row.onclick = async (e) => {
                const b = e.target.closest('[data-term]');
                if (!b) return;
                const h = b.dataset.term;
                if (state(h) === 'offline') { b.textContent = 'Starting…'; start([h], ch, b); }
                else window.scOpenAgent && window.scOpenAgent(h, 'terminal');
            };
        }
        if (list.lastElementChild !== row && list.lastElementChild?.id !== 'sc-working') list.appendChild(row);
    }
    setInterval(renderNoReply, 15000);
    setTimeout(renderNoReply, 3000);

    // ---- wiring --------------------------------------------------------------
    if (typeof handleServerEvent === 'function') {
        const orig = handleServerEvent;
        handleServerEvent = function (event) {
            const r = orig.apply(this, arguments);
            if (event && event.type === 'settings' && event.data && event.data.channel_members) {
                members = event.data.channel_members || {};
                renderHead();
                if (typeof buildMentionToggles === 'function') buildMentionToggles();
            }
            return r;
        };
    }
    window.scChannelMembers = () => members;

    function init() {
        // Decide on mousedown (the clicked node still exists then); clicking outside keeps your picks.
        document.addEventListener('mousedown', (e) => {
            const p = document.getElementById('sc-members-panel');
            if (p && !p.contains(e.target) && !e.target.closest('#sc-members-btn')) closePanel(true);
        });
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'Escape' || !document.getElementById('sc-members-panel')) return;
            closePanel(false);
            document.getElementById('sc-members-btn')?.focus();   // back to where you were
        });
        window.addEventListener('resize', () => closePanel(true));
        (window.scOnTeamChange || []).push(renderHead, makeDraggable, () => { if (typeof buildMentionToggles === 'function') buildMentionToggles(); });
        // channel switches and DM list re-renders
        const obs = new MutationObserver(() => { makeDraggable(); });
        const dm = document.getElementById('sc-dm-list');
        if (dm) obs.observe(dm, { childList: true });
        const title = document.getElementById('sc-pane-title');
        if (title) new MutationObserver(() => { closePanel(true); renderHead(); if (typeof buildMentionToggles === 'function') buildMentionToggles(); }).observe(title, { childList: true, characterData: true, subtree: true });
        setInterval(renderHead, 5000);   // status dots
        setInterval(renderWorking, 1500);
        const msgs = document.getElementById('messages');
        if (msgs) new MutationObserver(() => { const r = document.getElementById('sc-working'); if (r && msgs.lastElementChild !== r) msgs.appendChild(r); }).observe(msgs, { childList: true });
        renderHead(); makeDraggable();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
