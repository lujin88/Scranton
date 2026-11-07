// Scranton: reorder channels by dragging them, or select one and press Alt+↑ / Alt+↓.
// Delete or Backspace on a selected channel asks to delete it (general can't be deleted).
(function () {
    const MIME = 'application/x-scranton-channel';
    const list = () => document.getElementById('channel-sidebar-list');
    const rows = () => Array.from(list()?.querySelectorAll('.channel-sidebar-row[data-channel]') || []);
    const names = () => rows().map((r) => r.dataset.channel);

    function sendOrder(order) {
        if (!window.ws || window.ws.readyState !== WebSocket.OPEN) return;
        window.ws.send(JSON.stringify({ type: 'channel_reorder', order }));
    }
    function move(name, delta) {
        const order = names();
        const i = order.indexOf(name);
        const j = i + delta;
        if (i < 0 || j < 0 || j >= order.length) return;
        [order[i], order[j]] = [order[j], order[i]];
        sendOrder(order);
        // keep focus on the moved channel after the list re-renders
        setTimeout(() => list()?.querySelector(`.channel-sidebar-row[data-channel="${CSS.escape(name)}"]`)?.focus(), 120);
    }

    function wire() {
        rows().forEach((row) => {
            if (row.dataset.scOrder) return;
            row.dataset.scOrder = '1';
            row.draggable = true;
            row.title = `#${row.dataset.channel}. Drag to reorder; Alt+↑/↓ to move; Delete to remove`;
            row.addEventListener('dragstart', (e) => {
                e.dataTransfer.setData(MIME, row.dataset.channel);
                e.dataTransfer.effectAllowed = 'move';
                row.classList.add('sc-dragging');
            });
            row.addEventListener('dragend', () => {
                row.classList.remove('sc-dragging');
                rows().forEach((r) => r.classList.remove('sc-drop-before', 'sc-drop-after'));
            });
        });
    }

    document.addEventListener('dragover', (e) => {
        if (!Array.from(e.dataTransfer?.types || []).includes(MIME)) return;
        const row = e.target.closest && e.target.closest('#channel-sidebar-list .channel-sidebar-row');
        rows().forEach((r) => r.classList.remove('sc-drop-before', 'sc-drop-after'));
        if (!row) return;
        e.preventDefault();
        const r = row.getBoundingClientRect();
        row.classList.add(e.clientY < r.top + r.height / 2 ? 'sc-drop-before' : 'sc-drop-after');
    }, true);

    document.addEventListener('drop', (e) => {
        if (!Array.from(e.dataTransfer?.types || []).includes(MIME)) return;
        e.preventDefault(); e.stopPropagation();
        const name = e.dataTransfer.getData(MIME);
        const row = e.target.closest && e.target.closest('#channel-sidebar-list .channel-sidebar-row');
        rows().forEach((r) => r.classList.remove('sc-drop-before', 'sc-drop-after'));
        if (!row || !name || row.dataset.channel === name) return;
        const before = e.clientY < row.getBoundingClientRect().top + row.getBoundingClientRect().height / 2;
        const order = names().filter((n) => n !== name);
        let at = order.indexOf(row.dataset.channel) + (before ? 0 : 1);
        order.splice(at, 0, name);
        sendOrder(order);
    }, true);

    document.addEventListener('keydown', (e) => {
        const row = document.activeElement && document.activeElement.closest && document.activeElement.closest('#channel-sidebar-list .channel-sidebar-row');
        if (!row || e.target.closest('input, textarea')) return;
        const name = row.dataset.channel;
        if (row.classList.contains('confirm-delete')) {
            // "delete #x?" is showing: Enter confirms, Esc cancels
            const bar = Array.from(row.querySelectorAll('.channel-sidebar-row-actions')).pop();
            const [yes, no] = bar ? bar.querySelectorAll('button') : [];
            if (e.key === 'Enter' && yes) { e.preventDefault(); yes.click(); }
            if (e.key === 'Escape' && no) { e.preventDefault(); no.click(); row.focus(); }
            return;
        }
        if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
            e.preventDefault();
            move(name, e.key === 'ArrowUp' ? -1 : 1);
        } else if (!e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
            e.preventDefault();
            const all = rows(); const i = all.indexOf(row);
            all[Math.max(0, Math.min(all.length - 1, i + (e.key === 'ArrowUp' ? -1 : 1)))]?.focus();
        } else if ((e.key === 'Delete' || e.key === 'Backspace') && name !== 'general') {
            e.preventDefault();
            const label = row.querySelector('.channel-sidebar-row-label');
            if (typeof _sidebarConfirmDelete === 'function' && label) _sidebarConfirmDelete(name, row, label);
        }
    });

    function init() {
        const l = list();
        if (!l) return;
        new MutationObserver(wire).observe(l, { childList: true });
        wire();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
