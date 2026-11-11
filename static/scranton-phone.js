// Scranton on a phone (Lu, 11-10, "like Grok, three screens left to right"):
//   Home (search on top, channels and people, you at the bottom as on the desktop) → Conversation (‹ back, name, members) → Details (‹ back).
// Only below 760 px; the desktop layout is unchanged.
(function () {
    'use strict';
    const phone = () => window.matchMedia('(max-width: 760px)').matches;
    const ic = (n, s) => (window.scIcon ? window.scIcon(n, s) : '');
    // after the tap is done: the page's "tap outside closes the drawer" listener runs on the same tap
    const goHome = () => setTimeout(() => document.body.classList.add('sc-drawer-channels'), 0);

    function home() {
        const side = document.getElementById('channel-sidebar');
        if (!side || document.getElementById('sc-home-head')) return;
        const head = document.createElement('div');
        head.id = 'sc-home-head';
        head.innerHTML = `<button type="button" class="sc-glass sc-home-me" aria-label="You: status, settings, updates" aria-haspopup="menu"></button>
            <button type="button" class="sc-glass sc-home-new" aria-label="New" aria-haspopup="menu">${ic('add', 24)}</button>`;
        side.insertBefore(head, side.firstChild);
        const me = head.querySelector('.sc-home-me');
        const paint = () => { me.innerHTML = window.scMyAvatarHtml ? window.scMyAvatarHtml() : ''; };
        paint(); setTimeout(paint, 1500);
        (window.scOnTeamChange = window.scOnTeamChange || []).push(paint);
        me.addEventListener('click', (e) => { e.stopPropagation(); window.scToggleAccountMenu && window.scToggleAccountMenu(me); });
        head.querySelector('.sc-home-new').addEventListener('click', (e) => {
            e.stopPropagation();
            document.querySelectorAll('.sc-home-menu').forEach((m) => m.remove());
            const m = document.createElement('div');
            m.className = 'sc-pop sc-menu sc-home-menu';
            m.setAttribute('role', 'menu');
            m.innerHTML = `<button type="button" class="sc-menu-item" role="menuitem" data-n="dm">${ic('chat-smile', 18)}Message a teammate</button>
                <button type="button" class="sc-menu-item" role="menuitem" data-n="ch">${ic('add', 18)}New channel</button>`;
            document.body.appendChild(m);
            const r = e.currentTarget.getBoundingClientRect();
            m.style.top = `${r.bottom + 8}px`; m.style.right = `${window.innerWidth - r.right}px`;
            const away = (ev) => { if (!m.contains(ev.target)) { m.remove(); document.removeEventListener('pointerdown', away, true); } };
            setTimeout(() => document.addEventListener('pointerdown', away, true), 0);
            m.addEventListener('click', (ev) => {
                const n = ev.target.closest('[data-n]')?.dataset.n;
                if (!n) return;
                m.remove();
                if (n === 'dm') document.getElementById('sc-dm-add')?.click();
                if (n === 'ch') document.getElementById('channel-sidebar-add')?.click();
            });
        });
        const bar = document.createElement('button');
        bar.type = 'button';
        bar.id = 'sc-home-search';
        bar.className = 'sc-glass';
        bar.innerHTML = `${ic('search', 20)}<span>Search</span>`;
        bar.addEventListener('click', (e) => { e.stopPropagation(); document.getElementById('sc-search-btn')?.click(); });
        head.insertBefore(bar, head.querySelector('.sc-home-new'));   // search | +
    }

    // ‹ back instead of ×: thread and details go back to the conversation, Activity and Report to Home.
    // Runs on DOM changes: cheap when not a phone, and at most once per frame (every message
    // added used to run a whole-page query, on the desktop too).
    let backPending = false;
    function backButtonsSoon() {
        if (backPending || !phone()) return;
        backPending = true;
        requestAnimationFrame(() => { backPending = false; backButtons(); });
    }
    function backButtons() {
        if (!phone()) return;
        const back = ic('back', 24);
        document.querySelectorAll('.sc-thread-close, #sc-info .sc-info-x, .sc-inbox-x').forEach((b) => {
            if (!phone() || b.dataset.scBack) return;
            b.dataset.scBack = '1';
            b.dataset.scWas = b.innerHTML;
            b.innerHTML = back;
            b.setAttribute('aria-label', 'Back');
        });
    }
    function init() {
        home();
        backButtons();
        new MutationObserver(backButtonsSoon).observe(document.body, { childList: true, subtree: true });
        // ‹ in Activity goes back to Home, as on Grok. Only that button: other things close Activity too
        // (switching channel), and those must not send you Home.
        document.addEventListener('click', (e) => { if (phone() && e.target.closest('.sc-inbox-x')) goHome(); });
        // The phone opens on Home.
        if (phone() && !location.hash) goHome();
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 200));
    else setTimeout(init, 200);
})();
