// Shared attachment display and upload/download handling for chat and jobs.
function attachmentIsImage(att) {
    return att.kind === 'image' || (!att.kind && /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(att.url || ''));
}

function attachmentSize(size) {
    if (!Number.isFinite(size)) return '';
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function attachmentMarkup(att, pending = false) {
    // Only local upload paths are links; filenames and types are untrusted labels.
    if (!/^\/uploads\/[a-zA-Z0-9_.-]+$/.test(att.url || '')) return '';
    const name = escapeHtml(att.name || 'Attachment').replace(/"/g, '&quot;');
    const url = escapeHtml(att.url);
    if (attachmentIsImage(att)) {
        // Scranton: click the picture or the expand button to see it full size.
        // A picture whose file is gone (deleted, or history restored without uploads) becomes a plain note.
        return `<span class="sc-img"><img src="${url}" alt="${name}" onclick="openImageModal('${url}')" title="${name}" onerror="this.parentElement.outerHTML='<span class=&quot;sc-img-gone&quot;>' + this.alt + ' · no longer on this Mac</span>'">`
            + (pending ? '' : `<button type="button" class="sc-img-x" aria-label="Expand ${name}" title="Expand" onclick="event.stopPropagation(); openImageModal('${url}')">`
            + '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 3H22V9H20V5H16V3ZM2 3H8V5H4V9H2V3ZM20 19V15H22V21H16V19H20ZM4 19H8V21H2V15H4V19Z"/></svg></button>')
            + '</span>';
    }
    const filename = att.name || '';
    const type = filename.lastIndexOf('.') > 0 ? filename.split('.').pop().toUpperCase() : 'FILE';
    const detail = [type, attachmentSize(att.size)].filter(Boolean).join(' · ');
    const info = `<span class="file-attachment-info">
            <span class="file-attachment-name">${name}</span>
            <span class="file-attachment-detail">${escapeHtml(detail)}</span>
        </span>`;
    if (pending) {
        // Grok-style card: page icon, name cut in the middle so the extension stays, size.
        const raw = filename || 'Attachment';
        const dot = raw.lastIndexOf('.');
        const ext = dot > 0 ? raw.slice(dot) : '';
        const base = ext ? raw.slice(0, -ext.length) : raw;
        return `<div class="file-attachment sc-pend" title="${name}"><span class="sc-pend-ic" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="file-attachment-info"><span class="file-attachment-name sc-pend-name"><span>${escapeHtml(base)}</span><span>${escapeHtml(ext)}</span></span>
            <span class="file-attachment-detail">${escapeHtml(attachmentSize(att.size) || type)}</span></span></div>`;
    }
    return `<a class="file-attachment" href="${url}" data-name="${name}" title="Download ${name}" aria-label="Download ${name}" onclick="downloadAttachment(event, this)">
        ${info}
        <svg class="file-download-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>
        </svg>
    </a>`;
}

function createAttachmentPreview(att, onRemove) {
    const wrap = document.createElement('div');
    wrap.className = 'attachment-preview';
    wrap.innerHTML = attachmentMarkup(att, true);
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'attachment-remove';
    remove.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 10.59L16.95 5.64L18.36 7.05L13.41 12L18.36 16.95L16.95 18.36L12 13.41L7.05 18.36L5.64 16.95L10.59 12L5.64 7.05L7.05 5.64L12 10.59Z"/></svg>';
    remove.title = `Remove ${att.name || 'attachment'}`;
    remove.setAttribute('aria-label', remove.title);
    remove.addEventListener('click', onRemove);
    wrap.appendChild(remove);
    return wrap;
}

async function downloadAttachment(event, link) {
    event.preventDefault();
    try {
        const response = await fetch(link.getAttribute('href'), {
            headers: { 'X-Session-Token': window.SESSION_TOKEN },
        });
        if (!response.ok) throw new Error('Download failed. Refresh the page and try again.');
        const url = URL.createObjectURL(await response.blob());
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = link.dataset.name || 'Attachment';
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
        alert(error.message);
    }
}

async function uploadAttachment(file) {
    const form = new FormData();
    form.append('file', file);
    // Multipart headers percent-escape quotes; keep the original display name.
    form.append('display_name', file.name);
    const response = await fetch('/api/upload', {
        method: 'POST', headers: { 'X-Session-Token': window.SESSION_TOKEN }, body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Upload failed. Please try again.');
    return data;
}

async function uploadFiles(files, job = false) {
    const destination = job ? activeJobId : activeChannel;
    const errors = [];
    for (const file of files) {
        const error = job ? await uploadJobImage(file, destination) : await uploadImage(file, destination);
        if (error) errors.push(error);
    }
    document.getElementById(job ? 'job-attachment-status' : 'attachment-status').textContent = errors.join(' ');
}
