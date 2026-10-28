import os
import sys
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# Add root folder to sys.path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import config
from providers import list_providers, search_providers, resolve_manga, get_provider
from providers.base import ChapterInfo
from core.downloader import download_manager
from core.library import scan_library, combine_existing_folders
from core.exporter import sanitize_filename
from core.converter import cbz_to_pdf, pdf_to_cbz
import tempfile
from fastapi import UploadFile, File

app = FastAPI(title="MangaScrapper Pro", version="2.0")

# Request models
class ResolveRequest(BaseModel):
    query_or_url: str
    provider: Optional[str] = None

class DownloadRequest(BaseModel):
    provider: str
    manga_id: str
    manga_title: str
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

class ConvertLibraryRequest(BaseModel):
    filepath: str

class ConfigUpdateRequest(BaseModel):
    output_dir: str

# API Endpoints
@app.get("/api/providers")
def get_providers():
    return {"providers": list_providers()}

@app.get("/api/search")
def search(q: str = Query(..., min_length=1), provider: str = "all", limit: int = 20):
    try:
        results = search_providers(query=q, provider_name=provider, limit=limit)
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
    return {"status": "cancellation_requested"}

@app.get("/api/download/status")
def get_download_status():
    return download_manager.get_state()

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

@app.post("/api/convert/library")
def convert_library_file(req: ConvertLibraryRequest):
    if not os.path.isfile(req.filepath):
        raise HTTPException(status_code=404, detail="Source file not found")
    
    ext = os.path.splitext(req.filepath)[1].lower()
    try:
        if ext == ".cbz":
            out_file = cbz_to_pdf(req.filepath)
            return {"status": "success", "converted_file": out_file, "format": "pdf"}
        elif ext == ".pdf":
            out_file = pdf_to_cbz(req.filepath)
            return {"status": "success", "converted_file": out_file, "format": "cbz"}
        else:
            raise HTTPException(status_code=400, detail="Only .cbz and .pdf files can be converted")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")

@app.post("/api/convert/upload")
async def convert_uploaded_file(file: UploadFile = File(...)):
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".cbz", ".pdf"):
        raise HTTPException(status_code=400, detail="Upload file must be .cbz or .pdf")

    temp_input_dir = tempfile.mkdtemp(prefix="upload_conv_")
    input_path = os.path.join(temp_input_dir, filename)

    try:
        with open(input_path, "wb") as f:
            content = await file.read()
            f.write(content)

        if ext == ".cbz":
            output_path = cbz_to_pdf(input_path)
            out_filename = os.path.splitext(filename)[0] + ".pdf"
            media_type = "application/pdf"
        else:
            output_path = pdf_to_cbz(input_path)
            out_filename = os.path.splitext(filename)[0] + ".cbz"
            media_type = "application/vnd.comicbook+zip"

        return FileResponse(output_path, filename=out_filename, media_type=media_type)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert: {str(e)}")

@app.get("/api/files/download")
def download_file(path: str):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="File not found")
    # Basic security check: must be inside or related to OUTPUT_DIR
    return FileResponse(path, filename=os.path.basename(path))

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
        return FileResponse(index_file)
    return {"message": "MangaScrapper Pro API is running."}
