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
   - **Comick**: Multi-source aggregator support and fast metadata search.
   - **nhentai (18+)**: Official V2 API integration, full gallery search, 6-digit ID resolution, and direct URL support.
   - Extensible provider architecture to easily plug in new scrapers.

3. **🔄 CBZ ⇄ PDF Converter (Bidirectional)**
   - Convert **CBZ to PDF**: Unpacks images with natural page ordering and losslessly binds into PDF documents using `img2pdf`.
   - Convert **PDF to CBZ**: Extracts embedded raster page images with `pikepdf` and packages into a `.cbz` comic archive.
   - Available via Drag & Drop in the Web UI, 1-click in the Library tab, or directly via CLI (`--convert`).

4. **🔍 Universal Search & Direct URL Resolution (No manual IDs required!)**
   - Search by title or keyword across all providers in parallel.
   - Or paste any direct manga or chapter URL (from MangaDex, MangaPill, Comick) to open and download it immediately.

4. **📦 Flexible Export & Archiving**
   - Per-chapter **CBZ** (`Chapter_1.cbz`)
   - Per-chapter **PDF** (`Chapter_1.pdf`)
   - **Combined Manga Archive** (`MangaName_Chapter_1-100.cbz`)
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
