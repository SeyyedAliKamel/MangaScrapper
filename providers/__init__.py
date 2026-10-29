from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo
from .mangadex import MangaDexProvider
from .mangapill import MangaPillProvider
from .mangaplus import MangaPlusProvider
from .comick import ComickProvider
from .nhentai import NHentaiProvider
from .cin import CinProvider
from core.ranking import rank_search_results

# Standard Manga Providers (SFW & Simulpubs)
_MANGA_PROVIDERS: Dict[str, BaseMangaProvider] = {
    "mangadex": MangaDexProvider(),
    "mangapill": MangaPillProvider(),
    "mangaplus": MangaPlusProvider(),
    "comick": ComickProvider(),
}

# Dedicated Adult / Doujin Providers (18+)
_H_PROVIDERS: Dict[str, BaseMangaProvider] = {
    "cin": CinProvider(),
    "nhentai": NHentaiProvider(),
}

_ALL_PROVIDERS: Dict[str, BaseMangaProvider] = {
    **_MANGA_PROVIDERS,
    **_H_PROVIDERS,
}

def get_provider(name_or_url: str) -> Optional[BaseMangaProvider]:
    """Retrieve provider by key or auto-detect from URL."""
    lowered = name_or_url.lower().strip()
    if lowered in _ALL_PROVIDERS:
        return _ALL_PROVIDERS[lowered]

    for p in _ALL_PROVIDERS.values():
        if p.can_handle_url(name_or_url):
            return p

    return None

def list_manga_providers() -> List[Dict[str, str]]:
    """Return list of standard manga providers (MangaDex, MangaPill, MANGA Plus)."""
    return [
        {"id": key, "name": p.display_name}
        for key, p in _MANGA_PROVIDERS.items()
    ]

def list_h_providers() -> List[Dict[str, str]]:
    """Return list of dedicated adult / doujin providers (CIN, nhentai)."""
    return [
        {"id": key, "name": p.display_name}
        for key, p in _H_PROVIDERS.items()
    ]

def search_manga_providers(query: str, provider_name: str = "all", limit: int = 20) -> List[MangaSearchResult]:
    """
    Search manga across standard sources (MangaDex, MangaPill, MANGA Plus).
    Excludes adult / doujinshi sources.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    # If query is a URL matching a manga provider
    for p in _MANGA_PROVIDERS.values():
        if p.can_handle_url(cleaned_query):
            try:
                parsed_id = p.parse_url(cleaned_query)
                if parsed_id:
                    details = p.get_manga_details(parsed_id)
                    return [details]
            except Exception:
                pass

    if provider_name and provider_name != "all" and provider_name in _MANGA_PROVIDERS:
        try:
            return _MANGA_PROVIDERS[provider_name].search(cleaned_query, limit=limit)
        except Exception as e:
            print(f"Error searching {provider_name}: {e}")
            return []

    # Search all manga providers concurrently
    raw_results_with_rank: List[Tuple[MangaSearchResult, int]] = []
    with ThreadPoolExecutor(max_workers=len(_MANGA_PROVIDERS)) as executor:
        futures = {
            executor.submit(p.search, cleaned_query, limit): p.name
            for p in _MANGA_PROVIDERS.values()
        }
        for future in as_completed(futures):
            p_name = futures[future]
            try:
                res = future.result()
                for rank, r in enumerate(res):
                    raw_results_with_rank.append((r, rank))
            except Exception as e:
                print(f"Provider {p_name} search failed: {e}")

    # Unified cross-provider relevance ranking
    return rank_search_results(raw_results_with_rank, cleaned_query, limit=limit)

# Backwards compatibility alias
search_providers = search_manga_providers

def search_h_providers(query: str, provider_name: str = "all", limit: int = 20) -> List[MangaSearchResult]:
    """
    Search dedicated H / Doujinshi sources (CIN, nhentai).
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    # Direct URL match
    for p in _H_PROVIDERS.values():
        if p.can_handle_url(cleaned_query):
            try:
                parsed_id = p.parse_url(cleaned_query)
                if parsed_id:
                    details = p.get_manga_details(parsed_id)
                    return [details]
            except Exception:
                pass

    if provider_name and provider_name != "all" and provider_name in _H_PROVIDERS:
        try:
            return _H_PROVIDERS[provider_name].search(cleaned_query, limit=limit)
        except Exception as e:
            print(f"Error searching {provider_name}: {e}")
            return []

    # Query all H providers concurrently
    raw_h_results: List[Tuple[MangaSearchResult, int]] = []
    with ThreadPoolExecutor(max_workers=len(_H_PROVIDERS)) as executor:
        futures = {
            executor.submit(p.search, cleaned_query, limit): p.name
            for p in _H_PROVIDERS.values()
        }
        for future in as_completed(futures):
            p_name = futures[future]
            try:
                res = future.result()
                for rank, r in enumerate(res):
                    raw_h_results.append((r, rank))
            except Exception as e:
                print(f"H-Provider {p_name} search failed: {e}")

    # Unified relevance ranking across H sources
    return rank_search_results(raw_h_results, cleaned_query, limit=limit)

