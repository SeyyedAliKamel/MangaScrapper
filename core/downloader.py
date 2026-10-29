# Refactored download manager to track incomplete or failed pages and allow instant retry without re-downloading the whole manga
import os
import re
import time
import uuid
import shutil
import zipfile
import threading
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image

from providers.base import BaseMangaProvider, ChapterInfo, parse_chapter_number
from core.exporter import (
    save_chapter_as_cbz,
    save_chapter_as_pdf,
    combine_chapters_into_cbz,
    sanitize_filename,
    format_chapter_filename,
)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def _guess_ext(url: str) -> str:
    lowered = url.lower()
    if ".png" in lowered:
        return ".png"
    if ".webp" in lowered:
        return ".webp"
    return ".jpg"


def _page_num_from_path(p: str) -> int:
    bn = os.path.splitext(os.path.basename(p))[0]
    m = re.search(r"(\d+)", bn)
    return int(m.group(1)) if m else 0


def _is_valid_image(path: str) -> bool:
    try:
        if not os.path.isfile(path) or os.path.getsize(path) <= 100:
            return False
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


class DownloadManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.failed_lock = threading.RLock()
        self.repack_lock = threading.Lock()
        self.status = "idle"  # idle, running, completed, cancelled, error
        self.stage = ""
        self.cancel_requested = False
        self.current_job_id = ""
        self.current_manga_title = ""
        self.current_manga_cover = ""
        self.current_provider = ""
        self.total_chapters = 0
        self.completed_chapters = 0
        self.current_chapter_num = ""
        self.total_pages = 0
        self.completed_pages = 0
        self.logs: List[Dict[str, Any]] = []
        self.failed_pages: List[Dict[str, Any]] = []
        self.worker_thread: Optional[threading.Thread] = None

    def log(self, message: str, level: str = "info"):
        timestamp = time.strftime("%H:%M:%S")
        entry = {"time": timestamp, "message": message, "level": level}
        with self.lock:
            self.logs.append(entry)
            if len(self.logs) > 500:
                self.logs.pop(0)
        print(f"[{timestamp}] [{level.upper()}] {message}", flush=True)

    # Fields that stay on the server (paths, URLs, export flags)
    _PUBLIC_FAILED_KEYS = (
        "id", "series_title", "chapter_num", "chapter_title", "page_idx",
        "total_pages", "error", "status", "provider", "timestamp", "retry_count",
    )

    def _public_failed(self, f: Dict[str, Any]) -> Dict[str, Any]:
        return {k: f.get(k) for k in self._PUBLIC_FAILED_KEYS}

    def get_failed_pages(self) -> List[Dict[str, Any]]:
        with self.failed_lock:
            return [self._public_failed(f) for f in self.failed_pages]

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            with self.failed_lock:
                failed_items = [self._public_failed(f) for f in self.failed_pages]
            active_failed = [f for f in failed_items if f.get("status") in ("failed", "retrying")]
            resolved_count = len([f for f in failed_items if f.get("status") == "resolved"])

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
                "failed_pages": failed_items,
                "failed_count": len(active_failed),
                "resolved_count": resolved_count,
            }

    def cancel(self):
        with self.lock:
            if self.status in ("running", "idle"):
                self.cancel_requested = True
                self.status = "cancelled"
                self.stage = "Cancellation requested"
        self.log("Cancellation requested by user. Aborting all operations...", level="warning")

    def dismiss_failed(self, failed_id: Optional[str] = None, resolved_only: bool = False):
        with self.failed_lock:
            if failed_id:
                self.failed_pages = [
                    f for f in self.failed_pages
                    if f.get("id") != failed_id or f.get("status") == "retrying"
                ]
            elif resolved_only:
                self.failed_pages = [f for f in self.failed_pages if f.get("status") != "resolved"]
            else:
                self.failed_pages = [f for f in self.failed_pages if f.get("status") == "retrying"]

    # ==========================================
    # Retry logic
    # ==========================================
    def _claim_for_retry(self, failed_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Atomically mark an entry as retrying so two requests never retry the same page."""
        with self.lock:
            job_running = self.status == "running"
            running_job = self.current_job_id

        with self.failed_lock:
            entry = next((f for f in self.failed_pages if f.get("id") == failed_id), None)
            if not entry:
                return None, "Failed page entry not found"
            if entry.get("status") == "retrying":
                return None, "This page is already being retried"
            if entry.get("status") == "resolved":
                return None, "This page is already recovered"
            if job_running and entry.get("job_id") == running_job:
                return None, "Wait for the current download to finish before retrying its pages"
            entry["status"] = "retrying"
            return entry, None

    def _download_entry_image(self, provider: BaseMangaProvider, entry: Dict[str, Any], url: str) -> str:
        chap_folder = entry["chap_folder"]
        os.makedirs(chap_folder, exist_ok=True)
        idx = int(entry.get("page_idx", 1))

        # Drop stale or corrupted copies of this page so the archive never picks up a broken file
        for ext in IMAGE_EXTS:
            stale = os.path.join(chap_folder, f"{idx:03}{ext}")
            if os.path.exists(stale) and not _is_valid_image(stale):
                try:
                    os.remove(stale)
                except OSError:
                    pass

        img_path = os.path.join(chap_folder, f"{idx:03}{_guess_ext(url)}")
        provider.download_image(url, img_path)
        if not _is_valid_image(img_path):
            try:
                os.remove(img_path)
            except OSError:
                pass
            raise ValueError("Downloaded file is empty or not a valid image")
        return img_path

    def retry_single_page(self, failed_id: str, repack: bool = True) -> Dict[str, Any]:
        from providers import get_provider

        entry, claim_error = self._claim_for_retry(failed_id)
        if not entry:
            return {"success": False, "error": claim_error}

        idx = int(entry.get("page_idx", 1))
        chap_num = entry.get("chapter_num")
        provider = get_provider(entry.get("provider", ""))
        if not provider:
            with self.failed_lock:
                entry["status"] = "failed"
                entry["error"] = f"Provider '{entry.get('provider')}' not available"
            return {"success": False, "error": entry["error"]}

        self.log(f"Retrying page {idx} of Chapter {chap_num}...")
        try:
            try:
                self._download_entry_image(provider, entry, entry.get("page_url", ""))
            except Exception as first_err:
                # Signed image links (MangaDex, MANGA Plus) expire, so fetch fresh links and try once more
                fresh_urls = provider.get_page_urls(entry.get("chapter_id", ""), entry.get("chapter_extra") or {})
                if not fresh_urls or idx > len(fresh_urls):
                    raise first_err
                fresh_url = fresh_urls[idx - 1]
                with self.failed_lock:
                    entry["page_url"] = fresh_url
                self._download_entry_image(provider, entry, fresh_url)

            with self.failed_lock:
                entry["status"] = "resolved"
                entry["error"] = ""
                entry["retry_count"] = entry.get("retry_count", 0) + 1
            self.log(f"Page {idx} of Chapter {chap_num} recovered", level="success")

            repack_result = self._repack_chapter(entry) if repack else None
            return {"success": True, "message": f"Page {idx} downloaded", "repack": repack_result}

        except Exception as e:
            with self.failed_lock:
                entry["status"] = "failed"
                entry["error"] = str(e)
                entry["retry_count"] = entry.get("retry_count", 0) + 1
            self.log(f"Retry for page {idx} of Chapter {chap_num} failed: {e}", level="error")
            return {"success": False, "error": str(e)}

    def _retry_batch(self, targets: List[Dict[str, Any]]) -> Dict[str, Any]:
        succeeded = 0
        failed = 0
        skipped = 0
        to_repack: Dict[str, Dict[str, Any]] = {}

        for item in targets:
            res = self.retry_single_page(item["id"], repack=False)
            if res.get("success"):
                succeeded += 1
                to_repack[item["chap_folder"]] = item
            elif res.get("error") in (
                "This page is already being retried",
                "This page is already recovered",
            ):
                skipped += 1
            else:
                failed += 1

        # Repack each touched chapter once instead of once per page
        for entry in to_repack.values():
            self._repack_chapter(entry)

        return {
            "success": failed == 0,
            "total": len(targets),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
        }

    def retry_chapter(self, chapter_num: str, series_title: Optional[str] = None) -> Dict[str, Any]:
        with self.failed_lock:
            targets = [
                dict(f) for f in self.failed_pages
                if str(f.get("chapter_num")) == str(chapter_num)
                and (not series_title or f.get("series_title") == series_title)
                and f.get("status") == "failed"
            ]
        if not targets:
            return {"success": True, "message": "No failed pages found for this chapter", "total": 0, "succeeded": 0, "failed": 0}
        return self._retry_batch(targets)

    def retry_all_failed(self) -> Dict[str, Any]:
        with self.failed_lock:
            targets = [dict(f) for f in self.failed_pages if f.get("status") == "failed"]
        if not targets:
            return {"success": True, "message": "No failed pages to retry", "total": 0, "succeeded": 0, "failed": 0}
        return self._retry_batch(targets)

    # ==========================================
    # Archive rebuilding after a recovered page
    # ==========================================
    def _chapter_images(self, chap_folder: str) -> List[str]:
        if not os.path.isdir(chap_folder):
            return []
        images = [
            os.path.join(chap_folder, fn)
            for fn in os.listdir(chap_folder)
            if fn.lower().endswith(IMAGE_EXTS) and _is_valid_image(os.path.join(chap_folder, fn))
        ]
        images.sort(key=_page_num_from_path)
        return images

    def _patch_combined_cbz(self, combined_path: str, chap_num: str, images: List[str]):
        """Swap the chapter's pages inside the combined archive with the current folder contents."""
        prefix = f"Chapter_{chap_num}/"
        tmp_path = combined_path + ".tmp"
        with zipfile.ZipFile(combined_path, "r") as src, zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if not item.filename.startswith(prefix):
                    dst.writestr(item, src.read(item.filename))
            for img in images:
                dst.write(img, arcname=prefix + os.path.basename(img))
        os.replace(tmp_path, combined_path)

    def _repack_chapter(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        chap_folder = entry.get("chap_folder", "")
        images = self._chapter_images(chap_folder)
        if not images:
            return {"repacked": False, "reason": "No valid images found in chapter folder"}

        output_dir = entry.get("output_dir", "")
        chap_num = str(entry.get("chapter_num", ""))
        saved_files: List[str] = []

        # Two retries on the same chapter must not write the same archive at the same time
        with self.repack_lock:
            if entry.get("save_pdf"):
                try:
                    out = save_chapter_as_pdf(chap_num, images, output_dir, custom_filename=entry.get("pdf_filename"))
                    saved_files.append(os.path.basename(out))
                except Exception as e:
                    self.log(f"Could not rebuild PDF for Chapter {chap_num}: {e}", level="warning")

            if entry.get("save_cbz"):
                try:
                    out = save_chapter_as_cbz(chap_num, images, output_dir, custom_filename=entry.get("cbz_filename"))
                    saved_files.append(os.path.basename(out))
                except Exception as e:
                    self.log(f"Could not rebuild CBZ for Chapter {chap_num}: {e}", level="warning")

            combined_path = entry.get("combined_path")
            if combined_path and os.path.isfile(combined_path):
                try:
                    self._patch_combined_cbz(combined_path, chap_num, images)
                    saved_files.append(os.path.basename(combined_path))
                except Exception as e:
                    self.log(f"Could not update combined archive for Chapter {chap_num}: {e}", level="warning")

        if saved_files:
            self.log(f"Updated archives for Chapter {chap_num}: {', '.join(saved_files)}", level="success")
        else:
            self.log(f"Chapter {chap_num} pages saved to folder (no archive format selected)")

        return {"repacked": bool(saved_files), "files": saved_files, "page_count": len(images)}

    # ==========================================
    # Main download job
    # ==========================================
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
            self.current_job_id = uuid.uuid4().hex
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
        with self.lock:
            if not self.current_job_id:
                self.current_job_id = uuid.uuid4().hex
            job_id = self.current_job_id

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

                pdf_filename = format_chapter_filename(safe_series, chap_num, chap_title, ext="pdf")
                cbz_filename = format_chapter_filename(safe_series, chap_num, chap_title, ext="cbz")
                pdf_path = os.path.join(output_dir, pdf_filename)
                cbz_path = os.path.join(output_dir, cbz_filename)

                legacy_pdf = os.path.join(output_dir, f"Chapter_{chap_num}.pdf")
                legacy_cbz = os.path.join(output_dir, f"Chapter_{chap_num}.cbz")

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
                    with self.lock:
                        self.completed_chapters += 1
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

                def download_single_page(idx: int, url: str) -> Tuple[Optional[str], Optional[str]]:
                    if self.cancel_requested:
                        return (None, "Cancelled")

                    # Check if page already exists in current or legacy folder
                    for fld in (chap_folder, legacy_chap_folder):
                        if os.path.isdir(fld):
                            for cand_ext in IMAGE_EXTS:
                                cand_path = os.path.join(fld, f"{idx:03}{cand_ext}")
                                if os.path.exists(cand_path) and os.path.getsize(cand_path) > 1024:
                                    return (cand_path, None)

                    img_path = os.path.join(chap_folder, f"{idx:03}{_guess_ext(url)}")

                    try:
                        if self.cancel_requested:
                            return (None, "Cancelled")
                        provider.download_image(url, img_path)
                        if os.path.exists(img_path) and os.path.getsize(img_path) > 100:
                            return (img_path, None)
                        return (None, "Downloaded image file is empty or corrupted")
                    except Exception as err:
                        if not self.cancel_requested:
                            self.log(f"Page {idx} failed: {err}", level="error")
                        return (None, str(err))

                with ThreadPoolExecutor(max_workers=max(1, page_concurrency)) as executor:
                    future_to_info = {
                        executor.submit(download_single_page, i, u): (i, u)
                        for i, u in enumerate(page_urls, start=1)
                    }
                    for future in as_completed(future_to_info):
                        if self.cancel_requested:
                            executor.shutdown(wait=False, cancel_futures=True)
                            break
                        res_path, err_msg = future.result()
                        p_idx, p_url = future_to_info[future]
                        fail_id = f"{safe_series}_ch{chap_num}_p{p_idx}"

                        if res_path:
                            downloaded_image_paths.append(res_path)
                            # Mark any prior failed record as resolved
                            with self.failed_lock:
                                for f in self.failed_pages:
                                    if f.get("id") == fail_id and f.get("status") != "retrying":
                                        f["status"] = "resolved"
                                        f["error"] = ""
                        elif not self.cancel_requested:
                            fail_entry = {
                                "id": fail_id,
                                "job_id": job_id,
                                "series_title": effective_series,
                                "safe_series": safe_series,
                                "chapter_num": str(chap_num),
                                "chapter_title": chap_title,
                                "chapter_id": chap.id,
                                "chapter_extra": chap.extra or {},
                                "page_idx": p_idx,
                                "total_pages": len(page_urls),
                                "page_url": p_url,
                                "error": err_msg or "Failed to download image",
                                "status": "failed",
                                "provider": provider.name,
                                "chap_folder": os.path.abspath(chap_folder),
                                "output_dir": os.path.abspath(output_dir),
                                "pdf_filename": pdf_filename,
                                "cbz_filename": cbz_filename,
                                "save_pdf": save_pdf,
                                "save_cbz": save_cbz,
                                "combined_path": None,
                                "timestamp": time.strftime("%H:%M:%S"),
                                "retry_count": 0,
                            }
                            with self.failed_lock:
                                existing = next((f for f in self.failed_pages if f.get("id") == fail_id), None)
                                if existing:
                                    if existing.get("status") != "retrying":
                                        existing.update(fail_entry)
                                else:
                                    self.failed_pages.append(fail_entry)

                        with self.lock:
                            self.completed_pages += 1
                            self.stage = f"Downloading Chapter {chap_num} ({self.completed_pages}/{self.total_pages} pages)..."

                if self.cancel_requested:
                    with self.lock:
                        self.status = "cancelled"
                        self.stage = "Download stopped by user."
                    self.log("Download stopped by user.", level="warning")
                    return

                downloaded_image_paths.sort(key=_page_num_from_path)

                if downloaded_image_paths:
                    chapters_with_images.append((chap_num, downloaded_image_paths))

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

            if combine_cbz and chapters_with_images:
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
                    # Let page retries from this job patch the combined archive too
                    with self.failed_lock:
                        for f in self.failed_pages:
                            if f.get("job_id") == job_id:
                                f["combined_path"] = os.path.abspath(combined_path)
                except Exception as e:
                    self.log(f"Failed to create combined CBZ: {e}", level="error")

            # Keep folders that still have missing pages so they can be retried later
            if clean_temp and not save_images and not self.cancel_requested:
                with self.lock:
                    self.stage = "Cleaning up temporary image folders..."
                self.log("Cleaning up temporary chapter folders...")
                with self.failed_lock:
                    unresolved_folders = {
                        os.path.normcase(os.path.abspath(f["chap_folder"]))
                        for f in self.failed_pages
                        if f.get("status") in ("failed", "retrying")
                    }

                for fld in folders_to_clean:
                    if os.path.normcase(os.path.abspath(fld)) in unresolved_folders:
                        self.log(f"Keeping folder '{os.path.basename(fld)}' so missing pages can be retried", level="warning")
                        continue
                    if os.path.isdir(fld):
                        try:
                            shutil.rmtree(fld)
                        except Exception as err:
                            self.log(f"Could not remove folder {fld}: {err}", level="warning")

            with self.failed_lock:
                job_missing = len([
                    f for f in self.failed_pages
                    if f.get("job_id") == job_id and f.get("status") == "failed"
                ])

            with self.lock:
                if self.cancel_requested:
                    self.status = "cancelled"
                    self.stage = "Download cancelled by user."
                else:
                    self.status = "completed"
                    if job_missing:
                        self.stage = f"Finished with {job_missing} missing page(s). Retry them below."
                    else:
                        self.stage = "All operations finished successfully!"

            if self.cancel_requested:
                self.log("Download stopped by user.", level="warning")
            elif job_missing:
                self.log(f"Finished with {job_missing} missing page(s)", level="warning")
            else:
                self.log("All operations finished successfully!", level="success")

        except Exception as e:
            self.log(f"Unexpected error in download job: {e}", level="error")
            with self.lock:
                self.status = "error"
                self.stage = f"Error: {str(e)}"

# Global download manager instance
download_manager = DownloadManager()
