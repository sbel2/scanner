"""
prerank.py — cheap, no-LLM triage to choose which candidates get a page-read.

Reading a page (the accurate step, see enrich.py) costs a fetch + an LLM call, so
we can't do it for every one of the ~150 daily items — that is what made the old
run take hours. We only need enough good candidates to fill the digest, so this
module ranks items by a fast keyword/heuristic signal and the pipeline enriches
the top slice.

This is intentionally generous and recall-oriented: it is a coarse "is this worth
a closer look?" filter, NOT the final judgement. The real decision happens after
the page is read.
"""
from __future__ import annotations

import re

from .config import ALIGNMENT_CONTEXT, PREFERRED_CATEGORIES, PREFERRED_LOCATIONS, USER_PROFILE
from .models import Opportunity

_WORD_RE = re.compile(r"[a-z][a-z0-9+]{2,}")

# Generic words that carry no mission signal — excluded from the keyword profile
# so overlap reflects real topical match, not filler.
_STOP = frozenset(
    "the and for with from this that they you your our are was will has have its into "
    "who what when where why how about over under more most some any all can could would "
    "should may might must each other their there here than then them which while also "
    "building build builds working work works looking based using used use new join "
    "opportunity opportunities event events program programs apply application".split()
)

# Aggregator / listicle / job-board phrasing — almost never a single actionable
# opportunity. Penalized, not dropped (prefilter already handles repost domains).
_AGGREGATOR_RE = re.compile(
    r"\b(top \d+|best \d+|\d+ best|discover|browse|explore all|directory|listings?|"
    r"round[- ]?up|guide to|list of|jobs? (board|hiring)|search results)\b",
    re.IGNORECASE,
)


def _profile_keywords() -> set[str]:
    blob = f"{USER_PROFILE}\n{ALIGNMENT_CONTEXT}".lower()
    return {w for w in _WORD_RE.findall(blob) if w not in _STOP}


_KEYWORDS = _profile_keywords()
_LOC_TOKENS = {t.lower() for loc in PREFERRED_LOCATIONS for t in re.split(r"[,\s]+", loc) if len(t) > 2}


def _score(opp: Opportunity, keywords: set[str]) -> float:
    title = (opp.title or "").lower()
    summary = (opp.summary or "").lower()

    title_toks = {w for w in _WORD_RE.findall(title) if w not in _STOP}
    summ_toks = {w for w in _WORD_RE.findall(summary) if w not in _STOP}

    # Topical overlap — title matches count double (a title term is a stronger
    # signal than one buried in a blurb).
    score = 2.0 * len(title_toks & keywords) + 1.0 * len(summ_toks & keywords)

    # Prefer the categories the user actually asked for.
    if opp.category in PREFERRED_CATEGORIES:
        score += 2.0

    # Trust structured sources (watched pages / calendars already gave us a real
    # date or venue) — they are higher-signal than a raw search hit.
    if opp.source.startswith(("watch", "ical", "luma")):
        score += 2.0
    if opp.starts_at or opp.deadline:
        score += 1.5
    if opp.location:
        score += 1.0

    # A preferred-location mention in the text is a small positive.
    blob = f"{title} {summary}"
    if _LOC_TOKENS and any(tok in blob for tok in _LOC_TOKENS):
        score += 1.0

    # Push aggregator/listicle phrasing down.
    if _AGGREGATOR_RE.search(opp.title) or _AGGREGATOR_RE.search(summary):
        score -= 4.0

    return score


def prerank(items: list[Opportunity], k: int) -> list[Opportunity]:
    """Return the top `k` items most worth reading the page for (stable order)."""
    if len(items) <= k:
        return items
    keywords = _KEYWORDS
    ranked = sorted(items, key=lambda o: _score(o, keywords), reverse=True)
    return ranked[:k]
