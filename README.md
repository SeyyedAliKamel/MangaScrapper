# MangaScrapper Pro 📖

A modern, high-speed multi-source manga downloader, reader, and archiver with a sleek browser dashboard and command-line support.

---

## ✨ Features

1. **🎨 Modern Web UI Dashboard**
   - Clean, dark-themed responsive UI with cover previews, search cards, and chapter selection.
   - Live download manager with concurrent page downloading and real-time activity log console.
   - Built-in Library Explorer to view, download, or combine downloaded manga archives.

2. **🌐 Multi-Source Manga Engine**
   - **MangaDex**: Official API integration, English & multi-language feed, automatic preferred scanlation selection.
   - **MangaPill**: High-speed CDN mirror with full chapter archives and high-resolution images.
   - **MANGA Plus**: Official Shueisha platform API with real-time simulpubs (first 3 & latest chapters of *One Piece*, *Jujutsu Kaisen*, *Chainsaw Man*, *Oshi no Ko*, *Boruto*, *Dandadan*, etc.) featuring automatic 16-byte XOR image descrambling.
   - **ComicK**: Rich metadata index, exact total chapter counts, and official high-definition unblocked cover art (`meo.comick.pictures`) with automatic chapter download delegation.
   - Extensible provider architecture to easily plug in new scrapers.

3. **🔞 Dedicated Doujin / H-Gallery Tab (CIN & nhentai)**
   - Complete separation from regular manga search with dark ambient aura animation.
   - **CIN (`cin.wtf` / `cin.blue`)**: Next.js backend integration with high-speed mirror CDNs and automatic fallback.
   - **nhentai**: Official v2 REST API integration.
   - Quick 6-digit ID resolution (e.g. `177013`), title & tag search, and 1-click gallery downloads to CBZ or PDF.

4. **📖 Built-in Web Reader (CBZ & PDF)**
   - Read downloaded manga and doujinshi directly in your browser without external viewer apps.
   - Supports **Single Page** mode, **Webtoon / Vertical Scroll**, and **Native PDF**.
   - Includes reading direction toggle (LTR / RTL), zoom controls, fit-height / fit-width, live page slider, and chapter jump navigation.

5. **🛠️ Download Failure Recovery Dashboard**
   - Automatically tracks any missing or interrupted pages during high-speed concurrent downloads.
   - One-click retry for individual pages, full chapters, or all missing pages at once.
   - Automatically patches and repacks the final CBZ and PDF documents when missing pages are recovered.

6. **🏷️ Custom Series Naming & Series-Aware Chapter Names**
   - Live naming preview in the download modal with optional custom series/archive naming.
   - Series-aware chapter filenames: `Series - Chapter 1 - Title.pdf` (no more ambiguous `Chapter_1.pdf` files).
   - Optional chapter range toggle in combined archives (`Series_Chapter_1-50.cbz` vs. `Series.cbz`).

7. **🔄 CBZ ⇄ PDF Converter (with Live Progress & Cancel)**
   - Convert **CBZ to PDF**: Unpacks images with natural page ordering and losslessly binds into PDF documents using `img2pdf`.
   - Convert **PDF to CBZ**: High-speed, robust page rendering using `pypdfium2` and packages into a `.cbz` comic archive.
   - Real-time animated progress bar with percentage, page count indicator, and instant cancellation.
   - Available via Drag & Drop in the Web UI, 1-click in the Library tab, or directly via CLI (`--convert`).

8. **🔍 Universal Search & Direct URL Resolution (No manual IDs required!)**
   - Search by title or keyword across manga providers in parallel with cross-provider relevance ranking.
   - Or paste any direct manga or chapter URL (from MangaDex, MangaPill, CIN) to open and download it immediately.

9. **📦 Flexible Export & Archiving**
   - Per-chapter **CBZ** (`Series - Chapter 1.cbz`)
   - Per-chapter **PDF** (`Series - Chapter 1.pdf`)
   - **Combined Manga Archive** (`Series_Chapter_1-100.cbz`)
   - Auto-clean temporary folder artifacts after combining.
   - Incremental update support: append newly released chapters to an existing combined CBZ.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch the Web UI
