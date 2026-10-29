// State variables
let currentManga = null;
let currentChapters = [];
let selectedChapterIds = new Set();
let downloadPollInterval = null;

let currentHGallery = null;
let currentHChapters = [];

let activeConversionJobId = null;
let conversionPollInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initReturnButtons();
    loadProviders();
    loadConfig();
    startDownloadStatusPolling();
    loadLibrary();
    initConverter();
    initHSearch();

    // Manga Search form
    document.getElementById('search-form').addEventListener('submit', (e) => {
        e.preventDefault();
        performMangaSearch();
    });

    // Manga Chapter selection buttons
    document.getElementById('btn-select-all').addEventListener('click', selectAllChapters);
    document.getElementById('btn-deselect-all').addEventListener('click', deselectAllChapters);
    document.getElementById('btn-apply-range').addEventListener('click', applyChapterRange);
    document.getElementById('btn-start-download').addEventListener('click', startMangaDownloadJob);
    document.getElementById('btn-cancel-download').addEventListener('click', cancelDownloadJob);

    // Custom Naming inputs
    const customNameEl = document.getElementById('opt-custom-name');
    if (customNameEl) customNameEl.addEventListener('input', updateNamingPreview);
    const includeRangeEl = document.getElementById('opt-include-range');
    if (includeRangeEl) includeRangeEl.addEventListener('change', updateNamingPreview);

    // Library buttons
    document.getElementById('btn-refresh-library').addEventListener('click', loadLibrary);
    document.getElementById('settings-form').addEventListener('submit', saveConfig);
});

// ==========================================
// 1. Navigation & Return Buttons
// ==========================================
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

            // Aura Theme transition animation when switching to H-Search
            if (targetId === 'tab-h-search') {
                document.body.classList.add('theme-aura-dark');
            } else {
                document.body.classList.remove('theme-aura-dark');
            }

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

function initReturnButtons() {
    // Return from Manga Detail to Search Results
    const backToResults = () => {
        document.getElementById('detail-view').classList.remove('active');
        document.getElementById('results-section').style.display = 'block';
    };
    document.getElementById('btn-back-to-results').addEventListener('click', backToResults);
    document.getElementById('btn-bottom-back').addEventListener('click', backToResults);

    // Return from H-Gallery Detail to Galleries Results
    document.getElementById('btn-back-to-h-results').addEventListener('click', () => {
        document.getElementById('h-detail-view').classList.remove('active');
        document.getElementById('h-results-section').style.display = 'block';
    });

    // Return from Active Downloads
    document.getElementById('btn-return-from-downloads').addEventListener('click', () => {
        switchTab('tab-search');
    });
    document.getElementById('btn-goto-library').addEventListener('click', () => {
        switchTab('tab-library');
    });

    // Return from Library
    document.getElementById('btn-return-library-to-search').addEventListener('click', () => {
        switchTab('tab-search');
    });

    // Return from Converter
    document.getElementById('btn-return-converter-to-search').addEventListener('click', () => {
        switchTab('tab-search');
    });
    document.getElementById('btn-goto-library-from-conv').addEventListener('click', () => {
        switchTab('tab-library');
    });
}


// ==========================================
// 2. Standard Manga Search & Chapter Selection
// ==========================================
async function loadProviders() {
    try {
        const resp = await fetch('/api/providers');
        const data = await resp.json();
        const select = document.getElementById('search-provider');
        select.innerHTML = '<option value="all">🌐 All Manga Sources</option>';
        data.providers.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = p.name;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error('Failed to load manga providers:', err);
    }
}

