// Scranton: show which @names in a message box will reach someone.
// A textarea can't style part of its text, so a mirror div sits behind it with
// the same font, padding and wrapping; a matched "@name" gets a background in
// the mirror while the textarea (transparent background) draws the letters on
// top. Unmatched "@xyz" stays plain, so a typo is visible before sending.
(function () {
    'use strict';
    const COPY = ['fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'letterSpacing', 'lineHeight', 'textTransform',
        'wordSpacing', 'textIndent', 'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
        'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth', 'boxSizing', 'tabSize'];
    const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const reEsc = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    let cachedRe = null, cachedKey = '';
    function mentionRe() {
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const label = window.scLabelOf || ((h) => h);
        const names = new Set(['grok', 'all']);
        for (const h of Object.keys(team)) { names.add(h); const l = label(h); if (l) names.add(String(l)); }
        if (window.scLabelOf) names.add(String(window.scLabelOf('grok')));
        const list = Array.from(names).filter(Boolean).sort((a, b) => b.length - a.length);
        const key = list.join('\u0001');
        if (key !== cachedKey) {
            cachedKey = key;
            // A name counts when it ends the text or is followed by a space or punctuation,
            // so "@开发工程师 " matches but "@开发工程" (still typing) doesn't.
            cachedRe = list.length ? new RegExp(`(^|[\\s(（])@(${list.map(reEsc).join('|')})(?=$|[\\s,，.。:：;；!！?？)）])`, 'gi') : null;
        }
        return cachedRe;
    }

    function render(text) {
        const re = mentionRe();
        let html = '';
        let last = 0;
        if (re) {
            re.lastIndex = 0;
            let m;
            while ((m = re.exec(text))) {
                const at = m.index + m[1].length;
                html += esc(text.slice(last, at)) + `<mark>${esc('@' + m[2])}</mark>`;
                last = at + 1 + m[2].length;
            }
        }
        // Trailing newline needs a character after it or the mirror is one line short.
        return html + esc(text.slice(last)) + '​';
    }

    function attach(box) {
        if (!box || box._scHl) return;
        box._scHl = true;
        const host = box.parentElement;
        if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
        const mirror = document.createElement('div');
        mirror.className = 'sc-mention-hl';
        mirror.setAttribute('aria-hidden', 'true');
        host.insertBefore(mirror, box);
        box.classList.add('sc-mention-hl-input');

        function place() {
            const cs = getComputedStyle(box);
            for (const k of COPY) mirror.style[k] = cs[k];
            mirror.style.left = box.offsetLeft + 'px';
            mirror.style.top = box.offsetTop + 'px';
            mirror.style.width = box.offsetWidth + 'px';
            // a visible scrollbar narrows the text area; keep the same wrap width
            mirror.style.paddingRight = (parseFloat(cs.paddingRight) + (box.offsetWidth - box.clientWidth
                - parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth))) + 'px';
            mirror.style.height = box.offsetHeight + 'px';
            mirror.style.display = box.offsetParent ? '' : 'none';
        }
        function sync() {
            mirror.innerHTML = box.value ? render(box.value) : '';
            place();
            mirror.scrollTop = box.scrollTop;
        }
        ['input', 'change', 'focus', 'keyup'].forEach((e) => box.addEventListener(e, sync));
        box.addEventListener('scroll', () => { mirror.scrollTop = box.scrollTop; });
        if (window.ResizeObserver) { const ro = new ResizeObserver(place); ro.observe(box); ro.observe(host); }
        window.addEventListener('resize', place);
        // Code that sets .value directly (send clears the box, chips insert names) fires no event.
        const desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
        Object.defineProperty(box, 'value', {
            configurable: true,
            get() { return desc.get.call(this); },
            set(v) { desc.set.call(this, v); sync(); },
        });
        (window.scOnTeamChange || []).push(sync);
        sync();
    }

    window.scHighlightMentions = attach;
    function boot() {
        attach(document.getElementById('input'));
        const t = document.getElementById('sc-thread-input');
        if (t) attach(t);
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
