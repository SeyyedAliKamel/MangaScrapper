import os
import re
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from providers import resolve_manga
from providers.base import ChapterInfo, parse_chapter_number
from core.library import scan_library
from core.exporter import sanitize_filename, get_chapters_in_cbz

def check_archive_updates(archive_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Check if an existing combined CBZ archive has newer chapters available online.
    archive_info is a dictionary produced by scan_library()['combined_archives'].
    """
    manga_name = archive_info.get("manga_name") or ""
    filepath = archive_info.get("filepath") or ""
    existing_chapters = set(archive_info.get("chapters", []))

    if not existing_chapters and os.path.isfile(filepath):
        existing_chapters = set(get_chapters_in_cbz(filepath))

    # Clean manga name for search
    clean_name = manga_name.replace("_", " ").strip()
    clean_name = re.sub(r"\s+Chapter.*$", "", clean_name, flags=re.IGNORECASE).strip()

    prov, details, all_chapters = resolve_manga(clean_name or manga_name)
    if not prov or not details or not all_chapters:
        return {
            "manga_name": clean_name or manga_name,
            "filepath": filepath,
            "has_updates": False,
            "error": "Could not match series on manga providers",
            "provider": None,
            "existing_count": len(existing_chapters),
            "existing_range": archive_info.get("chapter_range", "?"),
            "latest_online": "?",
            "new_count": 0,
            "new_chapters": [],
        }

    # Determine highest chapter number currently in the archive
    max_existing = 0.0
    for c in existing_chapters:
        try:
            val = parse_chapter_number(c)
            if val > max_existing:
                max_existing = val
        except Exception:
            pass

    # A chapter is considered "new" if it's not already in the archive
    # Prefer chapters strictly greater than the current max chapter
    subsequent_new: List[ChapterInfo] = []
    missing_any: List[ChapterInfo] = []

    for chap in all_chapters:
        c_num = (chap.chapter_num or "").strip()
        if not c_num or c_num == "unknown":
            continue
        if c_num not in existing_chapters:
            missing_any.append(chap)
            try:
                if parse_chapter_number(c_num) > max_existing:
                    subsequent_new.append(chap)
            except Exception:
                pass

    # Target new chapters
    target_new = subsequent_new if subsequent_new else missing_any
    target_new.sort(key=lambda c: parse_chapter_number(c.chapter_num))

    latest_online = all_chapters[-1].chapter_num if all_chapters else "?"

    return {
        "manga_name": details.title or clean_name or manga_name,
        "filepath": filepath,
        "has_updates": len(target_new) > 0,
        "provider": prov.name,
        "provider_display": prov.display_name,
        "manga_id": details.id,
        "cover_url": details.cover_url or "",
        "existing_count": len(existing_chapters),
        "existing_range": archive_info.get("chapter_range", "?"),
        "latest_online": str(latest_online),
        "new_count": len(target_new),
        "new_chapters": [c.to_dict() for c in target_new],
    }

def check_all_library_updates(output_dir: str, max_workers: int = 4) -> List[Dict[str, Any]]:
    """
    Scans all combined archives in output_dir and checks each for updates in parallel.
    """
    lib = scan_library(output_dir)
    archives = lib.get("combined_archives", [])
    if not archives:
        return []

    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_arc = {executor.submit(check_archive_updates, arc): arc for arc in archives}
        for future in as_completed(future_to_arc):
            arc = future_to_arc[future]
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                results.append({
                    "manga_name": arc.get("manga_name", "Unknown"),
                    "filepath": arc.get("filepath", ""),
                    "has_updates": False,
                    "error": str(e),
                    "new_count": 0,
                    "new_chapters": [],
                })

    results.sort(key=lambda x: x.get("manga_name", "").lower())
    return results
