// Preview: on any device other than the Scranton computer itself, a teammate's
// "http://localhost:4661/…" link or "/Users/…/file.png" path opens through Scranton
// (scranton_preview.py) instead of pointing at the device in your hand.
// On the Scranton computer nothing changes: localhost links open directly, paths open in Finder.
(function () {
    'use strict';
    const here = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
    let info = null;

    async function load() {
        try {
            const r = await fetch('/api/scranton/preview', { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            if (r.ok) info = await r.json();
        } catch (_) { /* offline: links keep their plain behaviour */ }
    }
    const tell = (text) => { if (window.scToast) window.scToast(text); };

    function portUrl(href) {
        let u;
        try { u = new URL(href); } catch (_) { return null; }
        if (!['localhost', '127.0.0.1'].includes(u.hostname) || !u.port) return null;
        const port = Number(u.port);
        if (!info) return { error: 'Scranton is still loading. Try again in a moment.' };
        const ok = !info.own_ports.includes(port) && info.ports.some(([a, b]) => port >= a && port <= b);
        if (!ok) return { error: `Port ${port} is on the Scranton computer and is not one previews may open.` };
        return { url: `/api/scranton/preview-open?token=${encodeURIComponent(window.SESSION_TOKEN)}&port=${port}&path=${encodeURIComponent(u.pathname + u.search + u.hash)}` };
    }

    function fileUrl(text) {
        const path = String(text || '').trim().replace(/[\s.,;:，。；：]+$/, '');
        if (!path.startsWith('/')) return null;
        if (!info) return { error: 'Scranton is still loading. Try again in a moment.' };
        if (!info.roots.some((r) => path === r || path.startsWith(r + '/'))) {
            return { error: 'That path is on the Scranton computer, outside the folders previews may open.' };
        }
        return { url: `/api/scranton/preview-open?token=${encodeURIComponent(window.SESSION_TOKEN)}&file=${encodeURIComponent(path)}` };
    }

    // Exposed so other parts (board links, Activity) can ask for a preview address.
    window.scPreview = { here, portUrl, fileUrl, ready: () => !!info };

    if (!here) {
        document.addEventListener('click', (e) => {
            const a = e.target.closest && e.target.closest('a');
            if (!a) return;
            let hit = null;
            if (a.classList.contains('file-link')) hit = fileUrl(a.textContent);
            else if (/^https?:\/\/(localhost|127\.0\.0\.1):\d+/i.test(a.getAttribute('href') || '')) hit = portUrl(a.href);
            if (!hit) return;
            e.preventDefault();
            e.stopPropagation();          // the path link's own handler would ask the Scranton computer to open Finder
            if (hit.error) { tell(hit.error); return; }
            window.open(hit.url, '_blank', 'noopener');
        }, true);
    }
    const start = () => (window.SESSION_TOKEN ? load() : setTimeout(start, 400));
    start();
})();
