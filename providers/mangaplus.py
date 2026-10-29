import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import re
import time
import uuid
from typing import List, Optional, Dict, Any
from pymangaplus.utils import proto2dict
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo

class MangaPlusProvider(BaseMangaProvider):
    name = "mangaplus"
    display_name = "MANGA Plus (Official Shueisha)"
    domains = ["mangaplus.shueisha.co.jp"]
    api_base = "https://jumpg-webapi.tokyo-cdn.com/api"

    TITLE_URL_REGEX = re.compile(r"mangaplus\.shueisha\.co\.jp/titles/(\d+)")
    VIEWER_URL_REGEX = re.compile(r"mangaplus\.shueisha\.co\.jp/viewer/(\d+)")

    def __init__(self):
        super().__init__()
        self.session_token = str(uuid.uuid4())
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": "https://mangaplus.shueisha.co.jp",
            "Referer": "https://mangaplus.shueisha.co.jp/",
            "SESSION-TOKEN": self.session_token,
            "Accept": "*/*",
        })
        self._cached_titles: List[Dict[str, Any]] = []
        self._last_titles_fetch: float = 0.0
        self._key_cache: Dict[str, Optional[str]] = {}
        self._detail_cache: Dict[str, Dict[str, Any]] = {}

    def _ensure_titles(self) -> List[Dict[str, Any]]:
        now = time.time()
        if self._cached_titles and (now - self._last_titles_fetch < 3600):
            return self._cached_titles

        url = f"{self.api_base}/title_list/allV2"
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = proto2dict(resp.content)
            all_view = data.get("allView", {})
            titles = []
            for group in all_view.get("titles", []):
                for item in group.get("items", []):
                    # Prefer English titles
                    lang = item.get("language")
                    if lang and lang != "ENGLISH":
                        continue
                    titles.append(item)
            self._cached_titles = titles
            self._last_titles_fetch = now
        except Exception as e:
            print(f"Failed to fetch MangaPlus title catalog: {e}")

        return self._cached_titles

    def can_handle_url(self, url: str) -> bool:
        lowered = url.lower().strip()
        return any(d in lowered for d in self.domains)

    def parse_url(self, url: str) -> Optional[str]:
        cleaned = url.strip()
        m = self.TITLE_URL_REGEX.search(cleaned)
        if m:
            return m.group(1)
        m2 = self.VIEWER_URL_REGEX.search(cleaned)
        if m2:
            return m2.group(1)
        if cleaned.isdigit() and len(cleaned) in (6, 7):
            return cleaned
        return None

    def search(self, query: str, limit: int = 20) -> List[MangaSearchResult]:
        parsed = self.parse_url(query)
        if parsed:
            try:
                return [self.get_manga_details(parsed)]
            except Exception:
                pass

        titles = self._ensure_titles()
        q_lower = query.lower().strip()
        results: List[MangaSearchResult] = []

        for item in titles:
            name = item.get("titleName") or ""
            author = item.get("author") or ""
            if q_lower in name.lower() or q_lower in author.lower():
                tid = str(item.get("titleId"))
                cover = item.get("imagePortrait") or ""
                results.append(MangaSearchResult(
                    id=tid,
                    provider=self.name,
                    title=name,
                    cover_url=cover,
                    description=f"Author: {author} | Official Shueisha Simulpub",
                    status="Ongoing",
                    latest_chapter="Latest",
                    url=f"https://mangaplus.shueisha.co.jp/titles/{tid}",
                    extra={"author": author, "title_id": tid},
                ))
                if len(results) >= limit:
                    break

        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        parsed = self.parse_url(manga_id)
        tid = parsed if parsed else manga_id

        if tid in self._detail_cache:
            data = self._detail_cache[tid]
        else:
            url = f"{self.api_base}/title_detailV3?title_id={tid}"
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = proto2dict(resp.content).get("titleDetailView", {})
            self._detail_cache[tid] = data

        title_info = data.get("title", {})
        title_name = title_info.get("titleName") or f"Manga #{tid}"
        author = title_info.get("author") or ""
        cover_url = title_info.get("imagePortrait") or ""
        overview = data.get("overview") or ""

        return MangaSearchResult(
            id=tid,
            provider=self.name,
            title=title_name,
            cover_url=cover_url,
            description=overview or f"Author: {author} (Official Shueisha)",
            status="Ongoing",
            latest_chapter="Latest",
            url=f"https://mangaplus.shueisha.co.jp/titles/{tid}",
            extra={"author": author, "title_id": tid},
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        parsed = self.parse_url(manga_id)
        tid = parsed if parsed else manga_id

        if tid in self._detail_cache:
            data = self._detail_cache[tid]
        else:
            url = f"{self.api_base}/title_detailV3?title_id={tid}"
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            data = proto2dict(resp.content).get("titleDetailView", {})
            self._detail_cache[tid] = data

        # In MangaPlus, chapters are organized in chapter groups:
        # firstChapterList (first 3 free chapters) and lastChapterList (latest 3 simulpubs)
        collected_chapters: List[Dict[str, Any]] = []
        seen_ids = set()

        for group in data.get("chapters", []):
            if isinstance(group, dict):
                first_list = group.get("firstChapterList", [])
                last_list = group.get("lastChapterList", [])
                for ch in first_list + last_list:
                    cid = ch.get("chapterId")
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        collected_chapters.append(ch)

        # Build ChapterInfo objects
        chapter_infos: List[ChapterInfo] = []
        for ch in collected_chapters:
            cid = str(ch.get("chapterId"))
            raw_title = ch.get("titleName") or ""
            sub_title = ch.get("chapterSubTitle") or ""
            num_match = re.search(r"(\d+(?:\.\d+)?)", raw_title)
            c_num = num_match.group(1) if num_match else "1"

            full_title = f"{raw_title} - {sub_title}".strip(" -")
            chapter_infos.append(ChapterInfo(
                id=cid,
                provider=self.name,
                chapter_num=c_num,
                title=full_title or f"Chapter {c_num}",
                url=f"https://mangaplus.shueisha.co.jp/viewer/{cid}",
                extra={"thumbnail": ch.get("thumbnailUrl")},
            ))

        # Sort by chapter number numeric
        def sort_key(c: ChapterInfo):
            try:
                return float(c.chapter_num)
            except ValueError:
                return 0.0

        chapter_infos.sort(key=sort_key)
        return chapter_infos

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        parsed = self.parse_url(chapter_id)
        cid = parsed if parsed else chapter_id

        url = f"{self.api_base}/manga_viewer?chapter_id={cid}&split=yes&img_quality=super_high"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()
        data = proto2dict(resp.content)

        mv = data.get("mangaViewer", {})
        pages = mv.get("pages", [])
        page_urls: List[str] = []

        for p_wrapper in pages:
            page = p_wrapper.get("page")
            if not page:
                continue
            img_url = page.get("imagePage")
            if not img_url:
                continue
            encryption_key = page.get("encryptionKey")
            self._key_cache[img_url] = encryption_key
            page_urls.append(img_url)

        return page_urls

    def download_image(self, url: str, output_path: str, referer: Optional[str] = None) -> bool:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Origin": "https://mangaplus.shueisha.co.jp",
            "Referer": "https://mangaplus.shueisha.co.jp/",
        }
        try:
            resp = self.session.get(url, headers=headers, timeout=25)
            resp.raise_for_status()
            img_raw = resp.content

            encryption_key = self._key_cache.get(url)
            if encryption_key:
                key_bytes = bytes.fromhex(encryption_key)
                k_len = len(key_bytes)
                full_key = (key_bytes * ((len(img_raw) // k_len) + 1))[:len(img_raw)]
                int_data = int.from_bytes(img_raw, "big")
                int_key = int.from_bytes(full_key, "big")
                decrypted = (int_data ^ int_key).to_bytes(len(img_raw), "big")
                with open(output_path, "wb") as f:
                    f.write(decrypted)
            else:
                with open(output_path, "wb") as f:
                    f.write(img_raw)

            return True
        except Exception as e:
            print(f"Error downloading MangaPlus image: {e}")
            return False
