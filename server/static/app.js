let currentManga = null;
let currentChapters = [];
let selectedChapterIds = new Set();
let downloadPollInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadProviders();
    loadConfig();
    startDownloadStatusPolling();
    loadLibrary();
    initConverter();

    document.getElementById('search-form').addEventListener('submit', (e) => {
        e.preventDefault();
        performSearch();
    });

    document.getElementById('btn-select-all').addEventListener('click', selectAllChapters);
    document.getElementById('btn-deselect-all').addEventListener('click', deselectAllChapters);
    document.getElementById('btn-apply-range').addEventListener('click', applyChapterRange);
    document.getElementById('btn-start-download').addEventListener('click', startDownloadJob);
    document.getElementById('btn-cancel-download').addEventListener('click', cancelDownloadJob);
    document.getElementById('btn-back-to-results').addEventListener('click', () => {
        document.getElementById('detail-view').classList.remove('active');
        document.getElementById('results-section').style.display = 'block';
    });
    document.getElementById('btn-refresh-library').addEventListener('click', loadLibrary);
    document.getElementById('settings-form').addEventListener('submit', saveConfig);
});

// Tab Navigation
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetId = btn.dataset.tab;
            tabBtns.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

            btn.classList.add('active');
            const targetContent = document.getElementById(targetId);
            if (targetContent) targetContent.classList.add('active');

            if (targetId === 'tab-library') {
                loadLibrary();
            }
        });
    });
}

function switchTab(tabId) {
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (btn) btn.click();
}

// Load Available Providers
async function loadProviders() {
    try {
        const resp = await fetch('/api/providers');
        const data = await resp.json();
        const select = document.getElementById('search-provider');
        select.innerHTML = '<option value="all">🌐 All Sources</option>';
        data.providers.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error('Failed to load providers:', err);
    }
}

