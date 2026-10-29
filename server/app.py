# FastAPI application with endpoints for failed page tracking, single-page retry, and chapter rebuilding
import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import sys
import tempfile
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import requests

# Add root folder to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import config
from providers import (
    list_manga_providers,
    list_h_providers,
    search_manga_providers,
    resolve_manga,
    search_h_providers,
    resolve_h_gallery,
    get_provider,
)
from providers.base import ChapterInfo
from core.downloader import download_manager
from core.library import scan_library, combine_existing_folders
from core.exporter import sanitize_filename
from core.converter import conversion_manager
from core.reader import resolve_library_path, get_book_info, get_page_image
from core.updater import check_archive_updates, check_all_library_updates
from core.updater import check_archive_updates, check_all_library_updates

app = FastAPI(title="MangaScrapper Pro", version="2.5")

# Request models
class ResolveRequest(BaseModel):
    query_or_url: str
    provider: Optional[str] = None

class HResolveRequest(BaseModel):
    query_or_url: str
    provider: Optional[str] = None

class DownloadRequest(BaseModel):
    provider: str
    manga_id: str
    manga_title: str
    custom_title: Optional[str] = None
    include_range: bool = True
    manga_cover: Optional[str] = ""
    selected_chapter_ids: List[str]
    chapters: List[Dict[str, Any]]
    save_cbz: bool = True
    save_pdf: bool = True
    save_images: bool = False
    combine_cbz: bool = True
    clean_temp: bool = True
    output_dir: Optional[str] = None

class CombineRequest(BaseModel):
    manga_name: str
    clean_folders: bool = True

class UpdateArchiveRequest(BaseModel):
    filepath: str
    manga_name: Optional[str] = None
    provider: Optional[str] = None
    manga_id: Optional[str] = None
    chapter_ids: Optional[List[str]] = None
    max_chapters: Optional[int] = None
    save_cbz: bool = False
    save_pdf: bool = False
    clean_temp: bool = True

class ConvertLibraryRequest(BaseModel):
    filepath: str

class ConfigUpdateRequest(BaseModel):
    output_dir: str

class RetryPageRequest(BaseModel):
    id: str

class RetryChapterRequest(BaseModel):
    chapter_num: str
    series_title: Optional[str] = None

class DismissFailedRequest(BaseModel):
    id: Optional[str] = None
    resolved_only: bool = False


# ==========================================
# Image Proxy (Bypasses Hotlink Blocks)
# ==========================================
@app.get("/api/proxy/image")
def proxy_image(url: str = Query(...), referer: Optional[str] = None):
    if not url:
        raise HTTPException(status_code=400, detail="Missing url")

    # Auto-detect required headers based on destination
    req_referer = referer
    if not req_referer:
        if "readdetectiveconan.com" in url or "mangapill.com" in url:
            req_referer = "https://mangapill.com/"
        elif "mangadex.org" in url:
            req_referer = "https://mangadex.org/"
        elif "kontol.online" in url or "cin.wtf" in url:
            req_referer = "https://cin.wtf/"
        elif "tokyo-cdn.com" in url or "mangaplus" in url:
            req_referer = "https://mangaplus.shueisha.co.jp/"
        elif "comick" in url:
            req_referer = "https://comick.io/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    if req_referer:
        headers["Referer"] = req_referer
        if "cin.wtf" in req_referer:
            headers["Origin"] = "https://cin.wtf"
        elif "mangaplus" in req_referer:
            headers["Origin"] = "https://mangaplus.shueisha.co.jp"

    try:
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={
                    "Cache-Control": "public, max-age=86400",
                    "Access-Control-Allow-Origin": "*",
                }
            )
    except Exception as e:
        print(f"Proxy request failed for {url}: {e}")

    raise HTTPException(status_code=404, detail="Image could not be retrieved")


# ==========================================
# 1. Standard Manga API Endpoints
# ==========================================
@app.get("/api/providers")
def get_providers():
    return {"providers": list_manga_providers()}

