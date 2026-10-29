// Interactive frontend logic with real-time download monitoring, failed page recovery, and chapter filtering
let currentManga = null;
let currentChapters = [];
let selectedChapterIds = new Set();
let chapterSortAsc = true;
let chapterFilterText = '';
let downloadPollInterval = null;

let currentHGallery = null;
let currentHChapters = [];

let activeConversionJobId = null;
let conversionPollInterval = null;

let logFilterMode = 'all';
let cachedLogs = [];
let logClearMarker = null;
let lastLogSignature = '';
let lastFailedSignature = '';
let lastDownloadStatus = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initReturnButtons();
    loadProviders();
    loadConfig();
    startDownloadStatusPolling();
    loadLibrary();
    initConverter();
    initHSearch();
    initFailedRecoveryControls();
    initLogControls();
    initReader();

    // Manga Search form
    const searchForm = document.getElementById('search-form');
    if (searchForm) {
        searchForm.addEventListener('submit', (e) => {
            e.preventDefault();
            performMangaSearch();
        });
    }

    // Manga Chapter selection buttons
    const btnSelectAll = document.getElementById('btn-select-all');
    if (btnSelectAll) btnSelectAll.addEventListener('click', selectAllChapters);

    const btnDeselectAll = document.getElementById('btn-deselect-all');
    if (btnDeselectAll) btnDeselectAll.addEventListener('click', deselectAllChapters);

    const btnInvert = document.getElementById('btn-invert-selection');
    if (btnInvert) btnInvert.addEventListener('click', invertChapterSelection);

    const btnToggleSort = document.getElementById('btn-toggle-sort');
    if (btnToggleSort) btnToggleSort.addEventListener('click', toggleChapterSort);

    const filterInput = document.getElementById('filter-chapters-input');
    if (filterInput) {
        filterInput.addEventListener('input', (e) => {
            chapterFilterText = e.target.value.trim().toLowerCase();
            renderChaptersGrid();
        });
    }

    const btnApplyRange = document.getElementById('btn-apply-range');
    if (btnApplyRange) btnApplyRange.addEventListener('click', applyChapterRange);

    const btnStartDownload = document.getElementById('btn-start-download');
    if (btnStartDownload) btnStartDownload.addEventListener('click', startMangaDownloadJob);

    const btnCancelDownload = document.getElementById('btn-cancel-download');
    if (btnCancelDownload) btnCancelDownload.addEventListener('click', cancelDownloadJob);

    // Custom Naming inputs
    const customNameEl = document.getElementById('opt-custom-name');
    if (customNameEl) customNameEl.addEventListener('input', updateNamingPreview);
    const includeRangeEl = document.getElementById('opt-include-range');
    if (includeRangeEl) includeRangeEl.addEventListener('change', updateNamingPreview);

    // Library buttons
    const btnRefreshLib = document.getElementById('btn-refresh-library');
    if (btnRefreshLib) btnRefreshLib.addEventListener('click', () => loadLibrary());

    const btnCheckUpdates = document.getElementById('btn-check-library-updates');
    if (btnCheckUpdates) btnCheckUpdates.addEventListener('click', () => checkLibraryUpdates(true));

    const btnUpdateAll = document.getElementById('btn-update-all-series');
    if (btnUpdateAll) btnUpdateAll.addEventListener('click', handleUpdateAllSeries);

    const btnCloseModal = document.getElementById('btn-close-update-modal');
    if (btnCloseModal) btnCloseModal.addEventListener('click', closeUpdateModal);

    const btnCancelModal = document.getElementById('btn-cancel-update-modal');
    if (btnCancelModal) btnCancelModal.addEventListener('click', closeUpdateModal);

    const btnConfirmModal = document.getElementById('btn-confirm-update-modal');
    if (btnConfirmModal) btnConfirmModal.addEventListener('click', executeModalUpdate);

    const settingsForm = document.getElementById('settings-form');
    if (settingsForm) settingsForm.addEventListener('submit', saveConfig);
});

// ==========================================
// Toast Notification Utility
// ==========================================
function showToast(message, type = 'info', duration = 3800) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    let icon = 'ℹ️';
    if (type === 'success') icon = '✅';
    else if (type === 'error') icon = '❌';
    else if (type === 'warning') icon = '⚠️';

    toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(12px)';
        setTimeout(() => toast.remove(), 320);
    }, duration);
}

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
    const backToResults = () => {
        document.getElementById('detail-view').classList.remove('active');
        document.getElementById('results-section').style.display = 'block';
    };

    const btnBack = document.getElementById('btn-back-to-results');
    if (btnBack) btnBack.addEventListener('click', backToResults);

    const btnBottomBack = document.getElementById('btn-bottom-back');
    if (btnBottomBack) btnBottomBack.addEventListener('click', backToResults);

    const btnBackH = document.getElementById('btn-back-to-h-results');
    if (btnBackH) {
        btnBackH.addEventListener('click', () => {
            document.getElementById('h-detail-view').classList.remove('active');
            document.getElementById('h-results-section').style.display = 'block';
        });
    }

    const btnReturnDownloads = document.getElementById('btn-return-from-downloads');
    if (btnReturnDownloads) {
        btnReturnDownloads.addEventListener('click', () => switchTab('tab-search'));
    }

    const btnGotoLib = document.getElementById('btn-goto-library');
    if (btnGotoLib) {
        btnGotoLib.addEventListener('click', () => switchTab('tab-library'));
    }

    const btnReturnLib = document.getElementById('btn-return-library-to-search');
    if (btnReturnLib) {
        btnReturnLib.addEventListener('click', () => switchTab('tab-search'));
    }

    const btnReturnConv = document.getElementById('btn-return-converter-to-search');
    if (btnReturnConv) {
        btnReturnConv.addEventListener('click', () => switchTab('tab-search'));
    }

    const btnGotoLibConv = document.getElementById('btn-goto-library-from-conv');
    if (btnGotoLibConv) {
        btnGotoLibConv.addEventListener('click', () => switchTab('tab-library'));
    }
}

