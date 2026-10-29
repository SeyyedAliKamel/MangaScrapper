import re
from typing import List, Optional, Dict, Any
from urllib.parse import quote
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo

class CinProvider(BaseMangaProvider):
    name = "cin"
    display_name = "CIN (cin.wtf / cin.blue)"
    domains = ["cin.wtf", "cin.blue", "cin.pw"]
    api_base = "https://same.yui.pw/api/v6"

    ID_REGEX = re.compile(r"(?:cin\.(?:wtf|blue|pw)/[vg]/|book/|^)(\d{4,7})$")

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": "https://cin.wtf",
            "Referer": "https://cin.wtf/",
            "Accept": "application/json, text/plain, */*",
        })
        self._gallery_cache: Dict[str, Dict[str, Any]] = {}

    def can_handle_url(self, url: str) -> bool:
        lowered = url.lower().strip()
        if any(d in lowered for d in self.domains):
            return True
        if lowered.isdigit() and 4 <= len(lowered) <= 7:
            return True
        return False

    def parse_url(self, url: str) -> Optional[str]:
        cleaned = url.strip()
        if cleaned.isdigit() and 4 <= len(cleaned) <= 7:
            return cleaned
        match = re.search(r"/(?:v|g)/(\d+)", cleaned)
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

        encoded_query = quote(query.strip())
        url = f"{self.api_base}/search/{encoded_query}/1/popular-today"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        results = []
        for item in data.get("result", []):
            gid = str(item.get("id"))
            title_dict = item.get("title", {})
            title = (
                title_dict.get("pretty")
                or title_dict.get("english")
                or title_dict.get("japanese")
                or f"Doujin #{gid}"
            )

            cover_info = item.get("cover", {})
            cover_url = cover_info.get("t") if isinstance(cover_info, dict) else ""
            pages_count = item.get("num_pages") or 0
            lang = item.get("lang") or "N/A"

            results.append(MangaSearchResult(
                id=gid,
                provider=self.name,
                title=title,
                cover_url=cover_url,
                description=f"Pages: {pages_count} | Lang: {lang} | ID: {gid}",
                status="Completed",
                latest_chapter="1",
                url=f"https://cin.wtf/v/{gid}",
                extra={"media_id": item.get("media_id"), "pages_count": pages_count},
            ))
            if len(results) >= limit:
                break

        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        parsed = self.parse_url(manga_id)
        gid = parsed if parsed else manga_id

        if gid in self._gallery_cache:
            data = self._gallery_cache[gid]
        else:
            url = f"{self.api_base}/book/{gid}"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self._gallery_cache[gid] = data

        title_dict = data.get("title", {})
        title = (
            title_dict.get("pretty")
            or title_dict.get("english")
            or title_dict.get("japanese")
            or f"Doujin #{gid}"
        )

        cover_url = data.get("images", {}).get("cover", {}).get("t") or ""
        tags = [t.get("name") for t in data.get("tags", []) if isinstance(t, dict) and t.get("name")]
        desc = "Tags: " + ", ".join(tags[:15]) if tags else ""

        return MangaSearchResult(
            id=gid,
            provider=self.name,
            title=title,
            cover_url=cover_url,
            description=desc,
            status="Completed",
            latest_chapter="1",
            url=f"https://cin.wtf/v/{gid}",
            extra={"media_id": data.get("media_id"), "num_pages": data.get("num_pages")},
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        parsed = self.parse_url(manga_id)
        gid = parsed if parsed else manga_id

        details = self.get_manga_details(gid)
        pages_count = details.extra.get("num_pages") or 1

        return [
            ChapterInfo(
                id=gid,
                provider=self.name,
                chapter_num="1",
                title=details.title,
                url=f"https://cin.wtf/v/{gid}",
                page_count=pages_count,
            )
        ]

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        parsed = self.parse_url(chapter_id)
        gid = parsed if parsed else chapter_id

        if gid in self._gallery_cache:
            data = self._gallery_cache[gid]
        else:
            url = f"{self.api_base}/book/{gid}"
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            self._gallery_cache[gid] = data

        pages = data.get("images", {}).get("pages", [])
        page_urls = [p["t"] for p in pages if isinstance(p, dict) and p.get("t")]
        return page_urls

    def download_image(self, url: str, output_path: str, referer: Optional[str] = None) -> bool:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": "https://cin.wtf",
            "Referer": "https://cin.wtf/",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=25)
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
        except Exception as e:
            pass

        # Fallback to nhentai direct CDN if kontol mirror is unavailable
        # Extract media_id and page from url: e.g. /i/4279984/1.webp -> https://i.nhentai.net/galleries/4279984/1.webp
        match = re.search(r"/i/(\d+)/(\d+\.[a-zA-Z0-9]+)", url)
        if match:
            media_id, filename = match.groups()
            fallback_url = f"https://i.nhentai.net/galleries/{media_id}/{filename}"
            try:
                resp = self.session.get(fallback_url, headers={"User-Agent": headers["User-Agent"], "Referer": "https://nhentai.net/"}, timeout=25)
                if resp.status_code == 200:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    return True
            except Exception:
                pass

        return False
