"""
filters.py — universal, deterministic pre-scoring filters.

These run for every user before any LLM call and are mission-independent. They
solve two problems that no amount of mission tuning can fix:

1. Expired opportunities — an event whose date has passed, or a program whose
   deadline has closed, is useless to everyone. We drop it on the structured
   date rather than hoping the LLM notices.
2. Duplicate / repost noise — web search returns the same real-world event from
   dozens of social, video and forum reposts under different URLs and titles
   (e.g. one conference scraped from Facebook, YouTube, Reddit, LinkedIn …).
   We drop non-canonical repost domains and collapse near-identical titles so a
   single event surfaces once, not fifteen times.

None of this reads mission.yaml — it is the same for every user.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

from .models import Opportunity

# ---------------------------------------------------------------------------
# Repost / social domains — never the canonical place to apply or register, and
# the dominant source of the "same event fifteen times" problem. A real
# opportunity always has a landing page; a Reel or a Reddit thread about it is
# chatter, not the opportunity. Matched against the registrable host suffix.
# ---------------------------------------------------------------------------
BLOCKED_DOMAINS: frozenset[str] = frozenset({
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "reddit.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "threads.net",
    "pinterest.com",
    "quora.com",
})

# Tokens stripped before building a dedup key: generic filler plus the names of
# common platforms/aggregators that get appended as " - <Site>" title suffixes.
# Keeping years and numbers is deliberate — they distinguish annual editions
# (ODSC 2026 vs 2027) and dated events. This is a general list of widely-seen
# platforms, not tuned to any one user's results.
_STOP: frozenset[str] = frozenset(
    "the a an is are was were be been being to of in on at for and or with from "
    "your you we our their his her its it this that these those back join hear "
    "more announce announced excited first new just what i learned post posts "
    "reel reels shorts video videos news com www http https get s re ll".split()
)
_SITES: frozenset[str] = frozenset(
    "youtube facebook instagram linkedin reddit tiktok twitter threads pinterest "
    "quora medium substack eventbrite luma devpost meetup wikipedia github "
    "indeed glassdoor ziprecruiter lever greenhouse".split()
)


def registrable_domain(url: str) -> str:
    """Return the lowercased host without a leading 'www.' (best-effort)."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def canonical_url(url: str) -> str:
    """Scheme/host/path with query, fragment and trailing slash stripped, so the
    same page scraped with different titles or tracking params collapses."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = p.path.rstrip("/")
    return f"{host}{path}" if host else url.lower()


def is_blocked_domain(url: str) -> bool:
    """True if the URL lives on a known repost/social/video/forum platform."""
    host = registrable_domain(url)
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def title_dedup_key(title: str) -> str:
    """An order-independent fingerprint of a title's significant tokens.

    Collapses the same event scraped under cosmetically different titles
    (trailing " - SiteName", punctuation, word order) while keeping years and
    numbers so distinct editions stay distinct. Validated against real data to
    merge only true duplicates.
    """
    t = title.lower()
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"r/\w+", " ", t)            # reddit subs
    t = re.sub(r"[^a-z0-9]+", " ", t)
    toks = [w for w in t.split() if len(w) > 1 and w not in _STOP and w not in _SITES]
    return " ".join(sorted(set(toks)))


def is_expired(opp: Opportunity, today: date | None = None) -> tuple[bool, str]:
    """Deterministically decide whether a dated opportunity has already passed.

    Only fires when a concrete date is present; undated items pass through so the
    LLM/scoring can still judge them. A closed application deadline or a start
    date strictly before today both count as expired.
    """
    today = today or date.today()
    if opp.deadline and opp.deadline < today:
        return True, f"application deadline {opp.deadline.isoformat()} has passed"
    if opp.starts_at and opp.starts_at < today:
        return True, f"event date {opp.starts_at.isoformat()} has passed"
    return False, ""


def _completeness(opp: Opportunity) -> tuple:
    """Rank a duplicate variant by how useful/canonical it is. Higher is better."""
    return (
        opp.deadline is not None,        # has an actionable deadline
        opp.starts_at is not None,       # has a concrete date
        opp.location is not None,        # has a venue
        len(opp.summary or ""),          # richer description
        -len(opp.url or ""),             # shorter URL ≈ more canonical
    )


def _collapse(items: list[Opportunity], key_of) -> list[Opportunity]:
    """Keep the single most complete/canonical item per key, preserving order."""
    best: dict[str, Opportunity] = {}
    order: list[str] = []
    for o in items:
        k = key_of(o)
        if k not in best:
            best[k] = o
            order.append(k)
        elif _completeness(o) > _completeness(best[k]):
            best[k] = o
    return [best[k] for k in order]


def prefilter(items: list[Opportunity]) -> tuple[list[Opportunity], int, int]:
    """Drop repost domains and collapse within-run duplicates.

    Returns (kept, n_blocked, n_deduped). Collapses first by canonical URL (same
    page, cosmetically different titles) then by normalized title key (same event
    across different pages), keeping the most complete/canonical variant of each.
    """
    survivors: list[Opportunity] = []
    n_blocked = 0
    for o in items:
        if is_blocked_domain(o.url):
            n_blocked += 1
            continue
        survivors.append(o)

    by_url = _collapse(survivors, lambda o: canonical_url(o.url))
    # Empty title-key (no significant tokens) falls back to id so unrelated
    # untitled items are never merged together.
    by_title = _collapse(by_url, lambda o: o.dedup_key or o.id)

    n_deduped = len(survivors) - len(by_title)
    return by_title, n_blocked, n_deduped
