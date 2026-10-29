import os
import re
import time
import shutil
import threading
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from providers.base import BaseMangaProvider, ChapterInfo, parse_chapter_number
from core.exporter import (
    save_chapter_as_cbz,
    save_chapter_as_pdf,
    combine_chapters_into_cbz,
    sanitize_filename,
    format_chapter_filename,
)

class DownloadManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.status = "idle"  # idle, running, completed, cancelled, error
        self.stage = ""
        self.cancel_requested = False
        self.current_manga_title = ""
        self.current_manga_cover = ""
        self.current_provider = ""
        self.total_chapters = 0
        self.completed_chapters = 0
        self.current_chapter_num = ""
        self.total_pages = 0
        self.completed_pages = 0
        self.logs: List[Dict[str, Any]] = []
        self.worker_thread: Optional[threading.Thread] = None

    def log(self, message: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        entry = {"time": timestamp, "message": message, "level": level}
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > 500:
                self.logs.pop(0)
        print(f"[{timestamp}] [{level.upper()}] {message}", flush=True)

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "status": self.status,
                "stage": self.stage,
                "manga_title": self.current_manga_title,
                "manga_cover": self.current_manga_cover,
                "provider": self.current_provider,
                "total_chapters": self.total_chapters,
                "completed_chapters": self.completed_chapters,
                "current_chapter": self.current_chapter_num,
                "total_pages": self.total_pages,
                "completed_pages": self.completed_pages,
                "logs": list(self.logs[-50:]),
            }

    def cancel(self):
        with self.lock:
            if self.status in ("running", "idle"):
                self.cancel_requested = True
                self.status = "cancelled"
                self.stage = "Cancellation requested"
        self.log("Cancellation requested by user. Aborting all operations...", level="warning")

    def start_download_job(
        self,
        provider: BaseMangaProvider,
        manga_title: str,
        manga_cover: str,
        chapters: List[ChapterInfo],
        output_dir: str,
        custom_title: Optional[str] = None,
        include_range: bool = True,
        save_cbz: bool = True,
        save_pdf: bool = True,
        save_images: bool = False,
        combine_cbz: bool = True,
        clean_temp: bool = True,
        page_concurrency: int = 4,
    ) -> bool:
        with self.lock:
            if self.status == "running":
                return False
            self.status = "running"
            self.stage = "Starting download..."
            self.cancel_requested = False
            self.current_manga_title = custom_title.strip() if custom_title and custom_title.strip() else manga_title
            self.current_manga_cover = manga_cover
            self.current_provider = provider.name
            self.total_chapters = len(chapters)
            self.completed_chapters = 0
            self.current_chapter_num = ""
            self.total_pages = 0
            self.completed_pages = 0
            self.logs.clear()

        def run():
            self._execute_download(
                provider=provider,
                manga_title=manga_title,
                chapters=chapters,
                output_dir=output_dir,
                custom_title=custom_title,
                include_range=include_range,
                save_cbz=save_cbz,
                save_pdf=save_pdf,
                save_images=save_images,
                combine_cbz=combine_cbz,
                clean_temp=clean_temp,
                page_concurrency=page_concurrency,
            )

        self.worker_thread = threading.Thread(target=run, daemon=True)
        self.worker_thread.start()
        return True

    def _execute_download(
        self,
        provider: BaseMangaProvider,
        manga_title: str,
        chapters: List[ChapterInfo],
        output_dir: str,
        custom_title: Optional[str],
        include_range: bool,
        save_cbz: bool,
        save_pdf: bool,
        save_images: bool,
        combine_cbz: bool,
        clean_temp: bool,
        page_concurrency: int,
    ):
        try:
            os.makedirs(output_dir, exist_ok=True)
            effective_series = (custom_title.strip() if custom_title and custom_title.strip() else manga_title.strip())
            safe_series = sanitize_filename(effective_series)
            self.log(f"Starting download for '{effective_series}' ({len(chapters)} chapters) from {provider.display_name}")

            chapters_with_images = []
            folders_to_clean = []

            for chap in chapters:
                if self.cancel_requested:
                    with self.lock:
                        self.status = "cancelled"
                        self.stage = "Download stopped by user."
                    self.log("Download stopped by user.", level="warning")
                    return

                chap_num = chap.chapter_num
                chap_title = getattr(chap, "title", "") or ""
                with self.lock:
                    self.current_chapter_num = chap_num
                    self.total_pages = 0
                    self.completed_pages = 0
                    self.stage = f"Preparing Chapter {chap_num}..."

                # Filenames incorporating series name and chapter info
                pdf_filename = format_chapter_filename(safe_series, chap_num, chap_title, ext="pdf")
                cbz_filename = format_chapter_filename(safe_series, chap_num, chap_title, ext="cbz")
                pdf_path = os.path.join(output_dir, pdf_filename)
                cbz_path = os.path.join(output_dir, cbz_filename)

                # Legacy fallback checks (e.g. Chapter_1.pdf)
                legacy_pdf = os.path.join(output_dir, f"Chapter_{chap_num}.pdf")
                legacy_cbz = os.path.join(output_dir, f"Chapter_{chap_num}.cbz")

                # Folder for chapter images
                chap_folder_name = sanitize_filename(f"{safe_series}_Chapter_{chap_num}")
                chap_folder = os.path.join(output_dir, chap_folder_name)
                legacy_chap_folder = os.path.join(output_dir, f"Chapter_{chap_num}")
                folders_to_clean.extend([chap_folder, legacy_chap_folder])

                has_valid_pdf = (not save_pdf) or (
                    (os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1024) or
                    (os.path.exists(legacy_pdf) and os.path.getsize(legacy_pdf) > 1024)
                )
                has_valid_cbz = (not save_cbz) or (
                    (os.path.exists(cbz_path) and os.path.getsize(cbz_path) > 1024) or
                    (os.path.exists(legacy_cbz) and os.path.getsize(legacy_cbz) > 1024)
                )

                if has_valid_pdf and has_valid_cbz and not combine_cbz:
                    self.log(f"{safe_series} Chapter {chap_num} already downloaded, skipping.")
                    with self.lock:
                        self.completed_chapters += 1
                        self.stage = f"Chapter {chap_num} already downloaded."
                    continue

                with self.lock:
                    self.stage = f"Fetching page links for Chapter {chap_num}..."
                self.log(f"Fetching page links for Chapter {chap_num}...")
                try:
                    page_urls = provider.get_page_urls(chap.id, chap.extra)
                except Exception as e:
                    self.log(f"Failed to fetch page links for Chapter {chap_num}: {e}", level="error")
                    continue

                if not page_urls:
                    self.log(f"No pages found for Chapter {chap_num}", level="warning")
                    with self.lock:
                        self.completed_chapters += 1
                    continue

                with self.lock:
                    self.total_pages = len(page_urls)
                    self.completed_pages = 0
                    self.stage = f"Downloading Chapter {chap_num} (0/{len(page_urls)} pages)..."

                os.makedirs(chap_folder, exist_ok=True)
                downloaded_image_paths = []

                # Download pages concurrently with resume/partial awareness across current and legacy folders
                def download_single_page(idx: int, url: str) -> Optional[str]:
                    if self.cancel_requested:
                        return None

                    # If page was already downloaded in either folder, reuse it immediately
                    for fld in (chap_folder, legacy_chap_folder):
                        if os.path.isdir(fld):
                            for cand_ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                                cand_path = os.path.join(fld, f"{idx:03}{cand_ext}")
                                if os.path.exists(cand_path) and os.path.getsize(cand_path) > 1024:
                                    return cand_path

                    ext = ".jpg"
                    if ".png" in url.lower():
                        ext = ".png"
                    elif ".webp" in url.lower():
                        ext = ".webp"

                    img_path = os.path.join(chap_folder, f"{idx:03}{ext}")

                    try:
                        if self.cancel_requested:
                            return None
                        provider.download_image(url, img_path)
                        if os.path.exists(img_path) and os.path.getsize(img_path) > 100:
                            return img_path
                        return None
                    except Exception as err:
                        if not self.cancel_requested:
                            self.log(f"Page {idx} failed: {err}", level="error")
                        return None

                with ThreadPoolExecutor(max_workers=max(1, page_concurrency)) as executor:
                    future_to_idx = {
                        executor.submit(download_single_page, i, u): i
                        for i, u in enumerate(page_urls, start=1)
                    }
                    for future in as_completed(future_to_idx):
                        if self.cancel_requested:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        res = future.result()
                        if res:
                            downloaded_image_paths.append(res)
                        with self.lock:
                            self.completed_pages += 1
                            self.stage = f"Downloading Chapter {chap_num} ({self.completed_pages}/{self.total_pages} pages)..."

                if self.cancel_requested:
                    with self.lock:
                        self.status = "cancelled"
                        self.stage = "Download stopped by user."
                    self.log("Download stopped by user.", level="warning")
                    return

                # Sort pages by page index extracted from filename
                def _get_page_num(p: str) -> int:
                    bn = os.path.splitext(os.path.basename(p))[0]
                    m = re.search(r"(\d+)", bn)
                    return int(m.group(1)) if m else 0

                downloaded_image_paths.sort(key=_get_page_num)

                if downloaded_image_paths:
                    chapters_with_images.append((chap_num, downloaded_image_paths))

                    # Export per-chapter formats if requested
                    if save_pdf and (not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0):
                        if self.cancel_requested:
                            with self.lock:
                                self.status = "cancelled"
                                self.stage = "Download stopped by user."
                            return
                        with self.lock:
                            self.stage = f"Generating PDF for Chapter {chap_num}..."
                        self.log(f"Generating PDF: {pdf_filename}...")
                        try:
                            save_chapter_as_pdf(chap_num, downloaded_image_paths, output_dir, custom_filename=pdf_filename)
                            self.log(f"Saved: {pdf_filename}")
                        except Exception as e:
                            self.log(f"Failed to export {pdf_filename}: {e}", level="error")

                    if save_cbz and (not os.path.exists(cbz_path) or os.path.getsize(cbz_path) == 0):
                        if self.cancel_requested:
                            with self.lock:
                                self.status = "cancelled"
                                self.stage = "Download stopped by user."
                            return
                        with self.lock:
                            self.stage = f"Generating CBZ for Chapter {chap_num}..."
                        self.log(f"Generating CBZ: {cbz_filename}...")
                        try:
                            save_chapter_as_cbz(chap_num, downloaded_image_paths, output_dir, custom_filename=cbz_filename)
                            self.log(f"Saved: {cbz_filename}")
                        except Exception as e:
                            self.log(f"Failed to export {cbz_filename}: {e}", level="error")
                else:
                    self.log(f"Failed to download any images for Chapter {chap_num}", level="error")

                with self.lock:
                    self.completed_chapters += 1

            if self.cancel_requested:
                with self.lock:
                    self.status = "cancelled"
                    self.stage = "Download stopped by user."
                return

            # Check if combine into single CBZ requested
            if combine_cbz and chapters_with_images:
                if self.cancel_requested:
                    with self.lock:
                        self.status = "cancelled"
                        self.stage = "Download stopped by user."
                    return
                with self.lock:
                    self.stage = f"Combining {len(chapters_with_images)} chapters into archive..."
                self.log(f"Combining {len(chapters_with_images)} chapters into single CBZ archive...")
                chapters_with_images.sort(key=lambda pair: parse_chapter_number(pair[0]))
                try:
                    combined_path = combine_chapters_into_cbz(
                        manga_name=safe_series,
                        chapters_with_images=chapters_with_images,
                        output_dir=output_dir,
                        include_range=include_range,
                    )
                    self.log(f"Combined CBZ created: {os.path.basename(combined_path)}", level="success")
                except Exception as e:
                    self.log(f"Failed to create combined CBZ: {e}", level="error")

            # Clean temporary image folders if clean_temp is requested and save_images is False
            if clean_temp and not save_images and not self.cancel_requested:
                with self.lock:
                    self.stage = "Cleaning up temporary image folders..."
                self.log("Cleaning up temporary chapter folders...")
                for fld in folders_to_clean:
                    if os.path.isdir(fld):
                        try:
                            shutil.rmtree(fld)
                        except Exception as err:
                            self.log(f"Could not remove folder {fld}: {err}", level="warning")

            with self.lock:
                if not self.cancel_requested:
                    self.status = "completed"
                    self.stage = "All operations finished successfully!"
                else:
                    self.status = "cancelled"
                    self.stage = "Download cancelled by user."

            if not self.cancel_requested:
                self.log("All operations finished successfully!", level="success")
            else:
                self.log("Download stopped by user.", level="warning")

        except Exception as e:
            self.log(f"Unexpected error in download job: {e}", level="error")
            with self.lock:
                self.status = "error"
                self.stage = f"Error: {str(e)}"

# Global download manager instance
download_manager = DownloadManager()
