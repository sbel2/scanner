"""
enrich.py — read an opportunity's real page and vet it on facts, not a snippet.

This is the heart of the scanner's accuracy. A search snippet (~800 chars) almost
never contains the date, location, deadline, or who-is-eligible text, so judging
freshness/eligibility/relevance from it is guesswork — and the old pipeline did
exactly that, letting stale and ineligible items through whenever the snippet was
silent (which was almost always).

Instead, for each promising candidate we READ THE ACTUAL PAGE and, in one LLM
call, both (a) extract the structured fields (date, deadline, location, audience)
and (b) decide whether it has already passed and whether this specific candidate
is eligible. Every downstream gate then runs on real data.

The page read is made robust on purpose — reading the page is the whole point, so
we try hard before giving up:

    Tavily Extract (advanced)  →  Tavily Extract (basic)  →  direct HTTPS fetch

with retries on the transient connection-reset / timeout errors that the logs show
are common. Only when all of these fail do we treat the page as unreadable.
"""
from __future__ import annotations

import json
import re
import time
from datetime import date

import httpx
from tavily import TavilyClient

from .config import (
    ELIGIBILITY_RULES,
    MODEL_FILTER,
    NEWS_RECENCY_DAYS,
    PREFERRED_LOCATIONS,
    TAVILY_API_KEY,
    USER_PROFILE,
)
from .llm import complete
from .models import EligibilityVerdict, Opportunity

# A browser-ish UA for the direct-fetch fallback. Many event pages 403 a bare
# python-httpx client but serve a normal-looking request fine.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")
_BLANKLINES_RE = re.compile(r"\n{3,}")


def _clean_html(raw: str) -> str:
    """Crude HTML → text for the direct-fetch fallback (Tavily returns text already)."""
    raw = _TAG_RE.sub(" ", raw)
    raw = _STRIP_TAGS_RE.sub(" ", raw)
    raw = _WS_RE.sub(" ", raw)
    raw = _BLANKLINES_RE.sub("\n\n", raw)
    return raw.strip()


def _tavily_extract(client: TavilyClient, url: str, depth: str) -> str:
    try:
        res = client.extract(urls=url, extract_depth=depth, timeout=45)
    except Exception as e:
        print(f"[enrich] tavily extract ({depth}) failed '{url}': {e}")
        return ""
    results = res.get("results", []) if isinstance(res, dict) else []
    for r in results:
        content = (r.get("raw_content") or r.get("content") or "").strip()
        if content:
            return content
    return ""


