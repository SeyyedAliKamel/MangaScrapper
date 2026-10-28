import re
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo, parse_chapter_number

class MangaPillProvider(BaseMangaProvider):
    name = "mangapill"
    display_name = "MangaPill"
    domains = ["mangapill.com"]
    base_url = "https://mangapill.com"

    def parse_url(self, url: str) -> Optional[str]:
        # Matches e.g. https://mangapill.com/manga/723/chainsaw-man
        match = re.search(r"mangapill\.com/manga/(\d+(?:/[^/?#]+)?)", url)
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

        search_url = f"{self.base_url}/search"
        resp = self.session.get(search_url, params={"q": query}, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        # Find manga cards
        for container in soup.select("div.container .grid > div, div.my-3"):
            link_el = container.select_one("a[href^='/manga/']")
            if not link_el:
                continue
            href = link_el["href"]
            # e.g. /manga/723/chainsaw-man
            m_id = href.replace("/manga/", "").strip("/")
            
            title_el = container.select_one("div.font-bold, div.leading-tight, a[href^='/manga/'] div")
            title = title_el.text.strip() if title_el else link_el.text.strip()
            if not title:
                # check inside container
                for text_el in container.find_all(["div", "h2", "h3", "a"]):
                    t = text_el.text.strip()
                    if t and len(t) > 1 and not t.lower().startswith("type"):
                        title = t
                        break

            img_el = container.select_one("img")
            cover = ""
            if img_el:
                cover = img_el.get("data-src") or img_el.get("src") or ""

            # Check if we already have this id
            if any(r.id == m_id for r in results):
                continue

            results.append(MangaSearchResult(
                id=m_id,
                provider=self.name,
                title=title or m_id,
                cover_url=cover,
                description="",
                status="",
                latest_chapter="",
                url=f"{self.base_url}/manga/{m_id}",
            ))
            if len(results) >= limit:
                break

        return results

    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        parsed = self.parse_url(manga_id)
        path = parsed if parsed else manga_id
        url = f"{self.base_url}/manga/{path}"
        resp = self.session.get(url, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        title_el = soup.select_one("h1")
        title = title_el.text.strip() if title_el else path

        desc_el = soup.select_one("div.container p.text-sm, div.container div.text-secondary")
        desc = desc_el.text.strip() if desc_el else ""

        img_el = soup.select_one("div.container img")
        cover = img_el.get("data-src") or img_el.get("src") or "" if img_el else ""

        return MangaSearchResult(
            id=path,
            provider=self.name,
            title=title,
            cover_url=cover,
            description=desc,
            status="",
            latest_chapter="",
            url=url,
        )

    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        parsed = self.parse_url(manga_id)
        path = parsed if parsed else manga_id
        url = f"{self.base_url}/manga/{path}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        chap_links = soup.select("#chapters a, div[id*='chapter'] a[href^='/chapters/']")

        chapters = []
        for a in chap_links:
            href = a.get("href", "")
            if not href.startswith("/chapters/"):
                continue

            chap_id = href.replace("/chapters/", "")
            text = a.text.strip()

            # Extract chapter number, e.g. "Chapter 232" or "Chapter 10.5"
            match = re.search(r"Chapter\s+([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
            if match:
                chap_num = match.group(1)
            else:
                num_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", text)
                chap_num = num_match.group(1) if num_match else "unknown"

            chapters.append(ChapterInfo(
                id=chap_id,
                provider=self.name,
                chapter_num=chap_num,
                title=text,
                url=f"{self.base_url}{href}",
            ))

        # Sort ascending
        chapters.sort(key=lambda c: parse_chapter_number(c.chapter_num))
        return chapters

    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        url = f"{self.base_url}/chapters/{chapter_id}"
        resp = self.session.get(url, timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        imgs = soup.select("picture img, div[data-controller='chapter'] img, img.js-page")
        page_urls = []
        for img in imgs:
            src = img.get("data-src") or img.get("src")
            if src:
                page_urls.append(src)
        return page_urls

    def download_image(self, url: str, output_path: str, referer: Optional[str] = None) -> bool:
        ref = referer or self.base_url + "/"
        return super().download_image(url, output_path, referer=ref)