// Search
async function performSearch() {
    const query = document.getElementById('search-input').value.trim();
    const provider = document.getElementById('search-provider').value;
    if (!query) return;

    const btn = document.getElementById('search-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Searching...';
    btn.disabled = true;

    const resultsGrid = document.getElementById('results-grid');
    resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2rem;">Searching across sources...</div>';
    document.getElementById('results-section').style.display = 'block';
    document.getElementById('detail-view').classList.remove('active');

    try {
        // If it's a direct URL or ID resolve directly
        if (query.startsWith('http://') || query.startsWith('https://')) {
            const resolveResp = await fetch('/api/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query_or_url: query, provider: provider !== 'all' ? provider : null })
            });
            if (resolveResp.ok) {
                const data = await resolveResp.json();
                btn.innerHTML = originalText;
                btn.disabled = false;
                showMangaDetails(data.manga, data.provider, data.chapters);
                return;
            }
        }

        const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}&provider=${encodeURIComponent(provider)}`);
        const data = await resp.json();

        resultsGrid.innerHTML = '';
        if (!data.results || data.results.length === 0) {
            resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2rem;">No manga found. Try another query or paste a URL directly.</div>';
            return;
        }

        data.results.forEach(manga => {
            const card = document.createElement('div');
            card.className = 'manga-card';

            const coverUrl = manga.cover_url || 'https://via.placeholder.com/240x360?text=No+Cover';
            card.innerHTML = `
                <div class="manga-cover-wrap">
                    <img src="${coverUrl}" class="manga-cover-img" alt="${manga.title}" onerror="this.src='https://via.placeholder.com/240x360?text=Cover+Not+Found'">
                    <span class="provider-badge">${manga.provider}</span>
                </div>
                <div class="manga-card-info">
                    <div class="manga-card-title" title="${manga.title}">${manga.title}</div>
                    <div class="manga-card-meta">
                        <span>${manga.status || 'Manga'}</span>
                        <span>${manga.latest_chapter ? 'Ch. ' + manga.latest_chapter : ''}</span>
                    </div>
                </div>
            `;
            card.addEventListener('click', () => loadMangaAndChapters(manga));
            resultsGrid.appendChild(card);
        });

    } catch (err) {
        resultsGrid.innerHTML = `<div style="color:var(--danger);grid-column:1/-1;text-align:center;padding:2rem;">Error: ${err.message}</div>`;
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// Load Manga details and chapter list
async function loadMangaAndChapters(manga) {
    const detailView = document.getElementById('detail-view');
    detailView.classList.add('active');
    document.getElementById('results-section').style.display = 'none';

    document.getElementById('detail-title').textContent = manga.title;
    document.getElementById('detail-provider').textContent = manga.provider.toUpperCase();
    document.getElementById('detail-cover').src = manga.cover_url || 'https://via.placeholder.com/240x360?text=No+Cover';
    document.getElementById('detail-desc').textContent = manga.description || 'No description provided.';
    document.getElementById('chapters-grid').innerHTML = '<div style="color:var(--text-muted);padding:1rem;">Fetching chapters...</div>';
    document.getElementById('selected-count-badge').textContent = 'Loading...';

    currentManga = manga;
    currentChapters = [];
    selectedChapterIds.clear();

    try {
        const resp = await fetch(`/api/manga/${manga.provider}/${encodeURIComponent(manga.id)}/chapters`);
        const data = await resp.json();
        currentChapters = data.chapters || [];
        renderChaptersGrid();
    } catch (err) {
        document.getElementById('chapters-grid').innerHTML = `<div style="color:var(--danger);padding:1rem;">Failed to load chapters: ${err.message}</div>`;
    }
}

function showMangaDetails(manga, provider, chapters) {
    manga.provider = provider;
    currentManga = manga;
    currentChapters = chapters;
    selectedChapterIds.clear();

    const detailView = document.getElementById('detail-view');
    detailView.classList.add('active');
    document.getElementById('results-section').style.display = 'none';

    document.getElementById('detail-title').textContent = manga.title;
    document.getElementById('detail-provider').textContent = provider.toUpperCase();
    document.getElementById('detail-cover').src = manga.cover_url || 'https://via.placeholder.com/240x360?text=No+Cover';
    document.getElementById('detail-desc').textContent = manga.description || 'No description provided.';

    renderChaptersGrid();
}

function renderChaptersGrid() {
    const container = document.getElementById('chapters-grid');
    container.innerHTML = '';

    if (currentChapters.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted);padding:1rem;">No chapters found.</div>';
        updateSelectionCount();
        return;
    }

    currentChapters.forEach(chap => {
        const item = document.createElement('div');
        item.className = 'chapter-item' + (selectedChapterIds.has(chap.id) ? ' selected' : '');
        item.innerHTML = `
            <input type="checkbox" ${selectedChapterIds.has(chap.id) ? 'checked' : ''}>
            <span style="font-weight:600;">Ch. ${chap.chapter_num}</span>
        `;

        const chk = item.querySelector('input');
        item.addEventListener('click', (e) => {
            if (e.target !== chk) {
                chk.checked = !chk.checked;
            }
            if (chk.checked) {
                selectedChapterIds.add(chap.id);
                item.classList.add('selected');
            } else {
                selectedChapterIds.delete(chap.id);
                item.classList.remove('selected');
            }
            updateSelectionCount();
        });

        container.appendChild(item);
    });

    updateSelectionCount();
}

function selectAllChapters() {
    currentChapters.forEach(c => selectedChapterIds.add(c.id));
    renderChaptersGrid();
}

function deselectAllChapters() {
    selectedChapterIds.clear();
    renderChaptersGrid();
}

function applyChapterRange() {
    const fromVal = parseFloat(document.getElementById('range-from').value);
    const toVal = parseFloat(document.getElementById('range-to').value);

    if (isNaN(fromVal) || isNaN(toVal)) {
        alert('Please specify valid numbers for range');
        return;
    }

    const minVal = Math.min(fromVal, toVal);
    const maxVal = Math.max(fromVal, toVal);

    selectedChapterIds.clear();
    currentChapters.forEach(c => {
        const num = parseFloat(c.chapter_num);
        if (!isNaN(num) && num >= minVal && num <= maxVal) {
            selectedChapterIds.add(c.id);
        }
    });

    renderChaptersGrid();
}

function updateSelectionCount() {
    const badge = document.getElementById('selected-count-badge');
    badge.textContent = `${selectedChapterIds.size} of ${currentChapters.length} selected`;
    document.getElementById('btn-start-download').disabled = (selectedChapterIds.size === 0);
}

// Start Download Job
async function startDownloadJob() {
    if (selectedChapterIds.size === 0) return;

    const payload = {
        provider: currentManga.provider,
        manga_id: currentManga.id,
        manga_title: currentManga.title,
        manga_cover: currentManga.cover_url || '',
        selected_chapter_ids: Array.from(selectedChapterIds),
        chapters: currentChapters,
        save_cbz: document.getElementById('opt-cbz').checked,
        save_pdf: document.getElementById('opt-pdf').checked,
        save_images: document.getElementById('opt-images').checked,
        combine_cbz: document.getElementById('opt-combine').checked,
        clean_temp: document.getElementById('opt-clean-temp').checked,
    };

    try {
        const resp = await fetch('/api/download/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const err = await resp.json();
            alert(`Error: ${err.detail || 'Could not start download'}`);
            return;
        }

        switchTab('tab-downloads');
    } catch (err) {
        alert(`Failed: ${err.message}`);
    }
}

async function cancelDownloadJob() {
    try {
        await fetch('/api/download/cancel', { method: 'POST' });
    } catch (err) {
        console.error('Cancel request failed:', err);
    }
}

// Download Polling
function startDownloadStatusPolling() {
    if (downloadPollInterval) clearInterval(downloadPollInterval);
    downloadPollInterval = setInterval(pollDownloadStatus, 1000);
}

async function pollDownloadStatus() {
    try {
        const resp = await fetch('/api/download/status');
        const state = await resp.json();

        const dot = document.getElementById('status-indicator-dot');
        const text = document.getElementById('status-indicator-text');
        dot.className = 'status-dot ' + state.status;
        text.textContent = state.status.toUpperCase();

        const activeTitle = document.getElementById('active-manga-title');
        const activeSub = document.getElementById('active-manga-sub');
        if (state.manga_title) {
            activeTitle.textContent = state.manga_title;
            activeSub.textContent = `Provider: ${state.provider} | Total chapters: ${state.total_chapters}`;
        } else {
            activeTitle.textContent = 'No active task';
            activeSub.textContent = 'Select a manga and chapters to begin downloading';
        }

        // Chapters Progress
        const chPercent = state.total_chapters > 0 ? (state.completed_chapters / state.total_chapters) * 100 : 0;
        document.getElementById('chapters-progress-fill').style.width = `${chPercent}%`;
        document.getElementById('chapters-progress-label').textContent = `${state.completed_chapters} / ${state.total_chapters} Chapters ${state.current_chapter ? '(Ch. ' + state.current_chapter + ')' : ''}`;

        // Pages Progress
        const pgPercent = state.total_pages > 0 ? (state.completed_pages / state.total_pages) * 100 : 0;
        document.getElementById('pages-progress-fill').style.width = `${pgPercent}%`;
        document.getElementById('pages-progress-label').textContent = `${state.completed_pages} / ${state.total_pages} Pages`;

        // Logs
        const terminal = document.getElementById('log-terminal');
        if (state.logs && state.logs.length > 0) {
            terminal.innerHTML = state.logs.map(l => `
                <div class="log-entry">
                    <span class="log-time">[${l.time}]</span>
                    <span class="log-${l.level}">${escapeHtml(l.message)}</span>
                </div>
            `).join('');
            terminal.scrollTop = terminal.scrollHeight;
        }

        document.getElementById('btn-cancel-download').disabled = (state.status !== 'running');

    } catch (err) {
        console.error('Polling error:', err);
    }
}

// Library Management
async function loadLibrary() {
    try {
        const resp = await fetch('/api/library');
        const data = await resp.json();

        document.getElementById('stat-archives-count').textContent = data.combined_archives.length;
        document.getElementById('stat-individual-count').textContent = data.individual_chapters.length;
        document.getElementById('stat-total-size').textContent = `${data.total_size_mb} MB`;
        document.getElementById('output-dir-path').textContent = data.output_dir;

        // Combined CBZs
        const archivesList = document.getElementById('combined-archives-list');
        archivesList.innerHTML = '';
        if (data.combined_archives.length === 0) {
            archivesList.innerHTML = '<div style="color:var(--text-muted);padding:1rem;">No combined CBZ archives found.</div>';
        } else {
            data.combined_archives.forEach(arc => {
                const card = document.createElement('div');
                card.className = 'archive-card';
                card.innerHTML = `
                    <div>
                        <div class="archive-title">📦 ${escapeHtml(arc.filename)}</div>
                        <div class="archive-meta">${arc.chapter_count} chapters (${arc.chapter_range}) • ${arc.size_mb} MB</div>
                    </div>
                    <div style="display:flex;gap:0.5rem;align-items:center;">
                        <button class="btn-secondary" onclick="convertLibraryFile('${escapeHtml(arc.filepath)}')">🔄 Convert to PDF</button>
                        <a href="/api/files/download?path=${encodeURIComponent(arc.filepath)}" class="btn-secondary" download>⬇ Download</a>
                    </div>
                `;
                archivesList.appendChild(card);
            });
        }

        // Individual Files (CBZ & PDF)
        const individualList = document.getElementById('individual-files-list');
        if (individualList) {
            individualList.innerHTML = '';
            if (!data.individual_chapters || data.individual_chapters.length === 0) {
                individualList.innerHTML = '<div style="color:var(--text-muted);padding:1rem;">No individual chapter files found.</div>';
            } else {
                data.individual_chapters.forEach(f => {
                    const isCbz = f.format === 'cbz';
                    const targetFormat = isCbz ? 'PDF' : 'CBZ';
                    const icon = isCbz ? '📦' : '📄';

                    const item = document.createElement('div');
                    item.className = 'archive-card';
                    item.innerHTML = `
                        <div>
                            <div class="archive-title">${icon} ${escapeHtml(f.filename)}</div>
                            <div class="archive-meta">Chapter ${f.chapter_num} • ${f.size_mb} MB • ${f.format.toUpperCase()}</div>
                        </div>
                        <div style="display:flex;gap:0.5rem;align-items:center;">
                            <button class="btn-secondary" onclick="convertLibraryFile('${escapeHtml(f.filepath)}')">🔄 Convert to ${targetFormat}</button>
                            <a href="/api/files/download?path=${encodeURIComponent(f.filepath)}" class="btn-secondary" download>⬇ Download</a>
                        </div>
                    `;
                    individualList.appendChild(item);
                });
            }
        }

        // Uncombined Folders (if any)
        const uncombinedBox = document.getElementById('uncombined-folders-section');
        const uncombinedList = document.getElementById('uncombined-list');
        uncombinedList.innerHTML = '';

        if (data.uncombined_folders && data.uncombined_folders.length > 0) {
            uncombinedBox.style.display = 'block';
            data.uncombined_folders.forEach(f => {
                const item = document.createElement('div');
                item.className = 'archive-card';
                item.innerHTML = `
                    <div>
                        <div class="archive-title">📁 ${escapeHtml(f.folder_name)}</div>
                        <div class="archive-meta">${f.image_count} images • ${f.size_mb} MB</div>
                    </div>
                `;
                uncombinedList.appendChild(item);
            });
            document.getElementById('btn-combine-uncombined').onclick = () => combineUncombinedFolders();
        } else {
            uncombinedBox.style.display = 'none';
        }

    } catch (err) {
        console.error('Failed to load library:', err);
    }
}

async function combineUncombinedFolders() {
    const mangaName = prompt('Enter the Manga Name for this combined CBZ:');
    if (!mangaName) return;

    try {
        const resp = await fetch('/api/library/combine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ manga_name: mangaName, clean_folders: true })
        });
        const res = await resp.json();
        if (resp.ok) {
            alert(`Combined archive created: ${res.file}`);
            loadLibrary();
        } else {
            alert(`Error: ${res.detail}`);
        }
    } catch (err) {
        alert(`Failed: ${err.message}`);
    }
}

// Config / Settings
async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const data = await resp.json();
        document.getElementById('cfg-output-dir').value = data.output_dir;
    } catch (err) {
        console.error('Config load failed:', err);
    }
}

async function saveConfig(e) {
    e.preventDefault();
    const newDir = document.getElementById('cfg-output-dir').value.trim();
    if (!newDir) return;

    try {
        const resp = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ output_dir: newDir })
        });
        if (resp.ok) {
            alert('Settings saved!');
            loadLibrary();
        }
    } catch (err) {
        alert(`Failed to save settings: ${err.message}`);
    }
}

// Converter Module
function initConverter() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('converter-file-input');
    if (!dropZone || !fileInput) return;

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.style.borderColor = 'var(--accent-color)';
            dropZone.style.background = 'rgba(99, 102, 241, 0.08)';
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropZone.style.borderColor = 'var(--border-color)';
            dropZone.style.background = 'var(--bg-card)';
        });
    });

    dropZone.addEventListener('drop', (e) => {
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleConverterUpload(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleConverterUpload(e.target.files[0]);
        }
    });
}

async function handleConverterUpload(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'cbz' && ext !== 'pdf') {
        alert('Please choose a .cbz or .pdf file.');
        return;
    }

    const targetFormat = (ext === 'cbz') ? 'PDF' : 'CBZ';
    const statusBox = document.getElementById('conversion-status');
    const statusMsg = document.getElementById('conversion-msg');

    statusBox.style.display = 'block';
    statusMsg.innerHTML = `<span class="spinner"></span> Converting <strong>${escapeHtml(file.name)}</strong> to ${targetFormat}... please wait`;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/convert/upload', {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Conversion failed');
        }

        const blob = await resp.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = downloadUrl;
        const outName = file.name.substring(0, file.name.lastIndexOf('.')) + '.' + targetFormat.toLowerCase();
        a.download = outName;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(downloadUrl);
        a.remove();

        statusMsg.innerHTML = `✅ Successfully converted <strong>${escapeHtml(file.name)}</strong> to <strong>${escapeHtml(outName)}</strong> and started download!`;
    } catch (err) {
        statusMsg.innerHTML = `❌ Conversion failed: ${escapeHtml(err.message)}`;
    }
}

async function convertLibraryFile(filepath) {
    const filename = filepath.split(/[\/\\]/).pop();
    const ext = filename.split('.').pop().toLowerCase();
    const targetFormat = (ext === 'cbz') ? 'PDF' : 'CBZ';

    if (!confirm(`Convert '${filename}' into a .${targetFormat.toLowerCase()} document?`)) return;

    try {
        const resp = await fetch('/api/convert/library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        });

        const res = await resp.json();
        if (resp.ok) {
            alert(`Conversion complete!\nNew file: ${res.converted_file}`);
            loadLibrary();
        } else {
            alert(`Conversion failed: ${res.detail}`);
        }
    } catch (err) {
        alert(`Error: ${err.message}`);
    }
}

function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
