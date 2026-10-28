import re
import requests
from typing import List, Optional, Dict, Any
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo

class NHentaiProvider(BaseMangaProvider):
    name = "nhentai"
    display_name = "nhentai (18+)"
    domains = ["nhentai.net"]
    api_base = "https://nhentai.net/api/v2"

    ID_REGEX = re.compile(r"nhentai\.net/g/(\d+)")

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://nhentai.net/",
        })
        self.cdn_servers = ["https://i1.nhentai.net", "https://i2.nhentai.net", "https://i3.nhentai.net"]
        self.thumb_servers = ["https://t1.nhentai.net", "https://t2.nhentai.net"]

    def can_handle_url(self, url: str) -> bool:
        lowered = url.lower().strip()
        if any(d in lowered for d in self.domains):
            return True
        # If pure 5-7 digit number, could be an nhentai ID
        if lowered.isdigit() and 4 <= len(lowered) <= 7:
            return True
        return False

    def parse_url(self, url: str) -> Optional[str]:
        cleaned = url.strip()
        if cleaned.isdigit() and 4 <= len(cleaned) <= 7:
            return cleaned
        match = self.ID_REGEX.search(cleaned)
        if match:
            return match.group(1)
        return None

    def search(self, query: str, limit: int = 20) -> List[MangaSearchResult]:
        parsed = self.parse_url(query)
        if parsed:
            try:
                return [self.get_manga_details(parsed)]
            except Exception:
                pass

        url = f"{self.api_base}/search"
        params = {"query": query, "page": 1}
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        results = []
        for item in data.get("result", []):
            gid = str(item.get("id"))
            eng_title = item.get("english_title") or ""
            jap_title = item.get("japanese_title") or ""
            title = eng_title or jap_title or f"Gallery #{gid}"

            thumb_path = item.get("thumbnail") or ""
            cover_url = f"{self.thumb_servers[0]}/{thumb_path}" if thumb_path else ""
            pages_count = item.get("num_pages") or 0

            results.append(MangaSearchResult(
                id=gid,
                provider=self.name,
                title=title,
                cover_url=cover_url,
                description=f"Pages: {pages_count} | ID: {gid}",
                status="Completed",
                latest_chapter="1",
                url=f"https://nhentai.net/g/{gid}/",
                extra={"media_id": item.get("media_id"), "pages_count": pages_count},
            ))
            if len(results) >= limit:
                break

        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        parsed = self.parse_url(manga_id)
        gid = parsed if parsed else manga_id

        url = f"{self.api_base}/galleries/{gid}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        title_dict = data.get("title", {})
        title = (
            title_dict.get("english")
            or title_dict.get("pretty")
            or title_dict.get("japanese")
            or f"Gallery #{gid}"
        )

        cover_path = data.get("cover", {}).get("path") or data.get("thumbnail", {}).get("path")
        cover_url = f"{self.thumb_servers[0]}/{cover_path}" if cover_path else ""

        tags = [t.get("name") for t in data.get("tags", []) if t.get("name")]
        desc = "Tags: " + ", ".join(tags[:15]) if tags else ""

        return MangaSearchResult(
            id=gid,
            provider=self.name,
            title=title,
            cover_url=cover_url,
            description=desc,
            status="Completed",
            latest_chapter="1",
            url=f"https://nhentai.net/g/{gid}/",
            extra={"media_id": data.get("media_id"), "num_pages": data.get("num_pages")},
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        parsed = self.parse_url(manga_id)
        gid = parsed if parsed else manga_id

        # In nhentai, each gallery is a single doujin/book (Chapter 1)
        details = self.get_manga_details(gid)
        pages_count = details.extra.get("num_pages") or 1

        return [
            ChapterInfo(
                id=gid,
                provider=self.name,
                chapter_num="1",
                title=details.title,
                url=f"https://nhentai.net/g/{gid}/",
                page_count=pages_count,
            )
        ]

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        parsed = self.parse_url(chapter_id)
        gid = parsed if parsed else chapter_id

        url = f"{self.api_base}/galleries/{gid}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("pages", [])
        page_urls = []
        for p in pages:
            path = p.get("path")
            if path:
                page_urls.append(f"{self.cdn_servers[0]}/{path}")

        return page_urls

    def download_image(self, url: str, output_path: str, referer: Optional[str] = None) -> bool:
        return super().download_image(url, output_path, referer="https://nhentai.net/")
