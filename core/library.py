import os
import re
import glob
from typing import List, Dict, Any, Optional, Tuple
from core.exporter import (
    get_chapters_in_cbz,
    combine_chapters_into_cbz,
    append_to_existing_cbz,
    sanitize_filename,
)
from providers.base import parse_chapter_number

CBZ_PATTERN = re.compile(r"^(?P<name>.+)_Chapter_(?P<first>[^-]+)-(?P<last>.+)\.cbz$", re.IGNORECASE)

def scan_library(output_dir: str) -> Dict[str, Any]:
    """Scan the output directory and return all archives, chapters, and summary stats."""
    if not os.path.exists(output_dir):
        return {
            "output_dir": output_dir,
            "combined_archives": [],
            "individual_chapters": [],
            "uncombined_folders": [],
            "total_size_mb": 0.0,
        }

    combined_archives = []
    individual_chapters = []
    uncombined_folders = []
    total_bytes = 0

    # Scan combined CBZ archives
    for filepath in glob.glob(os.path.join(output_dir, "*_Chapter_*-*.cbz")):
        fname = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        mtime = os.path.getmtime(filepath)
        total_bytes += size

        match = CBZ_PATTERN.match(fname)
        manga_name = match.group("name") if match else "Unknown"
        first = match.group("first") if match else "?"
        last = match.group("last") if match else "?"

        chapters_inside = get_chapters_in_cbz(filepath)
        chapters_inside.sort(key=parse_chapter_number)

        combined_archives.append({
            "filename": fname,
            "filepath": filepath,
            "manga_name": manga_name,
            "chapter_range": f"{first}-{last}",
            "first_chapter": first,
            "last_chapter": last,
            "chapter_count": len(chapters_inside),
            "chapters": chapters_inside,
            "size_bytes": size,
            "size_mb": round(size / (1024 * 1024), 2),
            "modified": mtime,
        })

    # Scan individual chapter files (.cbz and .pdf)
    chap_file_regex = re.compile(r"^Chapter_([^.]+)\.(cbz|pdf)$", re.IGNORECASE)
    for fname in os.listdir(output_dir):
        fpath = os.path.join(output_dir, fname)
        if os.path.isfile(fpath):
            m = chap_file_regex.match(fname)
            if m:
                chap_num = m.group(1)
                ext = m.group(2).lower()
                size = os.path.getsize(fpath)
                total_bytes += size
                individual_chapters.append({
                    "filename": fname,
                    "filepath": fpath,
                    "chapter_num": chap_num,
                    "format": ext,
                    "size_mb": round(size / (1024 * 1024), 2),
                })
        elif os.path.isdir(fpath) and fname.startswith("Chapter_"):
            chap_num = fname[len("Chapter_"):]
            imgs = [
                os.path.join(fpath, f)
                for f in os.listdir(fpath)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            ]
            if imgs:
                folder_size = sum(os.path.getsize(img) for img in imgs)
                total_bytes += folder_size
                uncombined_folders.append({
                    "folder_name": fname,
                    "folder_path": fpath,
                    "chapter_num": chap_num,
                    "image_count": len(imgs),
                    "size_mb": round(folder_size / (1024 * 1024), 2),
                })

    individual_chapters.sort(key=lambda x: (parse_chapter_number(x["chapter_num"]), x["format"]))
    uncombined_folders.sort(key=lambda x: parse_chapter_number(x["chapter_num"]))

    return {
        "output_dir": output_dir,
        "combined_archives": combined_archives,
        "individual_chapters": individual_chapters,
        "uncombined_folders": uncombined_folders,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
    }

def combine_existing_folders(
    manga_name: str,
    output_dir: str,
    clean_folders: bool = False
) -> str:
    """Combines all uncombined Chapter_* directories into a single CBZ archive."""
    library_info = scan_library(output_dir)
    folders = library_info.get("uncombined_folders", [])
    if not folders:
        raise ValueError("No chapter image folders found to combine in output directory.")

    chapters_with_images = []
    for item in folders:
        chap_num = item["chapter_num"]
        folder_path = item["folder_path"]
        imgs = [
            os.path.join(folder_path, f)
            for f in sorted(os.listdir(folder_path))
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
        ]
        if imgs:
            chapters_with_images.append((chap_num, imgs))

    chapters_with_images.sort(key=lambda x: parse_chapter_number(x[0]))
    combined_path = combine_chapters_into_cbz(manga_name, chapters_with_images, output_dir)

    if clean_folders:
        for item in folders:
            import shutil
            shutil.rmtree(item["folder_path"], ignore_errors=True)

    return combined_path
