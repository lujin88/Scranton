// Scranton: zoom and pan in the picture viewer (Lu, 11-18: "图片预览的时候不可以放大、缩小").
// Pinch or scroll to zoom at the pointer, drag to move, double-click for 100% <-> fit,
// + / - / 0 on the keyboard, and three buttons at the bottom. Zoom resets with each picture.
(function () {
    'use strict';
    const MIN = 1, MAX = 8;
    let z = 1, x = 0, y = 0, drag = null, moved = false;
    const modal = () => document.getElementById('image-modal');
    const img = () => { const m = modal(); return m && m.querySelector(':scope > img'); };
    const open = () => { const m = modal(); return m && !m.classList.contains('hidden'); };
    const icon = (n) => (window.scIcon ? window.scIcon(n, 16) : '');

    function apply() {
        const i = img();
        if (!i) return;
        if (z <= 1) { z = 1; x = 0; y = 0; }
        else {   // keep some of the picture on screen
            const r = i.getBoundingClientRect(), w = r.width / 2, h = r.height / 2;
            x = Math.max(-w, Math.min(w, x)); y = Math.max(-h, Math.min(h, y));
        }
        i.style.transform = z === 1 ? '' : `translate(${x}px, ${y}px) scale(${z})`;
        i.style.cursor = z > 1 ? (drag ? 'grabbing' : 'grab') : 'zoom-in';
        const pct = modal().querySelector('.sc-zoom-pct');
        if (pct) pct.textContent = Math.round(z * 100) + '%';
    }
    function zoomAt(nz, cx, cy) {
        const i = img();
        if (!i) return;
        nz = Math.max(MIN, Math.min(MAX, nz));
        if (cx != null) {   // keep the point under the pointer where it is
            const r = i.getBoundingClientRect();
            const px = cx - (r.left + r.width / 2), py = cy - (r.top + r.height / 2);
            x -= px * (nz / z - 1); y -= py * (nz / z - 1);
        }
        z = nz; apply();
    }
    function reset() { z = 1; x = 0; y = 0; drag = null; apply(); }

    function ensure() {
        const m = modal();
        if (!m || m.dataset.zoom) return;
        m.dataset.zoom = '1';
        const bar = document.createElement('div');
        bar.className = 'sc-zoom';
        bar.innerHTML = `<button type="button" data-z="out" aria-label="Zoom out" title="Zoom out (-)">${icon('subtract')}</button>`
            + `<button type="button" class="sc-zoom-pct" data-z="reset" aria-label="Reset zoom" title="Fit (0)">100%</button>`
            + `<button type="button" data-z="in" aria-label="Zoom in" title="Zoom in (+)">${icon('add')}</button>`;
        bar.addEventListener('click', (e) => {
            e.stopPropagation();
            const b = e.target.closest('button');
            if (!b) return;
            if (b.dataset.z === 'in') zoomAt(z * 1.5);
            else if (b.dataset.z === 'out') zoomAt(z / 1.5);
            else reset();
        });
        m.appendChild(bar);
        m.addEventListener('wheel', (e) => {
            if (!open()) return;
            e.preventDefault();
            zoomAt(z * Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002)), e.clientX, e.clientY);
        }, { passive: false });
        m.addEventListener('dblclick', (e) => {
            if (e.target !== img()) return;
            e.stopPropagation();
            if (z > 1) reset(); else zoomAt(2.5, e.clientX, e.clientY);
        });
        m.addEventListener('pointerdown', (e) => {
            if (e.target !== img() || z <= 1) return;
            e.preventDefault();
            drag = { px: e.clientX, py: e.clientY, x, y }; moved = false;
            e.target.setPointerCapture(e.pointerId); apply();
        });
        m.addEventListener('pointermove', (e) => {
            if (!drag) return;
            x = drag.x + e.clientX - drag.px; y = drag.y + e.clientY - drag.py;
            if (Math.abs(e.clientX - drag.px) + Math.abs(e.clientY - drag.py) > 4) moved = true;
            apply();
        });
        const end = () => { if (drag) { drag = null; apply(); } };
        m.addEventListener('pointerup', end);
        m.addEventListener('pointercancel', end);
        // A drag that ends over the backdrop must not close the viewer; zoomed in, a click on the
        // backdrop goes back to fit first.
        m.addEventListener('click', (e) => {
            if (moved) { moved = false; e.stopPropagation(); return; }
            if (e.target === m && z > 1) { e.stopPropagation(); reset(); }
        }, true);
        // A new picture (arrows) starts at fit.
        const i = img();
        if (i) new MutationObserver(reset).observe(i, { attributes: true, attributeFilter: ['src'] });
    }

    const orig = window.openImageModal;
    if (typeof orig === 'function') {
        window.openImageModal = function (...a) { const r = orig.apply(this, a); ensure(); reset(); return r; };
    }
    document.addEventListener('keydown', (e) => {
        if (!open() || e.metaKey || e.ctrlKey || e.altKey) return;
        if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomAt(z * 1.5); }
        else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomAt(z / 1.5); }
        else if (e.key === '0') { e.preventDefault(); reset(); }
    });
})();