// ==========================================
// 2. Standard Manga Search & Chapter Selection
// ==========================================
async function loadProviders() {
    try {
        const resp = await fetch('/api/providers');
        const data = await resp.json();
        const select = document.getElementById('search-provider');
        if (!select) return;

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
    btn.innerHTML = '<span>⏳</span> Searching...';
    btn.disabled = true;

    const resultsGrid = document.getElementById('results-grid');
    resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2.5rem;">Searching manga sources...</div>';
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
            resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2.5rem;">No manga found. Try another query or paste a series URL directly.</div>';
            return;
        }

        data.results.forEach(manga => {
            const card = document.createElement('div');
            card.className = 'manga-card';

            const coverUrl = manga.cover_url || 'https://via.placeholder.com/240x360?text=No+Cover';
            card.innerHTML = `
                <div class="manga-card-cover-wrap">
                    <img src="${coverUrl}" class="manga-card-cover" alt="${escapeHtml(manga.title)}" onerror="this.src='https://via.placeholder.com/240x360?text=Cover+Not+Found'">
                    <span class="card-provider-pill">${escapeHtml(manga.provider)}</span>
                </div>
                <div class="manga-card-body">
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
        resultsGrid.innerHTML = `<div style="color:var(--danger);grid-column:1/-1;text-align:center;padding:2.5rem;">Error: ${escapeHtml(err.message)}</div>`;
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
    document.getElementById('chapters-grid').innerHTML = '<div style="color:var(--text-muted);padding:1.5rem;">Fetching chapters...</div>';
    document.getElementById('selected-count-badge').textContent = 'Loading...';

    currentManga = manga;
    currentChapters = [];
    selectedChapterIds.clear();

    const customNameEl = document.getElementById('opt-custom-name');
    if (customNameEl) {
        customNameEl.value = '';
        customNameEl.placeholder = manga.title || 'Manga Title';
    }

    try {
        const resp = await fetch(`/api/manga/${manga.provider}/${encodeURIComponent(manga.id)}/chapters`);
        const data = await resp.json();
        currentChapters = data.chapters || [];
        renderChaptersGrid();
        updateNamingPreview();
    } catch (err) {
        document.getElementById('chapters-grid').innerHTML = `<div style="color:var(--danger);padding:1.5rem;">Failed to load chapters: ${escapeHtml(err.message)}</div>`;
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

function parseChapterNum(c) {
    const raw = (c && c.chapter_num) !== undefined ? String(c.chapter_num) : '0';
    const num = parseFloat(raw);
    return isNaN(num) ? 999999 : num;
}

function renderChaptersGrid() {
    const container = document.getElementById('chapters-grid');
    if (!container) return;
    container.innerHTML = '';

    if (currentChapters.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted);padding:1.5rem;">No chapters found.</div>';
        updateSelectionCount();
        return;
    }

    // Sort chapters
    let chaptersToDisplay = [...currentChapters].sort((a, b) => {
        const diff = parseChapterNum(a) - parseChapterNum(b);
        return chapterSortAsc ? diff : -diff;
    });

    // Filter chapters
    if (chapterFilterText) {
        const visibleIds = new Set(getVisibleChapters().map(c => c.id));
        chaptersToDisplay = chaptersToDisplay.filter(c => visibleIds.has(c.id));
    }

    if (chaptersToDisplay.length === 0) {
        container.innerHTML = '<div style="color:var(--text-muted);padding:1.5rem;">No chapters match your filter.</div>';
        updateSelectionCount();
        return;
    }

    chaptersToDisplay.forEach(chap => {
        const isSelected = selectedChapterIds.has(chap.id);
        const item = document.createElement('div');
        item.className = 'chapter-pill' + (isSelected ? ' selected' : '');
        item.innerHTML = `
            <span class="chapter-pill-num">Ch. ${escapeHtml(chap.chapter_num)}</span>
            <span class="chapter-pill-title" title="${escapeHtml(chap.title || '')}">${escapeHtml(chap.title || '')}</span>
            <span style="font-size:0.75rem;">${isSelected ? '✓' : ''}</span>
        `;

        item.addEventListener('click', () => {
            if (selectedChapterIds.has(chap.id)) {
                selectedChapterIds.delete(chap.id);
                item.classList.remove('selected');
                item.querySelector('span:last-child').textContent = '';
            } else {
                selectedChapterIds.add(chap.id);
                item.classList.add('selected');
                item.querySelector('span:last-child').textContent = '✓';
            }
            updateSelectionCount();
        });

        container.appendChild(item);
    });

    updateSelectionCount();
}

function getVisibleChapters() {
    if (!chapterFilterText) return currentChapters;
    return currentChapters.filter(c => {
        const chapStr = String(c.chapter_num || '').toLowerCase();
        const titleStr = String(c.title || '').toLowerCase();
        return chapStr.includes(chapterFilterText) || titleStr.includes(chapterFilterText);
    });
}

function selectAllChapters() {
    getVisibleChapters().forEach(c => selectedChapterIds.add(c.id));
    renderChaptersGrid();
}

function deselectAllChapters() {
    if (chapterFilterText) {
        getVisibleChapters().forEach(c => selectedChapterIds.delete(c.id));
    } else {
        selectedChapterIds.clear();
    }
    renderChaptersGrid();
}

function invertChapterSelection() {
    getVisibleChapters().forEach(c => {
        if (selectedChapterIds.has(c.id)) {
            selectedChapterIds.delete(c.id);
        } else {
            selectedChapterIds.add(c.id);
        }
    });
    renderChaptersGrid();
}

function toggleChapterSort() {
    chapterSortAsc = !chapterSortAsc;
    const btn = document.getElementById('btn-toggle-sort');
    if (btn) {
        btn.textContent = chapterSortAsc ? '⇅ Order: Low to High' : '⇅ Order: High to Low';
    }
    renderChaptersGrid();
}

function applyChapterRange() {
    const fromVal = parseFloat(document.getElementById('range-from').value);
    const toVal = parseFloat(document.getElementById('range-to').value);

    if (isNaN(fromVal) || isNaN(toVal)) {
        showToast('Please enter valid numbers for chapter range', 'warning');
        return;
    }

    const minVal = Math.min(fromVal, toVal);
    const maxVal = Math.max(fromVal, toVal);

    selectedChapterIds.clear();
    currentChapters.forEach(c => {
        const num = parseChapterNum(c);
        if (num >= minVal && num <= maxVal) {
            selectedChapterIds.add(c.id);
        }
    });

    renderChaptersGrid();
    showToast(`Selected range ${minVal} - ${maxVal} (${selectedChapterIds.size} chapters)`, 'info');
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
            const nums = selected.map(parseChapterNum).filter(n => n !== 999999).sort((a, b) => a - b);
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
    if (badge) {
        badge.textContent = `${selectedChapterIds.size} of ${currentChapters.length} selected`;
    }

    const dlBtn = document.getElementById('btn-start-download');
    const dlCountSpan = document.getElementById('btn-dl-count');
    if (dlCountSpan) {
        dlCountSpan.textContent = selectedChapterIds.size;
    }
    if (dlBtn) {
        dlBtn.disabled = (selectedChapterIds.size === 0);
    }
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
            showToast(`Error: ${err.detail || 'Could not start download'}`, 'error');
            return;
        }

        showToast(`Download started for ${selectedChapterIds.size} chapters!`, 'success');
        switchTab('tab-downloads');
    } catch (err) {
        showToast(`Failed to start: ${err.message}`, 'error');
    }
}

// ==========================================
// 3. Dedicated H / Doujinshi Search
// ==========================================
function initHSearch() {
    const form = document.getElementById('h-search-form');
    if (!form) return;

    form.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = document.getElementById('h-search-input').value.trim();
        if (query) performHSearch(query);
    });

    document.querySelectorAll('.quick-tag-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            const q = pill.dataset.query;
            document.getElementById('h-search-input').value = q;
            performHSearch(q);
        });
    });

    const btnCbz = document.getElementById('btn-h-download-cbz');
    if (btnCbz) btnCbz.addEventListener('click', () => startHDownload(true, false));

    const btnPdf = document.getElementById('btn-h-download-pdf');
    if (btnPdf) btnPdf.addEventListener('click', () => startHDownload(false, true));

    const btnBoth = document.getElementById('btn-h-download-both');
    if (btnBoth) btnBoth.addEventListener('click', () => startHDownload(true, true));
}

async function performHSearch(query) {
    const btn = document.getElementById('h-search-btn');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<span>⏳</span> Searching...';
    btn.disabled = true;

    const providerSelect = document.getElementById('h-search-provider');
    const provider = providerSelect ? providerSelect.value : 'all';

    const resultsGrid = document.getElementById('h-results-grid');
    resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2.5rem;">Searching galleries...</div>';
    document.getElementById('h-results-section').style.display = 'block';
    document.getElementById('h-detail-view').classList.remove('active');

    try {
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
            resultsGrid.innerHTML = '<div style="color:var(--text-muted);grid-column:1/-1;text-align:center;padding:2.5rem;">No galleries found. Try another query or paste a 6-digit code.</div>';
            return;
        }

        data.results.forEach(gal => {
            const card = document.createElement('div');
            card.className = 'manga-card';

            const coverUrl = gal.cover_url || 'https://via.placeholder.com/240x360?text=18+Gallery';
            const provLabel = gal.provider ? gal.provider.toUpperCase() : '18+';

            card.innerHTML = `
                <div class="manga-card-cover-wrap">
                    <img src="${coverUrl}" class="manga-card-cover" alt="${escapeHtml(gal.title)}" onerror="this.src='https://via.placeholder.com/240x360?text=No+Cover'">
                    <span class="card-provider-pill">${provLabel} #${escapeHtml(gal.id)}</span>
                </div>
                <div class="manga-card-body">
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
        resultsGrid.innerHTML = `<div style="color:var(--danger);grid-column:1/-1;text-align:center;padding:2.5rem;">Error: ${escapeHtml(err.message)}</div>`;
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
        showToast('Failed to load gallery: ' + err.message, 'error');
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
            showToast(`Error: ${err.detail || 'Could not start download'}`, 'error');
            return;
        }

        showToast('Gallery download started!', 'success');
        switchTab('tab-downloads');
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
    }
}

