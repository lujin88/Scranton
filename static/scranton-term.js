// A teammate's real terminal inside Scranton (Lu, 11-10: "像 Cursor 一样 embed"). xterm.js (MIT,
// static/vendor/xterm) on a websocket to /ws/term/<handle>, which runs `tmux attach` to that
// teammate's session. Type, press Enter, use the arrows, as in Terminal. Closing the view only
// detaches: the teammate keeps running.
(function () {
    'use strict';
    let loading = null;
    function load() {
        if (window.Terminal && window.FitAddon) return Promise.resolve();
        if (loading) return loading;
        loading = new Promise((resolve, reject) => {
            const css = document.createElement('link');
            css.rel = 'stylesheet'; css.href = '/static/vendor/xterm/xterm.css';
            document.head.appendChild(css);
            const js = (src) => new Promise((ok, bad) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = bad; document.head.appendChild(s); });
            js('/static/vendor/xterm/xterm.js').then(() => js('/static/vendor/xterm/addon-fit.js')).then(resolve, reject);
        });
        return loading;
    }
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

    // Returns a function that closes the view.
    window.scTerm = function mount(el, handle) {
        let closed = false, ws = null, term = null, ro = null;
        el.classList.add('sc-xterm');
        // Fill what's left of the window below it, so the page itself never scrolls (Lu, 11-10).
        const fillDown = () => {
            const box = el.closest('.sc-st-main, #sc-info');
            if (!box) return;
            let pad = 0; for (let n = el.parentElement; n && n !== box.parentElement; n = n.parentElement) pad += parseFloat(getComputedStyle(n).paddingBottom) || 0;
            const room = box.getBoundingClientRect().bottom - el.getBoundingClientRect().top - pad - 10
                - [...el.parentElement.children].filter((c) => c !== el && c.getBoundingClientRect().top > el.getBoundingClientRect().top)
                    .reduce((n, c) => n + c.getBoundingClientRect().height + 8, 0);
            el.style.height = `${Math.max(220, Math.floor(room))}px`;
        };
        fillDown();
        window.addEventListener('resize', fillDown);
        el.textContent = 'Connecting…';
        load().then(() => {
            if (closed) return;
            el.textContent = '';
            const dark = document.documentElement.dataset.theme === 'dark'
                || (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
            term = new window.Terminal({
                fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace', fontSize: 12, lineHeight: 1.2,
                cursorBlink: true, scrollback: 2000, allowProposedApi: false,
                macOptionClickForcesSelection: true,
                // Selection = the accent at reading strength, kept when focus leaves (Lu, 11-11: "选的看不到").
                theme: dark ? { background: '#161616', foreground: '#e6e6e6', cursor: '#e6e6e6',
                        selectionBackground: 'rgba(76,141,246,.5)', selectionInactiveBackground: 'rgba(76,141,246,.35)' }
                    : { background: '#f5f5f5', foreground: '#1a1a1a', cursor: '#1a1a1a',
                        selectionBackground: 'rgba(47,111,222,.32)', selectionInactiveBackground: 'rgba(47,111,222,.22)' },
            });
            // Claude Code and tmux turn on mouse reporting, so a drag went to them and nothing got
            // selected. A plain left drag now always selects here (the wheel still scrolls them):
            // on a Mac we press Option for you, which is xterm's "force selection" key.
            if (/Mac|iPhone|iPad/.test(navigator.platform)) {
                el.addEventListener('mousedown', (e) => {
                    if (e.button === 0 && !e.altKey && !e.metaKey && !e.ctrlKey && !e.shiftKey) Object.defineProperty(e, 'altKey', { get: () => true });
                }, true);
            }
            const fit = new window.FitAddon.FitAddon();
            term.loadAddon(fit);
            term.open(el);
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${proto}//${location.host}/ws/term/${encodeURIComponent(handle)}?token=${encodeURIComponent(window.SESSION_TOKEN)}`);
            ws.binaryType = 'arraybuffer';
            const send = (o) => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(o)); };
            const resize = () => { try { fit.fit(); } catch (_) { return; } send({ t: 'size', c: term.cols, r: term.rows }); };
            ws.onopen = () => { resize(); term.focus(); };
            ws.onmessage = (e) => term.write(typeof e.data === 'string' ? e.data : new Uint8Array(e.data));
            ws.onclose = () => { if (!closed) term.write('\r\n\x1b[2m(disconnected: close and open this tab again)\x1b[0m\r\n'); };
            term.onData((d) => send({ t: 'in', d }));
            ro = new ResizeObserver(() => resize());
            ro.observe(el);
            // Gone from the page (tab switched, panel closed): detach.
            const iv = setInterval(() => { if (!el.isConnected) { clearInterval(iv); stop(); } }, 1000);
        }).catch(() => { el.textContent = "Couldn't load the terminal. Reload Scranton."; });
        function stop() {
            closed = true;
            window.removeEventListener('resize', fillDown);
            try { ro && ro.disconnect(); } catch (_) {}
            try { ws && ws.close(); } catch (_) {}
            try { term && term.dispose(); } catch (_) {}
        }
        return stop;
    };
    void css;
})();
