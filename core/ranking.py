import re
from typing import List, Tuple, Optional
from providers.base import MangaSearchResult

def compute_relevance(title: str, query: str, original_rank: int = 0) -> float:
    """
    Computes a cross-provider relevance score for a manga/gallery title
    against a search query.
    """
    t = title.strip().lower()
    q = query.strip().lower()
    if not t or not q:
        return 0.0

    # 1. Exact match (highest possible priority)
    if t == q:
        return 2000.0 - (original_rank * 1.0)

    t_clean = re.sub(r"[^\w\s]", " ", t)
    q_clean = re.sub(r"[^\w\s]", " ", q)
    t_words = t_clean.split()
    q_words = q_clean.split()

    if t_clean.strip() == q_clean.strip():
        return 1900.0 - (original_rank * 1.0)

    score = 0.0

    # 2. Title starts with query
    if t.startswith(q) or t_clean.startswith(q_clean):
        score += 350.0

    # 3. Whole word or prefix boundary matches
    q_escaped = re.escape(q_clean)
    if re.search(r"\b" + q_escaped + r"\b", t_clean):
        # Exact word match (e.g. "Komi" in "Komi Can't Communicate")
        score += 260.0
    elif re.search(r"\b" + q_escaped, t_clean):
        # Word-prefix match (e.g. "Komi" in "Komi-san")
        score += 210.0
    else:
        # Query only exists buried inside another word (e.g. "komi" in "nekomimi", "yarikomi")
        # Heavy penalty so unrelated compound words don't displace true titles
        score += 15.0

    # 4. Multi-word phrase & token matching
    if len(q_words) > 1:
        matched_words = sum(1 for w in q_words if re.search(r"\b" + re.escape(w), t_clean))
        score += (matched_words / len(q_words)) * 250.0
        if q_clean in t_clean:
            score += 120.0

    # 5. Length compactness ratio (shorter, focused title gets bonus)
    ratio = min(1.0, len(q) / max(len(t), 1))
    score += ratio * 70.0

    # 6. Preserve relative ranking from provider
    score += max(0, 20 - original_rank) * 1.5

    return score


def rank_search_results(
    results_with_rank: List[Tuple[MangaSearchResult, int]],
    query: str,
    limit: Optional[int] = None
) -> List[MangaSearchResult]:
    """
    Ranks multi-source search results by true relevance, placing top matches
    from all sources together at the top of page 1.
    """
    if not results_with_rank:
        return []

    # Calculate score for each
    scored_items = []
    max_score = 0.0
    for item, orig_rank in results_with_rank:
        score = compute_relevance(item.title, query, orig_rank)
        scored_items.append((score, item))
        if score > max_score:
            max_score = score

    # Sort descending by score
    scored_items.sort(key=lambda pair: pair[0], reverse=True)

    # Filter out pure junk if we have high confidence matches
    final_results: List[MangaSearchResult] = []
    seen_keys = set()

    cutoff = 40.0 if max_score > 300.0 else 0.0

    for score, item in scored_items:
        if score < cutoff and len(final_results) >= 5:
            continue

        # Deduplicate identical items from same provider
        key = (item.provider, item.id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        final_results.append(item)

        if limit and len(final_results) >= limit:
            break

    return final_results
