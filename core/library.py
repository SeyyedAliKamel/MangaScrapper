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
    combined_paths = set()
    individual_chapters = []
    uncombined_folders = []
    total_bytes = 0

    # Scan combined CBZ archives
    for filepath in glob.glob(os.path.join(output_dir, "*.cbz")):
        fname = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        mtime = os.path.getmtime(filepath)

        match = CBZ_PATTERN.match(fname)
        chapters_inside = get_chapters_in_cbz(filepath)
        chapters_inside.sort(key=parse_chapter_number)

        # It is a combined archive if it matches the pattern or has chapters inside
        if match or len(chapters_inside) >= 1:
            total_bytes += size
            combined_paths.add(os.path.abspath(filepath))

            manga_name = match.group("name") if match else os.path.splitext(fname)[0]
            if match:
                first = match.group("first")
                last = match.group("last")
            elif chapters_inside:
                first = chapters_inside[0]
                last = chapters_inside[-1]
            else:
                first, last = "?", "?"

            combined_archives.append({
                "filename": fname,
                "filepath": filepath,
                "manga_name": manga_name,
                "chapter_range": f"{first}-{last}" if first != last else str(first),
                "first_chapter": first,
                "last_chapter": last,
                "chapter_count": len(chapters_inside),
                "chapters": chapters_inside,
                "size_bytes": size,
                "size_mb": round(size / (1024 * 1024), 2),
                "modified": mtime,
            })

    # Scan individual chapter files (.cbz and .pdf)
    chap_file_regex = re.compile(
        r"^(?:(?P<series>.+?)[_ -]+)?Chapter[ _](?P<chap>[0-9]+(?:\.[0-9]+)?|[a-zA-Z0-9_]+)(?:[ _-]+(?P<title>.*?))?\.(?P<ext>cbz|pdf)$",
        re.IGNORECASE
    )

    for fname in os.listdir(output_dir):
        fpath = os.path.join(output_dir, fname)
        if os.path.abspath(fpath) in combined_paths:
            continue

        if os.path.isfile(fpath):
            m = chap_file_regex.match(fname)
            if m:
                chap_num = m.group("chap")
                series_name = (m.group("series") or "").strip()
                chap_title = (m.group("title") or "").strip()
                ext = m.group("ext").lower()
                size = os.path.getsize(fpath)
                total_bytes += size
                individual_chapters.append({
                    "filename": fname,
                    "filepath": fpath,
                    "series_name": series_name or "General",
                    "chapter_num": chap_num,
                    "chapter_title": chap_title,
                    "format": ext,
                    "size_mb": round(size / (1024 * 1024), 2),
                })
        elif os.path.isdir(fpath) and ("Chapter_" in fname or "Chapter " in fname):
            m_fld = re.search(r"Chapter[ _]([0-9]+(?:\.[0-9]+)?|[a-zA-Z0-9_]+)", fname, re.IGNORECASE)
            chap_num = m_fld.group(1) if m_fld else fname
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

    individual_chapters.sort(key=lambda x: (x.get("series_name", ""), parse_chapter_number(x["chapter_num"]), x["format"]))
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
