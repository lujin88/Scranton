// One pop-up at a time (Lu, 11-10: the ⚡ shortcuts and the model picker were both open). When any
// menu, picker or popover appears, the others close: their own close path if they have one, else removed.
(function () {
    'use strict';
    const SEL = '#sc-agentpick, #sc-shortcut-menu, #sc-attach-menu, #sc-dm-pop, #sc-account-menu, #sc-members-panel, .sc-pop';
    const closeOne = (el) => {
        if (el.id === 'sc-account-menu' && window.scToggleAccountMenu) { window.scToggleAccountMenu(); if (!el.isConnected) return; }
        if (el.id === 'sc-members-panel') { document.getElementById('sc-members-btn')?.click(); if (!el.isConnected) return; }
        el.remove();
    };
    new MutationObserver((muts) => {
        for (const m of muts) {
            for (const n of m.addedNodes) {
                if (n.nodeType !== 1 || !n.matches(SEL)) continue;
                document.querySelectorAll(SEL).forEach((o) => { if (o !== n && !o.contains(n) && !n.contains(o)) closeOne(o); });
            }
        }
    }).observe(document.body, { childList: true, subtree: true });
})();
