import os
import re
import shutil
import zipfile
from typing import List, Tuple, Optional
import img2pdf
from PIL import Image

def sanitize_filename(name: str) -> str:
    """Strip characters that are problematic in filenames across OSes."""
    if not name:
        return "Manga"
    invalid = '<>:"/\\|?*\n\r\t'
    cleaned = "".join(c for c in name if c not in invalid)
    cleaned = cleaned.strip(" .")
    return cleaned if cleaned else "Manga"

def save_chapter_as_pdf(chapter_num: str, image_paths: List[str], output_dir: str) -> str:
    """Convert a list of images into a single chapter PDF."""
    os.makedirs(output_dir, exist_ok=True)
    pdf_filename = f"Chapter_{chapter_num}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)

    # Filter out corrupted or unreadable images
    valid_paths = []
    for p in image_paths:
        try:
            with Image.open(p) as img:
                img.verify()
            valid_paths.append(p)
        except Exception as e:
            print(f"Skipping corrupted image {p} for PDF conversion: {e}")

    if not valid_paths:
        raise ValueError(f"No valid images to convert to PDF for chapter {chapter_num}")

    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert(valid_paths, rotation=img2pdf.Rotation.ifvalid))

    return pdf_path

def save_chapter_as_cbz(chapter_num: str, image_paths: List[str], output_dir: str) -> str:
    """Pack chapter images into a standard .cbz zip archive."""
    os.makedirs(output_dir, exist_ok=True)
    cbz_filename = f"Chapter_{chapter_num}.cbz"
    cbz_path = os.path.join(output_dir, cbz_filename)

    with zipfile.ZipFile(cbz_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for img_path in image_paths:
            if os.path.isfile(img_path):
                zf.write(img_path, arcname=os.path.basename(img_path))

    return cbz_path

def combine_chapters_into_cbz(
    manga_name: str,
    chapters_with_images: List[Tuple[str, List[str]]],
    output_dir: str
) -> str:
    """
    Combine multiple chapters into a single archive, with images organized
    under Chapter_<num>/... subdirectories.
    """
    os.makedirs(output_dir, exist_ok=True)
    if not chapters_with_images:
        raise ValueError("No chapters provided to combine")

    chap_nums = [c for c, _ in chapters_with_images]
    first, last = chap_nums[0], chap_nums[-1]
    safe_name = sanitize_filename(manga_name)
    combined_filename = f"{safe_name}_Chapter_{first}-{last}.cbz"
    combined_path = os.path.join(output_dir, combined_filename)

    with zipfile.ZipFile(combined_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for chap_num, image_paths in chapters_with_images:
            for img_path in sorted(image_paths):
                if os.path.isfile(img_path):
                    arcname = f"Chapter_{chap_num}/{os.path.basename(img_path)}"
                    zf.write(img_path, arcname=arcname)

    return combined_path

def append_to_existing_cbz(
    cbz_path: str,
    manga_name: str,
    new_chapters: List[Tuple[str, List[str]]],
    all_sorted_chap_nums: List[str],
    output_dir: str
) -> str:
    """
    Append new chapters into an existing combined CBZ archive and rename with updated range.
    """
    tmp_path = cbz_path + ".tmp"
    with zipfile.ZipFile(cbz_path, "r") as src_zf, \
         zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst_zf:
        
        # Copy existing entries
        for item in src_zf.infolist():
            dst_zf.writestr(item, src_zf.read(item.filename))

        # Add new chapters
        for chap_num, image_paths in new_chapters:
            for img_path in sorted(image_paths):
                if os.path.isfile(img_path):
                    arcname = f"Chapter_{chap_num}/{os.path.basename(img_path)}"
                    dst_zf.write(img_path, arcname=arcname)

    first, last = all_sorted_chap_nums[0], all_sorted_chap_nums[-1]
    safe_name = sanitize_filename(manga_name)
    new_filename = f"{safe_name}_Chapter_{first}-{last}.cbz"
    new_path = os.path.join(output_dir, new_filename)

    os.remove(cbz_path)
    shutil.move(tmp_path, new_path)
    return new_path

def get_chapters_in_cbz(cbz_path: str) -> List[str]:
    """Read chapter numbers present inside a combined CBZ."""
    chapters = set()
    try:
        with zipfile.ZipFile(cbz_path, "r") as zf:
            for name in zf.namelist():
                parts = name.split("/", 1)
                if len(parts) == 2 and parts[0].startswith("Chapter_"):
                    chap_num = parts[0][len("Chapter_"):]
                    chapters.add(chap_num)
    except Exception as e:
        print(f"Error reading CBZ {cbz_path}: {e}")
    return list(chapters)
