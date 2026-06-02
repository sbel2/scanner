"""
freshness.py — verify, by reading the actual page, that an opportunity hasn't
already passed before it goes into the digest.

Why this exists, and why it isn't deterministic date parsing:

A search snippet is a terrible freshness signal. Dates come in too many formats
to parse reliably, and far more often the concrete date simply isn't in the
snippet at all — an annual workshop's blurb rarely states "April 14, 2026". The
only accurate source is the page itself. So for each opportunity that is about to
be emailed, we fetch its landing page (via Tavily Extract, which gets past the JS
rendering and 403/Cloudflare blocking that a raw fetch hits) and ask the model,
given today's date, whether the event is over or the application/registration
deadline has already closed.

This costs an extra fetch + LLM call per candidate. That is deliberate: it runs
only on the handful of items that would actually be sent, and accuracy on
freshness is worth far more than the tokens. The check fails OPEN — any fetch or
parse problem keeps the item — so a transient hiccup never silently suppresses a
good opportunity.
"""
from __future__ import annotations

import json
import re
from datetime import date

from tavily import TavilyClient

from .config import MODEL_FILTER, TAVILY_API_KEY
from .llm import complete
from .models import Opportunity

_SYSTEM = """You decide whether an opportunity has already passed, by reading the
full text of its web page.

You are given today's date and the page content. Determine the opportunity's
timing from the page and answer about its status RELATIVE TO TODAY.

Return strict JSON, nothing else:
{"expired": "yes" | "no" | "unclear", "date": "<the deciding date as YYYY-MM-DD or null>", "reason": "<one short sentence>"}

Answer "yes" ONLY when the page makes it clear the opportunity is over:
- a one-time event whose end date is strictly before today, OR
- an application/registration deadline that is the only way in and is strictly
  before today (with no later cohort, rolling, or "applications open" signal).

Answer "no" when there is a future date, a rolling/ongoing/evergreen program, an
upcoming edition, or applications are currently open.

Answer "unclear" when the page genuinely gives no usable date signal.

Be precise: do not call something expired on a copyright year, a "since 2024"
mention, or a past edition that has a future one. The deadline/event date must
itself be in the past."""


def _fetch_page_text(client: TavilyClient, url: str) -> str:
    """Best-effort full-page text via Tavily Extract. Empty string on failure."""
    try:
        res = client.extract(urls=url, extract_depth="advanced")
    except Exception as e:
        print(f"[freshness] fetch failed '{url}': {e}")
        return ""
    results = res.get("results", []) if isinstance(res, dict) else []
    for r in results:
        content = (r.get("raw_content") or r.get("content") or "").strip()
        if content:
            return content
    return ""


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def verify_fresh(
    opp: Opportunity,
    client: TavilyClient | None = None,
    today: date | None = None,
) -> tuple[bool, str]:
    """Return (is_expired, reason) by reading the opportunity's actual page.

    Fails OPEN: if the page can't be fetched, the model errors, or the verdict is
    anything other than an explicit "yes", the item is treated as fresh and kept.
    Only a clear, page-backed "the date has passed" drops it.
    """
    today = today or date.today()
    if not TAVILY_API_KEY:
        return False, "no Tavily key; freshness unverified"

    client = client or TavilyClient(api_key=TAVILY_API_KEY)
    content = _fetch_page_text(client, opp.url)
    if not content:
        return False, "page could not be read; kept unverified"

    user = (
        f"TODAY'S DATE: {today.isoformat()}\n"
        f"OPPORTUNITY TITLE: {opp.title}\n"
        f"PAGE URL: {opp.url}\n\n"
        f"PAGE CONTENT (truncated):\n{content[:12000]}"
    )
    try:
        text = complete(_SYSTEM, user, MODEL_FILTER)
        data = json.loads(_extract_json(text))
    except Exception as e:
        print(f"[freshness] verdict failed for '{opp.url}': {e}")
        return False, "freshness check errored; kept unverified"

    if data.get("expired") == "yes":
        deciding = data.get("date") or "?"
        return True, f"page shows it has passed ({deciding}): {data.get('reason', '')}".strip()
    return False, str(data.get("reason") or "page shows it is still open")
