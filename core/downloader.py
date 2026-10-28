import os
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
)

class DownloadManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "idle"  # idle, running, completed, cancelled, error
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
        print(f"[{timestamp}] [{level.upper()}] {message}")

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "status": self.status,
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
            if self.status == "running":
                self.cancel_requested = True
                self.log("Cancellation requested by user.", level="warning")

    def start_download_job(
        self,
        provider: BaseMangaProvider,
        manga_title: str,
        manga_cover: str,
        chapters: List[ChapterInfo],
        output_dir: str,
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
            self.cancel_requested = False
            self.current_manga_title = manga_title
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
        save_cbz: bool,
        save_pdf: bool,
        save_images: bool,
        combine_cbz: bool,
        clean_temp: bool,
        page_concurrency: int,
    ):
        try:
            os.makedirs(output_dir, exist_ok=True)
            self.log(f"Starting download for '{manga_title}' ({len(chapters)} chapters) from {provider.display_name}")

            chapters_with_images = []
            folders_to_clean = []

            for chap in chapters:
                if self.cancel_requested:
                    self.log("Download stopped by user.", level="warning")
                    with self.lock:
                        self.status = "cancelled"
                    return

                chap_num = chap.chapter_num
                with self.lock:
                    self.current_chapter_num = chap_num
                    self.total_pages = 0
                    self.completed_pages = 0

                chap_folder = os.path.join(output_dir, f"Chapter_{chap_num}")
                folders_to_clean.append(chap_folder)

                # Check if chapter outputs already exist
                pdf_path = os.path.join(output_dir, f"Chapter_{chap_num}.pdf")
                cbz_path = os.path.join(output_dir, f"Chapter_{chap_num}.cbz")
                already_has_pdf = (not save_pdf) or os.path.exists(pdf_path)
                already_has_cbz = (not save_cbz) or os.path.exists(cbz_path)

                # If we have existing images in folder, reuse them
                existing_images = []
                if os.path.isdir(chap_folder):
                    existing_images = [
                        os.path.join(chap_folder, f)
                        for f in sorted(os.listdir(chap_folder))
                        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif"))
                    ]

                if already_has_pdf and already_has_cbz and not combine_cbz:
                    self.log(f"Chapter {chap_num} already downloaded, skipping.")
                    with self.lock:
                        self.completed_chapters += 1
                    continue

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

                os.makedirs(chap_folder, exist_ok=True)
                downloaded_image_paths = []

                # Download pages concurrently
                def download_single_page(idx: int, url: str) -> Optional[str]:
                    ext = ".jpg"
                    if ".png" in url.lower():
                        ext = ".png"
                    elif ".webp" in url.lower():
                        ext = ".webp"

                    img_path = os.path.join(chap_folder, f"{idx:03}{ext}")
                    if os.path.exists(img_path) and os.path.getsize(img_path) > 1024:
                        return img_path

                    try:
                        provider.download_image(url, img_path)
                        return img_path
                    except Exception as err:
                        self.log(f"Page {idx} failed: {err}", level="error")
                        return None

                with ThreadPoolExecutor(max_workers=max(1, page_concurrency)) as executor:
                    future_to_idx = {
                        executor.submit(download_single_page, i, u): i
                        for i, u in enumerate(page_urls, start=1)
                    }
                    for future in as_completed(future_to_idx):
                        if self.cancel_requested:
                            break
                        res = future.result()
                        if res:
                            downloaded_image_paths.append(res)
                        with self.lock:
                            self.completed_pages += 1

                downloaded_image_paths.sort()

                if downloaded_image_paths:
                    chapters_with_images.append((chap_num, downloaded_image_paths))

                    # Export per-chapter formats if requested
                    if save_pdf and not os.path.exists(pdf_path):
                        try:
                            save_chapter_as_pdf(chap_num, downloaded_image_paths, output_dir)
                            self.log(f"Chapter {chap_num} saved as PDF")
                        except Exception as e:
                            self.log(f"Failed to export Chapter {chap_num} to PDF: {e}", level="error")

                    if save_cbz and not os.path.exists(cbz_path):
                        try:
                            save_chapter_as_cbz(chap_num, downloaded_image_paths, output_dir)
                            self.log(f"Chapter {chap_num} saved as CBZ")
                        except Exception as e:
                            self.log(f"Failed to export Chapter {chap_num} to CBZ: {e}", level="error")
                else:
                    self.log(f"Failed to download any images for Chapter {chap_num}", level="error")

                with self.lock:
                    self.completed_chapters += 1

            # Check if combine into single CBZ requested
            if combine_cbz and chapters_with_images:
                self.log(f"Combining {len(chapters_with_images)} chapters into a single CBZ archive...")
                chapters_with_images.sort(key=lambda pair: parse_chapter_number(pair[0]))
                try:
                    combined_path = combine_chapters_into_cbz(
                        manga_title=manga_title,
                        chapters_with_images=chapters_with_images,
                        output_dir=output_dir,
                    )
                    self.log(f"Combined CBZ successfully created: {os.path.basename(combined_path)}", level="success")

                    # If clean_temp requested and combined archive is made, delete temporary per-chapter folders
                    if clean_temp and not save_images:
                        self.log("Cleaning up temporary chapter folders...")
                        for fld in folders_to_clean:
                            if os.path.isdir(fld):
                                try:
                                    shutil.rmtree(fld)
                                except Exception as err:
                                    self.log(f"Could not remove folder {fld}: {err}", level="warning")

                except Exception as e:
                    self.log(f"Failed to create combined CBZ: {e}", level="error")

            with self.lock:
                self.status = "completed"
            self.log(f"All operations finished successfully!", level="success")

        except Exception as e:
            self.log(f"Unexpected error in download job: {e}", level="error")
            with self.lock:
                self.status = "error"

# Global download manager instance
download_manager = DownloadManager()
