// Mark up a picture and send it back (Lu, 11-10: "参考豆包或 GPT，直接圈出来，然后打文字").
// In the picture viewer, "Mark up" opens the picture full screen: circle or box what you mean,
// drop a note on it, type what to change, and it goes back into that message's thread,
// to whoever posted the picture.
(function () {
    'use strict';
    const COLORS = ['#ff3b30', '#ffcc00', '#34c759', '#0a84ff', '#ffffff'];
    const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const icon = (n, s = 18) => (window.scIcon ? window.scIcon(n, s) : '');
    const me = () => (window.username || (window.scMe && window.scMe()) || 'Lu');

    // ---- where the picture came from: its message, sender, channel
    function sourceOf(url) {
        const imgs = document.querySelectorAll('.msg-attachments img, .job-msg-attachments img, .msg-text img, .sc-tmsg-text img, .sc-tmsg-att img');
        for (const img of imgs) {
            const full = img.dataset.full ? new URL(img.dataset.full, location.href).href : img.src;
            if (full !== url && !full.endsWith(url)) continue;
            const holder = img.closest('[data-mid]') || img.closest('[id^="message-"]');
            if (!holder) continue;
            const id = Number(holder.dataset.mid || String(holder.id).replace('message-', ''));
            const msg = window.scMsgs && window.scMsgs.get(id);
            if (msg) return msg;
        }
        return null;
    }
    function rootOf(msg) {
        let cur = msg, guard = 0;
        while (cur && cur.reply_to != null && guard++ < 50) {
            const p = window.scMsgs && window.scMsgs.get(Number(cur.reply_to));
            if (!p) return Number(cur.reply_to);
            cur = p;
        }
        return cur ? Number(cur.id) : null;
    }
    function isTeammate(sender) {
        const s = String(sender || '').toLowerCase();
        if (!s || s === 'system' || s === String(me()).toLowerCase()) return false;
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        return !!team[s] || !!team[s.replace(/-\d+$/, '')];
    }

    // ---- the button in the viewer
    function addButton() {
        const modal = document.getElementById('image-modal');
        if (!modal || modal.querySelector('.sc-mk-open')) return;
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'sc-mk-open';
        b.innerHTML = `${icon('brush', 16)}<span>Edit</span>`;
        b.addEventListener('click', (e) => {
            e.stopPropagation();
            const src = modal.querySelector('img') && modal.querySelector('img').src;
            if (src) openEditor(src);
        });
        modal.appendChild(b);
    }
    const orig = window.openImageModal;
    if (typeof orig === 'function') {
        window.openImageModal = function (...a) { const r = orig.apply(this, a); addButton(); return r; };
    }

    // ---- the editor
    // Who edits pictures: whoever made it if they make pictures, else the visual intern, else
    // the visual designer (Lu, 11-11: "image edit like 豆包 / GPT").
    const IMAGE_MAKERS = ['visintern', 'visual', 'motion', 'motionintern'];
    function editors(sender) {
        const team = (window.scGetTeam && window.scGetTeam()) || {};
        const have = (n) => Object.prototype.hasOwnProperty.call(team, n);
        const list = IMAGE_MAKERS.filter(have);
        const s = String(sender || '').replace(/-\d+$/, '');
        if (s && have(s) && !list.includes(s)) list.unshift(s);
        const first = list.includes(s) ? s : (list[0] || '');
        return { list, first };
    }
    // Quick asks, as in 豆包: they fill in the sentence; "area" ones want a painted area.
    const ASKS = [
        { k: 'change', icon: 'brush', label: 'Change this', zh: '把涂的地方改成：', area: true },
        { k: 'remove', icon: 'eraser', label: 'Remove', zh: '去掉涂的地方的东西，背景补得自然，其他不变', area: true },
        { k: 'expand', icon: 'expand-diagonal', label: 'Expand', zh: '向四周扩展画面，风格和光线一致，原来的部分不变' },
        { k: 'cutout', icon: 'scissors', label: 'Cut out', zh: '去掉背景，主体保留，导出透明 PNG' },
        { k: 'sharpen', icon: 'sparkling', label: 'Sharpen', zh: '放大到 2 倍并变清晰，不改内容' },
    ];

    function openEditor(src) {
        const msg = sourceOf(src);
        const ed = editors(msg && msg.sender);
        let to = ed.first || (msg && isTeammate(msg.sender) ? String(msg.sender) : '');
        const labelOf = (n) => (n && window.scLabelOf ? window.scLabelOf(n) : n);
        const label = labelOf(to);
        const viewer = document.getElementById('image-modal');
        if (viewer) viewer.classList.add('hidden');

        const root = document.createElement('div');
        root.id = 'sc-markup';
        root.setAttribute('role', 'dialog');
        root.setAttribute('aria-label', 'Mark up picture');
        root.innerHTML = `
            <div class="sc-mk-top">
                <button type="button" class="sc-mk-x" aria-label="Cancel">${icon('close', 20)}</button>
                <div class="sc-mk-tools" role="toolbar" aria-label="Tools">
                    <button type="button" data-tool="area" aria-pressed="true" title="Paint the area to change">${icon('brush', 18)}<span>Area</span></button>
                    <button type="button" data-tool="pen" aria-pressed="false" title="Circle (draw)">${icon('pencil', 18)}<span>Circle</span></button>
                    <button type="button" data-tool="box" aria-pressed="false" title="Box">${icon('square', 18)}<span>Box</span></button>
                    <button type="button" data-tool="text" aria-pressed="false" title="Note">${icon('text', 18)}<span>Note</span></button>
                    <span class="sc-mk-sep"></span>
                    ${COLORS.map((c, i) => `<button type="button" class="sc-mk-color" data-color="${c}" aria-pressed="${i === 0}" aria-label="Colour ${c}" style="--c:${c}"></button>`).join('')}
                    <span class="sc-mk-sep"></span>
                    <button type="button" class="sc-mk-undo" title="Undo" aria-label="Undo">${icon('undo', 18)}</button>
                </div>
                <span class="sc-mk-spacer"></span>
            </div>
            <div class="sc-mk-stage"><canvas></canvas></div>
            <div class="sc-mk-asks" role="group" aria-label="Quick edits">${ASKS.map((a) => `<button type="button" class="sc-mk-ask" data-ask="${a.k}">${icon(a.icon, 16)}<span>${a.label}</span></button>`).join('')}</div>
            <form class="sc-mk-send">
                ${ed.list.length > 1 ? `<select class="sc-mk-to" aria-label="Who edits it">${ed.list.map((n) => `<option value="${esc(n)}"${n === to ? ' selected' : ''}>${esc(labelOf(n))}</option>`).join('')}</select>` : ''}
                <input type="text" enterkeyhint="send" placeholder="${to ? `Paint an area, then tell ${esc(label)} what to change…` : 'What should change?'}" aria-label="What to change">
                <button type="submit" class="sc-mk-go" aria-label="Send">${icon('send', 18)}</button>
            </form>
            <div class="sc-mk-note" role="status"></div>`;
        document.body.appendChild(root);

        const canvas = root.querySelector('canvas');
        const ctx = canvas.getContext('2d');
        const status = root.querySelector('.sc-mk-note');
        const input = root.querySelector('.sc-mk-send input');
        let tool = 'area', color = COLORS[0];
        const AREA = 'rgba(76, 141, 246, 0.45)';
        const shapes = [];
        let cur = null, img = null, scale = 1;

        const pic = new Image();
        pic.crossOrigin = 'anonymous';
        pic.onload = () => { img = pic; fit(); draw(); };
        pic.onerror = () => { status.textContent = 'This picture can’t be opened for marking up.'; };
        pic.src = src;

        function fit() {
            if (!img) return;
            canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
            const stage = root.querySelector('.sc-mk-stage').getBoundingClientRect();
            scale = Math.min(stage.width / img.naturalWidth, stage.height / img.naturalHeight, 1.5);
            canvas.style.width = `${Math.round(img.naturalWidth * scale)}px`;
            canvas.style.height = `${Math.round(img.naturalHeight * scale)}px`;
        }
        const lw = () => Math.max(3, Math.round(Math.max(canvas.width, canvas.height) / 300));
        const fs = () => Math.max(16, Math.round(Math.max(canvas.width, canvas.height) / 40));

        function paint(s) {
            ctx.strokeStyle = s.color; ctx.fillStyle = s.color;
            ctx.lineWidth = s.w; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
            if (s.kind === 'area') {
                ctx.strokeStyle = AREA;
                ctx.beginPath();
                s.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
                if (s.pts.length === 1) ctx.lineTo(s.pts[0][0] + 0.1, s.pts[0][1]);
                ctx.stroke();
            } else if (s.kind === 'pen') {
                ctx.beginPath();
                s.pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
                ctx.stroke();
            } else if (s.kind === 'box') {
                ctx.strokeRect(Math.min(s.x, s.x2), Math.min(s.y, s.y2), Math.abs(s.x2 - s.x), Math.abs(s.y2 - s.y));
            } else if (s.kind === 'text') {
                // a filled label, like a sticky note: readable on any picture
                ctx.font = `600 ${s.size}px -apple-system, system-ui, sans-serif`;
                const pad = s.size * 0.4, w = ctx.measureText(s.text).width;
                ctx.beginPath();
                ctx.roundRect(s.x, s.y, w + pad * 2, s.size * 1.5, s.size * 0.35);
                ctx.fill();
                ctx.fillStyle = s.color === '#ffffff' || s.color === '#ffcc00' ? '#111' : '#fff';
                ctx.textBaseline = 'middle';
                ctx.fillText(s.text, s.x + pad, s.y + s.size * 0.78);
            }
        }
        function draw() {
            if (!img) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(img, 0, 0);
            shapes.forEach(paint);
            if (cur) paint(cur);
        }
        function at(e) {
            const r = canvas.getBoundingClientRect();
            return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height];
        }

        canvas.addEventListener('pointerdown', (e) => {
            if (!img) return;
            e.preventDefault();
            const [x, y] = at(e);
            if (tool === 'text') { placeNote(e, x, y); return; }
            canvas.setPointerCapture(e.pointerId);
            cur = tool === 'area' ? { kind: 'area', color: AREA, w: lw() * 8, pts: [[x, y]] }
                : tool === 'pen' ? { kind: 'pen', color, w: lw(), pts: [[x, y]] } : { kind: 'box', color, w: lw(), x, y, x2: x, y2: y };
        });
        canvas.addEventListener('pointermove', (e) => {
            if (!cur) return;
            const [x, y] = at(e);
            if (cur.kind === 'pen' || cur.kind === 'area') cur.pts.push([x, y]); else { cur.x2 = x; cur.y2 = y; }
            draw();
        });
        const end = () => {
            if (!cur) return;
            const tiny = cur.kind === 'area' ? false : cur.kind === 'pen' ? cur.pts.length < 2 : Math.abs(cur.x2 - cur.x) < 4 && Math.abs(cur.y2 - cur.y) < 4;
            if (!tiny) shapes.push(cur);
            cur = null; draw();
        };
        canvas.addEventListener('pointerup', end);
        canvas.addEventListener('pointercancel', end);

        function placeNote(e, x, y) {
            const box = document.createElement('input');
            box.className = 'sc-mk-noteinput';
            box.placeholder = 'Note';
            box.style.left = `${e.clientX}px`; box.style.top = `${e.clientY}px`;
            box.style.setProperty('--c', color);
            box.style.color = color === '#ffffff' || color === '#ffcc00' ? '#111' : '#fff';
            root.appendChild(box);
            box.focus();
            let done = false;
            const commit = () => {
                if (done) return; done = true;
                const t = box.value.trim();
                box.remove();
                if (t) { shapes.push({ kind: 'text', color, size: fs(), x, y: y - fs() * 0.75, text: t }); draw(); }
            };
            box.addEventListener('keydown', (k) => { if (k.key === 'Enter') { k.preventDefault(); commit(); } if (k.key === 'Escape') { box.value = ''; commit(); } });
            box.addEventListener('blur', commit);
        }

        root.querySelectorAll('[data-tool]').forEach((b) => b.addEventListener('click', () => {
            tool = b.dataset.tool;
            root.querySelectorAll('[data-tool]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        }));
        root.querySelectorAll('.sc-mk-color').forEach((b) => b.addEventListener('click', () => {
            color = b.dataset.color;
            root.querySelectorAll('.sc-mk-color').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        }));
        root.querySelector('.sc-mk-undo').addEventListener('click', () => { shapes.pop(); draw(); });
        root.querySelectorAll('.sc-mk-ask').forEach((b) => b.addEventListener('click', () => {
            const a = ASKS.find((x) => x.k === b.dataset.ask);
            input.value = a.zh;
            input.focus();
            input.setSelectionRange(input.value.length, input.value.length);
            if (a.area && !shapes.some((x) => x.kind === 'area')) status.textContent = 'Paint the area first (Area tool).';
            else status.textContent = '';
        }));
        const pick = root.querySelector('.sc-mk-to');
        if (pick) pick.addEventListener('change', () => { to = pick.value; });

        // The area painted, as a black-and-white mask the size of the picture (white = change this).
        async function maskFile() {
            const areas = shapes.filter((x) => x.kind === 'area');
            if (!areas.length) return null;
            const c = document.createElement('canvas');
            c.width = canvas.width; c.height = canvas.height;
            const m = c.getContext('2d');
            m.fillStyle = '#000'; m.fillRect(0, 0, c.width, c.height);
            m.strokeStyle = '#fff'; m.lineCap = 'round'; m.lineJoin = 'round';
            for (const a of areas) {
                m.lineWidth = a.w;
                m.beginPath();
                a.pts.forEach(([x, y], i) => (i ? m.lineTo(x, y) : m.moveTo(x, y)));
                if (a.pts.length === 1) m.lineTo(a.pts[0][0] + 0.1, a.pts[0][1]);
                m.stroke();
            }
            const blob = await new Promise((res, rej) => c.toBlob((b) => (b ? res(b) : rej(new Error('empty'))), 'image/png'));
            return new File([blob], `edit-mask-${Date.now()}.png`, { type: 'image/png' });
        }

        function close() {
            window.removeEventListener('resize', onResize);
            document.removeEventListener('keydown', onKey, true);
            root.remove();
            if (viewer) viewer.classList.remove('hidden');
        }
        const onResize = () => fit();
        const onKey = (e) => {
            if (e.key === 'Escape' && !e.target.classList.contains('sc-mk-noteinput')) { e.stopPropagation(); close(); }
            if ((e.metaKey || e.ctrlKey) && e.key === 'z' && e.target === document.body) { e.preventDefault(); shapes.pop(); draw(); }
        };
        window.addEventListener('resize', onResize);
        document.addEventListener('keydown', onKey, true);
        root.querySelector('.sc-mk-x').addEventListener('click', close);

        root.querySelector('.sc-mk-send').addEventListener('submit', async (e) => {
            e.preventDefault();
            const note = input.value.trim();
            if (!img) return;
            if (!shapes.length && !note) { status.textContent = 'Paint an area or type what to change first.'; return; }
            if (!window.ws || window.ws.readyState !== WebSocket.OPEN) { status.textContent = 'Not connected. Try again in a moment.'; return; }
            const go = root.querySelector('.sc-mk-go');
            go.disabled = true; status.textContent = 'Sending…';
            try {
                const blob = await new Promise((res, rej) => {
                    try { canvas.toBlob((b) => (b ? res(b) : rej(new Error('empty'))), 'image/png'); } catch (err) { rej(err); }
                });
                const file = new File([blob], `marked-up-${Date.now()}.png`, { type: 'image/png' });
                const att = await window.uploadAttachment(file);
                const mf = await maskFile();
                const atts = [att];
                let text;
                if (mf) {
                    atts.push(await window.uploadAttachment(mf));
                    const name = decodeURIComponent(String(src).split('?')[0].split('/').pop() || '');
                    text = `${to ? `@${to} ` : ''}修图：${note || '按涂的地方改'}\n`
                        + `原图：${name}（这条 thread 里的那张）。第 1 张是我涂过的预览，第 2 张是遮罩：白色是要改的地方，黑色的地方保持原样、一个像素都不要动。`
                        + `用你的出图/改图工具做，结果发在这个 thread 里。`;
                } else {
                    text = `${to ? `@${to} ` : ''}${note || 'See the marked-up picture.'}`;
                }
                const payload = { type: 'message', text, sender: me(), attachments: atts,
                    channel: (msg && msg.channel) || window.activeChannel || 'general' };
                if (msg) payload.reply_to = rootOf(msg);
                window.ws.send(JSON.stringify(payload));
                close();
                const v = document.getElementById('image-modal');
                if (v) v.classList.add('hidden');
                if (msg && payload.reply_to != null && window.scOpenThread) window.scOpenThread(payload.reply_to);
            } catch (err) {
                go.disabled = false;
                status.textContent = /tainted|insecure|SecurityError/i.test(String(err && (err.name + err.message)))
                    ? 'Pictures from other websites can’t be sent back marked up.'
                    : `Couldn’t send: ${err && err.message ? err.message : 'try again'}`;
            }
        });
        setTimeout(() => { fit(); draw(); }, 0);
    }
    window.scMarkup = openEditor;
})();
