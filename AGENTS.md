# AGENTS.md — MangaScrapper Pro

> Reference guide for AI agents (and contributors) working in this codebase.

---

## Project Overview

MangaScrapper Pro is a **Python + FastAPI + vanilla JS** web application that:
- Searches manga across multiple online providers (MangaDex, MangaPill, ComicK, MANGA Plus)
- Downloads manga chapters concurrently with live progress tracking
- Exports chapters to **CBZ**, **PDF**, or raw images
- Combines all chapters into a single combined CBZ archive
- Reads/renders CBZ and PDF files in a built-in browser reader
- Checks online providers for new chapters and appends them to existing archives
- Converts between CBZ ↔ PDF
- Tracks failed pages and allows one-click recovery

---

## Directory Structure

```
MangaScrapper/
├── main.py                  # Entrypoint — Web UI server or CLI mode
├── config.py                # Single-file config: OUTPUT_DIR, IMAGE_EXTS
├── requirements.txt
├── README.md
├── AGENTS.md                # ← you are here
│
├── providers/               # All source adapters (manga + 18+)
│   ├── __init__.py          # Provider registry, search routing, resolve_manga()
│   ├── base.py              # Abstract base class + shared dataclasses
│   ├── mangadex.py
│   ├── mangapill.py
│   ├── comick.py            # Also used for cover enrichment
│   ├── mangaplus.py
│   ├── nhentai.py           # 18+
│   └── cin.py               # 18+
│
├── core/                    # Backend business logic
│   ├── downloader.py        # DownloadManager (singleton)
│   ├── exporter.py          # CBZ/PDF writing, combine, append
│   ├── library.py           # scan_library(), combine_existing_folders()
│   ├── updater.py           # check_archive_updates(), check_all_library_updates()
│   ├── converter.py         # ConversionManager — CBZ↔PDF background jobs
│   ├── reader.py            # resolve_library_path(), get_book_info(), get_page_image()
│   ├── ranking.py           # Cross-provider search result scoring
│   └── comick_meta.py       # Fetches canonical covers from ComicK
│
├── server/
│   ├── app.py               # FastAPI app — all REST endpoints
│   └── static/
│       ├── index.html       # Single-page app shell
│       ├── app.js           # All frontend logic (~2100 lines)
│       └── style.css        # Dark-mode theme (~1845 lines)
│
└── manga_download/          # Default output dir (gitignored)
```

---

## Key Singletons

| Object | Module | Notes |
|---|---|---|
| `download_manager` | `core.downloader` | One global instance; one download job at a time |
| `conversion_manager` | `core.converter` | One global instance; multiple CBZ↔PDF jobs can queue |
| `app` | `server.app` | FastAPI application |

---

## Core Data Contracts

### `ChapterInfo` (`providers/base.py`)

```python
@dataclass
class ChapterInfo:
    id: str           # Provider-specific chapter ID
    provider: str     # Provider name key (e.g. "mangadex", "mangapill")
    chapter_num: str  # String, may be "12.5" — always str, never int
    title: str
    volume: str
    url: str
    page_count: Optional[int]
    extra: Dict[str, Any]  # Provider-specific data (signed URL tokens etc.)
```

### Chapter number parsing

Always use `parse_chapter_number(chap_str) -> float` from `providers.base` for sorting or comparison. **Never compare chapter strings directly.**

---

## Adding a New Manga Provider

1. Create `providers/yournewprovider.py` subclassing `BaseMangaProvider`
2. Implement: `parse_url`, `search`, `get_manga_details`, `get_chapters`, `get_page_urls`
3. Register in `providers/__init__.py` in `_MANGA_PROVIDERS` (or `_H_PROVIDERS` for 18+)
4. No other changes needed — search, download, update, and API all auto-discover it

---

## Download Flow

```
POST /api/download/start
  → download_manager.start_download_job(provider, chapters, append_to_cbz=None)
    → Worker thread: _execute_download()
      → For each chapter: get_page_urls() → concurrent page downloads
      → Track failed pages in self.failed_pages[]
      → save_chapter_as_cbz() / save_chapter_as_pdf()
      → If combine_cbz=True and append_to_cbz=None:
          → combine_chapters_into_cbz()   (new combined archive)
      → If append_to_cbz is set:
          → append_to_existing_cbz()      (appends + renames existing)
```

### Key `start_download_job` parameters

| Param | Default | Notes |
|---|---|---|
| `combine_cbz` | `True` | Create combined CBZ |
| `save_pdf` | `True` | Per-chapter PDFs |
| `clean_temp` | `True` | Delete temp image folders |
| `append_to_cbz` | `None` | Path to existing CBZ (auto-update flow) |

---

## File Naming Conventions

- **Combined archive:** `{SeriesName}_Chapter_{first}-{last}.cbz`
- **Per-chapter:** `{Series} - Chapter {num} - {Title}.pdf`
- **Inside CBZ:** `Chapter_1/001.jpg`, `Chapter_2/001.jpg` ...

---

