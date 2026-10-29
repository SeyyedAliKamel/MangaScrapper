import requests
import time
from typing import Optional, Dict, Any

_COMICK_CACHE: Dict[str, Dict[str, Any]] = {}

def get_comick_metadata(query: str) -> Optional[Dict[str, Any]]:
    """
    Fetches high-resolution cover art, accurate total chapter count,
    and official metadata from Comick (comick.io / api.comick.dev).
    """
    cleaned = query.strip().lower()
    if not cleaned:
        return None

    if cleaned in _COMICK_CACHE:
        return _COMICK_CACHE[cleaned]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Referer": "https://comick.io/",
        "Accept": "application/json, text/plain, */*",
    }

    url = f"https://api.comick.dev/v1.0/search?q={requests.utils.quote(cleaned)}"
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                # Find best matching title
                best_item = data[0]
                for item in data:
                    t = item.get("title", "").lower()
                    if t == cleaned or cleaned in t:
                        best_item = item
                        break

                cover_b2 = best_item.get("md_covers", [{}])[0].get("b2key")
                cover_url = f"https://meo.comick.pictures/{cover_b2}" if cover_b2 else ""

                result = {
                    "title": best_item.get("title", ""),
                    "slug": best_item.get("slug", ""),
                    "hid": best_item.get("hid", ""),
                    "cover_url": cover_url,
                    "last_chapter": best_item.get("last_chapter"),
                    "desc": best_item.get("desc", ""),
                    "status": "Completed" if best_item.get("status") == 2 else "Ongoing",
                    "rating": best_item.get("rating"),
                    "demographic": best_item.get("demographic"),
                }
                _COMICK_CACHE[cleaned] = result
                return result
    except Exception as e:
        print(f"Comick metadata fetch error for '{query}': {e}")

    return None
