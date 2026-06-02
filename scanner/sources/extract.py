"""
extract.py — scrape specific watched pages into opportunities.

For sites that aren't well served by keyword search or an .ics/Luma feed
(conference landing pages, community event listings behind bot protection),
this collector fetches the page content via Tavily's Extract endpoint — which
runs through Tavily's infrastructure, so it gets past the JS rendering and
403/Cloudflare blocking that a raw fetch hits — and then asks a small LLM to
pull any concrete opportunities out of the page text.

Pages to watch live in `preferences.watch_urls` in mission.yaml.
"""
from __future__ import annotations

import json

from tavily import TavilyClient

from ..config import MODEL_FILTER, TAVILY_API_KEY, WATCH_URLS
from ..llm import complete
from ..models import Opportunity

_SYSTEM = """You extract concrete opportunities from the raw text of a web page.

An "opportunity" is a specific event, conference, hackathon, meetup, funding
program, grant, fellowship, accelerator, residency, or internship that a person
could attend or apply to. Navigation links, generic marketing copy, past/expired
listings, and blog commentary are NOT opportunities — skip them.

Return ONLY a JSON array (no prose, no markdown fences). Each element:
{
  "title": "<concise name of the event/program>",
  "url": "<the most specific URL for this item; use the page URL if none>",
  "category": "event" | "funding" | "research" | "internship" | "other",
  "summary": "<1-2 sentence description>",
  "location": "<city/venue or 'Remote' or null>",
  "starts_at": "<YYYY-MM-DD or null>",
  "deadline": "<application/registration deadline YYYY-MM-DD or null>"
}

If the page lists nothing concrete, return []. Never invent dates."""


def _parse_items(page_url: str, content: str) -> list[Opportunity]:
    user = (
        f"Page URL: {page_url}\n\n"
        f"Page content (truncated):\n{content[:12000]}"
    )
    raw = complete(_SYSTEM, user, MODEL_FILTER)
    raw = raw.strip()
    # Be forgiving if the model wraps the array in a fenced block.
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].lstrip("json").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[extract] could not parse LLM output for {page_url}")
        return []
    if not isinstance(data, list):
        return []

    out: list[Opportunity] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        title = (d.get("title") or "").strip()
        url = (d.get("url") or "").strip() or page_url
        if not title:
            continue
        out.append(
            Opportunity(
                title=title,
                url=url,
                source="watch",
                category=d.get("category") or "other",
                summary=(d.get("summary") or "").strip()[:800],
                location=d.get("location") or None,
                starts_at=d.get("starts_at") or None,
                deadline=d.get("deadline") or None,
            )
        )
    return out


def collect_extract() -> list[Opportunity]:
    if not WATCH_URLS:
        return []
    if not TAVILY_API_KEY:
        print("[extract] TAVILY_API_KEY not set, skipping watch_urls")
        return []

    client = TavilyClient(api_key=TAVILY_API_KEY)
    items: list[Opportunity] = []

    for url in WATCH_URLS:
        try:
            res = client.extract(urls=url, extract_depth="advanced")
        except Exception as e:
            print(f"[extract] fetch failed '{url}': {e}")
            continue

        results = res.get("results", []) if isinstance(res, dict) else []
        content = ""
        for r in results:
            content = (r.get("raw_content") or r.get("content") or "").strip()
            if content:
                break
        if not content:
            print(f"[extract] no content extracted from '{url}'")
            continue

        try:
            parsed = _parse_items(url, content)
        except Exception as e:
            print(f"[extract] LLM parse failed '{url}': {e}")
            continue
        print(f"[extract] {len(parsed)} item(s) from {url}")
        items.extend(parsed)

    return items
