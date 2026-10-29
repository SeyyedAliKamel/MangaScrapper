# In-app reader backend that serves single pages from CBZ archives and rendered PDF files
import io
import os
import re
import zipfile
import threading
from typing import Dict, Any, List, Tuple

from PIL import Image

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

# pdfium is not thread safe, so every PDF call goes through this lock
_pdf_lock = threading.Lock()
_index_cache: Dict[Tuple[str, float], List[str]] = {}
_cache_lock = threading.Lock()


def _natural_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+(?:\.\d+)?)", name) if part]


def _chapter_sort_key(name: str):
    folder, _, base = name.rpartition("/")
    m = re.search(r"(\d+(?:\.\d+)?)", folder)
    chap = float(m.group(1)) if m else -1.0
    return (chap, _natural_key(folder), _natural_key(base))


def resolve_library_path(path: str, library_root: str) -> str:
    """Only allow files that live inside the library folder."""
    if not path:
        raise ValueError("Missing file path")
    real_root = os.path.normcase(os.path.realpath(library_root))
    real_path = os.path.realpath(path)
    if os.path.commonpath([real_root, os.path.normcase(real_path)]) != real_root:
        raise PermissionError("File is outside the library folder")
    if not os.path.isfile(real_path):
        raise FileNotFoundError("File not found")
    ext = os.path.splitext(real_path)[1].lower()
    if ext not in (".cbz", ".pdf"):
        raise ValueError("Only .cbz and .pdf files can be opened in the reader")
    return real_path


def _cbz_entries(path: str) -> List[str]:
    key = (path, os.path.getmtime(path))
    with _cache_lock:
        cached = _index_cache.get(key)
    if cached is not None:
        return cached

    with zipfile.ZipFile(path, "r") as zf:
        names = [
            n for n in zf.namelist()
            if not n.endswith("/")
            and n.lower().endswith(IMAGE_EXTS)
            and not os.path.basename(n).startswith(".")
            and "__MACOSX" not in n
        ]
    names.sort(key=_chapter_sort_key)

    with _cache_lock:
        # Drop stale entries for the same file (archive was rebuilt after a retry)
        for k in [k for k in _index_cache if k[0] == path]:
            del _index_cache[k]
        _index_cache[key] = names
    return names


def get_book_info(path: str) -> Dict[str, Any]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".cbz":
        entries = _cbz_entries(path)
        chapters: List[Dict[str, Any]] = []
        last_folder = None
        for i, name in enumerate(entries):
            folder = name.rpartition("/")[0]
            if folder and folder != last_folder:
                label = folder.split("/")[-1].replace("Chapter_", "Chapter ").replace("_", " ")
                chapters.append({"label": label, "start": i})
                last_folder = folder
        return {"format": "cbz", "pages": len(entries), "chapters": chapters if len(chapters) > 1 else []}

    import pypdfium2 as pdfium
    with _pdf_lock:
        pdf = pdfium.PdfDocument(path)
        try:
            count = len(pdf)
        finally:
            pdf.close()
    return {"format": "pdf", "pages": count, "chapters": []}


def get_page_image(path: str, index: int) -> Tuple[bytes, str]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".cbz":
        entries = _cbz_entries(path)
        if index < 0 or index >= len(entries):
            raise IndexError("Page out of range")
        name = entries[index]
        with zipfile.ZipFile(path, "r") as zf:
            data = zf.read(name)
        mime = MIME_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream")
        return data, mime

    import pypdfium2 as pdfium
    with _pdf_lock:
        pdf = pdfium.PdfDocument(path)
        try:
            if index < 0 or index >= len(pdf):
                raise IndexError("Page out of range")
            page = pdf[index]
            try:
                # Scale so the long edge lands around 2000px, sharp enough for reading without huge files
                width, height = page.get_size()
                scale = max(1.0, min(3.0, 2000 / max(width, height, 1)))
                pil_image = page.render(scale=scale).to_pil()
            finally:
                page.close()
        finally:
            pdf.close()

    if pil_image.mode not in ("RGB", "L"):
        pil_image = pil_image.convert("RGB")
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=88, optimize=True)
    return buf.getvalue(), "image/jpeg"