// ==========================================
// 4. Download Status, Incomplete Pages & Logs
// ==========================================
async function cancelDownloadJob() {
    const btn = document.getElementById('btn-cancel-download');
    btn.innerHTML = '<span>⏳</span> Cancelling...';
    btn.disabled = true;

    try {
        await fetch('/api/download/cancel', { method: 'POST' });
        showToast('Cancellation requested', 'warning');
        pollDownloadStatus();
    } catch (err) {
        console.error('Cancel request failed:', err);
    }
}

function startDownloadStatusPolling() {
    if (downloadPollInterval) clearInterval(downloadPollInterval);
    downloadPollInterval = setInterval(pollDownloadStatus, 1200);
}

async function pollDownloadStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 3500);
        const resp = await fetch('/api/download/status', { signal: controller.signal });
        clearTimeout(timeoutId);
        if (!resp.ok) return;
        const state = await resp.json();

        // Status Indicator
        const dot = document.getElementById('status-indicator-dot');
        const text = document.getElementById('status-indicator-text');
        dot.className = 'status-dot ' + (state.status || 'idle');
        text.textContent = (state.status || 'IDLE').toUpperCase();

        // Hero Info
        const activeTitle = document.getElementById('active-manga-title');
        const activeSub = document.getElementById('active-manga-sub');
        const activeStage = document.getElementById('active-manga-stage');

        if (state.manga_title) {
            activeTitle.textContent = state.manga_title;
            activeSub.textContent = `Source: ${state.provider || 'Unknown'} | Chapters in queue: ${state.total_chapters}`;
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
            chLabel = `All ${state.total_chapters} Chapters Complete!`;
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

        // Cancel Button state
        const cancelBtn = document.getElementById('btn-cancel-download');
        if (state.status === 'running') {
            cancelBtn.disabled = false;
            cancelBtn.innerHTML = '⏹ Cancel Task';
        } else {
            cancelBtn.disabled = true;
            cancelBtn.innerHTML = state.status === 'cancelled' ? 'Cancelled' : '⏹ Cancel Task';
        }

        // Render Incomplete & Failed Pages Section
        renderFailedPagesSection(state.failed_pages || [], state.failed_count || 0, state.status);

        // Logs
        cachedLogs = state.logs || [];
        renderLogs();

        // Refresh library on completion
        if (lastDownloadStatus === 'running' && state.status === 'completed') {
            loadLibrary();
            if (state.failed_count > 0) {
                showToast(`Download finished with ${state.failed_count} missing page(s). Retry them below`, 'warning', 6000);
            } else {
                showToast('Download finished successfully!', 'success');
            }
        }
        lastDownloadStatus = state.status;

    } catch (err) {
        if (err.name !== 'AbortError') {
            console.error('Polling error:', err);
        }
    }
}

// ==========================================
// 5. Incomplete / Failed Pages UI & Retry Controls
// ==========================================
function initFailedRecoveryControls() {
    const btnRetryAll = document.getElementById('btn-retry-all-failed');
    if (btnRetryAll) {
        btnRetryAll.addEventListener('click', async () => {
            btnRetryAll.disabled = true;
            btnRetryAll.innerHTML = '<span>⏳</span> Retrying All...';
            try {
                const resp = await fetch('/api/download/retry-all', { method: 'POST' });
                const res = await resp.json();
                if (!resp.ok) {
                    showToast(`Retry failed: ${res.detail || 'Server error'}`, 'error');
                } else if (res.total === 0) {
                    showToast('No missing pages to recover', 'info');
                } else if (res.failed === 0) {
                    showToast(`Recovered ${res.succeeded} missing page(s)!`, 'success');
                } else {
                    showToast(`Retry finished (${res.succeeded} recovered, ${res.failed} still failing)`, 'warning');
                }
                pollDownloadStatus();
            } catch (err) {
                showToast(`Retry all failed: ${err.message}`, 'error');
            } finally {
                btnRetryAll.disabled = false;
                btnRetryAll.innerHTML = '<span>🔄</span> Retry All Missing Pages';
            }
        });
    }

    const btnClearFailed = document.getElementById('btn-clear-failed');
    if (btnClearFailed) {
        btnClearFailed.addEventListener('click', async () => {
            try {
                await fetch('/api/download/dismiss-failed', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ resolved_only: true })
                });
                showToast('Cleared recovered pages', 'info');
                pollDownloadStatus();
            } catch (err) {
                console.error('Failed to dismiss:', err);
            }
        });
    }
}