async function performMangaSearch() {
    const query = document.getElementById('search-input').value.trim();
    const provider = document.getElementById('search-provider').value;
    if (!query) return;

    const btn = document.getElementById('search-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Searching...';
    btn.disabled = true;

    const resultsGrid = document.getElementById('results-grid');
    resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2rem;">Searching manga sources...</div>';
    document.getElementById('results-section').style.display = 'block';
    document.getElementById('detail-view').classList.remove('active');

    try {
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
                    <img src="${coverUrl}" class="manga-cover-img" alt="${escapeHtml(manga.title)}" onerror="this.src='https://via.placeholder.com/240x360?text=Cover+Not+Found'">
                    <span class="provider-badge">${escapeHtml(manga.provider)}</span>
                </div>
                <div class="manga-card-info">
                    <div class="manga-card-title" title="${escapeHtml(manga.title)}">${escapeHtml(manga.title)}</div>
                    <div class="manga-card-meta">
                        <span>${escapeHtml(manga.status || 'Manga')}</span>
                        <span>${manga.latest_chapter ? 'Ch. ' + escapeHtml(manga.latest_chapter) : ''}</span>
                    </div>
                </div>
            `;
            card.addEventListener('click', () => loadMangaAndChapters(manga));
            resultsGrid.appendChild(card);
        });

    } catch (err) {
        resultsGrid.innerHTML = `<div style="color:var(--danger);grid-column:1/-1;text-align:center;padding:2rem;">Error: ${escapeHtml(err.message)}</div>`;
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

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
        document.getElementById('chapters-grid').innerHTML = `<div style="color:var(--danger);padding:1rem;">Failed to load chapters: ${escapeHtml(err.message)}</div>`;
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

    const customNameEl = document.getElementById('opt-custom-name');
    if (customNameEl) {
        customNameEl.value = '';
        customNameEl.placeholder = manga.title || 'Manga Title';
    }

    renderChaptersGrid();
    updateNamingPreview();
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
            <span style="font-weight:600;">Ch. ${escapeHtml(chap.chapter_num)}</span>
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

function updateNamingPreview() {
    if (!currentManga) return;
    const customNameEl = document.getElementById('opt-custom-name');
    const includeRangeEl = document.getElementById('opt-include-range');
    const previewArchiveEl = document.getElementById('naming-preview-archive');
    const previewChapterEl = document.getElementById('naming-preview-chapter');
    if (!previewArchiveEl || !previewChapterEl) return;

    const customName = customNameEl ? customNameEl.value.trim() : '';
    const baseName = customName || currentManga.title || 'Manga';
    const includeRange = includeRangeEl ? includeRangeEl.checked : true;

    let first = '1', last = '1';
    if (currentChapters && currentChapters.length > 0) {
        const selected = currentChapters.filter(c => selectedChapterIds.has(c.id));
        if (selected.length > 0) {
            const nums = selected.map(c => parseFloat(c.chapter_num)).filter(n => !isNaN(n)).sort((a,b) => a - b);
            if (nums.length > 0) {
                first = nums[0].toString();
                last = nums[nums.length - 1].toString();
            } else {
                first = selected[0].chapter_num || '1';
                last = selected[selected.length - 1].chapter_num || first;
            }
        }
    }

    const archiveName = includeRange ? `${baseName}_Chapter_${first}-${last}.cbz` : `${baseName}.cbz`;
    const chapterName = `${baseName} - Chapter ${first}.pdf`;

    previewArchiveEl.textContent = `📦 Archive: ${archiveName}`;
    previewChapterEl.textContent = `📄 Chapter: ${chapterName}`;
}

function updateSelectionCount() {
    const badge = document.getElementById('selected-count-badge');
    badge.textContent = `${selectedChapterIds.size} of ${currentChapters.length} selected`;
    document.getElementById('btn-start-download').disabled = (selectedChapterIds.size === 0);
    updateNamingPreview();
}

async function startMangaDownloadJob() {
    if (selectedChapterIds.size === 0) return;

    const customNameEl = document.getElementById('opt-custom-name');
    const includeRangeEl = document.getElementById('opt-include-range');
    const customTitle = customNameEl && customNameEl.value.trim() ? customNameEl.value.trim() : undefined;
    const includeRange = includeRangeEl ? includeRangeEl.checked : true;

    const payload = {
        provider: currentManga.provider,
        manga_id: currentManga.id,
        manga_title: currentManga.title,
        custom_title: customTitle,
        include_range: includeRange,
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


// ==========================================
// 3. Dedicated H / Doujinshi Search (nhentai)
// ==========================================
function initHSearch() {
    const form = document.getElementById('h-search-form');
    if (!form) return;

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = document.getElementById('h-search-input').value.trim();
        if (query) performHSearch(query);
    });

    // Quick tag pills
    document.querySelectorAll('.quick-tag-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            const q = pill.dataset.query;
            document.getElementById('h-search-input').value = q;
            performHSearch(q);
        });
    });

    // H-Download action buttons
    document.getElementById('btn-h-download-cbz').addEventListener('click', () => startHDownload(true, false));
    document.getElementById('btn-h-download-pdf').addEventListener('click', () => startHDownload(false, true));
    document.getElementById('btn-h-download-both').addEventListener('click', () => startHDownload(true, true));
}

async function performHSearch(query) {
    const btn = document.getElementById('h-search-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span class="spinner"></span> Searching...';
    btn.disabled = true;

    const providerSelect = document.getElementById('h-search-provider');
    const provider = providerSelect ? providerSelect.value : 'all';

    const resultsGrid = document.getElementById('h-results-grid');
    resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2rem;">Searching doujin galleries...</div>';
    document.getElementById('h-results-section').style.display = 'block';
    document.getElementById('h-detail-view').classList.remove('active');

    try {
        // Direct ID or URL resolution
        if (/^\d{4,7}$/.test(query) || query.includes('nhentai.net') || query.includes('cin.wtf') || query.includes('cin.blue')) {
            const resolveResp = await fetch('/api/h/resolve', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query_or_url: query, provider: provider !== 'all' ? provider : null })
            });
            if (resolveResp.ok) {
                const data = await resolveResp.json();
                btn.innerHTML = originalText;
                btn.disabled = false;
                showHGalleryDetails(data.gallery, data.chapters, data.provider);
                return;
            }
        }

        const resp = await fetch(`/api/h/search?q=${encodeURIComponent(query)}&provider=${encodeURIComponent(provider)}&limit=24`);
        const data = await resp.json();

        resultsGrid.innerHTML = '';
        if (!data.results || data.results.length === 0) {
            resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2rem;">No galleries found. Try another query or enter a 6-digit ID.</div>';
            return;
        }

        data.results.forEach(gal => {
            const card = document.createElement('div');
            card.className = 'manga-card';

            const coverUrl = gal.cover_url || 'https://via.placeholder.com/240x360?text=18+Gallery';
            const badgeBg = gal.provider === 'cin' ? 'linear-gradient(135deg, #8b5cf6, #ec4899)' : 'linear-gradient(135deg, #ec4899, #f43f5e)';
            const provLabel = gal.provider ? gal.provider.toUpperCase() : '18+';

            card.innerHTML = `
                <div class="manga-cover-wrap">
                    <img src="${coverUrl}" class="manga-cover-img" alt="${escapeHtml(gal.title)}" onerror="this.src='https://via.placeholder.com/240x360?text=No+Cover'">
                    <span class="provider-badge" style="background:${badgeBg};">${provLabel} #${escapeHtml(gal.id)}</span>
                </div>
                <div class="manga-card-info">
                    <div class="manga-card-title" title="${escapeHtml(gal.title)}">${escapeHtml(gal.title)}</div>
                    <div class="manga-card-meta">
                        <span style="color:#ec4899;font-weight:600;">${provLabel}</span>
                        <span>${escapeHtml(gal.description || '')}</span>
                    </div>
                </div>
            `;
            card.addEventListener('click', () => loadHGallery(gal.id, gal.provider));
            resultsGrid.appendChild(card);
        });

    } catch (err) {
        resultsGrid.innerHTML = `<div style="color:var(--danger);grid-column:1/-1;text-align:center;padding:2rem;">Error: ${escapeHtml(err.message)}</div>`;
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

async function loadHGallery(gid, provider) {
    try {
        const resp = await fetch('/api/h/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query_or_url: String(gid), provider: provider || null })
        });
        if (resp.ok) {
            const data = await resp.json();
            showHGalleryDetails(data.gallery, data.chapters, data.provider);
        }
    } catch (err) {
        alert('Failed to load gallery: ' + err.message);
    }
}

function showHGalleryDetails(gallery, chapters, providerName) {
    currentHGallery = gallery;
    currentHChapters = chapters;

    const detailView = document.getElementById('h-detail-view');
    detailView.classList.add('active');
    document.getElementById('h-results-section').style.display = 'none';

    document.getElementById('h-detail-title').textContent = gallery.title;
    document.getElementById('h-detail-id').textContent = `ID: #${gallery.id}`;
    if (document.getElementById('h-detail-provider')) {
        document.getElementById('h-detail-provider').textContent = (providerName || gallery.provider || 'H-SOURCE').toUpperCase();
    }
    document.getElementById('h-detail-cover').src = gallery.cover_url || 'https://via.placeholder.com/240x360?text=No+Cover';
    document.getElementById('h-detail-pages').textContent = gallery.description || `${chapters[0]?.page_count || 1} pages`;

    const tagsContainer = document.getElementById('h-detail-tags');
    tagsContainer.innerHTML = '';
    if (gallery.description && gallery.description.startsWith('Tags:')) {
        const tags = gallery.description.replace('Tags:', '').split(',');
        tags.forEach(t => {
            const pill = document.createElement('span');
            pill.className = 'h-tag-item';
            pill.textContent = t.trim();
            tagsContainer.appendChild(pill);
        });
    }
}

async function startHDownload(saveCbz, savePdf) {
    if (!currentHGallery || !currentHChapters || currentHChapters.length === 0) return;

    const chap = currentHChapters[0];
    const customTitle = (document.getElementById('h-custom-name')?.value.trim()) || undefined;
    const provName = currentHGallery.provider || 'nhentai';
    const payload = {
        provider: provName,
        manga_id: currentHGallery.id,
        manga_title: `[${currentHGallery.id}] ${currentHGallery.title}`,
        custom_title: customTitle,
        include_range: false,
        manga_cover: currentHGallery.cover_url || '',
        selected_chapter_ids: [chap.id],
        chapters: currentHChapters,
        save_cbz: saveCbz,
        save_pdf: savePdf,
        save_images: false,
        combine_cbz: false,
        clean_temp: true,
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


// ==========================================
// 4. Download Manager & Immediate Cancellation
// ==========================================
async function cancelDownloadJob() {
    const btn = document.getElementById('btn-cancel-download');
    btn.innerHTML = '<span class="spinner"></span> Cancelling...';
    btn.disabled = true;

    try {
        await fetch('/api/download/cancel', { method: 'POST' });
        pollDownloadStatus();
    } catch (err) {
        console.error('Cancel request failed:', err);
    }
}

function startDownloadStatusPolling() {
    if (downloadPollInterval) clearInterval(downloadPollInterval);
    downloadPollInterval = setInterval(pollDownloadStatus, 1000);
}

let lastDownloadStatus = null;

async function pollDownloadStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3500);
        const resp = await fetch('/api/download/status', { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!resp.ok) return;
        const state = await resp.json();

        const dot = document.getElementById('status-indicator-dot');
        const text = document.getElementById('status-indicator-text');
        dot.className = 'status-dot ' + (state.status || 'idle');
        text.textContent = (state.status || 'IDLE').toUpperCase();

        const activeTitle = document.getElementById('active-manga-title');
        const activeSub = document.getElementById('active-manga-sub');
        const activeStage = document.getElementById('active-manga-stage');

        if (state.manga_title) {
            activeTitle.textContent = state.manga_title;
            activeSub.textContent = `Provider: ${state.provider || 'Unknown'} | Total chapters: ${state.total_chapters}`;
        } else {
            activeTitle.textContent = 'No active task';
            activeSub.textContent = 'Select a manga or gallery to begin downloading';
        }

        if (activeStage) {
            activeStage.textContent = state.stage || (state.status === 'running' ? 'Downloading...' : '');
            if (state.status === 'completed') {
                activeStage.style.color = 'var(--success)';
            } else if (state.status === 'error') {
                activeStage.style.color = 'var(--danger)';
            } else if (state.status === 'cancelled') {
                activeStage.style.color = 'var(--warning)';
            } else {
                activeStage.style.color = 'var(--accent-color)';
            }
        }

        // Chapters Progress
        const chPercent = state.total_chapters > 0 ? (state.completed_chapters / state.total_chapters) * 100 : 0;
        document.getElementById('chapters-progress-fill').style.width = `${chPercent}%`;
        let chLabel = `${state.completed_chapters} / ${state.total_chapters} Chapters`;
        if (state.status === 'completed' && state.total_chapters > 0) {
            chLabel = `All ${state.total_chapters} Chapters Completed!`;
        } else if (state.current_chapter) {
            chLabel += ` (Ch. ${state.current_chapter})`;
        }
        document.getElementById('chapters-progress-label').textContent = chLabel;

        // Pages Progress
        const pgPercent = state.total_pages > 0 ? (state.completed_pages / state.total_pages) * 100 : 0;
        document.getElementById('pages-progress-fill').style.width = `${pgPercent}%`;
        let pgLabel = `${state.completed_pages} / ${state.total_pages} Pages`;
        if (state.status === 'completed' && state.total_pages > 0) {
            pgLabel = `${state.completed_pages} / ${state.total_pages} Pages (Done)`;
        }
        document.getElementById('pages-progress-label').textContent = pgLabel;

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

        // If newly finished, refresh library tab so downloaded files appear immediately
        if (lastDownloadStatus === 'running' && state.status === 'completed') {
            loadLibrary();
        }
        lastDownloadStatus = state.status;

        // Cancel Button state
        const cancelBtn = document.getElementById('btn-cancel-download');
        if (state.status === 'running') {
            cancelBtn.disabled = false;
            cancelBtn.innerHTML = '⏹ Cancel Download';
        } else {
            cancelBtn.disabled = true;
            if (state.status === 'cancelled') {
                cancelBtn.innerHTML = 'Cancelled';
            } else {
                cancelBtn.innerHTML = '⏹ Cancel Download';
            }
        }

    } catch (err) {
        if (err.name !== 'AbortError') {
            console.error('Polling error:', err);
        }
    }
}


// ==========================================
// 5. CBZ ⇄ PDF Converter (with Live Progress & Cancel)
// ==========================================
function initConverter() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('converter-file-input');
    const cancelBtn = document.getElementById('btn-cancel-conversion');

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
            uploadAndConvertFile(files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadAndConvertFile(e.target.files[0]);
        }
    });

    cancelBtn.addEventListener('click', () => {
        if (activeConversionJobId) {
            cancelActiveConversion(activeConversionJobId);
        }
    });
}

