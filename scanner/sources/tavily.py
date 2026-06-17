from __future__ import annotations

import re
from datetime import date

from tavily import TavilyClient

from ..config import (
    ALIGNMENT_CONTEXT,
    MODEL_FILTER,
    SEARCH_STRATEGY,
    TAVILY_API_KEY,
    TAVILY_QUERIES,
    USER_PROFILE,
)
from ..models import Opportunity


def _classify(title: str, summary: str) -> str:
    blob = f"{title} {summary}".lower()
    if any(k in blob for k in ("hackathon", "conference", "workshop", "summit", "pitch", "competition")):
        return "event"
    if any(k in blob for k in ("credit", "grant", "fund", "fellowship", "accelerator", "program")):
        return "funding"
    if any(k in blob for k in ("residency", "research", "lab", "scholar")):
        return "research"
    if any(k in blob for k in ("internship", "intern")):
        return "internship"
    return "other"


def _generate_queries() -> list[str]:
    """Ask the LLM to invent today's search queries from the mission directive."""
    from ..llm import complete

    system = (
        "You are a search-query strategist for a daily AI-opportunity scanner. "
        "Your job: each morning, generate a fresh, diverse batch of Tavily web-search "
        "queries that will surface SPECIFIC, NAMED, NEAR-TERM opportunities for the user.\n\n"
        "Hard rules:\n"
        "- Output ONE QUERY PER LINE. No numbering, no bullets, no commentary, no headers.\n"
        "- 18 to 24 queries total.\n"
        "- Vary phrasing, angle, time-window words, venue/org specificity, and search surface "
        "  (lu.ma, partiful, eventbrite, devpost, mit.edu, harvard.edu, etc.). Don't repeat "
        "  near-duplicates.\n"
        "- Favor wording that hits real event pages over aggregator/category landing pages "
        "  (avoid phrasings that match 'discover X events' listicles or '15 best Y' roundups).\n"
        "- Include the actual month/year naturally where it improves recency.\n"
        "- Reason like an explorer: include at least 3 queries probing angles the user did NOT "
        "  explicitly name but that fit their mission (adjacent labs, communities, programs).\n"
    )
    user_msg = (
        f"TODAY: {date.today().isoformat()}\n\n"
        f"USER PROFILE:\n{USER_PROFILE}\n\n"
        f"ALIGNMENT (priorities, most important first):\n{ALIGNMENT_CONTEXT}\n\n"
        f"SEARCH STRATEGY DIRECTIVE FROM USER:\n{SEARCH_STRATEGY}\n\n"
        "Generate today's queries now, one per line."
    )
    try:
        text = complete(system, user_msg, MODEL_FILTER)
    except Exception as e:
        print(f"[tavily] query generation failed, falling back to static list: {e}")
        return []

    queries: list[str] = []
    for line in text.splitlines():
        q = line.strip().lstrip("-•*0123456789. )\t").strip().strip('"').strip()
        if 6 <= len(q) <= 200:
            queries.append(q)
    # de-dupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for q in queries:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq[:24]


def collect_tavily() -> list[Opportunity]:
    if not TAVILY_API_KEY:
        print("[tavily] TAVILY_API_KEY not set, skipping")
        return []

    if SEARCH_STRATEGY:
        queries = _generate_queries()
        if queries:
            print(f"[tavily] generated {len(queries)} queries from strategy directive:")
            for q in queries:
                print(f"  → {q}")
        else:
            queries = TAVILY_QUERIES
            print(f"[tavily] using {len(queries)} static queries (generation returned empty)")
    else:
        queries = TAVILY_QUERIES

    client = TavilyClient(api_key=TAVILY_API_KEY)
    seen_urls: set[str] = set()
    items: list[Opportunity] = []

    for q in queries:
        try:
            res = client.search(
                query=q,
                search_depth="basic",
                max_results=5,
                topic="general",
            )
        except Exception as e:
            print(f"[tavily] query failed '{q}': {e}")
            continue

        for r in res.get("results", []):
            url = (r.get("url") or "").strip()
            title = (r.get("title") or "").strip()
            content = (r.get("content") or "").strip()
            if not url or not title or url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(
                Opportunity(
                    title=title,
                    url=url,
                    source=f"tavily:{_shorten(q)}",
                    category=_classify(title, content),
                    summary=content[:800],
                )
            )
    return items


def _shorten(q: str) -> str:
    return re.sub(r"\s+", "-", q.strip().lower())[:40]
