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
        el.textContent = 'Connecting…';
        load().then(() => {
            if (closed) return;
            el.textContent = '';
            const dark = document.documentElement.dataset.theme === 'dark'
                || (document.documentElement.dataset.theme !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
            term = new window.Terminal({
                fontFamily: 'ui-monospace, "SF Mono", Menlo, monospace', fontSize: 12, lineHeight: 1.2,
                cursorBlink: true, scrollback: 2000, allowProposedApi: false,
                theme: dark ? { background: '#161616', foreground: '#e6e6e6', cursor: '#e6e6e6', selectionBackground: '#3a3a3a' }
                    : { background: '#f5f5f5', foreground: '#1a1a1a', cursor: '#1a1a1a', selectionBackground: '#cfdcf5' },
            });
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
            try { ro && ro.disconnect(); } catch (_) {}
            try { ws && ws.close(); } catch (_) {}
            try { term && term.dispose(); } catch (_) {}
        }
        return stop;
    };
    void css;
})();
