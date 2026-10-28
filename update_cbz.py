import os
import re
import glob
import shutil
import time
import zipfile

from config import MANGA_ID, OUTPUT_DIR, IMAGE_EXTS
from manga_utils import (
    get_chapter_map,
    get_chapter_sort_key,
    get_chapter_folder,
    download_chapter_images,
)
from providers import resolve_manga

CBZ_PATTERN = re.compile(r"^(?P<name>.+)_Chapter_(?P<first>[^-]+)-(?P<last>.+)\.cbz$")

def find_combined_cbz():
    """Find the combined CBZ in OUTPUT_DIR matching the '<Name>_Chapter_X-Y.cbz' pattern."""
    candidates = glob.glob(os.path.join(OUTPUT_DIR, "*_Chapter_*-*.cbz"))
    if not candidates:
        return None
    if len(candidates) > 1:
        print("Multiple combined CBZ files found; using the most recently modified one:")
        for c in candidates:
            print(f"  - {c}")
    return max(candidates, key=os.path.getmtime)

def parse_cbz_filename(path):
    match = CBZ_PATTERN.match(os.path.basename(path))
    if not match:
        return None, None, None
    return match.group("name"), match.group("first"), match.group("last")

def get_chapters_in_cbz(cbz_path):
    """
    Returns the set of chapter numbers (as strings) already stored in the CBZ,
    based on the 'Chapter_<num>/...' subfolder layout.
    """
    chapters = set()
    with zipfile.ZipFile(cbz_path, "r") as zf:
        for name in zf.namelist():
            parts = name.split("/", 1)
            if len(parts) == 2 and parts[0].startswith("Chapter_"):
                chap_num = parts[0][len("Chapter_"):]
                chapters.add(chap_num)
    return chapters

def append_chapters_to_cbz(cbz_path, manga_name, new_chapters_with_folders, all_chapter_numbers):
    """
    Rebuilds the CBZ with its existing contents plus the newly downloaded chapters,
    renaming the file if the chapter range has changed. Returns the final path.
    """
    tmp_path = cbz_path + ".tmp"

    with zipfile.ZipFile(cbz_path, "r") as src_zf, \
         zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst_zf:
        # Copy everything that was already there
        for item in src_zf.infolist():
            dst_zf.writestr(item, src_zf.read(item.filename))

        # Add the newly downloaded chapters
        for chap_num, folder in new_chapters_with_folders:
            images = sorted(
                f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXTS)
            )
            for img in images:
                img_path = os.path.join(folder, img)
                arcname = f"Chapter_{chap_num}/{img}"
                dst_zf.write(img_path, arcname=arcname)

    # Recompute the filename from the full chapter range now in the archive
    sorted_all = sorted(all_chapter_numbers, key=get_chapter_sort_key)
    first, last = sorted_all[0], sorted_all[-1]
    new_filename = f"{manga_name}_Chapter_{first}-{last}.cbz"
    new_path = os.path.join(OUTPUT_DIR, new_filename)

    os.remove(cbz_path)
    shutil.move(tmp_path, new_path)
    return new_path

def main():
    combined_cbz = find_combined_cbz()
    if not combined_cbz:
        print(f"No combined CBZ found in '{OUTPUT_DIR}'.")
        return

    manga_name, old_first, old_last = parse_cbz_filename(combined_cbz)
    if manga_name is None:
        print(f"Couldn't parse chapter range from filename: {combined_cbz}")
        return

    print(f"Found combined CBZ: {combined_cbz}")
    print(f"  Manga name: {manga_name}")
    print(f"  Current range: {old_first}-{old_last}")

    manga_id = MANGA_ID
    if not manga_id or manga_id == "MangaIdHere":
        print(f"Auto-resolving '{manga_name}' on MangaDex...")
        _, details, _ = resolve_manga(manga_name, "mangadex")
        if details:
            manga_id = details.id
            print(f"Resolved to ID: {manga_id}")
        else:
            manga_id = input("Could not auto-resolve. Enter MangaDex ID or URL: ").strip()

    print("\nFetching current chapter list from MangaDex...")
    chap_num_to_id, all_chap_numbers = get_chapter_map(manga_id)

    if not all_chap_numbers:
        print("No English chapters found for this manga.")
        return

    chapters_in_cbz = get_chapters_in_cbz(combined_cbz)
    missing_chapters = [c for c in all_chap_numbers if c not in chapters_in_cbz]

    if not missing_chapters:
        print("\nCBZ is already up to date. Nothing to do.")
        return

    print(f"\n{len(missing_chapters)} new chapter(s) found:")
    for c in missing_chapters:
        print(f"  - Chapter {c}")

    proceed = input("\nDownload these and add them to the CBZ? (y/n): ").strip().lower()
    if proceed != "y":
        print("Skipped. Done.")
        return

    new_chapters_with_folders = []
    failed = {}

    for chap_num in missing_chapters:
        if chap_num == "unknown":
            failed[chap_num] = "no chapter number, skipped"
            continue

        chap_id = chap_num_to_id.get(chap_num)
        if not chap_id:
            continue
        print(f"  Downloading Chapter {chap_num} ...")
        success, reason = download_chapter_images(chap_id, chap_num)
        time.sleep(0.2)

        if success:
            print("    Success.")
            new_chapters_with_folders.append((chap_num, get_chapter_folder(chap_num)))
        else:
            print(f"    Failed: {reason}")
            failed[chap_num] = reason

    if not new_chapters_with_folders:
        print("\nNo new chapters were successfully downloaded. CBZ left unchanged.")
        return

    all_chapters_now = chapters_in_cbz.union(c for c, _ in new_chapters_with_folders)
    new_path = append_chapters_to_cbz(
        combined_cbz, manga_name, new_chapters_with_folders, all_chapters_now
    )

    print(f"\nUpdated CBZ saved: {new_path}")

    print("Cleaning up downloaded chapter folders...")
    for _, folder in new_chapters_with_folders:
        try:
            shutil.rmtree(folder)
        except Exception as e:
            print(f"  Warning: couldn't delete {folder}: {e}")

    if failed:
        print("\nSome chapters could not be downloaded:")
        for c, reason in failed.items():
            print(f"  - Chapter {c}: {reason}")

    print("Done.")

if __name__ == "__main__":
    main()