async function uploadAndConvertFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'cbz' && ext !== 'pdf') {
        alert('Please choose a .cbz or .pdf file.');
        return;
    }

    const container = document.getElementById('converter-progress-container');
    const fileNameEl = document.getElementById('conv-file-name');
    const badgeEl = document.getElementById('conv-target-badge');
    const stageEl = document.getElementById('conv-stage-text');
    const percentEl = document.getElementById('conv-percent-text');
    const fillEl = document.getElementById('conv-progress-fill');
    const downloadBtn = document.getElementById('btn-download-converted');
    const cancelBtn = document.getElementById('btn-cancel-conversion');

    container.style.display = 'block';
    fileNameEl.textContent = file.name;
    badgeEl.textContent = (ext === 'cbz') ? 'CONVERTING TO PDF' : 'CONVERTING TO CBZ';
    stageEl.textContent = 'Uploading file to server...';
    percentEl.textContent = '0%';
    fillEl.style.width = '0%';
    downloadBtn.style.display = 'none';
    cancelBtn.disabled = false;
    cancelBtn.style.display = 'inline-block';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const resp = await fetch('/api/convert/start-upload', {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Upload failed');
        }

        const data = await resp.json();
        activeConversionJobId = data.job_id;
        startConversionPolling(data.job_id);

    } catch (err) {
        stageEl.textContent = 'Error: ' + err.message;
        cancelBtn.style.display = 'none';
    }
}

