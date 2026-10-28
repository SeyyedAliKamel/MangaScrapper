import re
import requests
from typing import List, Optional, Dict, Any
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo, parse_chapter_number

class ComickProvider(BaseMangaProvider):
    name = "comick"
    display_name = "Comick"
    domains = ["comick.io", "comick.app", "comick.cc", "comick.dev"]
    api_base = "https://api.comick.dev"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "Referer": "https://comick.io/",
            "Origin": "https://comick.io",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })

    def parse_url(self, url: str) -> Optional[str]:
        # Matches https://comick.io/comic/{slug} or comic/{hid}
        match = re.search(r"comic/([^/?#]+)", url)
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

        url = f"{self.api_base}/v1.0/search"
        params = {"q": query, "limit": min(limit, 25)}
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        results = []
        for item in data:
            hid = item.get("hid")
            slug = item.get("slug")
            identifier = slug or hid
            title = item.get("title") or "Unknown"

            # Cover
            cover = ""
            md_covers = item.get("md_covers", [])
            if md_covers and isinstance(md_covers, list):
                b2key = md_covers[0].get("b2key")
                if b2key:
                    cover = f"https://meo.comick.pictures/{b2key}"

            desc = item.get("desc") or ""
            status_num = item.get("status")
            status_str = "ongoing" if status_num == 1 else "completed" if status_num == 2 else ""
            last_chap = item.get("last_chapter") or ""

            results.append(MangaSearchResult(
                id=identifier,
                provider=self.name,
                title=title,
                cover_url=cover,
                description=desc[:300] + ("..." if len(desc) > 300 else ""),
                status=status_str,
                latest_chapter=str(last_chap) if last_chap else "",
                url=f"https://comick.io/comic/{identifier}",
                extra={"hid": hid, "slug": slug},
            ))
            if len(results) >= limit:
                break

        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        parsed = self.parse_url(manga_id)
        slug_or_hid = parsed if parsed else manga_id

        url = f"{self.api_base}/comic/{slug_or_hid}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        comic = data.get("comic", {})
        title = comic.get("title") or slug_or_hid
        desc = comic.get("desc") or ""
        hid = comic.get("hid") or slug_or_hid
        slug = comic.get("slug") or slug_or_hid

        cover = ""
        md_covers = comic.get("md_covers", [])
        if md_covers and isinstance(md_covers, list):
            b2key = md_covers[0].get("b2key")
            if b2key:
                cover = f"https://meo.comick.pictures/{b2key}"

        return MangaSearchResult(
            id=slug_or_hid,
            provider=self.name,
            title=title,
            cover_url=cover,
            description=desc,
            status=str(comic.get("status", "")),
            latest_chapter=str(comic.get("last_chapter", "")),
            url=f"https://comick.io/comic/{slug_or_hid}",
            extra={"hid": hid, "slug": slug},
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        parsed = self.parse_url(manga_id)
        slug_or_hid = parsed if parsed else manga_id

        # First get comic details to obtain correct hid
        hid = slug_or_hid
        if len(slug_or_hid) != 8: # Comick hid is usually 8 chars
            try:
                details = self.get_manga_details(slug_or_hid)
                hid = details.extra.get("hid") or slug_or_hid
            except Exception:
                pass

        all_chapters: List[ChapterInfo] = []
        page = 1
        limit = 100

        while True:
            url = f"{self.api_base}/comic/{hid}/chapters"
            params = {"lang": "en", "limit": limit, "page": page}
            resp = self.session.get(url, params=params, timeout=20)
            if resp.status_code != 200:
                break
            data = resp.json()
            raw_chaps = data.get("chapters", [])
            if not raw_chaps:
                break

            for c in raw_chaps:
                chap_hid = c.get("hid")
                chap_num = str(c.get("chap") or "unknown")
                title = c.get("title") or ""
                vol = str(c.get("vol") or "")
                mdid = c.get("mdid")

                all_chapters.append(ChapterInfo(
                    id=chap_hid,
                    provider=self.name,
                    chapter_num=chap_num,
                    title=title,
                    volume=vol,
                    url=f"https://comick.io/comic/{hid}/{chap_hid}",
                    extra={"mdid": mdid, "external": c.get("external")},
                ))

            if len(raw_chaps) < limit or page >= 10:
                break
            page += 1

        # Deduplicate
        seen = {}
        unique_chaps = []
        for ch in all_chapters:
            if ch.chapter_num not in seen:
                seen[ch.chapter_num] = True
                unique_chaps.append(ch)

        unique_chaps.sort(key=lambda c: parse_chapter_number(c.chapter_num))
        return unique_chaps

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        # Fetch chapter details
        url = f"{self.api_base}/chapter/{chapter_id}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()

        chap = data.get("chapter", {})
        images = chap.get("images") or chap.get("md_images") or []
        page_urls = []

        for img in images:
            if isinstance(img, dict):
                b2key = img.get("b2key")
                u = img.get("url")
                if u:
                    page_urls.append(u)
                elif b2key:
                    page_urls.append(f"https://meo.comick.pictures/{b2key}")
            elif isinstance(img, str):
                page_urls.append(img)

        # Fallback to MangaDex if chapter is linked via mdid
        if not page_urls and chap.get("mdid"):
            mdid = chap.get("mdid")
            try:
                server_resp = self.session.get(f"https://api.mangadex.org/at-home/server/{mdid}", timeout=15)
                if server_resp.status_code == 200:
                    server = server_resp.json()
                    base = server["baseUrl"]
                    h = server["chapter"]["hash"]
                    page_urls = [f"{base}/data/{h}/{f}" for f in server["chapter"]["data"]]
            except Exception:
                pass

        return page_urls
