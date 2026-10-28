from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .base import BaseMangaProvider, MangaSearchResult, ChapterInfo
from .mangadex import MangaDexProvider
from .mangapill import MangaPillProvider
from .comick import ComickProvider
from .nhentai import NHentaiProvider

_PROVIDERS: Dict[str, BaseMangaProvider] = {
    "mangadex": MangaDexProvider(),
    "mangapill": MangaPillProvider(),
    "comick": ComickProvider(),
    "nhentai": NHentaiProvider(),
}

# Default providers included when searching 'all'
_SFW_PROVIDERS = ["mangadex", "mangapill", "comick"]

def get_provider(name_or_url: str) -> Optional[BaseMangaProvider]:
    """Retrieve provider by key or auto-detect from URL."""
    lowered = name_or_url.lower().strip()
    if lowered in _PROVIDERS:
        return _PROVIDERS[lowered]

    # Check URLs or patterns
    for p in _PROVIDERS.values():
        if p.can_handle_url(name_or_url):
            return p

    return None

def list_providers() -> List[Dict[str, str]]:
    """Return list of available provider metadata."""
    return [
        {"id": key, "name": p.display_name}
        for key, p in _PROVIDERS.items()
    ]

def search_providers(query: str, provider_name: str = "all", limit: int = 20) -> List[MangaSearchResult]:
    """
    Search for manga across one or multiple providers.
    """
    cleaned_query = query.strip()
    if not cleaned_query:
        return []

    # If query is a URL or matches an explicit provider pattern
    for p in _PROVIDERS.values():
        if p.can_handle_url(cleaned_query):
            try:
                parsed_id = p.parse_url(cleaned_query)
                if parsed_id:
                    details = p.get_manga_details(parsed_id)
                    return [details]
            except Exception:
                pass

    if provider_name and provider_name != "all" and provider_name in _PROVIDERS:
        try:
            return _PROVIDERS[provider_name].search(cleaned_query, limit=limit)
        except Exception as e:
            print(f"Error searching provider {provider_name}: {e}")
            return []

    # Search default SFW providers in parallel
    results: List[MangaSearchResult] = []
    target_providers = [p for name, p in _PROVIDERS.items() if name in _SFW_PROVIDERS]

    with ThreadPoolExecutor(max_workers=len(target_providers)) as executor:
        futures = {
            executor.submit(p.search, cleaned_query, limit): p.name
            for p in target_providers
        }
        for future in as_completed(futures):
            p_name = futures[future]
            try:
                res = future.result()
                results.extend(res)
            except Exception as e:
                print(f"Provider {p_name} search failed: {e}")

    return results

def resolve_manga(query_or_url: str, provider_name: Optional[str] = None) -> Tuple[Optional[BaseMangaProvider], Optional[MangaSearchResult], List[ChapterInfo]]:
    """
    Resolves input (URL, ID, or search query) into (provider, manga_details, chapter_list).
    """
    cleaned = query_or_url.strip()
    provider = None
    details = None
    manga_id = None

    # 1. Check if direct URL or pattern matches
    for p in _PROVIDERS.values():
        if p.can_handle_url(cleaned):
            provider = p
            manga_id = p.parse_url(cleaned)
            break

    # 2. Check explicit provider name
    if not provider and provider_name and provider_name in _PROVIDERS:
        provider = _PROVIDERS[provider_name]

    # 3. Detect MangaDex UUID format if no provider matched
    if not provider and MangaDexProvider.UUID_REGEX.search(cleaned):
        provider = _PROVIDERS["mangadex"]
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

    # 5. If provider is nhentai and query is not an ID, search nhentai
    if provider and provider.name == "nhentai" and not manga_id:
        matches = provider.search(cleaned, limit=1)
        if matches:
            details = matches[0]
            manga_id = details.id
        else:
            return None, None, []

    # 6. If still no provider or manga_id, search SFW providers
    if not provider or not manga_id:
        matches = search_providers(cleaned, provider_name or "all", limit=1)
        if matches:
            first = matches[0]
            provider = _PROVIDERS.get(first.provider)
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