function startConversionPolling(jobId) {
    if (conversionPollInterval) clearInterval(conversionPollInterval);

    conversionPollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`/api/convert/status/${jobId}`);
            if (!resp.ok) return;

            const job = await resp.json();
            const stageEl = document.getElementById('conv-stage-text');
            const percentEl = document.getElementById('conv-percent-text');
            const fillEl = document.getElementById('conv-progress-fill');
            const downloadBtn = document.getElementById('btn-download-converted');
            const cancelBtn = document.getElementById('btn-cancel-conversion');

            stageEl.textContent = job.stage;
            percentEl.textContent = `${job.percent}%`;
            fillEl.style.width = `${job.percent}%`;

            if (job.status === 'completed') {
                clearInterval(conversionPollInterval);
                activeConversionJobId = null;
                cancelBtn.style.display = 'none';

                const dlUrl = `/api/convert/download/${jobId}`;
                downloadBtn.href = dlUrl;
                downloadBtn.style.display = 'inline-block';

                // Trigger automatic download
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = dlUrl;
                document.body.appendChild(a);
                a.click();
                a.remove();
            }
            else if (job.status === 'cancelled') {
                clearInterval(conversionPollInterval);
                activeConversionJobId = null;
                cancelBtn.style.display = 'none';
                stageEl.textContent = 'Conversion was cancelled.';
            }
            else if (job.status === 'error') {
                clearInterval(conversionPollInterval);
                activeConversionJobId = null;
                cancelBtn.style.display = 'none';
                stageEl.textContent = 'Conversion failed: ' + (job.error_message || 'Unknown error');
            }

        } catch (err) {
            console.error('Error polling conversion:', err);
        }
    }, 600);
}

