import re
import requests
from typing import List, Optional, Dict, Any
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo
from core.comick_meta import get_comick_metadata

class ComickProvider(BaseMangaProvider):
    name = "comick"
    display_name = "ComicK (Covers & Catalog)"
    domains = ["comick.io", "comick.dev", "comick.cc", "comick.app"]
    api_base = "https://api.comick.dev"

    def __init__(self):
        super().__init__()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": "https://comick.io/",
            "Accept": "application/json, text/plain, */*",
        })
        self._pill_provider = None
        self._dex_provider = None

    def _get_pill(self):
        if not self._pill_provider:
            from .mangapill import MangaPillProvider
            self._pill_provider = MangaPillProvider()
        return self._pill_provider

    def _get_dex(self):
        if not self._dex_provider:
            from .mangadex import MangaDexProvider
            self._dex_provider = MangaDexProvider()
        return self._dex_provider

    def can_handle_url(self, url: str) -> bool:
        lowered = url.lower().strip()
        return any(d in lowered for d in self.domains)

    def parse_url(self, url: str) -> Optional[str]:
        # Matches https://comick.io/comic/00-naruto or https://comick.io/comic/naruto
        m = re.search(r"comic/([^/?#]+)", url)
        if m:
            return m.group(1)
        return None

    def search(self, query: str, limit: int = 20) -> List[MangaSearchResult]:
        parsed = self.parse_url(query)
        slug_or_q = parsed if parsed else query.strip()

        url = f"{self.api_base}/v1.0/search?q={requests.utils.quote(slug_or_q)}"
        resp = self.session.get(url, timeout=12)
        resp.raise_for_status()

        data = resp.json()
        results = []
        if isinstance(data, list):
            for item in data:
                slug = item.get("slug") or str(item.get("hid"))
                title = item.get("title") or slug
                last_chap = item.get("last_chapter")
                chap_label = f"{last_chap} Chapters" if last_chap else "Ongoing"

                cover_b2 = item.get("md_covers", [{}])[0].get("b2key") if item.get("md_covers") else ""
                cover_url = f"https://meo.comick.pictures/{cover_b2}" if cover_b2 else ""

                desc = item.get("desc") or ""

                results.append(MangaSearchResult(
                    id=slug,
                    provider=self.name,
                    title=title,
                    cover_url=cover_url,
                    description=desc[:280] + ("..." if len(desc) > 280 else ""),
                    status="Completed" if item.get("status") == 2 else "Ongoing",
                    latest_chapter=chap_label,
                    url=f"https://comick.io/comic/{slug}",
                    extra={"hid": item.get("hid"), "last_chapter": last_chap},
                ))
                if len(results) >= limit:
                    break

        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        parsed = self.parse_url(manga_id)
        slug = parsed if parsed else manga_id

        url = f"{self.api_base}/comic/{slug}"
        resp = self.session.get(url, timeout=12)
        resp.raise_for_status()
        data = resp.json()

        comic = data.get("comic", {})
        title = comic.get("title") or slug
        desc = comic.get("desc") or ""
        last_chap = comic.get("last_chapter")
        chap_label = f"{last_chap} Chapters" if last_chap else "Ongoing"

        cover_b2 = comic.get("md_covers", [{}])[0].get("b2key") if comic.get("md_covers") else ""
        cover_url = f"https://meo.comick.pictures/{cover_b2}" if cover_b2 else ""

        return MangaSearchResult(
            id=slug,
            provider=self.name,
            title=title,
            cover_url=cover_url,
            description=desc,
            status="Completed" if comic.get("status") == 2 else "Ongoing",
            latest_chapter=chap_label,
            url=f"https://comick.io/comic/{slug}",
            extra={"hid": comic.get("hid"), "last_chapter": last_chap},
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        """
        Resolves chapter downloads through MangaPill (or MangaDex)
        by matching title/slug cleanly.
        """
        details = self.get_manga_details(manga_id)
        search_title = details.title

        # Try MangaPill first (fastest full back-catalogs)
        pill = self._get_pill()
        try:
            pill_matches = pill.search(search_title, limit=3)
            if pill_matches:
                # Find closest title match
                target_pill = pill_matches[0]
                for m in pill_matches:
                    if m.title.lower() == search_title.lower():
                        target_pill = m
                        break
                chapters = pill.get_chapters(target_pill.id)
                if chapters:
                    return chapters
        except Exception as e:
            print(f"MangaPill chapter resolution failed for {search_title}: {e}")

        # Fallback to MangaDex
        dex = self._get_dex()
        try:
            dex_matches = dex.search(search_title, limit=3)
            if dex_matches:
                target_dex = dex_matches[0]
                for m in dex_matches:
                    if m.title.lower() == search_title.lower():
                        target_dex = m
                        break
                chapters = dex.get_chapters(target_dex.id)
                if chapters:
                    return chapters
        except Exception as e:
            print(f"MangaDex chapter resolution failed for {search_title}: {e}")

        return []

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        # Delegate to MangaPill or MangaDex based on chapter ID format
        if "-" in chapter_id and "/" in chapter_id:
            return self._get_pill().get_page_urls(chapter_id, extra)
        return self._get_dex().get_page_urls(chapter_id, extra)

    def download_image(self, url: str, output_path: str, referer: Optional[str] = None) -> bool:
        if "mangapill" in url or "readdetectiveconan" in url:
            return self._get_pill().download_image(url, output_path, referer)
        return super().download_image(url, output_path, referer)
