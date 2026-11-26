// 接回 (Lu, 11-26): one click in a channel asks for what happened since she last spoke there
// and what is waiting for her, with enough background to decide. Facts come from the server.
(function () {
    'use strict';
    const ID = 'sc-catchup-btn';

    function channelShown() {
        const tl = document.getElementById('timeline');
        return !!(window.activeChannel && tl && tl.offsetParent !== null);
    }

    function ensure() {
        const head = document.getElementById('sc-pane-head');
        if (!head) return;
        let btn = document.getElementById(ID);
        if (!btn) {
            btn = document.createElement('button');
            btn.id = ID;
            btn.type = 'button';
            btn.title = 'Catch me up: what happened here since my last message, and what needs my decision';
            btn.setAttribute('aria-label', 'Catch me up on this channel');
            btn.innerHTML = (window.scIcon ? window.scIcon('history', 18) : '') + '<span class="sc-catchup-label">Catch up</span>';
            btn.onclick = ask;
            const pill = document.getElementById('sc-pane-pill');
            if (pill && pill.parentElement === head) pill.insertAdjacentElement('afterend', btn);
            else head.appendChild(btn);
        }
        btn.hidden = !channelShown();
    }

    async function ask(e) {
        e.stopPropagation();
        const btn = e.currentTarget;
        if (btn.disabled) return;
        btn.disabled = true;
        const label = btn.querySelector('.sc-catchup-label');
        try {
            const r = await fetch('/api/scranton/catch-up', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Session-Token': window.SESSION_TOKEN || '' },
                body: JSON.stringify({ channel: window.activeChannel }),
            });
            const d = await r.json().catch(() => ({}));
            if (label) label.textContent = !r.ok ? 'Failed' : d.state === 'already asked' ? 'Already asked' : d.state === 'nothing new' ? 'Nothing new' : 'Asked';
        } catch (_) {
            if (label) label.textContent = 'Failed';
        }
        setTimeout(() => { btn.disabled = false; if (label) label.textContent = 'Catch up'; }, 4000);
    }

    function start() {
        ensure();
        const center = document.getElementById('sc-center') || document.body;
        new MutationObserver(ensure).observe(center, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'hidden'] });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
    else start();
})();