## API Endpoints Quick Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/providers` | List manga providers |
| `GET` | `/api/manga/search` | Search across providers |
| `POST` | `/api/manga/resolve` | Resolve URL/query to manga details + chapters |
| `POST` | `/api/download/start` | Start download job |
| `GET` | `/api/download/status` | Poll download state (UI polls every 1.5s) |
| `POST` | `/api/download/cancel` | Cancel active download |
| `POST` | `/api/download/retry-page` | Retry a single failed page |
| `POST` | `/api/download/retry-chapter` | Retry all failed pages in a chapter |
| `POST` | `/api/download/retry-all` | Retry all failed pages |
| `GET` | `/api/library` | Scan and return library contents |
| `GET` | `/api/library/check-updates` | Check all archives for new chapters online |
| `POST` | `/api/library/update-archive` | Download new chapters and append to existing CBZ |
| `POST` | `/api/library/combine` | Combine uncombined chapter folders into CBZ |
| `DELETE` | `/api/files/delete` | Delete a library file from disk |
| `GET` | `/api/files/download` | Download a file |
| `GET` | `/api/reader/info` | Get book metadata + chapter list |
| `GET` | `/api/reader/page` | Get a rendered page image |
| `POST` | `/api/convert/start-library` | Start CBZ↔PDF conversion |
| `GET` | `/api/convert/status/{job_id}` | Poll conversion progress |
| `GET` | `/api/proxy/image` | Proxy cover/image URLs (bypass hotlink blocks) |
| `GET` | `/api/h/search` | Search 18+ providers |
| `POST` | `/api/h/resolve` | Resolve 18+ gallery |

> **Security:** All `path` parameters are validated by `_checked_library_file()` — a directory traversal guard. Every new API endpoint that accepts a file path **must** call this.

---

## Frontend Architecture (`server/static/`)

- **Single Page App** — one `index.html`, no framework
- **Tabs:** `tab-search`, `tab-h-search`, `tab-downloads`, `tab-library`, `tab-converter`, `tab-settings`
- **Key globals in `app.js`:**
  - `libraryUpdatesCache` — dict keyed by filepath, populated after "Check for Updates"
  - `currentModalUpdateTarget` — update info object in update modal
  - `readerState` — page index, total pages, chapters, zoom, fit mode
- **Polling:** `startDownloadStatusPolling()` fetches `/api/download/status` every 1.5s
- **CSS/JS cache busting:** Increment `?v=X.X` in `index.html` `<link>` and `<script>` tags on every meaningful change

### Button classes (do not invent new ones)

| Class | Use |
|---|---|
| `.btn-primary` | Default action (purple gradient) |
| `.btn-secondary` | Secondary / neutral |
| `.btn-danger` | Destructive (red) |
| `.btn-amber` | Update / special action (amber/gold) |
| `.btn-green` | Modifier on `.btn-primary` for success |
| `.btn-sm` | Smaller variant (outside `.archive-actions` only) |

> **Critical:** Inside `.archive-actions`, all buttons are normalized by a CSS rule using `!important`. Never use `!important` on `padding` or `font-size` in button class definitions — it breaks the normalizer and causes size inconsistencies.

---

## Common Pitfalls

1. **PowerShell multi-line scripts:** Use temp `.py` files in `scratch/`, not `python -c "..."` — PowerShell mangles quotes and backslashes in multi-line strings.
2. **CRLF line endings:** `core/downloader.py` uses CRLF. When patching with Python scripts, normalize with `.replace('\r\n', '\n')` before string matching, then write back with `open(..., newline='')`.
3. **`threading.RLock`:** `DownloadManager` uses `RLock` — **never revert to `Lock`**. `self.log()` is called inside lock scopes, which would deadlock with a plain `Lock`.
4. **Chapter number sorting:** Always use `parse_chapter_number()`, never compare strings directly (e.g. `"9" > "10"` is `True` lexicographically).
5. **Path security:** Every API endpoint accepting a `path` query param must call `_checked_library_file(path)`.
6. **Port conflicts:** Multiple server instances cause 404 on new endpoints. Kill all Python processes (`Stop-Process -Name python -Force`) before restarting.
7. **Duplicate model classes:** Patch scripts that run twice can create duplicate Pydantic model definitions. Always grep for the class name before adding.

---

## Testing Changes

```bash
# Start server (from project root)
python main.py --no-browser

# Quick endpoint check (use a .py file in PS, not -c)
import requests
print(requests.get("http://127.0.0.1:8000/api/library").json())

# Syntax check before restarting
python -m py_compile server/app.py
python -m py_compile core/downloader.py
python -m py_compile core/exporter.py
python -m py_compile core/updater.py
```

Hard-reload the browser with **Ctrl+Shift+R** after any CSS/JS change to bypass the cache.

---

## Dependencies

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | Web server |
| `requests` | HTTP for provider scrapers |
| `beautifulsoup4` | HTML parsing (MangaPill, nhentai) |
| `pillow` | Image validation/conversion |
| `img2pdf` | Lossless image → PDF |
| `pypdfium2` | PDF rendering for in-app reader |
| `pikepdf` | PDF manipulation (PDF→CBZ) |
| `python-multipart` | File upload support |
| `pymangaplus` | MANGA Plus API client |
| `protobuf` | Required by `pymangaplus` |
| `rich` | CLI pretty output |

Install all: `pip install -r requirements.txt`

---

## Git Workflow Notes

- **Git binary (Windows):** `C:\Users\SAK\AppData\Local\GitHubDesktop\app-3.6.7\resources\app\git\cmd\git.exe`
- **Gitignored:** `manga_download/`, `*.cbz`, `*.pdf`, `__pycache__/`, `.env`
- **Branch:** `main`
- Commit message format: short imperative summary, e.g. `"Add auto-update library flow"`