async function cancelActiveConversion(jobId) {
    const cancelBtn = document.getElementById('btn-cancel-conversion');
    cancelBtn.textContent = 'Cancelling...';
    cancelBtn.disabled = true;

    try {
        await fetch(`/api/convert/cancel/${jobId}`, { method: 'POST' });
    } catch (err) {
        console.error('Cancel failed:', err);
    }
}

async function convertLibraryFile(filepath) {
    const filename = filepath.split(/[\/\\]/).pop();
    const ext = filename.split('.').pop().toLowerCase();
    const targetFormat = (ext === 'cbz') ? 'PDF' : 'CBZ';

    if (!confirm(`Convert '${filename}' into a .${targetFormat.toLowerCase()} file?`)) return;

    try {
        const resp = await fetch('/api/convert/start-library', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filepath: filepath })
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || 'Could not start conversion');
        }

        const data = await resp.json();
        switchTab('tab-converter');

        const container = document.getElementById('converter-progress-container');
        document.getElementById('conv-file-name').textContent = filename;
        document.getElementById('conv-target-badge').textContent = `TO ${targetFormat}`;
        container.style.display = 'block';

        activeConversionJobId = data.job_id;
        startConversionPolling(data.job_id);

    } catch (err) {
        alert('Failed: ' + err.message);
    }
}


// ==========================================
// 6. Library Management
// ==========================================
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
                            <div class="archive-meta">
                                ${f.series_name && f.series_name !== 'General' ? `<span class="tag" style="background:rgba(99,102,241,0.2);color:var(--accent-color);font-weight:600;margin-right:0.4rem;">${escapeHtml(f.series_name)}</span>` : ''}
                                Chapter ${escapeHtml(f.chapter_num)}${f.chapter_title ? ' - ' + escapeHtml(f.chapter_title) : ''} • ${f.size_mb} MB • ${f.format.toUpperCase()}
                            </div>
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


// ==========================================
// 7. Config / Settings
// ==========================================
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

function escapeHtml(text) {
    if (!text) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
