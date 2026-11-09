// Scranton: scroll up to load older messages. The page gets the last 150 per channel
// when it opens; the rest come 100 at a time from /api/scranton/older, rendered with the
// normal renderer off-screen, then put at the top without moving what you're reading.
(function () {
    'use strict';
    const done = new Set();     // channels with nothing older left
    let loading = false;

    function oldestId(ch) {
        let min = Infinity;
        document.querySelectorAll(`#messages .message[data-channel="${CSS.escape(ch)}"]`).forEach((el) => {
            const id = Number(el.dataset.id);
            if (window.scExtraIds && window.scExtraIds.has(id)) return;   // an old thread start, not the window's edge
            if (Number.isFinite(id) && id < min) min = id;
        });
        return Number.isFinite(min) ? min : null;
    }

    async function loadOlder() {
        const ch = window.activeChannel || 'general';
        const tl = document.getElementById('timeline');
        const box = document.getElementById('messages');
        if (loading || done.has(ch) || !tl || !box || typeof appendMessage !== 'function') return;
        // not while the page is still filling in history (it starts at the top, then jumps down)
        if (typeof historyLoading !== 'undefined' && historyLoading) return;
        if (tl.scrollHeight <= tl.clientHeight) return;   // nothing to scroll yet
        const before = oldestId(ch);
        if (before == null || before <= 0) { done.add(ch); return; }
        loading = true;
        const note = document.createElement('div');
        note.className = 'sc-older-note';
        note.textContent = 'Loading earlier messages…';
        box.prepend(note);
        try {
            const r = await fetch(`/api/scranton/older?channel=${encodeURIComponent(ch)}&before=${before}`,
                { headers: { 'X-Session-Token': window.SESSION_TOKEN } });
            const data = r.ok ? await r.json() : null;
            note.remove();
            if (!data || (window.activeChannel || 'general') !== ch) return;
            if (!data.more) done.add(ch);
            if (!data.messages.length) return;
            // An old thread start shown early sits at the top; once this batch reaches it, draw it in its place.
            const lo = Math.min(...data.messages.map((m) => Number(m.id)));
            for (const id of [...(window.scExtraIds || [])]) {
                if (id >= lo) { window.scExtraIds.delete(id); document.getElementById(`message-${id}`)?.remove(); }
            }
            const tmp = document.createElement('div');
            // the day-divider logic remembers the last date it drew; render the batch from scratch
            // and put the live value back, or the next new message gets a second "Today"
            const dates = typeof lastMessageDates === 'object' ? lastMessageDates : null;
            const keepDate = dates ? dates[ch] : undefined;
            if (dates) delete dates[ch];
            try { data.messages.forEach((m) => appendMessage(m, { container: tmp })); }
            finally { if (dates) dates[ch] = keepDate; }
            // a day divider repeated at the seam
            const firstOld = box.querySelector('.date-divider');
            const lastNew = tmp.querySelectorAll('.date-divider');
            const keepH = tl.scrollHeight, keepTop = tl.scrollTop;
            box.prepend(...tmp.childNodes);
            if (firstOld && lastNew.length && firstOld.textContent === lastNew[lastNew.length - 1].textContent) firstOld.remove();
            tl.scrollTop = keepTop + (tl.scrollHeight - keepH);
        } catch (_) {
            note.remove();
        } finally {
            loading = false;
        }
    }

    function hook() {
        const tl = document.getElementById('timeline');
        if (!tl) return;
        // A channel switch briefly sits at the top before jumping to the latest: wait it out.
        let lastCh = null, armedAt = 0;
        tl.addEventListener('scroll', () => {
            const ch = window.activeChannel || 'general';
            if (ch !== lastCh) { lastCh = ch; armedAt = Date.now() + 800; return; }
            if (Date.now() < armedAt) return;
            if (tl.scrollTop < 300) loadOlder();
        }, { passive: true });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', hook); else hook();
})();
