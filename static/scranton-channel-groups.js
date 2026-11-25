// Scranton: her own groups of channels in the sidebar (Lu, 11-25). A group is a heading she named
// with channels under it; it folds. Moving a channel changes only where it sits in the sidebar.
// Put a channel in a group: the folder button on its row, or drag it onto a heading or onto a
// channel already in the group. Out again: the same menu, "No group", or drag it back up.
(function () {
    'use strict';
    const MIME = 'application/x-scranton-channel';
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const ic = (n, s) => (window.scIcon ? window.scIcon(n, s) : '');
    const groups = () => (Array.isArray(window.scChannelGroups) ? window.scChannelGroups : []);
    const redraw = () => { if (window.renderChannelSidebar) window.renderChannelSidebar(); else if (typeof renderChannelSidebar === 'function') renderChannelSidebar(); };

    async function send(body) {
        try {
            const r = await fetch('/api/scranton/channel-groups', {
                method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN || '' }, body: JSON.stringify(body) });
            const d = await r.json();
            if (Array.isArray(d.groups)) { window.scChannelGroups = d.groups; redraw(); }
            return d;
        } catch (e) { return { ok: false, error: 'Could not reach Scranton.' }; }
    }

    function head(g, unread) {
        const el = document.createElement('div');
        el.className = 'sc-group-head' + (g.collapsed ? ' collapsed' : '');
        el.dataset.group = String(g.id);
        el.innerHTML = `<button type="button" class="sc-group-toggle" aria-expanded="${!g.collapsed}">${ic('chevron-down', 16)}<span class="sc-group-name">${esc(g.name)}</span>${
            g.collapsed ? `<span class="sc-group-n">${g.channels.length}</span>` : ''}${g.collapsed && unread ? '<span class="sc-group-dot" aria-label="Unread inside"></span>' : ''}</button>
            <span class="sc-group-actions"><button type="button" data-g="rename" title="Rename group" aria-label="Rename group">${ic('edit', 16)}</button><button type="button" data-g="delete" title="Remove this group. Its channels stay." aria-label="Remove group">${ic('delete', 16)}</button></span>`;
        el.querySelector('.sc-group-toggle').onclick = () => send({ action: 'collapse', id: g.id, on: !g.collapsed });
        el.querySelector('[data-g="delete"]').onclick = () => send({ action: 'delete', id: g.id });
        el.querySelector('[data-g="rename"]').onclick = () => rename(el, g);
        return el;
    }

    function rename(el, g) {
        const span = el.querySelector('.sc-group-name');
        if (!span || el.querySelector('input')) return;
        const inp = document.createElement('input');
        inp.className = 'sc-group-input'; inp.value = g.name; inp.maxLength = 32; inp.setAttribute('aria-label', 'Group name');
        span.replaceWith(inp); inp.focus(); inp.select();
        let done = false;
        const finish = async (save) => {
            if (done) return; done = true;
            const v = inp.value.trim();
            if (save && v && v !== g.name) { const d = await send({ action: 'rename', id: g.id, name: v }); if (!d.ok) redraw(); } else redraw();
        };
        inp.onclick = (e) => e.stopPropagation();
        inp.onkeydown = (e) => { e.stopPropagation(); if (e.key === 'Enter') finish(true); if (e.key === 'Escape') finish(false); };
        inp.onblur = () => finish(true);
    }

    // What the sidebar draws, in order: ungrouped channels, then each group's heading and channels.
    window.scChannelPlan = function (list) {
        const all = Array.isArray(list) ? list : [];
        const where = {};
        groups().forEach((g) => (g.channels || []).forEach((c) => { where[c] = g.id; }));
        const out = all.filter((c) => !where[c]).map((c) => ({ ch: c }));
        const unread = window.channelUnread || {};
        groups().forEach((g) => {
            const mine = all.filter((c) => where[c] === g.id);
            out.push({ head: head(g, mine.some((c) => unread[c] > 0 && c !== window.activeChannel)) });
            mine.forEach((c) => { if (!g.collapsed || c === window.activeChannel) out.push({ ch: c, group: g.id }); });
        });
        return out;
    };

    function closeMenu() { document.getElementById('sc-group-menu')?.remove(); }
    window.scGroupMenu = function (channel, anchor) {
        if (document.getElementById('sc-group-menu')) { closeMenu(); return; }
        const cur = (groups().find((g) => (g.channels || []).includes(channel)) || {}).id || 0;
        const m = document.createElement('div');
        m.id = 'sc-group-menu'; m.className = 'sc-pop sc-group-menu'; m.setAttribute('role', 'menu');
        m.innerHTML = `<div class="sc-group-menu-title">Move #${esc(channel)} to</div>`
            + groups().map((g) => `<button type="button" role="menuitem" data-id="${g.id}"${g.id === cur ? ' class="on"' : ''}>${ic('folder', 16)}<span>${esc(g.name)}</span>${g.id === cur ? ic('check', 16) : ''}</button>`).join('')
            + (cur ? `<button type="button" role="menuitem" data-id="0">${ic('subtract', 16)}<span>No group</span></button>` : '')
            + `<form class="sc-group-new"><input type="text" maxlength="32" placeholder="New group name" aria-label="New group name"><button type="submit" class="sc-btn sm primary">Create</button></form><div class="sc-group-err" role="alert"></div>`;
        document.body.appendChild(m);
        const r = anchor.getBoundingClientRect();
        m.style.left = Math.max(8, Math.min(r.left, window.innerWidth - m.offsetWidth - 8)) + 'px';
        m.style.top = Math.max(8, Math.min(r.bottom + 4, window.innerHeight - m.offsetHeight - 8)) + 'px';
        m.querySelectorAll('button[data-id]').forEach((b) => { b.onclick = async () => { await send({ action: 'move', channel, id: Number(b.dataset.id) }); closeMenu(); }; });
        const form = m.querySelector('form'); const inp = form.querySelector('input');
        form.onsubmit = async (e) => {
            e.preventDefault();
            const v = inp.value.trim(); if (!v) { inp.focus(); return; }
            const d = await send({ action: 'create', name: v, channel });
            if (d.ok) closeMenu(); else m.querySelector('.sc-group-err').textContent = d.error || 'Could not create it.';
        };
        if (!groups().length) inp.focus();
    };
    document.addEventListener('mousedown', (e) => { const m = document.getElementById('sc-group-menu'); if (m && !m.contains(e.target) && !e.target.closest('[title="Move to a group"]')) closeMenu(); }, true);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeMenu(); });

    // Dragging: onto a heading puts the channel in that group; onto a row takes that row's group
    // (none for an ungrouped row). The order itself is handled by scranton-channel-order.js.
    const groupOf = (name) => (groups().find((g) => (g.channels || []).includes(name)) || {}).id || 0;
    document.addEventListener('dragover', (e) => {
        if (!Array.from(e.dataTransfer?.types || []).includes(MIME)) return;
        const h = e.target.closest && e.target.closest('.sc-group-head');
        document.querySelectorAll('.sc-group-head.sc-drop').forEach((x) => x.classList.remove('sc-drop'));
        if (h) { e.preventDefault(); h.classList.add('sc-drop'); }
    }, true);
    document.addEventListener('drop', (e) => {
        if (!Array.from(e.dataTransfer?.types || []).includes(MIME)) return;
        const name = e.dataTransfer.getData(MIME);
        document.querySelectorAll('.sc-group-head.sc-drop').forEach((x) => x.classList.remove('sc-drop'));
        if (!name) return;
        const h = e.target.closest && e.target.closest('.sc-group-head');
        const row = e.target.closest && e.target.closest('#channel-sidebar-list .channel-sidebar-row');
        if (!h && !row) return;
        const to = h ? Number(h.dataset.group) : Number(row.dataset.group || 0);
        if (h) e.preventDefault();
        if (to !== groupOf(name)) send({ action: 'move', channel: name, id: to });
    }, true);
    document.addEventListener('dragend', () => document.querySelectorAll('.sc-group-head.sc-drop').forEach((x) => x.classList.remove('sc-drop')), true);
})();