function renderFailedPagesSection(failedList, activeCount, status) {
    const container = document.getElementById('failed-pages-container');
    const noFailedNotice = document.getElementById('no-failed-notice');
    const badgeNav = document.getElementById('nav-failed-badge');
    const countSpan = document.getElementById('failed-pages-count');
    const listContainer = document.getElementById('failed-pages-list');

    // Update Nav Tab Badge
    if (badgeNav) {
        if (activeCount > 0) {
            badgeNav.style.display = 'inline-block';
            badgeNav.textContent = activeCount;
        } else {
            badgeNav.style.display = 'none';
        }
    }

    if (!container || !listContainer) return;

    if (failedList.length === 0) {
        lastFailedSignature = '';
        listContainer.innerHTML = '';
        container.style.display = 'none';
        if (status === 'completed') {
            noFailedNotice.style.display = 'flex';
        } else {
            noFailedNotice.style.display = 'none';
        }
        return;
    }

    // We have failed/incomplete items to display
    noFailedNotice.style.display = 'none';
    container.style.display = 'block';
    if (countSpan) countSpan.textContent = activeCount;

    // Rebuilding the list on every poll would eat clicks, so only redraw when something changed
    const signature = JSON.stringify(failedList.map(f => [f.id, f.status, f.error]));
    if (signature === lastFailedSignature) return;
    lastFailedSignature = signature;

    listContainer.innerHTML = '';

    failedList.forEach(item => {
        const card = document.createElement('div');
        const isResolved = (item.status === 'resolved');
        const isRetrying = (item.status === 'retrying');

        card.className = 'failed-card' + (isResolved ? ' resolved' : '');

        card.innerHTML = `
            <div>
                <div class="failed-card-top">
                    <span class="failed-chap-badge">Chapter ${escapeHtml(item.chapter_num)}</span>
                    <span class="failed-page-badge">Page ${item.page_idx} of ${item.total_pages}</span>
                </div>
                <div class="failed-card-body" style="margin-top:0.6rem;">
                    <div class="failed-series-name">${escapeHtml(item.series_title || 'Manga Series')}</div>
                    ${!isResolved ? `<div class="failed-error-msg">⚠️ ${escapeHtml(item.error || 'Connection error')}</div>` : ''}
                </div>
            </div>
            <div class="failed-card-actions">
                ${isResolved ? `
                    <span class="status-badge-resolved">✓ Repacked & Complete</span>
                    <button type="button" class="btn-dismiss-failed" title="Dismiss" data-id="${escapeHtml(item.id)}">✕</button>
                ` : `
                    <div style="display:flex;gap:0.45rem;">
                        <button type="button" class="btn-retry-page" data-id="${escapeHtml(item.id)}" ${isRetrying ? 'disabled' : ''}>
                            ${isRetrying ? '⏳ Retrying...' : '🔄 Retry Page'}
                        </button>
                        <button type="button" class="btn-retry-chap" data-chap="${escapeHtml(item.chapter_num)}" data-title="${escapeHtml(item.series_title)}" ${isRetrying ? 'disabled' : ''}>
                            ⚡ Retry Chapter
                        </button>
                    </div>
                    <button type="button" class="btn-dismiss-failed" title="Dismiss" data-id="${escapeHtml(item.id)}">✕</button>
                `}
            </div>
        `;

        // Event Listeners for actions
        const btnRetry = card.querySelector('.btn-retry-page');
        if (btnRetry) {
            btnRetry.addEventListener('click', () => retrySinglePage(item.id, btnRetry));
        }

        const btnChap = card.querySelector('.btn-retry-chap');
        if (btnChap) {
            btnChap.addEventListener('click', () => retryChapter(item.chapter_num, item.series_title, btnChap));
        }

        const btnDismiss = card.querySelector('.btn-dismiss-failed');
        if (btnDismiss) {
            btnDismiss.addEventListener('click', () => dismissSingleFailed(item.id));
        }

        listContainer.appendChild(card);
    });
}

async function retrySinglePage(failedId, btnElement) {
    if (btnElement) {
        btnElement.disabled = true;
        btnElement.innerHTML = '<span>⏳</span> Retrying...';
    }

    try {
        const resp = await fetch('/api/download/retry-page', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: failedId })
        });

        const data = await resp.json();
        if (resp.ok && data.success) {
            showToast('Page recovered and archives updated!', 'success');
        } else {
            showToast(`Retry failed: ${data.detail || data.error || 'Server error'}`, 'error');
        }
        pollDownloadStatus();
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
        pollDownloadStatus();
    }
}

async function retryChapter(chapterNum, seriesTitle, btnElement) {
    if (btnElement) {
        btnElement.disabled = true;
        btnElement.innerHTML = '<span>⏳</span> Retrying...';
    }

    try {
        const resp = await fetch('/api/download/retry-chapter', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chapter_num: String(chapterNum), series_title: seriesTitle })
        });

        const data = await resp.json();
        if (!resp.ok) {
            showToast(`Chapter retry failed: ${data.detail || 'Server error'}`, 'error');
        } else if (!data.total) {
            showToast(`Chapter ${chapterNum}: nothing left to retry`, 'info');
        } else if (data.failed === 0) {
            showToast(`Chapter ${chapterNum}: recovered ${data.succeeded} page(s)`, 'success');
        } else {
            showToast(`Chapter ${chapterNum}: ${data.succeeded} recovered, ${data.failed} still failing`, 'warning');
        }
        pollDownloadStatus();
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
        pollDownloadStatus();
    }
}

async function dismissSingleFailed(failedId) {
    try {
        await fetch('/api/download/dismiss-failed', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: failedId })
        });
        pollDownloadStatus();
    } catch (err) {
        console.error('Failed to dismiss:', err);
    }
}

// ==========================================
// 6. Log Terminal & Filter Controls
// ==========================================
function initLogControls() {
    const btnAll = document.getElementById('btn-filter-logs-all');
    const btnErr = document.getElementById('btn-filter-logs-errors');
    const btnClear = document.getElementById('btn-clear-logs');

    if (btnAll) {
        btnAll.addEventListener('click', () => {
            logFilterMode = 'all';
            btnAll.classList.add('active');
            if (btnErr) btnErr.classList.remove('active');
            renderLogs();
        });
    }

    if (btnErr) {
        btnErr.addEventListener('click', () => {
            logFilterMode = 'errors';
            btnErr.classList.add('active');
            if (btnAll) btnAll.classList.remove('active');
            renderLogs();
        });
    }

    if (btnClear) {
        btnClear.addEventListener('click', () => {
            // Remember the last visible entry so the next poll does not bring old logs back
            const last = cachedLogs[cachedLogs.length - 1];
            logClearMarker = last ? `${last.time}|${last.message}` : null;
            lastLogSignature = '';
            renderLogs();
        });
    }
}

function getVisibleLogs() {
    let logs = cachedLogs;
    if (logClearMarker) {
        const idx = logs.map(l => `${l.time}|${l.message}`).lastIndexOf(logClearMarker);
        if (idx >= 0) logs = logs.slice(idx + 1);
    }
    if (logFilterMode === 'errors') {
        logs = logs.filter(l => l.level === 'error' || l.level === 'warning');
    }
    return logs;
}

function renderLogs() {
    const terminal = document.getElementById('log-terminal');
    if (!terminal) return;

    const logsToRender = getVisibleLogs();
    const signature = logFilterMode + '|' + logsToRender.map(l => `${l.time}|${l.message}`).join('\n');
    if (signature === lastLogSignature) return;
    lastLogSignature = signature;

    if (logsToRender.length === 0) {
        terminal.innerHTML = '<div class="log-entry" style="color:var(--text-dim);">No logs in this view.</div>';
        return;
    }

    // Only auto-scroll when the user is already at the bottom
    const nearBottom = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 40;
    terminal.innerHTML = logsToRender.map(l => `
        <div class="log-entry">
            <span class="log-time">[${escapeHtml(l.time)}]</span>
            <span class="log-${escapeHtml(l.level)}">${escapeHtml(l.message)}</span>
        </div>
    `).join('');
    if (nearBottom) terminal.scrollTop = terminal.scrollHeight;
}

