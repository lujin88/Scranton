// Scranton keyboard shortcuts (Slack's keys, so they're already in your fingers).
// ⌘/ shows the list. Keys that type text (letters, arrows) only act outside the message box,
// except the ⌥ and ⌘ combinations, which never type anything.
(function () {
    'use strict';
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    const M = mac ? '⌘' : 'Ctrl', A = mac ? '⌥' : 'Alt', S = '⇧';
    const LIST = [
        ['Moving around', [
            [[M, 'K'], 'Search messages, people and channels'],
            [[A, '↑'], [A, '↓'], 'Previous / next channel or DM'],
            [[A, S, '↑'], [A, S, '↓'], 'Previous / next unread'],
            [[M, S, 'A'], 'Activity'],
            [[M, ','], 'Settings'],
        ]],
        ['This conversation', [
            [[M, 'U'], 'Attach files'],
            [[M, S, 'M'], 'Agent model and effort'],
            [['Tab'], 'Use the suggestion in an empty message box (/continue while paused)'],
            [[M, '.'], 'Close the right panel (thread or details)'],
        ]],
        ['Window', [
            [[M, S, 'D'], 'Hide / show the sidebar'],
            [[M, '/'], 'This list'],
            [['Esc'], 'Close a menu or dialog'],
        ]],
    ];
    const kbd = (keys) => keys.map((k) => `<kbd>${k}</kbd>`).join('');

    function rows() {
        return [...document.querySelectorAll('.channel-sidebar-row[data-channel]')].filter((r) => r.offsetParent !== null);
    }
    function go(dir, unreadOnly) {
        const all = rows();
        if (!all.length) return;
        const i = all.findIndex((r) => r.dataset.channel === window.activeChannel);
        for (let step = 1; step <= all.length; step++) {
            const r = all[(i + dir * step + all.length * step) % all.length];
            if (!unreadOnly || r.classList.contains('has-unread')) { r.click(); r.scrollIntoView({ block: 'nearest' }); return; }
        }
        if (unreadOnly && window.scToast) window.scToast('No unread conversations');
    }

    function help() {
        const old = document.getElementById('sc-dialog');
        if (old && old.querySelector('.sc-keys-dlg')) { old.remove(); return; }
        old?.remove();
        const d = document.createElement('div');
        d.id = 'sc-dialog';
        d.innerHTML = `<div class="sc-dlg sc-keys-dlg" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
            <div class="sc-keys-head"><b>Keyboard shortcuts</b><button type="button" class="sc-ap-tool" data-x aria-label="Close" title="Close"><svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 10.586l4.95-4.95 1.414 1.414-4.95 4.95 4.95 4.95-1.414 1.414-4.95-4.95-4.95 4.95-1.414-1.414 4.95-4.95-4.95-4.95L7.05 5.636z"/></svg></button></div>
            ${LIST.map(([title, items]) => `<section><h3>${title}</h3>${items.map((it) => {
                const label = it[it.length - 1], combos = it.slice(0, -1);
                return `<div class="sc-keys-row"><span>${label}</span><span class="sc-keys-k">${combos.map(kbd).join('<i>/</i>')}</span></div>`;
            }).join('')}</section>`).join('')}
        </div>`;
        document.body.appendChild(d);
        const release = window.scModal ? window.scModal(d) : () => {};
        const close = () => { d.remove(); release(); };
        d.addEventListener('click', (e) => { if (e.target === d || e.target.closest('[data-x]')) close(); });
        d.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
        const dlg = d.querySelector('.sc-keys-dlg'); dlg.tabIndex = -1; dlg.focus();
    }
    window.scShowKeys = help;

    document.addEventListener('keydown', (e) => {
        if (e.isComposing) return;
        const mod = mac ? e.metaKey : e.ctrlKey;
        const code = e.code;
        // ⌥↑ / ⌥↓ (+⇧ for unread): never types anything, so it works inside the message box too
        if (e.altKey && !mod && (code === 'ArrowUp' || code === 'ArrowDown')) {
            e.preventDefault(); go(code === 'ArrowUp' ? -1 : 1, e.shiftKey); return;
        }
        if (!mod || e.altKey) return;
        const k = code.replace(/^Key/, '').toLowerCase();
        const act = {
            'slash': !e.shiftKey && help,
            'comma': !e.shiftKey && (() => window.scOpenSettings && window.scOpenSettings()),
            'period': !e.shiftKey && (() => window.scCloseRightPanel && window.scCloseRightPanel()),
            'a': e.shiftKey && (() => window.scOpenInbox && window.scOpenInbox()),
            'd': e.shiftKey && (() => window.scToggleDrawer && window.scToggleDrawer()),
            'm': e.shiftKey && (() => document.getElementById('sc-agentpick-btn')?.click()),
        }[k];
        if (act) { e.preventDefault(); e.stopPropagation(); act(); }
    }, true);
})();
