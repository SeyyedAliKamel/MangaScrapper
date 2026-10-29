import os
import re
import io
import time
import zipfile
import tempfile
import shutil
import uuid
import threading
from typing import Optional, List, Callable, Dict, Any
from PIL import Image
import img2pdf
import pikepdf
import pypdfium2

def natural_sort_key(s: str):
    """Sort strings containing numbers in natural human order (e.g. 1, 2, 10 instead of 1, 10, 2)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

def cbz_to_pdf(
    cbz_path: str,
    output_path: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Convert a .cbz archive to a .pdf document with progress updates and cancellation.
    """
    if not os.path.isfile(cbz_path):
        raise FileNotFoundError(f"CBZ file not found: {cbz_path}")

    base_name = os.path.splitext(os.path.basename(cbz_path))[0]
    out_dir = os.path.dirname(cbz_path) or "."
    final_pdf_path = output_path or os.path.join(out_dir, f"{base_name}.pdf")

    temp_dir = tempfile.mkdtemp(prefix="cbz2pdf_")
    try:
        image_files = []
        with zipfile.ZipFile(cbz_path, "r") as zf:
            names = [
                n for n in zf.namelist()
                if not n.startswith("__MACOSX")
                and not os.path.basename(n).startswith(".")
                and n.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".jfif"))
            ]
            names.sort(key=natural_sort_key)

            if not names:
                raise ValueError("No valid image files found inside the CBZ archive.")

            total = len(names)
            for i, name in enumerate(names, start=1):
                if cancel_check and cancel_check():
                    raise InterruptedError("Conversion cancelled by user.")

                if progress_cb:
                    progress_cb(i, total, f"Extracting & processing page {i} of {total}...")

                extracted_path = zf.extract(name, temp_dir)
                try:
                    with Image.open(extracted_path) as img:
                        # Convert non-standard modes/formats for img2pdf
                        if img.format not in ("JPEG", "PNG") or img.mode not in ("RGB", "L", "1"):
                            converted_path = os.path.join(temp_dir, f"conv_{i:04d}.jpg")
                            rgb = img.convert("RGB")
                            rgb.save(converted_path, format="JPEG", quality=92)
                            image_files.append(converted_path)
                        else:
                            image_files.append(extracted_path)
                except Exception as e:
                    print(f"Skipping damaged image {name}: {e}")

        if cancel_check and cancel_check():
            raise InterruptedError("Conversion cancelled by user.")

        if not image_files:
            raise ValueError("No convertible images could be extracted from CBZ.")

        if progress_cb:
            progress_cb(total, total, f"Compiling {len(image_files)} pages into PDF...")

        with open(final_pdf_path, "wb") as f:
            f.write(img2pdf.convert(image_files, rotation=img2pdf.Rotation.ifvalid))

        return final_pdf_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def pdf_to_cbz(
    pdf_path: str,
    output_path: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Extract images from a .pdf document and pack them into a .cbz archive with progress updates.
    Uses pypdfium2 for reliable, high-speed page rendering with pikepdf fallback.
    """
    if not os.path.isfile(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    out_dir = os.path.dirname(pdf_path) or "."
    final_cbz_path = output_path or os.path.join(out_dir, f"{base_name}.cbz")

    temp_dir = tempfile.mkdtemp(prefix="pdf2cbz_")
    try:
        extracted_images = []
        pdf = pypdfium2.PdfDocument(pdf_path)
        total_pages = len(pdf)

        if total_pages == 0:
            raise ValueError("PDF document contains 0 pages.")

        for i in range(total_pages):
            if cancel_check and cancel_check():
                raise InterruptedError("Conversion cancelled by user.")

            page_num = i + 1
            if progress_cb:
                progress_cb(page_num, total_pages, f"Rendering page {page_num} of {total_pages}...")

            page = pdf[i]
            # Render at 2.0x scale (standard crisp 144 DPI for comic readers)
            pil_img = page.render(scale=2.0).to_pil()

            img_filename = f"page_{page_num:04d}.jpg"
            img_dest = os.path.join(temp_dir, img_filename)
            if pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")
            pil_img.save(img_dest, format="JPEG", quality=90)
            extracted_images.append(img_dest)

        if cancel_check and cancel_check():
            raise InterruptedError("Conversion cancelled by user.")

        if not extracted_images:
            raise ValueError("No images could be extracted/rendered from the PDF.")

        if progress_cb:
            progress_cb(total_pages, total_pages, f"Packing {len(extracted_images)} pages into CBZ...")

        with zipfile.ZipFile(final_cbz_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for img_p in extracted_images:
                zf.write(img_p, arcname=os.path.basename(img_p))

        return final_cbz_path

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


class ConversionJob:
    def __init__(self, job_id: str, filename: str, target_format: str):
        self.job_id = job_id
        self.filename = filename
        self.target_format = target_format
        self.status = "running"  # running, completed, cancelled, error
        self.current_page = 0
        self.total_pages = 0
        self.percent = 0
        self.stage = "Starting conversion..."
        self.output_file = ""
        self.error_message = ""
        self.cancel_requested = False
        self.start_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "target_format": self.target_format,
            "status": self.status,
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "percent": self.percent,
            "stage": self.stage,
            "output_file": self.output_file,
            "error_message": self.error_message,
        }


class ConversionManager:
    def __init__(self):
        self.jobs: Dict[str, ConversionJob] = {}
        self.lock = threading.RLock()

    def start_job(self, input_path: str, target_format: str, output_path: Optional[str] = None) -> str:
        job_id = str(uuid.uuid4())
        fname = os.path.basename(input_path)
        job = ConversionJob(job_id=job_id, filename=fname, target_format=target_format.upper())

        with self.lock:
            self.jobs[job_id] = job

        def worker():
            def progress(current, total, stage_text):
                with self.lock:
                    job.current_page = current
                    job.total_pages = total
                    job.stage = stage_text
                    if total > 0:
                        job.percent = int((current / total) * 100)

            def cancel_check():
                with self.lock:
                    return job.cancel_requested

            try:
                if target_format.lower() == "pdf":
                    out = cbz_to_pdf(input_path, output_path, progress_cb=progress, cancel_check=cancel_check)
                elif target_format.lower() == "cbz":
                    out = pdf_to_cbz(input_path, output_path, progress_cb=progress, cancel_check=cancel_check)
                else:
                    raise ValueError(f"Unsupported target format: {target_format}")

                with self.lock:
                    job.status = "completed"
                    job.percent = 100
                    job.stage = "Conversion completed!"
                    job.output_file = out

            except InterruptedError:
                with self.lock:
                    job.status = "cancelled"
                    job.stage = "Conversion cancelled by user."

            except Exception as e:
                with self.lock:
                    job.status = "error"
                    job.stage = f"Error: {str(e)}"
                    job.error_message = str(e)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return job_id

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job.status == "running":
                job.cancel_requested = True
                job.status = "cancelled"
                job.stage = "Cancelling conversion..."
                return True
        return False

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            job = self.jobs.get(job_id)
            return job.to_dict() if job else None

# Global instance
conversion_manager = ConversionManager()