// ==========================================
// 7. CBZ ⇄ PDF Converter (with Progress & Cancel)
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

    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
            if (activeConversionJobId) {
                cancelActiveConversion(activeConversionJobId);
            }
        });
    }
}

async function uploadAndConvertFile(file) {
    const ext = file.name.split('.').pop().toLowerCase();
    if (ext !== 'cbz' && ext !== 'pdf') {
        showToast('Please select a .cbz or .pdf archive', 'warning');
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
        showToast(`Conversion failed: ${err.message}`, 'error');
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

                showToast('Conversion completed! Starting download...', 'success');

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
                showToast('Conversion failed', 'error');
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
        showToast('Conversion cancelled', 'warning');
    } catch (err) {
        console.error('Cancel failed:', err);
    }
}

async function convertLibraryFile(filepath) {
    const filename = filepath.split(/[\/\\]/).pop();
    const ext = filename.split('.').pop().toLowerCase();
    const targetFormat = (ext === 'cbz') ? 'PDF' : 'CBZ';

    if (!confirm(`Convert '${filename}' into a .${targetFormat.toLowerCase()} archive?`)) return;

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
        showToast(`Failed: ${err.message}`, 'error');
    }
}

// ==========================================
// 8. Library Management & Auto-Updater
// ==========================================
let libraryUpdatesCache = {};
let currentModalUpdateTarget = null;

async function checkLibraryUpdates(userTriggered = false) {
    const btn = document.getElementById('btn-check-library-updates');
    const origText = btn ? btn.innerHTML : '⚡ Check for Updates';
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '🔄 Checking online...';
    }

    try {
        const resp = await fetch('/api/library/check-updates');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        
        libraryUpdatesCache = {};
        let updateCount = 0;
        let totalNewChaps = 0;

        (data.updates || []).forEach(u => {
            if (u.filepath) {
                libraryUpdatesCache[u.filepath] = u;
                if (u.has_updates && u.new_count > 0) {
                    updateCount++;
                    totalNewChaps += u.new_count;
                }
            }
        });

        // Update banner
        const banner = document.getElementById('library-updates-banner');
        const bannerText = document.getElementById('updates-banner-text');
        if (banner) {
            if (updateCount > 0) {
                banner.style.display = 'block';
                if (bannerText) {
                    bannerText.textContent = `Found ${updateCount} series with updates available (${totalNewChaps} total new chapters online)!`;
                }
            } else {
                banner.style.display = 'none';
            }
        }

        // Re-render library archives to show badges/buttons
        await loadLibrary();

        if (userTriggered) {
            if (updateCount > 0) {
                showToast(`🔥 Found updates for ${updateCount} series (${totalNewChaps} new chapters)!`, 'success');
            } else {
                showToast('✅ All library series are currently up-to-date!', 'info');
            }
        }
    } catch (err) {
        console.error('Failed to check library updates:', err);
        if (userTriggered) {
            showToast(`Update check failed: ${err.message}`, 'error');
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = origText;
        }
    }
}

function openUpdateModal(updateInfo) {
    currentModalUpdateTarget = updateInfo;
    const modal = document.getElementById('update-modal');
    const titleEl = document.getElementById('update-modal-title');
    const bodyEl = document.getElementById('update-modal-body');

    if (!modal || !bodyEl) return;

    if (titleEl) {
        titleEl.textContent = `⚡ Update: ${updateInfo.manga_name}`;
    }

    const newChaps = updateInfo.new_chapters || [];
    const firstNew = newChaps[0] ? newChaps[0].chapter_num : '?';
    const lastNew = newChaps[newChaps.length - 1] ? newChaps[newChaps.length - 1].chapter_num : '?';

    bodyEl.innerHTML = `
        <div style="display:flex; gap:1.25rem; margin-bottom:1.35rem; align-items:flex-start;">
            ${updateInfo.cover_url ? `<img src="/api/proxy/image?url=${encodeURIComponent(updateInfo.cover_url)}" style="width:78px; height:112px; object-fit:cover; border-radius:8px; border:1px solid #334155; box-shadow:0 4px 12px rgba(0,0,0,0.35); flex-shrink:0;">` : ''}
            <div style="flex:1; min-width:0;">
                <h4 style="margin:0 0 0.55rem 0; font-size:1.18rem; font-weight:700; color:#f8fafc; line-height:1.35;">${escapeHtml(updateInfo.manga_name)}</h4>
                <div style="display:flex; flex-direction:column; gap:0.35rem; font-size:0.88rem;">
                    <div style="color:#94a3b8;">Source: <strong style="color:#38bdf8;">${escapeHtml(updateInfo.provider_display || updateInfo.provider || 'Online')}</strong></div>
                    <div style="color:#94a3b8;">Current Archive: <strong>${escapeHtml(updateInfo.existing_range)}</strong> <span style="color:#64748b;">(${updateInfo.existing_count} chapters)</span></div>
                    <div style="color:#94a3b8;">Latest Online: <strong style="color:#4ade80;">Chapter ${escapeHtml(String(updateInfo.latest_online))}</strong></div>
                </div>
            </div>
        </div>

        <div style="background:linear-gradient(135deg, rgba(245, 158, 11, 0.12) 0%, rgba(217, 119, 6, 0.05) 100%); border-radius:10px; padding:1rem 1.15rem; border:1px solid rgba(245, 158, 11, 0.35); margin-bottom:1.35rem;">
            <div style="font-size:0.95rem; font-weight:700; color:#fbbf24; margin-bottom:0.35rem; display:flex; align-items:center; gap:0.4rem;">
                🔥 ${updateInfo.new_count} New Chapters Available (Ch. ${escapeHtml(firstNew)} – ${escapeHtml(lastNew)})
            </div>
            <div style="font-size:0.84rem; color:#94a3b8; line-height:1.45;">
                Downloaded chapters will be seamlessly appended into your existing combined archive without re-downloading previously saved pages.
            </div>
        </div>

        <div style="margin-bottom:1.25rem;">
            <label style="display:block; font-size:0.88rem; font-weight:600; color:#cbd5e1; margin-bottom:0.45rem;">
                How many new chapters to download:
            </label>
            <select id="modal-update-count-select" class="search-input" style="width:100%; padding:0.65rem 0.85rem; background:#0f172a; border:1px solid #334155; color:#fff; border-radius:8px; font-size:0.9rem;">
                <option value="all">All ${updateInfo.new_count} new chapters (Ch. ${escapeHtml(firstNew)} – Ch. ${escapeHtml(lastNew)})</option>
                ${updateInfo.new_count > 1 ? '<option value="1">Next 1 chapter only</option>' : ''}
                ${updateInfo.new_count > 5 ? '<option value="5">Next 5 chapters</option>' : ''}
                ${updateInfo.new_count > 10 ? '<option value="10">Next 10 chapters</option>' : ''}
                ${updateInfo.new_count > 25 ? '<option value="25">Next 25 chapters</option>' : ''}
                ${updateInfo.new_count > 50 ? '<option value="50">Next 50 chapters</option>' : ''}
            </select>
        </div>

        <div style="display:flex; flex-direction:column; gap:0.65rem; background:rgba(15, 23, 42, 0.6); border:1px solid #334155; border-radius:8px; padding:0.85rem 1rem;">
            <label style="display:flex; align-items:center; gap:0.65rem; font-size:0.86rem; color:#cbd5e1; cursor:pointer; user-select:none;">
                <input type="checkbox" id="modal-update-save-pdf" style="accent-color:#f59e0b; width:16px; height:16px; cursor:pointer;">
                Also save new chapters as individual PDF files
            </label>
            <label style="display:flex; align-items:center; gap:0.65rem; font-size:0.86rem; color:#cbd5e1; cursor:pointer; user-select:none;">
                <input type="checkbox" id="modal-update-clean-temp" checked style="accent-color:#f59e0b; width:16px; height:16px; cursor:pointer;">
                Clean temporary image folders after appending
            </label>
        </div>
    `;

    modal.style.display = 'flex';
}

