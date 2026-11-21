// The skills of whoever you are writing to, as chips under the message box (Lu, 11-21: "我记不住
// 那么多 skill"). A teammate uses a skill for certain only when the message names it; left alone it
// may or may not pick one. Click a chip to add "用 <skill> skill：" to the message, click again to
// take it out. Hover says what the skill is for, in the skill's own words.
(function () {
    'use strict';
    const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const team = () => (window.scGetTeam && window.scGetTeam()) || {};
    const phrase = (n) => `用 ${n} skill`;

    function targets(text) {
        const t = team(), out = [];
        const byLabel = {};
        for (const [h, v] of Object.entries(t)) if (v && v.label) byLabel[String(v.label).toLowerCase()] = h;
        for (const m of String(text || '').matchAll(/@([^\s@，。,.:：!?！？()（）]+)/g)) {
            const k = m[1].toLowerCase(), h = t[k] ? k : byLabel[k];
            if (h && !out.includes(h)) out.push(h);
        }
        const ch = String(window.activeChannel || '');
        if (!out.length && ch.startsWith('dm-') && t[ch.slice(3)]) out.push(ch.slice(3));   // a DM needs no @
        return out.filter((h) => (t[h].skills || []).length);
    }

    function render() {
        const input = document.getElementById('input'), anchor = document.getElementById('mention-toggles-row');
        if (!input || !anchor) return;
        let row = document.getElementById('sc-skill-row');
        const who = targets(input.value).slice(0, 2);
        if (!who.length) { if (row) row.hidden = true; return; }
        if (!row) {
            row = document.createElement('div');
            row.id = 'sc-skill-row';
            anchor.insertAdjacentElement('afterend', row);
            row.addEventListener('click', (e) => {
                const b = e.target.closest('.sc-skill-chip');
                if (!b) return;
                const p = phrase(b.dataset.skill), v = input.value;
                if (v.includes(p)) input.value = v.replace(new RegExp('\\s*' + p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '[：:]?\\s*'), ' ').replace(/^\s+/, '');
                else input.value = v.replace(/\s*$/, '') + (v.trim() ? ' ' : '') + p + '：';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.focus();
            });
        }
        const t = team();
        row.hidden = false;
        row.innerHTML = who.map((h) => `<span class="sc-skill-who">${esc(t[h].label || h)} can use</span>`
            + (t[h].skills || []).map((s) => `<button type="button" class="mention-toggle sc-skill-chip${input.value.includes(phrase(s.name)) ? ' active' : ''}${s.installed === false ? ' missing' : ''}" data-skill="${esc(s.name)}" data-tip="${esc(s.installed === false ? 'Not installed on this Mac yet' : (s.about || s.name))}" aria-pressed="${input.value.includes(phrase(s.name))}">${esc(s.name)}</button>`).join('')).join('');
    }

    let timer = 0;
    const soon = () => { clearTimeout(timer); timer = setTimeout(render, 120); };
    document.addEventListener('input', (e) => { if (e.target && e.target.id === 'input') soon(); });
    document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#mention-toggles, .channel-sidebar-row, #mention-menu')) setTimeout(render, 200); });
    window.addEventListener('load', () => setTimeout(render, 1500));
    window.scRenderSkillRow = render;
})();