def resolve_manga(query_or_url: str, provider_name: Optional[str] = None) -> Tuple[Optional[BaseMangaProvider], Optional[MangaSearchResult], List[ChapterInfo]]:
    """
    Resolves input (URL, ID, or search query) for manga.
    """
    cleaned = query_or_url.strip()
    provider = None
    details = None
    manga_id = None

    # 1. Check if direct URL matches manga providers
    for p in _MANGA_PROVIDERS.values():
        if p.can_handle_url(cleaned):
            provider = p
            manga_id = p.parse_url(cleaned)
            break

    # 2. Check explicit provider name
    if not provider and provider_name and provider_name in _MANGA_PROVIDERS:
        provider = _MANGA_PROVIDERS[provider_name]

    # 3. Detect MangaDex UUID format if no provider matched
    if not provider and MangaDexProvider.UUID_REGEX.search(cleaned):
        provider = _MANGA_PROVIDERS["mangadex"]
        manga_id = MangaDexProvider.UUID_REGEX.search(cleaned).group(0)

    # 4. If provider is MangaDex and query is not a UUID, search for the manga first
    if provider and provider.name == "mangadex" and not manga_id:
        if not MangaDexProvider.UUID_REGEX.search(cleaned):
            matches = provider.search(cleaned, limit=1)
            if matches:
                details = matches[0]
                manga_id = details.id
            else:
                manga_id = cleaned
        else:
            manga_id = MangaDexProvider.UUID_REGEX.search(cleaned).group(0)

    # 5. Search manga providers
    if not provider or not manga_id:
        matches = search_manga_providers(cleaned, provider_name or "all", limit=1)
        if matches:
            first = matches[0]
            provider = _MANGA_PROVIDERS.get(first.provider)
            manga_id = first.id
            details = first
        else:
            return None, None, []

    if not provider or not manga_id:
        return None, None, []

    if not details:
        try:
            details = provider.get_manga_details(manga_id)
        except Exception:
            details = MangaSearchResult(
                id=manga_id,
                provider=provider.name,
                title=manga_id,
                url=cleaned if cleaned.startswith("http") else "",
            )

    try:
        chapters = provider.get_chapters(manga_id)
    except Exception as e:
        print(f"Failed to fetch chapters for {manga_id} on {provider.name}: {e}")
        chapters = []

    return provider, details, chapters

def resolve_h_gallery(query_or_url: str, provider_name: Optional[str] = None) -> Tuple[Optional[BaseMangaProvider], Optional[MangaSearchResult], List[ChapterInfo]]:
    """
    Resolves 6-digit code or URL for CIN or nhentai gallery.
    """
    cleaned = query_or_url.strip()
    provider = None

    # Check direct URL match
    for p in _H_PROVIDERS.values():
        if p.can_handle_url(cleaned):
            provider = p
            break

    # If provider specified
    if not provider and provider_name and provider_name in _H_PROVIDERS:
        provider = _H_PROVIDERS[provider_name]

    # Default to CIN first (faster / mirror with high availability), fallback to nhentai
    if not provider:
        provider = _H_PROVIDERS.get("cin") or _H_PROVIDERS["nhentai"]

    gid = provider.parse_url(cleaned) or cleaned

    try:
        details = provider.get_manga_details(gid)
        chapters = provider.get_chapters(gid)
        return provider, details, chapters
    except Exception as e:
        print(f"Failed to resolve on {provider.name}: {e}, trying alternate provider...")
        alt_name = "nhentai" if provider.name == "cin" else "cin"
        alt_prov = _H_PROVIDERS.get(alt_name)
        if alt_prov:
            try:
                details = alt_prov.get_manga_details(gid)
                chapters = alt_prov.get_chapters(gid)
                return alt_prov, details, chapters
            except Exception as e2:
                print(f"Failed to resolve on {alt_name}: {e2}")

        return None, None, []