function closeUpdateModal() {
    const modal = document.getElementById('update-modal');
    if (modal) modal.style.display = 'none';
    currentModalUpdateTarget = null;
}

async function deleteLibraryFile(filepath, filename) {
    const confirmed = window.confirm(`Delete "${filename}"?\n\nThis permanently removes the file from disk. This cannot be undone.`);
    if (!confirmed) return;

    try {
        const resp = await fetch(`/api/files/delete?path=${encodeURIComponent(filepath)}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
        showToast(`🗑️ Deleted: ${filename}`, 'success');
        // Remove from update cache
        delete libraryUpdatesCache[filepath];
        loadLibrary();
    } catch (err) {
        showToast(`Failed to delete: ${err.message}`, 'error');
    }
}

async function executeModalUpdate() {
    if (!currentModalUpdateTarget) return;

    const target = currentModalUpdateTarget;
    const countSelect = document.getElementById('modal-update-count-select');
    const savePdfEl = document.getElementById('modal-update-save-pdf');
    const cleanTempEl = document.getElementById('modal-update-clean-temp');

    let maxChapters = null;
    if (countSelect && countSelect.value !== 'all') {
        maxChapters = parseInt(countSelect.value, 10);
    }

    const payload = {
        filepath: target.filepath,
        manga_name: target.manga_name,
        provider: target.provider,
        max_chapters: maxChapters,
        save_pdf: savePdfEl ? savePdfEl.checked : false,
        clean_temp: cleanTempEl ? cleanTempEl.checked : true,
    };

    closeUpdateModal();

    try {
        const resp = await fetch('/api/library/update-archive', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });

        const resData = await resp.json();
        if (!resp.ok) {
            throw new Error(resData.detail || `HTTP ${resp.status}`);
        }

        if (resData.status === 'started') {
            showToast(`🚀 Update started for ${target.manga_name} (${resData.queued_chapters} chapters)!`, 'success');
            switchTab('tab-downloads');
        } else {
            showToast(resData.message || 'Archive is already up to date.', 'info');
        }
    } catch (err) {
        showToast(`Failed to start update: ${err.message}`, 'error');
    }
}

function handleUpdateAllSeries() {
    const seriesWithUpdates = Object.values(libraryUpdatesCache).filter(u => u && u.has_updates && u.new_count > 0);
    if (seriesWithUpdates.length === 0) {
        showToast('No series have pending updates.', 'info');
        return;
    }

    // Open update modal for the first one
    openUpdateModal(seriesWithUpdates[0]);
    if (seriesWithUpdates.length > 1) {
        showToast(`Starting update for 1 of ${seriesWithUpdates.length} series.`, 'info');
    }
}

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
            archivesList.innerHTML = '<div style="color:var(--text-muted);padding:1.2rem;">No combined CBZ archives found.</div>';
        } else {
            data.combined_archives.forEach(arc => {
                const arcUpdate = libraryUpdatesCache[arc.filepath];
                const hasUpdate = arcUpdate && arcUpdate.has_updates && arcUpdate.new_count > 0;

                const card = document.createElement('div');
                card.className = 'archive-item-card';
                card.innerHTML = `
                    <div class="archive-item-info">
                        <div class="archive-item-title">
                            <span>📦 ${escapeHtml(arc.filename)}</span>
                            ${hasUpdate ? `<span class="badge-update">🔥 +${arcUpdate.new_count} New Ch.</span>` : ''}
                        </div>
                        <div class="archive-item-meta">
                            <span>${arc.chapter_count} chapters (${arc.chapter_range})</span>
                            <span>•</span>
                            <span>${arc.size_mb} MB</span>
                            ${hasUpdate ? `<span style="color:#fbbf24; font-weight:600;">• Latest Online: Ch. ${escapeHtml(String(arcUpdate.latest_online))}</span>` : ''}
                        </div>
                    </div>
                    <div class="archive-actions">
                        ${hasUpdate ? `<button type="button" class="btn-amber btn-update">⚡ Update (+${arcUpdate.new_count})</button>` : ''}
                        <button type="button" class="btn-primary btn-read">📖 Read</button>
                        <button type="button" class="btn-secondary btn-convert">🔄 Convert to PDF</button>
                        <a href="/api/files/download?path=${encodeURIComponent(arc.filepath)}" class="btn-secondary" download>⬇ Download</a>
                        <button type="button" class="btn-danger btn-delete">🗑️</button>
                    </div>
                `;
                if (hasUpdate) {
                    card.querySelector('.btn-update').addEventListener('click', () => openUpdateModal(arcUpdate));
                }
                card.querySelector('.btn-read').addEventListener('click', () => openReader(arc.filepath, arc.filename));
                card.querySelector('.btn-convert').addEventListener('click', () => convertLibraryFile(arc.filepath));
                card.querySelector('.btn-delete').addEventListener('click', () => deleteLibraryFile(arc.filepath, arc.filename));
                archivesList.appendChild(card);
            });
        }

        // Individual Files
        const individualList = document.getElementById('individual-files-list');
        if (individualList) {
            individualList.innerHTML = '';
            if (!data.individual_chapters || data.individual_chapters.length === 0) {
                individualList.innerHTML = '<div style="color:var(--text-muted);padding:1.2rem;">No individual chapter files found.</div>';
            } else {
                data.individual_chapters.forEach(f => {
                    const isCbz = f.format === 'cbz';
                    const targetFormat = isCbz ? 'PDF' : 'CBZ';
                    const icon = isCbz ? '📦' : '📄';

                    const item = document.createElement('div');
                    item.className = 'archive-item-card';
                    item.innerHTML = `
                        <div class="archive-item-info">
                            <div class="archive-item-title">
                                <span>${icon} ${escapeHtml(f.filename)}</span>
                            </div>
                            <div class="archive-item-meta">
                                ${f.series_name && f.series_name !== 'General' ? `<span class="tag tag-provider">${escapeHtml(f.series_name)}</span>` : ''}
                                <span>Chapter ${escapeHtml(f.chapter_num)}${f.chapter_title ? ' - ' + escapeHtml(f.chapter_title) : ''}</span>
                                <span>•</span>
                                <span>${f.size_mb} MB</span>
                                <span>•</span>
                                <span>${f.format.toUpperCase()}</span>
                            </div>
                        </div>
                        <div class="archive-actions">
                            <button type="button" class="btn-primary btn-read">📖 Read</button>
                            <button type="button" class="btn-secondary btn-convert">🔄 Convert to ${targetFormat}</button>
                            <a href="/api/files/download?path=${encodeURIComponent(f.filepath)}" class="btn-secondary" download>⬇ Download</a>
                            <button type="button" class="btn-danger btn-delete">🗑️</button>
                        </div>
                    `;
                    item.querySelector('.btn-read').addEventListener('click', () => openReader(f.filepath, f.filename));
                    item.querySelector('.btn-convert').addEventListener('click', () => convertLibraryFile(f.filepath));
                    item.querySelector('.btn-delete').addEventListener('click', () => deleteLibraryFile(f.filepath, f.filename));
                    individualList.appendChild(item);
                });
            }
        }

        // Uncombined Folders
        const uncombinedBox = document.getElementById('uncombined-folders-section');
        const uncombinedList = document.getElementById('uncombined-list');
        uncombinedList.innerHTML = '';

        if (data.uncombined_folders && data.uncombined_folders.length > 0) {
            uncombinedBox.style.display = 'block';
            data.uncombined_folders.forEach(f => {
                const item = document.createElement('div');
                item.className = 'archive-item-card';
                item.innerHTML = `
                    <div>
                        <div class="archive-item-title">📁 ${escapeHtml(f.folder_name)}</div>
                        <div class="archive-item-meta">${f.image_count} images • ${f.size_mb} MB</div>
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
            showToast(`Combined archive created: ${res.file}`, 'success');
            loadLibrary();
        } else {
            showToast(`Error: ${res.detail}`, 'error');
        }
    } catch (err) {
        showToast(`Failed: ${err.message}`, 'error');
    }
}

