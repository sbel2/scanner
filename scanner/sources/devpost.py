from __future__ import annotations

import re
from datetime import date, datetime

import httpx

from ..models import Opportunity

URLS = [
    "https://devpost.com/api/hackathons?challenge_type=in-person%2Conline&search=AI",
    "https://devpost.com/api/hackathons?challenge_type=in-person%2Conline&search=agent",
    "https://devpost.com/api/hackathons?challenge_type=in-person%2Conline&search=LLM",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; scanner/1.0)"}

DATE_RE = re.compile(r"([A-Z][a-z]{2})\s+(\d{1,2})(?:\s*[-–]\s*(?:([A-Z][a-z]{2})\s+)?(\d{1,2}))?,\s*(\d{4})")


def _parse_end_date(s: str) -> date | None:
    if not s:
        return None
    m = DATE_RE.search(s)
    if not m:
        return None
    start_mon, start_day, end_mon, end_day, year = m.groups()
    end_mon = end_mon or start_mon
    end_day = end_day or start_day
    try:
        return datetime.strptime(f"{end_mon} {end_day} {year}", "%b %d %Y").date()
    except ValueError:
        return None


def collect_devpost() -> list[Opportunity]:
    items: list[Opportunity] = []
    seen: set[str] = set()
    for url in URLS:
        try:
            resp = httpx.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[devpost] fetch failed for {url}: {e}")
            continue

        for h in data.get("hackathons", []):
            if h.get("open_state") != "open":
                continue
            link = (h.get("url") or "").strip()
            title = (h.get("title") or "").strip()
            if not link or not title or link in seen:
                continue
            seen.add(link)

            loc = (h.get("displayed_location") or {}).get("location")
            period = h.get("submission_period_dates", "")
            deadline = _parse_end_date(period)
            themes = ", ".join(t.get("name", "") for t in h.get("themes", []))
            org = h.get("organization_name", "")
            elig = h.get("eligibility_requirement_invite_only_description") if h.get("invite_only") else None

            summary_parts = [
                f"By {org}." if org else "",
                f"Period: {period}." if period else "",
                f"Themes: {themes}." if themes else "",
                f"Prizes: {h.get('prize_amount', 'unspecified')}.",
            ]
            items.append(
                Opportunity(
                    title=title,
                    url=link,
                    source="devpost",
                    category="event",
                    summary=" ".join(p for p in summary_parts if p)[:600],
                    deadline=deadline,
                    location=loc,
                    eligibility_raw=elig,
                )
            )
    return items
