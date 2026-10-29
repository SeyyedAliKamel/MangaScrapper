# Application entrypoint supporting Web UI and CLI modes with background download management
import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
import socket
import argparse
import webbrowser
import threading
import time
import uvicorn

import config
from providers import (
    get_provider,
    search_providers,
    search_manga_providers,
    search_h_providers,
    resolve_manga,
    resolve_h_gallery,
)
from core.downloader import download_manager
from core.exporter import save_chapter_as_pdf, save_chapter_as_cbz, combine_chapters_into_cbz
from core.converter import cbz_to_pdf, pdf_to_cbz

def find_available_port(host: str, start_port: int = 8000) -> int:
    for p in [start_port, 8080, 8085, 8888, 5000]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start_port

def run_web_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True):
    port = find_available_port(host, port)
    url = f"http://{host}:{port}"
    print(f"\n" + "=" * 60)
    print(f"📖 MangaScrapper Pro - Web UI")
    print(f"Server starting at: {url}")
    print(f"=" * 60 + "\n")

    if open_browser:
        def opener():
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=opener, daemon=True).start()

    from server.app import app
    uvicorn.run(app, host=host, port=port, log_level="info")

def run_cli_mode(target: str, provider_name: str = "mangadex", limit_chapters: int = None):
    print(f"Resolving '{target}' with provider '{provider_name}'...")
    provider, details, chapters = resolve_manga(target, provider_name)

    if not provider or not details:
        print(f"Could not find manga for query: {target}")
        return

    print(f"\nFound: {details.title} (Source: {provider.display_name})")
    print(f"Total chapters: {len(chapters)}")

    if not chapters:
        print("No chapters found.")
        return

    if limit_chapters:
        chapters = chapters[:limit_chapters]
        print(f"Downloading first {limit_chapters} chapters...")

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    started = download_manager.start_download_job(
        provider=provider,
        manga_title=details.title,
        manga_cover=details.cover_url,
        chapters=chapters,
        output_dir=config.OUTPUT_DIR,
        save_cbz=True,
        save_pdf=True,
        save_images=False,
        combine_cbz=True,
        clean_temp=True,
    )

    if not started:
        print("A download job is already active.")
        return

    # Print progress to console
    last_msg = ""
    while True:
        state = download_manager.get_state()
        status = state["status"]
        if state["logs"]:
            latest = state["logs"][-1]["message"]
            if latest != last_msg:
                print(f"[{state['logs'][-1]['time']}] {latest}")
                last_msg = latest

        if status in ("completed", "cancelled", "error"):
            print(f"\nDownload finished with status: {status.upper()}")
            break
        time.sleep(1)

def main():
    parser = argparse.ArgumentParser(description="MangaScrapper Pro - Multi-source Manga Downloader & Reader")
    parser.add_argument("--web", action="store_true", help="Launch the Web UI dashboard (default)")
    parser.add_argument("--cli", action="store_true", help="Run in command-line mode")
    parser.add_argument("--query", "-q", type=str, help="Manga title, keyword, or URL to download in CLI mode")
    parser.add_argument("--provider", "-p", type=str, default="mangadex", help="Provider (mangadex, mangapill, mangaplus, all)")
    parser.add_argument("--id", type=str, help="Manga ID or URL")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Web UI host")
    parser.add_argument("--port", type=int, default=8000, help="Web UI port")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    parser.add_argument("--convert", "-c", type=str, help="Convert a .cbz to .pdf or .pdf to .cbz directly")

    args = parser.parse_args()

    if args.convert:
        fpath = args.convert
        if not os.path.isfile(fpath):
            print(f"File not found: {fpath}")
            return
        ext = os.path.splitext(fpath)[1].lower()
        if ext == ".cbz":
            print(f"Converting CBZ -> PDF: {fpath} ...")
            out = cbz_to_pdf(fpath)
            print(f"Successfully created: {out}")
        elif ext == ".pdf":
            print(f"Converting PDF -> CBZ: {fpath} ...")
            out = pdf_to_cbz(fpath)
            print(f"Successfully created: {out}")
        else:
            print("Error: file must be a .cbz or .pdf file.")
        return

    # Determine mode: if CLI flag or query/id is explicitly provided, run CLI; otherwise default to Web UI
    if args.cli or args.query or args.id:
        target = args.query or args.id or config.MANGA_ID
        if not target or target == "MangaIdHere":
            target = input("Enter manga title, ID, or URL: ").strip()
        run_cli_mode(target, provider_name=args.provider)
    else:
        run_web_server(host=args.host, port=args.port, open_browser=not args.no_browser)

if __name__ == "__main__":
    main()
