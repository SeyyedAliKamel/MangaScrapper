import re
import requests
from typing import List, Optional, Dict, Any
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo, parse_chapter_number

class MangaDexProvider(BaseMangaProvider):
    name = "mangadex"
    display_name = "MangaDex"
    domains = ["mangadex.org", "api.mangadex.org"]

    UUID_REGEX = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        re.IGNORECASE
    )

    def parse_url(self, url: str) -> Optional[str]:
        match = self.UUID_REGEX.search(url)
        if match:
            return match.group(0).lower()
        return None

    def _extract_cover_url(self, manga_id: str, relationships: List[Dict[str, Any]]) -> str:
        for rel in relationships:
            if rel.get("type") == "cover_art":
                filename = rel.get("attributes", {}).get("fileName")
                if filename:
                    return f"https://uploads.mangadex.org/covers/{manga_id}/{filename}.256.jpg"
        return ""

    def _extract_title(self, attributes: Dict[str, Any]) -> str:
        titles = attributes.get("title", {})
        if isinstance(titles, dict):
            # Prefer 'en' or first available
            if "en" in titles:
                return titles["en"]
            for v in titles.values():
                if v:
                    return v
        alt_titles = attributes.get("altTitles", [])
        for alt in alt_titles:
            if isinstance(alt, dict) and "en" in alt:
                return alt["en"]
        return "Unknown Title"

    def search(self, query: str, limit: int = 20) -> List[MangaSearchResult]:
        # If query is a UUID or MangaDex URL, resolve directly
        parsed_id = self.parse_url(query)
        if parsed_id:
            try:
                details = self.get_manga_details(parsed_id)
                return [details]
            except Exception:
                pass

        url = "https://api.mangadex.org/manga"
        params = {
            "title": query,
            "limit": min(limit, 25),
            "includes[]": ["cover_art"],
            "order[relevance]": "desc",
            "contentRating[]": ["safe", "suggestive", "erotica"],
        }
        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data", [])

        results = []
        for item in data:
            m_id = item["id"]
            attrs = item.get("attributes", {})
            title = self._extract_title(attrs)
            cover = self._extract_cover_url(m_id, item.get("relationships", []))
            
            desc_dict = attrs.get("description", {})
            desc = desc_dict.get("en", "") if isinstance(desc_dict, dict) else ""
            if not desc and isinstance(desc_dict, dict) and desc_dict:
                desc = next(iter(desc_dict.values()), "")

            status = attrs.get("status", "")
            last_chap = attrs.get("lastChapter", "") or ""

            results.append(MangaSearchResult(
                id=m_id,
                provider=self.name,
                title=title,
                cover_url=cover,
                description=desc[:300] + ("..." if len(desc) > 300 else ""),
                status=status,
                latest_chapter=last_chap,
                url=f"https://mangadex.org/title/{m_id}",
            ))
        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        # Extract UUID if full URL passed
        parsed = self.parse_url(manga_id)
        actual_id = parsed if parsed else manga_id

        url = f"https://api.mangadex.org/manga/{actual_id}"
        resp = self.session.get(url, params={"includes[]": ["cover_art"]}, timeout=15)
        resp.raise_for_status()
        item = resp.json().get("data", {})

        attrs = item.get("attributes", {})
        title = self._extract_title(attrs)
        cover = self._extract_cover_url(actual_id, item.get("relationships", []))
        desc_dict = attrs.get("description", {})
        desc = desc_dict.get("en", "") if isinstance(desc_dict, dict) else ""
        if not desc and isinstance(desc_dict, dict) and desc_dict:
            desc = next(iter(desc_dict.values()), "")

        status = attrs.get("status", "")
        last_chap = attrs.get("lastChapter", "") or ""

        return MangaSearchResult(
            id=actual_id,
            provider=self.name,
            title=title,
            cover_url=cover,
            description=desc,
            status=status,
            latest_chapter=last_chap,
            url=f"https://mangadex.org/title/{actual_id}",
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        parsed = self.parse_url(manga_id)
        actual_id = parsed if parsed else manga_id

        chapters = []
        limit = 100
        offset = 0

        while True:
            feed_url = (
                f"https://api.mangadex.org/manga/{actual_id}/feed"
                f"?translatedLanguage[]=en&limit={limit}&offset={offset}"
                f"&order[chapter]=asc"
            )
            resp = self.session.get(feed_url, timeout=20)
            resp.raise_for_status()
            data = resp.json()

            batch = data.get("data", [])
            chapters.extend(batch)

            total = data.get("total", len(chapters))
            offset += limit
            if offset >= total or not batch:
                break

        # Deduplicate chapters by chapter number, preferring chapters with actual pages
        seen_chaps: Dict[str, Dict[str, Any]] = {}
        for chap in chapters:
            chap_num = chap.get("attributes", {}).get("chapter") or "unknown"
            pages = chap.get("attributes", {}).get("pages") or 0
            is_external = bool(chap.get("attributes", {}).get("externalUrl"))

            if chap_num not in seen_chaps:
                seen_chaps[chap_num] = chap
            else:
                existing = seen_chaps[chap_num]
                existing_pages = existing.get("attributes", {}).get("pages") or 0
                existing_ext = bool(existing.get("attributes", {}).get("externalUrl"))
                
                # Replace if existing has 0 pages or is external, and this one has pages
                if (existing_pages == 0 or existing_ext) and pages > 0:
                    seen_chaps[chap_num] = chap

        result_chapters = []
        for chap_num, chap in seen_chaps.items():
            attrs = chap.get("attributes", {})
            title = attrs.get("title") or ""
            pages = attrs.get("pages")
            vol = attrs.get("volume") or ""
            result_chapters.append(ChapterInfo(
                id=chap["id"],
                provider=self.name,
                chapter_num=chap_num,
                title=title,
                volume=vol,
                url=f"https://mangadex.org/chapter/{chap['id']}",
                page_count=pages,
            ))

        result_chapters.sort(key=lambda c: parse_chapter_number(c.chapter_num))
        return result_chapters

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        server_resp = self.session.get(f"https://api.mangadex.org/at-home/server/{chapter_id}", timeout=20)
        server_resp.raise_for_status()
        server = server_resp.json()

        base_url = server["baseUrl"]
        chapter_hash = server["chapter"]["hash"]
        filenames = server["chapter"]["data"]

        return [f"{base_url}/data/{chapter_hash}/{fname}" for fname in filenames]
