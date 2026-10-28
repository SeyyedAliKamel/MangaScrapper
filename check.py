import os
import shutil
import time
import zipfile

from config import MANGA_ID, OUTPUT_DIR, IMAGE_EXTS
from manga_utils import (
    get_chapter_map,
    get_chapter_folder,
    get_chapter_sort_key,
    check_chapter_status,
    download_chapter_images,
    sanitize_filename,
)
from providers import resolve_manga

def combine_all_chapters(manga_name, chapters_with_images):
    """
    Combine all non-empty chapters (in order) into one CBZ, named after the
    manga and its chapter range, e.g. "One Piece_Chapter_1-65.cbz".
    Returns the path to the combined CBZ.
    """
    chap_nums = [c for c, _ in chapters_with_images]
    first, last = chap_nums[0], chap_nums[-1]

    safe_name = sanitize_filename(manga_name) or "Manga"
    combined_filename = f"{safe_name}_Chapter_{first}-{last}.cbz"
    combined_path = os.path.join(OUTPUT_DIR, combined_filename)

    with zipfile.ZipFile(combined_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for chap_num, folder in chapters_with_images:
            images = sorted(
                f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXTS)
            )
            for img in images:
                img_path = os.path.join(folder, img)
                arcname = f"Chapter_{chap_num}/{img}"
                zf.write(img_path, arcname=arcname)

    print(f"\nCombined CBZ saved: {combined_path}")
    return combined_path

def delete_chapter_artifacts(chapters_with_images):
    for chap_num, folder in chapters_with_images:
        for extension in (".pdf", ".cbz"):
            chapter_file = os.path.join(
                OUTPUT_DIR, f"Chapter_{chap_num}{extension}"
            )
            try:
                os.remove(chapter_file)
            except FileNotFoundError:
                pass
            except OSError as e:
                print(f"  Warning: couldn't delete {chapter_file}: {e}")

        try:
            shutil.rmtree(folder)
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"  Warning: couldn't delete {folder}: {e}")

def print_empty_report(empty_dict):
    if not empty_dict:
        print("All chapters are present and downloaded.")
        return
    print("The following chapters have issues:")
    for c, reason in empty_dict.items():
        print(f"  - Chapter {c}: {reason}")

def main():
    manga_id = MANGA_ID
    if not manga_id or manga_id == "MangaIdHere":
        user_input = input("Enter Manga Title, ID, or URL (leave blank to combine existing folders): ").strip()
        if not user_input:
            # Check local uncombined folders
            folders = [
                d for d in os.listdir(OUTPUT_DIR)
                if os.path.isdir(os.path.join(OUTPUT_DIR, d)) and d.startswith("Chapter_")
            ]
            if not folders:
                print("No chapter folders found in output directory.")
                return
            manga_name = input("Enter Manga name for CBZ: ").strip() or "Manga"
            chapters_with_images = []
            for d in folders:
                chap_num = d.replace("Chapter_", "")
                p = os.path.join(OUTPUT_DIR, d)
                if any(f.lower().endswith(IMAGE_EXTS) for f in os.listdir(p)):
                    chapters_with_images.append((chap_num, p))
            chapters_with_images.sort(key=lambda pair: get_chapter_sort_key(pair[0]))
            combine_all_chapters(manga_name, chapters_with_images)
            delete_chapter_artifacts(chapters_with_images)
            print("Done!")
            return
        manga_id = user_input

    # If it's a title, resolve to UUID or ID
    if len(manga_id) != 36:
        _, details, _ = resolve_manga(manga_id, "mangadex")
        if details:
            print(f"Resolved to: {details.title} ({details.id})")
            manga_id = details.id

    print(f"Fetching chapter list from MangaDex for {manga_id}...")
    chap_num_to_id, chap_numbers = get_chapter_map(manga_id)

    if not chap_numbers:
        print("No English chapters found for this manga.")
        return

    latest = [c for c in chap_numbers if c != "unknown"]
    if latest:
        print(f"Latest chapter available: {latest[-1]}")
    print(f"Total chapters found: {len(chap_numbers)}\n")

    # Initial check
    empty_chapters = {}
    chapters_with_images = []

    for chap_num in chap_numbers:
        is_empty, reason = check_chapter_status(chap_num)
        if is_empty:
            empty_chapters[chap_num] = reason
        else:
            chapters_with_images.append((chap_num, get_chapter_folder(chap_num)))

    print_empty_report(empty_chapters)
    print(f"\n{len(chapters_with_images)} chapter(s) have images and can be combined.")

    # Retry option
    if empty_chapters:
        retry_answer = input(
            "\nRetry downloading missing/empty chapters? (y/n): "
        ).strip().lower()

        if retry_answer == "y":
            print("\nRetrying missing/empty chapters...")
            still_empty = {}

            for chap_num in list(empty_chapters.keys()):
                if chap_num == "unknown":
                    still_empty[chap_num] = "no chapter number, skipped retry"
                    continue

                chap_id = chap_num_to_id.get(chap_num)
                if not chap_id:
                    continue
                print(f"  Retrying Chapter {chap_num} ...")
                success, reason = download_chapter_images(chap_id, chap_num)
                time.sleep(0.2)

                if success:
                    print("    Success.")
                    chapters_with_images.append((chap_num, get_chapter_folder(chap_num)))
                else:
                    print(f"    Still failed: {reason}")
                    still_empty[chap_num] = reason

            print("\nRetry finished. Updated status:")
            print_empty_report(still_empty)
            print(f"\n{len(chapters_with_images)} chapter(s) now have images.")
            empty_chapters = still_empty

    if not chapters_with_images:
        print("\nNothing to combine. Exiting.")
        return

    # Combine confirmation
    combine_answer = input(
        "\nCombine all downloaded chapters into a single CBZ? (y/n): "
    ).strip().lower()

    if combine_answer == "y":
        manga_name = input("Enter the manga's name: ").strip()
        while not manga_name:
            manga_name = input("Please enter a non-empty name: ").strip()

        chapters_with_images.sort(key=lambda pair: get_chapter_sort_key(pair[0]))
        combine_all_chapters(manga_name, chapters_with_images)

        print("Deleting per-chapter files and folders...")
        delete_chapter_artifacts(chapters_with_images)
        print("Done.")

if __name__ == "__main__":
    main()
