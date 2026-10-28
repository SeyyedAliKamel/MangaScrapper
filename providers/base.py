from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import requests
import os

@dataclass
class MangaSearchResult:
    id: str
    provider: str
    title: str
    cover_url: str = ""
    description: str = ""
    status: str = ""
    latest_chapter: str = ""
    url: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "title": self.title,
            "cover_url": self.cover_url,
            "description": self.description,
            "status": self.status,
            "latest_chapter": self.latest_chapter,
            "url": self.url,
            "extra": self.extra,
        }

@dataclass
class ChapterInfo:
    id: str
    provider: str
    chapter_num: str
    title: str = ""
    volume: str = ""
    url: str = ""
    page_count: Optional[int] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "chapter_num": self.chapter_num,
            "title": self.title,
            "volume": self.volume,
            "url": self.url,
            "page_count": self.page_count,
            "extra": self.extra,
        }


def parse_chapter_number(chap_str: Any) -> float:
    """Parse chapter number to float for proper numerical sorting."""
    if chap_str is None:
        return 999999.0
    s = str(chap_str).strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        pass
    # Try finding first float in string e.g. "ch. 12.5"
    import re
    match = re.search(r"(\d+(\.\d+)?)", s)
    if match:
        try:
            return float(match.group(1))
        except (ValueError, TypeError):
            pass
    return 999999.0


class BaseMangaProvider(ABC):
    name: str = "base"
    display_name: str = "Base Provider"
    domains: List[str] = []

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })

    def can_handle_url(self, url: str) -> bool:
        lowered = url.lower()
        return any(domain in lowered for domain in self.domains)

    @abstractmethod
    def parse_url(self, url: str) -> Optional[str]:
        """Extract manga ID or slug from a URL."""
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 20) -> List[MangaSearchResult]:
        """Search for manga by title or keyword."""
        pass

    @abstractmethod
    def get_manga_details(self, manga_id: str) -> MangaSearchResult:
        """Fetch details for a given manga."""
        pass

    @abstractmethod
    def get_chapters(self, manga_id: str) -> List[ChapterInfo]:
        """Fetch all chapters for a manga in ascending order."""
        pass

    @abstractmethod
    def get_page_urls(self, chapter_id: str, extra: Optional[Dict[str, Any]] = None) -> List[str]:
        """Fetch image URLs for a chapter."""
        pass

    def download_image(self, url: str, output_path: str, referer: Optional[str] = None) -> bool:
        """Download an image to output_path."""
        headers = {}
        if referer:
            headers["Referer"] = referer
        resp = self.session.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