def _direct_fetch(url: str) -> str:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": _UA, "Accept": "text/html,*/*"},
        ) as c:
            resp = c.get(url)
            resp.raise_for_status()
            return _clean_html(resp.text)
    except Exception as e:
        print(f"[enrich] direct fetch failed '{url}': {e}")
        return ""


def fetch_page_text(url: str, client: TavilyClient | None = None) -> str:
    """Read a page's text, trying hard. Empty string only if everything failed.

    Order: Tavily advanced (2 tries) → Tavily basic → direct HTTPS fetch. The
    Tavily path gets past most JS rendering and Cloudflare/403 blocking; the
    direct fetch is a last resort for pages Tavily can't reach.
    """
    if TAVILY_API_KEY:
        client = client or TavilyClient(api_key=TAVILY_API_KEY)
        for attempt in range(2):
            text = _tavily_extract(client, url, "advanced")
            if text:
                return text
            time.sleep(1.0 + attempt)  # brief backoff on the transient resets
        text = _tavily_extract(client, url, "basic")
        if text:
            return text
    return _direct_fetch(url)


# ---------------------------------------------------------------------------
# Combined "vet" call: extract structured fields + judge freshness + eligibility
# in a single LLM round-trip over the real page. Replaces the old separate
# snippet-eligibility and end-stage freshness calls.
# ---------------------------------------------------------------------------
def _build_vet_system() -> str:
    rules_block = ""
    if ELIGIBILITY_RULES:
        rules_block = "\n\nReject (eligible=\"no\") if any of these candidate-specific rules apply:\n" + "\n".join(
            f"- {r}" for r in ELIGIBILITY_RULES
        )
    locs_block = ""
    if PREFERRED_LOCATIONS:
        locs_block = (
            "\n\nCANDIDATE'S ATTENDABLE LOCATIONS (priority order):\n"
            + ", ".join(PREFERRED_LOCATIONS)
        )

    return f"""You read the full text of an opportunity's web page and return a single \
structured judgement for a specific candidate.

CANDIDATE PROFILE:
{USER_PROFILE}{locs_block}

You are given today's date and the page content. Do TWO things from the page:

1. EXTRACT the opportunity's real details (use null when the page truly doesn't say —
   never invent a date or location).
2. JUDGE, relative to today, whether it has already passed and whether THIS candidate
   is eligible.

Return STRICT JSON ONLY, no prose, no markdown fences:
{{
  "title": "<clean name of the opportunity>",
  "summary": "<1-2 sentence factual description>",
  "location": "<city/venue, or 'Remote', or null>",
  "starts_at": "<event/start date YYYY-MM-DD, or null>",
  "deadline": "<application/registration deadline YYYY-MM-DD, or null>",
  "audience": "<who it is for / eligibility text from the page, or null>",
  "expired": "yes" | "no" | "unclear",
  "eligible": "yes" | "no" | "unclear",
  "reason": "<one short sentence covering the expired+eligible verdict>"
}}

EXPIRED:
- "yes" only if the page makes it clear it is over: a one-time event whose end date is
  strictly before today, OR the sole application/registration deadline is strictly
  before today with no later cohort / rolling / "applications open" signal.
- "no" for a future date, a rolling/ongoing/evergreen program, an upcoming edition, or
  currently-open applications.
- "unclear" only if the page genuinely gives no usable date.
- Never call something expired on a copyright year or a past edition that has a future one.

ELIGIBLE:
- "no" if the page shows the opportunity excludes this candidate (audience/role/citizenship/
  age/enrollment mismatch), OR it is an IN-PERSON event whose location is not one of the
  candidate's attendable locations and is not remote/virtual/online/hybrid. Funding, grants,
  fellowships and remote-friendly roles are not rejected on location unless they require
  relocating somewhere the candidate cannot go.
- "yes" if there is positive evidence they qualify, or it is broadly open and nothing excludes them.
- "unclear" only when the page is genuinely silent on who may participate.{rules_block}

Base every field and verdict ONLY on the page content provided."""


_VET_SYSTEM = _build_vet_system()


# ---------------------------------------------------------------------------
# News lane — informational articles (papers, launches, lab announcements) are
# not attendable/applicable opportunities, so they are judged differently: on
# recency and on-topic-ness, not eligibility/expiry. We still READ THE PAGE
# (never the snippet) so the verdict is grounded in the real article.
# ---------------------------------------------------------------------------
def _build_news_system() -> str:
    return f"""You read the full text of a NEWS / informational article and judge whether it \
is worth surfacing to a reader with this profile.

READER PROFILE:
{USER_PROFILE}

You are given today's date and the article text. Return STRICT JSON ONLY, no prose, no fences:
{{
  "title": "<clean headline>",
  "summary": "<1-2 sentence factual summary of what the article reports>",
  "published": "<publication date YYYY-MM-DD, or null>",
  "recent": "yes" | "no" | "unclear",
  "on_topic": "yes" | "no",
  "reason": "<one short sentence>"
}}

RECENT (freshness — stale news is noise):
- "yes" if the article was published within the last {NEWS_RECENCY_DAYS} days, or clearly reports current/breaking developments.
- "no" if it was published more than {NEWS_RECENCY_DAYS} days ago.
- "unclear" only if the page genuinely exposes no publication date.

ON_TOPIC:
- "yes" if it is a genuine news/research article about AI / ML / LLMs / AI agents / AI startups / AI research relevant to the reader's mission.
- "no" if it is off-topic, OR not actually a news article (a product/marketing page, login wall, pricing page, listicle/roundup, category index, or an attendable event/job posting).

Base every field ONLY on the page content provided."""


_VET_NEWS_SYSTEM = _build_news_system()


def _vet_news(opp: Opportunity, content: str, today: date) -> VetResult:
    """Judge a news article on recency + on-topic instead of eligibility/expiry."""
    user = (
        f"TODAY'S DATE: {today.isoformat()}\n"
        f"HEADLINE: {opp.title}\n"
        f"PAGE URL: {opp.url}\n\n"
        f"ARTICLE TEXT (truncated):\n{content[:14000]}"
    )
    try:
        raw = complete(_VET_NEWS_SYSTEM, user, MODEL_FILTER)
        data = json.loads(_extract_json(raw))
    except Exception as e:
        print(f"[enrich] news vet failed '{opp.url}': {e}")
        return VetResult(
            opp,
            EligibilityVerdict(eligible="unclear", reason=f"news vet parse failed: {e}"),
            expired=False,
            readable=True,
        )

    enriched = opp.model_copy(
        update={"summary": (data.get("summary") or opp.summary or "").strip()[:800] or opp.summary}
    )
    on_topic = data.get("on_topic") == "yes"
    stale = data.get("recent") == "no"  # "unclear" is kept — better a maybe-fresh AI item than a false drop
    reason = str(data.get("reason", "")) or "news vetted from page"
    verdict = EligibilityVerdict(
        eligible="yes" if on_topic else "no",
        reason=reason if on_topic else (reason or "off-topic or not a news article"),
    )
    return VetResult(enriched, verdict, expired=stale, readable=True, expired_reason=reason)


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def _parse_date(v) -> date | None:
    if not v or not isinstance(v, str):
        return None
    try:
        return date.fromisoformat(v.strip()[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Web-search date verification — the fallback for pages that hide their own date.
# Partiful / Luma / many event pages render the date client-side in JavaScript,
# so the scraped page text has the title and venue but NO date. Reading the page
# then tells us nothing about freshness, and an undated item gets shipped even
# when it is plainly over (e.g. a "#BOSTechWeek" event from a week that already
# ended). When the page yields no date, we search the web for the event and judge
# expiry from what the wider web says — recap/past-tense hits are strong "it's
# over" signals; a concrete future date clears it.
# ---------------------------------------------------------------------------
_SEARCH_SYSTEM = """You determine whether a specific event/opportunity is still upcoming \
or has already happened, using web search results.

You are given today's date, the opportunity, and a set of search-result snippets.
Decide its status RELATIVE TO TODAY from the snippets.

Return STRICT JSON ONLY:
{"expired": "yes" | "no" | "unclear", "date": "<YYYY-MM-DD or null>", "reason": "<one short sentence with the evidence>"}

- "yes" if the snippets show its date/deadline is strictly before today, or describe it
  in the past tense / as a recap of something that already happened (with no future edition).
- "no" if the snippets give a concrete date on or after today, or show it is an ongoing /
  recurring / evergreen program currently running.
- "unclear" if the snippets genuinely don't pin down the timing.
Base the verdict only on the snippets; do not invent a date."""


def _strip_site_suffix(title: str) -> str:
    # "ScaleUp Labs Demo Day #BOSTechWeek - Partiful" → "ScaleUp Labs Demo Day #BOSTechWeek"
    return re.split(r"\s+[|\-–]\s+(?:partiful|luma|lu\.ma|eventbrite|meetup|devpost)\b", title, flags=re.IGNORECASE)[0].strip()


def verify_date_via_search(
    opp: Opportunity, client: TavilyClient | None = None, today: date | None = None
) -> tuple[str, date | None, str]:
    """Return (expired_verdict, found_date, reason) by web-searching for the event.

    Used only when the page itself exposed no date. Returns ("unclear", None, ...)
    on any failure so it never falsely drops an item.
    """
    today = today or date.today()
    if not TAVILY_API_KEY:
        return "unclear", None, "no Tavily key; date unverified"
    client = client or TavilyClient(api_key=TAVILY_API_KEY)

    name = _strip_site_suffix(opp.title)
    loc = (opp.location or "").split(",")[0].strip()
    query = f"{name} {loc} {today.year} date".strip()

    snippets: list[str] = []
    try:
        res = client.search(query=query, search_depth="basic", max_results=6, topic="general")
    except Exception as e:
        print(f"[enrich] date-search failed '{opp.title[:60]}': {e}")
        return "unclear", None, "date search failed"
    for r in res.get("results", []):
        t = (r.get("title") or "").strip()
        c = (r.get("content") or "").strip()
        if t or c:
            snippets.append(f"- {t}: {c}"[:500])
    if not snippets:
        return "unclear", None, "no search results"

    user = (
        f"TODAY'S DATE: {today.isoformat()}\n"
        f"OPPORTUNITY: {name}\n"
        f"LOCATION: {opp.location or '(unknown)'}\n\n"
        "SEARCH RESULTS:\n" + "\n".join(snippets[:6])
    )
    try:
        raw = complete(_SEARCH_SYSTEM, user, MODEL_FILTER)
        data = json.loads(_extract_json(raw))
    except Exception as e:
        print(f"[enrich] date-search verdict failed '{opp.title[:60]}': {e}")
        return "unclear", None, "date search verdict failed"

    return (
        data.get("expired", "unclear"),
        _parse_date(data.get("date")),
        str(data.get("reason", "")) or "verified via web search",
    )


class VetResult:
    """Outcome of reading + judging a candidate's page."""

    def __init__(
        self,
        opp: Opportunity,
        verdict: EligibilityVerdict,
        expired: bool,
        readable: bool,
        expired_reason: str = "",
    ):
        self.opp = opp
        self.verdict = verdict
        self.expired = expired
        self.readable = readable
        self.expired_reason = expired_reason


def vet(opp: Opportunity, client: TavilyClient | None = None, today: date | None = None) -> VetResult:
    """Read the page, enrich `opp` with real fields, and judge freshness + eligibility.

    Returns a VetResult. When the page cannot be read after every fallback,
    `readable` is False and the caller decides what to do (we drop, since an
    unverifiable item is exactly the noise the user is trying to escape).
    """
    today = today or date.today()
    client = client or (TavilyClient(api_key=TAVILY_API_KEY) if TAVILY_API_KEY else None)

    content = fetch_page_text(opp.url, client)
    if not content:
        return VetResult(
            opp,
            EligibilityVerdict(eligible="unclear", reason="page could not be read"),
            expired=False,
            readable=False,
        )

    # News runs its own recency/on-topic judgement (still on the real page).
    if opp.category == "news":
        return _vet_news(opp, content, today)

    user = (
        f"TODAY'S DATE: {today.isoformat()}\n"
        f"SEARCH TITLE: {opp.title}\n"
        f"PAGE URL: {opp.url}\n"
        f"SEARCH SNIPPET: {opp.summary[:400]}\n\n"
        f"PAGE CONTENT (truncated):\n{content[:14000]}"
    )
    try:
        raw = complete(_VET_SYSTEM, user, MODEL_FILTER)
        data = json.loads(_extract_json(raw))
    except Exception as e:
        print(f"[enrich] vet verdict failed '{opp.url}': {e}")
        # We DID read the page but couldn't parse a verdict — keep the item with
        # what we have rather than dropping a real page over a parse hiccup.
        return VetResult(
            opp,
            EligibilityVerdict(eligible="unclear", reason=f"vet parse failed: {e}"),
            expired=False,
            readable=True,
        )

    enriched = opp.model_copy(
        update={
            "summary": (data.get("summary") or opp.summary or "").strip()[:800] or opp.summary,
            "location": (data.get("location") or opp.location) or None,
            "starts_at": _parse_date(data.get("starts_at")) or opp.starts_at,
            "deadline": _parse_date(data.get("deadline")) or opp.deadline,
            "eligibility_raw": (data.get("audience") or opp.eligibility_raw) or None,
        }
    )

    expired = data.get("expired") == "yes"
    verdict = EligibilityVerdict(
        eligible=data.get("eligible", "unclear"),
        reason=str(data.get("reason", "")) or "vetted from page",
    )
    expired_reason = verdict.reason

    # Date-on-page missing? The page hid it (JS-rendered Partiful/Luma etc.).
    # Verify freshness via web search rather than shipping an undated item that
    # may well be over. Only when the page didn't already settle expiry.
    if not expired and enriched.starts_at is None and enriched.deadline is None:
        se_expired, se_date, se_reason = verify_date_via_search(enriched, client, today)
        if se_expired == "yes":
            expired = True
            expired_reason = f"web search: {se_reason}"
        elif se_date is not None:
            enriched = enriched.model_copy(update={"starts_at": se_date})

    return VetResult(enriched, verdict, expired=expired, readable=True, expired_reason=expired_reason)