// ==========================================
// 9. Config / Settings
// ==========================================
async function loadConfig() {
    try {
        const resp = await fetch('/api/config');
        const data = await resp.json();
        const input = document.getElementById('cfg-output-dir');
        if (input) input.value = data.output_dir;
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
            showToast('Settings saved successfully', 'success');
            loadLibrary();
        }
    } catch (err) {
        showToast(`Failed to save settings: ${err.message}`, 'error');
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

// ==========================================
// 10. Built-in PDF & CBZ Reader
// ==========================================
const readerState = {
    open: false,
    filepath: '',
    filename: '',
    format: 'pdf',
    totalPages: 0,
    page: 0,
    chapters: [],
    mode: 'single',      // 'single' | 'webtoon' | 'pdf-native'
    rtl: false,          // false = LTR, true = RTL manga mode
    fit: 'fit-height',   // 'fit-height' | 'fit-width' | 'fit-original'
    zoom: 100,
    observer: null,
};

function readerPageUrl(index) {
    return `/api/reader/page?path=${encodeURIComponent(readerState.filepath)}&index=${index}`;
}

function initReader() {
    const modal = document.getElementById('reader-modal');
    if (!modal) return;

    document.getElementById('reader-close-btn').addEventListener('click', closeReader);
    document.getElementById('reader-prev-btn').addEventListener('click', () => stepReaderPage(-1));
    document.getElementById('reader-next-btn').addEventListener('click', () => stepReaderPage(1));

    // Left / right click zones inside single-page view respect LTR vs RTL reading direction
    document.getElementById('reader-Zone-left').addEventListener('click', () => {
        stepReaderPage(readerState.rtl ? 1 : -1);
    });
    document.getElementById('reader-Zone-right').addEventListener('click', () => {
        stepReaderPage(readerState.rtl ? -1 : 1);
    });

    const slider = document.getElementById('reader-page-slider');
    slider.addEventListener('input', (e) => {
        goToReaderPage(parseInt(e.target.value, 10) - 1, true);
    });

    const pageInput = document.getElementById('reader-page-input');
    pageInput.addEventListener('change', (e) => {
        const val = parseInt(e.target.value, 10);
        if (!isNaN(val)) {
            goToReaderPage(val - 1, true);
        }
    });

    const chapSelect = document.getElementById('reader-chapter-select');
    chapSelect.addEventListener('change', (e) => {
        const startIdx = parseInt(e.target.value, 10);
        if (!isNaN(startIdx)) {
            goToReaderPage(startIdx, true);
        }
    });

    // Mode buttons
    ['reader-mode-single', 'reader-mode-webtoon', 'reader-mode-native'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) {
            btn.addEventListener('click', () => setReaderMode(btn.dataset.mode));
        }
    });

    // Direction toggle (LTR / RTL)
    const dirBtn = document.getElementById('reader-dir-btn');
    dirBtn.addEventListener('click', () => {
        readerState.rtl = !readerState.rtl;
        dirBtn.textContent = readerState.rtl ? '← RTL (Manga)' : 'LTR →';
    });

    // Fit mode cycle
    const fitBtn = document.getElementById('reader-fit-btn');
    const fits = [
        { cls: 'fit-height', label: 'Fit Height' },
        { cls: 'fit-width', label: 'Fit Width' },
        { cls: 'fit-original', label: 'Original Size' },
    ];
    fitBtn.addEventListener('click', () => {
        const idx = fits.findIndex(f => f.cls === readerState.fit);
        const next = fits[(idx + 1) % fits.length];
        readerState.fit = next.cls;
        readerState.zoom = 100;
        fitBtn.textContent = next.label;
        applyReaderZoomAndFit();
    });

    // Zoom controls
    document.getElementById('reader-zoom-in').addEventListener('click', () => {
        readerState.zoom = Math.min(250, readerState.zoom + 15);
        applyReaderZoomAndFit();
    });
    document.getElementById('reader-zoom-out').addEventListener('click', () => {
        readerState.zoom = Math.max(50, readerState.zoom - 15);
        applyReaderZoomAndFit();
    });

    // Fullscreen toggle
    document.getElementById('reader-fullscreen-btn').addEventListener('click', () => {
        if (!document.fullscreenElement) {
            modal.requestFullscreen?.().catch(() => {});
        } else {
            document.exitFullscreen?.().catch(() => {});
        }
    });

    // Keyboard shortcuts while reader is open
    document.addEventListener('keydown', (e) => {
        if (!readerState.open) return;
        const tag = (e.target && e.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;

        if (e.key === 'Escape') {
            e.preventDefault();
            closeReader();
        } else if (e.key === 'ArrowRight') {
            if (readerState.mode === 'single') {
                e.preventDefault();
                stepReaderPage(readerState.rtl ? -1 : 1);
            }
        } else if (e.key === 'ArrowLeft') {
            if (readerState.mode === 'single') {
                e.preventDefault();
                stepReaderPage(readerState.rtl ? 1 : -1);
            }
        }
    });
}

