from __future__ import annotations

import re

from tavily import TavilyClient

from ..config import TAVILY_API_KEY, TAVILY_QUERIES
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


def collect_tavily() -> list[Opportunity]:
    if not TAVILY_API_KEY:
        print("[tavily] TAVILY_API_KEY not set, skipping")
        return []

    client = TavilyClient(api_key=TAVILY_API_KEY)
    seen_urls: set[str] = set()
    items: list[Opportunity] = []

    for q in TAVILY_QUERIES:
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