@app.get("/api/search")
def search_manga(q: str = Query(..., min_length=1), provider: str = "all", limit: int = 20):
    try:
        results = search_manga_providers(query=q, provider_name=provider, limit=limit)
        return {"results": [r.to_dict() for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/resolve")
def resolve(req: ResolveRequest):
    try:
        provider, details, chapters = resolve_manga(req.query_or_url, req.provider)
        if not provider or not details:
            raise HTTPException(status_code=404, detail="Could not resolve manga or provider")

        return {
            "provider": provider.name,
            "provider_name": provider.display_name,
            "manga": details.to_dict(),
            "chapters": [c.to_dict() for c in chapters],
            "total_chapters": len(chapters),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve: {str(e)}")

@app.get("/api/manga/{provider_name}/{manga_id}/chapters")
def get_manga_chapters(provider_name: str, manga_id: str):
    prov = get_provider(provider_name)
    if not prov:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found")
    try:
        chapters = prov.get_chapters(manga_id)
        return {"chapters": [c.to_dict() for c in chapters], "total": len(chapters)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 2. Dedicated H / Doujinshi API Endpoints
# ==========================================
@app.get("/api/h/providers")
def get_h_providers():
    return {"providers": list_h_providers()}

@app.get("/api/h/search")
def search_h(q: str = Query(..., min_length=1), provider: str = "all", limit: int = 24):
    try:
        results = search_h_providers(query=q, provider_name=provider, limit=limit)
        return {"results": [r.to_dict() for r in results]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/h/resolve")
def resolve_h(req: HResolveRequest):
    try:
        provider, details, chapters = resolve_h_gallery(req.query_or_url, req.provider)
        if not provider or not details:
            raise HTTPException(status_code=404, detail="Could not find or resolve gallery")

        return {
            "provider": provider.name,
            "provider_name": provider.display_name,
            "gallery": details.to_dict(),
            "chapters": [c.to_dict() for c in chapters],
            "total_pages": details.extra.get("num_pages") or (chapters[0].page_count if chapters else 1),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve gallery: {str(e)}")


# ==========================================
# 3. Downloads, Task Management & Failed Pages
# ==========================================
@app.post("/api/download/start")
def start_download(req: DownloadRequest):
    prov = get_provider(req.provider)
    if not prov:
        raise HTTPException(status_code=400, detail=f"Unknown provider '{req.provider}'")

    selected_set = set(req.selected_chapter_ids)
    target_chapters = [
        ChapterInfo(
            id=c["id"],
            provider=c.get("provider", req.provider),
            chapter_num=c["chapter_num"],
            title=c.get("title", ""),
            volume=c.get("volume", ""),
            url=c.get("url", ""),
            extra=c.get("extra", {}),
        )
        for c in req.chapters
        if c["id"] in selected_set
    ]

    if not target_chapters:
        raise HTTPException(status_code=400, detail="No valid chapters selected")

    target_dir = req.output_dir or config.OUTPUT_DIR

    started = download_manager.start_download_job(
        provider=prov,
        manga_title=req.manga_title,
        manga_cover=req.manga_cover or "",
        chapters=target_chapters,
        output_dir=target_dir,
        custom_title=req.custom_title,
        include_range=req.include_range,
        save_cbz=req.save_cbz,
        save_pdf=req.save_pdf,
        save_images=req.save_images,
        combine_cbz=req.combine_cbz,
        clean_temp=req.clean_temp,
    )

    if not started:
        raise HTTPException(status_code=409, detail="A download job is already actively running")

    return {"status": "started", "queued_chapters": len(target_chapters)}

@app.post("/api/download/cancel")
def cancel_download():
    download_manager.cancel()
    return {"status": "cancelled"}

@app.get("/api/download/status")
def get_download_status():
    return download_manager.get_state()

@app.get("/api/download/failed")
def get_failed_pages():
    pages = download_manager.get_failed_pages()
    active = [p for p in pages if p.get("status") in ("failed", "retrying")]
    return {
        "failed_pages": pages,
        "total": len(active),
        "resolved": len(pages) - len(active),
    }

@app.post("/api/download/retry-page")
def retry_page(req: RetryPageRequest):
    result = download_manager.retry_single_page(req.id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Retry failed"))
    return result

@app.post("/api/download/retry-chapter")
def retry_chapter(req: RetryChapterRequest):
    return download_manager.retry_chapter(req.chapter_num, req.series_title)

@app.post("/api/download/retry-all")
def retry_all_failed():
    return download_manager.retry_all_failed()

@app.post("/api/download/dismiss-failed")
def dismiss_failed(req: Optional[DismissFailedRequest] = None):
    fid = req.id if req else None
    resolved_only = req.resolved_only if req else False
    download_manager.dismiss_failed(fid, resolved_only=resolved_only)
    return {"status": "success"}


# ==========================================
# 4. Library & Archive Operations
# ==========================================
@app.get("/api/library")
def get_library():
    try:
        return scan_library(config.OUTPUT_DIR)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/library/combine")
def combine_folders(req: CombineRequest):
    try:
        res = combine_existing_folders(
            manga_name=req.manga_name,
            output_dir=config.OUTPUT_DIR,
            clean_folders=req.clean_folders,
        )
        return {"status": "success", "file": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/library/check-updates")
def check_library_updates(filepath: Optional[str] = None):
    try:
        if filepath:
            real_path = _checked_library_file(filepath)
            lib = scan_library(config.OUTPUT_DIR)
            arc_info = None
            for a in lib.get("combined_archives", []):
                if os.path.abspath(a["filepath"]) == os.path.abspath(real_path):
                    arc_info = a
                    break
            if not arc_info:
                arc_info = {
                    "manga_name": os.path.splitext(os.path.basename(real_path))[0],
                    "filepath": real_path,
                    "chapters": [],
                }
            result = check_archive_updates(arc_info)
            return {"updates": [result]}
        else:
            results = check_all_library_updates(config.OUTPUT_DIR)
            return {"updates": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/library/update-archive")
def update_archive(req: UpdateArchiveRequest):
    real_path = _checked_library_file(req.filepath)
    if not os.path.isfile(real_path):
        raise HTTPException(status_code=404, detail="Archive file not found")

    # If chapter_ids are explicitly provided with provider and manga_id
    if req.provider and req.chapter_ids:
        prov = get_provider(req.provider)
        if not prov:
            raise HTTPException(status_code=400, detail=f"Provider {req.provider} not found")
        try:
            _, _, all_chaps = prov.get_manga_details(req.manga_id) if req.manga_id else (None, None, [])
            chap_map = {c.id: c for c in all_chaps}
            target_chapters = [chap_map[cid] for cid in req.chapter_ids if cid in chap_map]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch chapter details: {e}")
        manga_title = req.manga_name or os.path.splitext(os.path.basename(real_path))[0]
    else:
        # Run check_archive_updates to discover new chapters
        lib = scan_library(config.OUTPUT_DIR)
        arc_info = None
        for a in lib.get("combined_archives", []):
            if os.path.abspath(a["filepath"]) == os.path.abspath(real_path):
                arc_info = a
                break
        if not arc_info:
            arc_info = {
                "manga_name": req.manga_name or os.path.splitext(os.path.basename(real_path))[0],
                "filepath": real_path,
                "chapters": [],
            }
        
        update_info = check_archive_updates(arc_info)
        if not update_info.get("has_updates") or not update_info.get("new_chapters"):
            return {
                "status": "up_to_date",
                "message": update_info.get("error") or "No new chapters found to update.",
                "queued_chapters": 0,
            }

        prov = get_provider(update_info["provider"])
        if not prov:
            raise HTTPException(status_code=400, detail=f"Provider {update_info.get('provider')} not found")

        raw_chaps = update_info["new_chapters"]
        if req.chapter_ids:
            cset = set(req.chapter_ids)
            raw_chaps = [c for c in raw_chaps if c.get("id") in cset]
        elif req.max_chapters and req.max_chapters > 0:
            raw_chaps = raw_chaps[:req.max_chapters]

        target_chapters = [
            ChapterInfo(
                id=c["id"],
                provider=c.get("provider", prov.name),
                chapter_num=c["chapter_num"],
                title=c.get("title", ""),
                volume=c.get("volume", ""),
                url=c.get("url", ""),
                extra=c.get("extra", {}),
            )
            for c in raw_chaps
        ]
        manga_title = update_info.get("manga_name") or req.manga_name or "Manga"

    if not target_chapters:
        return {"status": "up_to_date", "message": "No new chapters selected for update.", "queued_chapters": 0}

    started = download_manager.start_download_job(
        provider=prov,
        manga_title=manga_title,
        manga_cover="",
        chapters=target_chapters,
        output_dir=config.OUTPUT_DIR,
        custom_title=None,
        include_range=True,
        save_cbz=req.save_cbz,
        save_pdf=req.save_pdf,
        save_images=False,
        combine_cbz=True,
        clean_temp=req.clean_temp,
        append_to_cbz=real_path,
    )

    if not started:
        raise HTTPException(status_code=409, detail="A download job is already actively running")

    return {
        "status": "started",
        "manga_title": manga_title,
        "queued_chapters": len(target_chapters),
        "target_file": os.path.basename(real_path),
    }

def _checked_library_file(path: str) -> str:
    try:
        return resolve_library_path(path, config.OUTPUT_DIR)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/files/download")
def download_file(path: str):
    real_path = _checked_library_file(path)
    return FileResponse(real_path, filename=os.path.basename(real_path))

@app.delete("/api/files/delete")
def delete_library_file(path: str):
    real_path = _checked_library_file(path)
    try:
        os.remove(real_path)
        return {"status": "deleted", "filename": os.path.basename(real_path)}
    except PermissionError:
        raise HTTPException(status_code=403, detail="File is in use and cannot be deleted right now.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not delete file: {e}")

@app.get("/api/files/view")
def view_file_inline(path: str):
    real_path = _checked_library_file(path)
    ext = os.path.splitext(real_path)[1].lower()
    media_type = "application/pdf" if ext == ".pdf" else "application/octet-stream"
    return FileResponse(
        real_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{os.path.basename(real_path)}"'},
    )

@app.get("/api/reader/info")
def reader_info(path: str):
    real_path = _checked_library_file(path)
    try:
        info = get_book_info(real_path)
        info["filename"] = os.path.basename(real_path)
        info["filepath"] = real_path
        return info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not open file: {e}")

@app.get("/api/reader/page")
def reader_page(path: str, index: int = Query(0, ge=0)):
    real_path = _checked_library_file(path)
    try:
        data, mime = get_page_image(real_path, index)
        return Response(
            content=data,
            media_type=mime,
            headers={"Cache-Control": "private, max-age=300"},
        )
    except IndexError:
        raise HTTPException(status_code=404, detail="Page out of range")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not render page: {e}")


# ==========================================
# 5. Background CBZ ⇄ PDF Converter (with Progress & Cancel)
# ==========================================
@app.post("/api/convert/start-upload")
async def start_convert_upload(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".cbz", ".pdf"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .cbz or .pdf archive")

    target_format = "pdf" if ext == ".cbz" else "cbz"
    temp_dir = tempfile.mkdtemp(prefix="upload_conv_")
    input_path = os.path.join(temp_dir, filename)

    with open(input_path, "wb") as f:
        content = await file.read()
        f.write(content)

    job_id = conversion_manager.start_job(input_path, target_format)
    return {"job_id": job_id, "filename": filename, "target_format": target_format.upper()}

@app.post("/api/convert/start-library")
def start_convert_library(req: ConvertLibraryRequest):
    real_path = _checked_library_file(req.filepath)
    ext = os.path.splitext(real_path)[1].lower()
    target_format = "pdf" if ext == ".cbz" else "cbz"
    job_id = conversion_manager.start_job(real_path, target_format)
    return {"job_id": job_id, "filename": os.path.basename(real_path), "target_format": target_format.upper()}

@app.get("/api/convert/status/{job_id}")
def get_conversion_status(job_id: str):
    job = conversion_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.post("/api/convert/cancel/{job_id}")
def cancel_conversion(job_id: str):
    cancelled = conversion_manager.cancel_job(job_id)
    return {"status": "cancelled" if cancelled else "not_running"}

@app.get("/api/convert/download/{job_id}")
def download_converted_file(job_id: str):
    job = conversion_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed" or not os.path.isfile(job["output_file"]):
        raise HTTPException(status_code=400, detail="Conversion not yet completed or file unavailable")

    out_path = job["output_file"]
    return FileResponse(out_path, filename=os.path.basename(out_path))


# ==========================================
# 6. Configuration & Static Files
# ==========================================
@app.get("/api/config")
def get_config():
    return {
        "output_dir": os.path.abspath(config.OUTPUT_DIR),
        "default_provider": "mangadex",
    }

@app.post("/api/config")
def update_config(req: ConfigUpdateRequest):
    config.OUTPUT_DIR = req.output_dir
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    return {"status": "updated", "output_dir": os.path.abspath(config.OUTPUT_DIR)}

# Serve frontend static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    return {"message": "MangaScrapper Pro API is running."}