async function openReader(filepath, filename) {
    try {
        const resp = await fetch(`/api/reader/info?path=${encodeURIComponent(filepath)}`);
        const data = await resp.json();
        if (!resp.ok) {
            showToast(`Could not open reader: ${data.detail || 'Error'}`, 'error');
            return;
        }
        if (!data.pages || data.pages < 1) {
            showToast('This file has no readable pages', 'warning');
            return;
        }

        readerState.open = true;
        readerState.filepath = data.filepath || filepath;
        readerState.filename = data.filename || filename || 'Manga';
        readerState.format = data.format || 'pdf';
        readerState.totalPages = data.pages;
        readerState.page = 0;
        readerState.chapters = data.chapters || [];
        readerState.zoom = 100;

        document.getElementById('reader-book-title').textContent = readerState.filename;
        document.getElementById('reader-format-badge').textContent = readerState.format.toUpperCase();
        document.getElementById('reader-page-total').textContent = readerState.totalPages;

        const slider = document.getElementById('reader-page-slider');
        const pageInput = document.getElementById('reader-page-input');
        slider.max = readerState.totalPages;
        slider.value = 1;
        pageInput.max = readerState.totalPages;
        pageInput.value = 1;

        // Populate chapter dropdown if archive has multiple chapters
        const chapSelect = document.getElementById('reader-chapter-select');
        chapSelect.innerHTML = '';
        if (readerState.chapters.length > 1) {
            readerState.chapters.forEach(ch => {
                const opt = document.createElement('option');
                opt.value = ch.start;
                opt.textContent = `${ch.label} (p. ${ch.start + 1})`;
                chapSelect.appendChild(opt);
            });
            chapSelect.style.display = 'inline-block';
        } else {
            chapSelect.style.display = 'none';
        }

        // Show Native PDF tab only when opening a .pdf file
        const nativeBtn = document.getElementById('reader-mode-native');
        if (nativeBtn) {
            nativeBtn.style.display = readerState.format === 'pdf' ? 'inline-block' : 'none';
        }

        // Reset webtoon container for the newly opened book
        document.getElementById('reader-webtoon-wrap').innerHTML = '';
        document.getElementById('reader-pdf-frame').src = '';

        const modal = document.getElementById('reader-modal');
        modal.style.display = 'flex';
        modal.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';

        setReaderMode('single');
    } catch (err) {
        showToast(`Failed to open reader: ${err.message}`, 'error');
    }
}

function closeReader() {
    readerState.open = false;
    if (readerState.observer) {
        readerState.observer.disconnect();
        readerState.observer = null;
    }
    const modal = document.getElementById('reader-modal');
    if (modal) {
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
    }
    document.getElementById('reader-pdf-frame').src = '';
    document.getElementById('reader-webtoon-wrap').innerHTML = '';
    document.body.style.overflow = '';
    if (document.fullscreenElement) {
        document.exitFullscreen?.().catch(() => {});
    }
}

function setReaderMode(mode) {
    if (mode === 'pdf-native' && readerState.format !== 'pdf') {
        mode = 'single';
    }
    readerState.mode = mode;

    ['reader-mode-single', 'reader-mode-webtoon', 'reader-mode-native'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.classList.toggle('active', btn.dataset.mode === mode);
    });

    const singleWrap = document.getElementById('reader-single-wrap');
    const webtoonWrap = document.getElementById('reader-webtoon-wrap');
    const pdfFrame = document.getElementById('reader-pdf-frame');
    const bottomBar = document.getElementById('reader-bottombar');

    singleWrap.style.display = mode === 'single' ? 'flex' : 'none';
    webtoonWrap.style.display = mode === 'webtoon' ? 'flex' : 'none';
    pdfFrame.style.display = mode === 'pdf-native' ? 'block' : 'none';
    bottomBar.style.display = mode === 'pdf-native' ? 'none' : 'flex';

    if (mode === 'single') {
        goToReaderPage(readerState.page, false);
    } else if (mode === 'webtoon') {
        buildWebtoonStrip();
        goToReaderPage(readerState.page, true);
    } else if (mode === 'pdf-native') {
        const viewUrl = `/api/files/view?path=${encodeURIComponent(readerState.filepath)}#page=${readerState.page + 1}`;
        if (pdfFrame.src !== location.origin + viewUrl) {
            pdfFrame.src = viewUrl;
        }
    }
}

function buildWebtoonStrip() {
    const wrap = document.getElementById('reader-webtoon-wrap');
    if (wrap.childElementCount === readerState.totalPages) return;
    wrap.innerHTML = '';

    if (readerState.observer) {
        readerState.observer.disconnect();
    }

    const viewport = document.getElementById('reader-viewport');
    readerState.observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const idx = parseInt(entry.target.dataset.index, 10);
                if (!isNaN(idx) && readerState.mode === 'webtoon') {
                    syncReaderCounters(idx);
                }
            }
        });
    }, { root: viewport, threshold: 0.45 });

    for (let i = 0; i < readerState.totalPages; i++) {
        const img = document.createElement('img');
        img.className = 'reader-webtoon-page';
        img.loading = 'lazy';
        img.dataset.index = i;
        img.alt = `Page ${i + 1}`;
        img.src = readerPageUrl(i);
        wrap.appendChild(img);
        readerState.observer.observe(img);
    }
    applyReaderZoomAndFit();
}

function stepReaderPage(delta) {
    goToReaderPage(readerState.page + delta, true);
}

function syncReaderCounters(index) {
    readerState.page = index;
    document.getElementById('reader-page-slider').value = index + 1;
    document.getElementById('reader-page-input').value = index + 1;
    document.getElementById('reader-prev-btn').disabled = index <= 0;
    document.getElementById('reader-next-btn').disabled = index >= readerState.totalPages - 1;

    // Keep chapter selector aligned with current page
    const chapSelect = document.getElementById('reader-chapter-select');
    if (readerState.chapters.length > 1 && chapSelect) {
        let currentStart = readerState.chapters[0].start;
        for (const ch of readerState.chapters) {
            if (ch.start <= index) currentStart = ch.start;
            else break;
        }
        chapSelect.value = String(currentStart);
    }
}

function goToReaderPage(index, scrollWebtoon) {
    if (!readerState.totalPages) return;
    const clamped = Math.max(0, Math.min(readerState.totalPages - 1, index));
    syncReaderCounters(clamped);

    if (readerState.mode === 'single') {
        const img = document.getElementById('reader-page-img');
        img.src = readerPageUrl(clamped);
        document.getElementById('reader-viewport').scrollTop = 0;

        // Preload next two pages for instant page turns
        for (let ahead = 1; ahead <= 2; ahead++) {
            const nextIdx = clamped + ahead;
            if (nextIdx < readerState.totalPages) {
                const pre = new Image();
                pre.src = readerPageUrl(nextIdx);
            }
        }
    } else if (readerState.mode === 'webtoon' && scrollWebtoon) {
        const targetImg = document.querySelector(`#reader-webtoon-wrap img[data-index="${clamped}"]`);
        if (targetImg) {
            targetImg.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
}

function applyReaderZoomAndFit() {
    const label = document.getElementById('reader-zoom-label');
    if (label) label.textContent = `${readerState.zoom}%`;

    const img = document.getElementById('reader-page-img');
    if (img) {
        img.className = `reader-page-img ${readerState.fit}`;
        if (readerState.zoom === 100) {
            img.style.width = '';
            img.style.maxWidth = '';
            img.style.maxHeight = '';
        } else {
            img.style.maxWidth = 'none';
            img.style.maxHeight = 'none';
            img.style.width = `${readerState.zoom}vw`;
        }
    }

    document.querySelectorAll('#reader-webtoon-wrap .reader-webtoon-page').forEach(el => {
        el.style.width = readerState.zoom === 100 ? '' : `${Math.min(100, readerState.zoom)}vw`;
    });
}