Simply run:
```bash
python main.py
```
This automatically starts the local server and opens your browser at **http://127.0.0.1:8000**.

---

## 💻 Command-Line Usage (CLI)

You can also use MangaScrapper completely from the terminal:

### Search & Download a Manga
```bash
python main.py --cli --query "Chainsaw Man"
```

### Download from a Specific Provider
```bash
python main.py --cli --query "One Piece" --provider mangapill
```

### Download using Direct URL
```bash
python main.py --cli --query "https://mangadex.org/title/a77742b1-befd-49a4-bff5-1ad4e6b0ef7b"
```

### Convert CBZ ⇄ PDF
```bash
# Convert a CBZ into a PDF
python main.py --convert "manga_download/Chapter_1.cbz"

# Convert a PDF into a CBZ
python main.py --convert "manga_download/Chapter_1.pdf"
```

### Utilities
- **`python check.py`**: Check status of downloaded chapters, retry missing chapters, and combine into a single CBZ.
- **`python update_cbz.py`**: Scan existing combined CBZ files in your output directory and append newly released chapters.

---

## ⚙️ Configuration

Settings can be managed directly in the **Settings tab** of the Web UI or in `config.py`:
- `OUTPUT_DIR`: The folder where chapters, PDFs, and CBZ archives are stored (default: `manga_download`).

---

## 🗺️ Roadmap & Planned Features (TODO List)

The following improvements are queued for evaluation and approval:

- [ ] **1. 🖼️ AI Manga Upscaler (2× / 4× Real-ESRGAN / Waifu2x)**
  - Optional toggle in download options (`[ ] AI Upscale Pages`) powered by a lightweight, cross-platform Vulkan binary (`realesrgan-ncnn-vulkan`).
  - Reconstructs jagged line art and cleans low-res retro scans/furigana into razor-sharp, print-grade pages without needing heavy CUDA/PyTorch setups.

- [ ] **2. 📖 Reader Polish: Two-Page Spread Mode (Manga Spread View)**
  - Add a **Double-Page (Spread)** reading mode to the built-in reader displaying side-by-side pages with proper Japanese Right-to-Left (RTL) page pairing.
  - Preserves dramatic two-page action spreads and panoramic artwork.

- [ ] **3. 🔖 Reading Progress & Bookmark Persistence**
  - Save last read page, reading mode, and zoom settings per manga/chapter in `localStorage`.
  - Automatically resumes reading where you left off when opening any book from the Library.

- [x] **4. 🔄 Auto-Update Library (Check for New Chapters)** *(Implemented)*
  - A "Check for Updates" button on library series cards and global toolbar that queries online catalogs for new releases.
  - 1-click update modal with scope selection (All new chapters, next 1/5/10/25/50 chapters), automatically fetching and cleanly appending them to existing combined CBZ archives with natural chapter sorting and automatic range updating (e.g. `Chapter 1-2.cbz` -> `Chapter 1-10.cbz`).

- [ ] **5. 🗂️ Sequential Download Queue**
  - Queue multiple manga series to download sequentially in the background.
  - Ideal for large multi-series batch downloads and overnight runs.

- [ ] **6. 🏷️ Embedded `ComicInfo.xml` Metadata (Tachiyomi / Mihon / Kavita / Komga)**
  - Automatically inject a standard `ComicInfo.xml` file inside all generated `.cbz` archives containing title, author, summary, tags, and chapter numbers.
  - Instantly loads rich cover art, series info, and chapter indices in third-party readers.

- [ ] **7. 📱 Kindle & E-Reader Optimized Export (EPUB & Grayscale Compression)**
  - Add dedicated export profiles for e-ink devices (Kindle Paperwhite, Kobo) with 8-bit grayscale optimization and `.epub` packaging.
  - Cuts file sizes by 60–70% while perfectly formatting images for e-reader aspect ratios.
