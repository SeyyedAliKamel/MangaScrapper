import os
import re
import io
import zipfile
import tempfile
import shutil
from typing import Optional, List
from PIL import Image
import img2pdf
import pikepdf

def natural_sort_key(s: str):
    """Sort strings containing numbers in natural human order (e.g. 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def cbz_to_pdf(cbz_path: str, output_path: Optional[str] = None) -> str:
    """
    Convert a .cbz archive to a .pdf document.
    """
    if not os.path.isfile(cbz_path):
        raise FileNotFoundError(f"CBZ file not found: {cbz_path}")

    base_name = os.path.splitext(os.path.basename(cbz_path))[0]
    out_dir = os.path.dirname(cbz_path)
    final_pdf_path = output_path or os.path.join(out_dir, f"{base_name}.pdf")

    temp_dir = tempfile.mkdtemp(prefix="cbz2pdf_")
    try:
        image_files = []
        with zipfile.ZipFile(cbz_path, "r") as zf:
            names = [
                n for n in zf.namelist()
                if not n.startswith("__MACOSX") and n.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))
            ]
            names.sort(key=natural_sort_key)

            if not names:
                raise ValueError("No valid image files found inside the CBZ archive.")

            for i, name in enumerate(names, start=1):
                extracted_path = zf.extract(name, temp_dir)
                # Verify image can be opened
                try:
                    with Image.open(extracted_path) as img:
                        # Convert RGBA or WebP if needed for img2pdf compatibility
                        if img.format not in ("JPEG", "PNG") or img.mode not in ("RGB", "L", "1"):
                            converted_path = os.path.join(temp_dir, f"converted_{i:04d}.jpg")
                            rgb = img.convert("RGB")
                            rgb.save(converted_path, format="JPEG", quality=95)
                            image_files.append(converted_path)
                        else:
                            image_files.append(extracted_path)
                except Exception as e:
                    print(f"Skipping unreadable image {name}: {e}")

        if not image_files:
            raise ValueError("No convertible images could be extracted from CBZ.")

        with open(final_pdf_path, "wb") as f:
            f.write(img2pdf.convert(image_files, rotation=img2pdf.Rotation.ifvalid))

        return final_pdf_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def pdf_to_cbz(pdf_path: str, output_path: Optional[str] = None) -> str:
    """
    Extract images from a .pdf document and pack them into a .cbz archive.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    out_dir = os.path.dirname(pdf_path)
    final_cbz_path = output_path or os.path.join(out_dir, f"{base_name}.cbz")

    temp_dir = tempfile.mkdtemp(prefix="pdf2cbz_")
    try:
        extracted_images = []
        with pikepdf.open(pdf_path) as pdf:
            img_counter = 1
            for page_idx, page in enumerate(pdf.pages, start=1):
                # Use get_images() to find images on this page
                raw_images = page.get_images()
                for img_name, raw_image in raw_images.items():
                    try:
                        p_img = pikepdf.PdfImage(raw_image)
                        pil_img = p_img.as_pil_image()
                        
                        ext = "jpg"
                        if pil_img.format == "PNG" or pil_img.mode in ("RGBA", "P"):
                            ext = "png"
                            save_format = "PNG"
                        else:
                            save_format = "JPEG"
                            if pil_img.mode != "RGB":
                                pil_img = pil_img.convert("RGB")

                        img_filename = f"page_{img_counter:04d}.{ext}"
                        img_dest = os.path.join(temp_dir, img_filename)
                        pil_img.save(img_dest, format=save_format, quality=95)
                        extracted_images.append(img_dest)
                        img_counter += 1
                    except Exception as err:
                        print(f"Warning: Failed to extract image {img_name} on page {page_idx}: {err}")

        if not extracted_images:
            raise ValueError("No images could be extracted from the PDF document.")

        with zipfile.ZipFile(final_cbz_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for img_p in extracted_images:
                zf.write(img_p, arcname=os.path.basename(img_p))

        return final_cbz_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
