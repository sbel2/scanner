# Scanner — Design

Scanner is an autonomous daily agent that discovers AI-related opportunities
(events, funding/credits, research programs, internships), filters out anything
you are ineligible for, scores the rest against your personal mission, and
emails you a ranked shortlist every morning.

This document describes how it is put together and why.

## Design goals

1. **One file to configure.** A user should be able to clone the repo, run a
   single `init` command, fill out a single `mission.yaml`, and have a
   personalized scanner running daily.
2. **No personal data in the repo.** Everything specific to a user lives in
   `mission.yaml`, `.env`, and the local SQLite database — all gitignored. The
   committed code is fully generic.
3. **Bring-your-own auth.** Scoring runs on the user's own Claude subscription
   (via a long-lived Claude Code OAuth token) or an Anthropic API key. No
   shared keys, no hosted backend.

## `mission.yaml` — the single source of truth

Rather than scattering configuration across environment variables, Python
constants, and local notes, all user-specific settings live in one YAML file:

1. **Profile** — name, role, location, and a free-form background/mission
   statement, injected directly into the LLM prompts.
2. **Alignment context** — your goals, research interests, or product pitches as
   multiline strings. These are what the scorer judges relevance against.
3. **Preferences** — geographic priorities, target categories, a natural-language
   `search_strategy` directive (the LLM generates fresh web-search queries from it
   each morning; a static `search_queries` list still works as a fallback), and
   optional calendar feeds.
4. **Settings** — email addresses, scoring weights, model selection, and digest
   size.

`mission.yaml` is gitignored; `mission.example.yaml` is the committed blank
that `init` copies for new users.

## Pipeline

```
collect → dedupe → cheap gates → prerank → ENRICH+VET (read page) → score → rank → deliver
```

1. **Collect** (`sources/`) — pulls raw opportunities from Lu.ma calendars,
   institutional ICS feeds, Devpost hackathons, and long-tail web search
   (Tavily). Each source is independent and failures are isolated.
2. **Dedupe** (`db.py` + `filters.py`) — repost/social domains are dropped, the
   same event under cosmetically different URLs/titles is collapsed, and a
   content hash per opportunity is stored in SQLite so only new or changed items
   continue.
3. **Cheap gates** (`filters.py`, `eligibility.py`) — items that already carry a
   past date are dropped deterministically, and a fast regex pass rejects
   structurally incompatible ones. No LLM, no fetch.
4. **Prerank** (`prerank.py`) — a no-LLM keyword/heuristic triage picks the most
   promising slice (`settings.enrich_candidates`, default 40) to spend a page
   read on. We only need enough confirmed-good items to fill the digest, so we
   don't read every page — this is what keeps the run fast.
5. **Enrich + vet** (`enrich.py`) — the core accuracy step. For each candidate we
   **read the real page** (Tavily Extract advanced → basic → direct HTTPS fetch,
   with retries) and, in one LLM call, extract its real date/location/deadline/
   audience *and* decide whether it has already passed and whether the user is
   eligible. A search snippet rarely contains any of this, so judging on it is
   guesswork; judging on the page is not. **Date-on-page fallback:** many event
   pages (Partiful, Luma, …) render their date in JavaScript, so the scraped text
   has the venue but no date — leaving freshness unjudgeable and stale items
   shippable. When the page yields no date, we **web-search the event** and judge
   expiry from the wider web (recap/past-tense hits ⇒ over; a concrete future date
   clears it). Pages that genuinely can't be read are dropped (an unverifiable
   item is noise) and left unmarked so a later run can retry them.
6. **Score** (`scoring.py`) — a stronger LLM grades each surviving item 0–10
   across relevance, impact, eligibility fit, geographic fit, and credits, now on
   the enriched real-page content, using a rubric built from `mission.yaml`.
7. **Rank** (`ranker.py`) — combines the alignment score with deadline urgency
   using configurable weights.
8. **Deliver** (`emailer.py`) — renders an HTML digest of the top N items and
   sends it via Resend.

**News lane (optional).** When `news` is in `preferences.categories`, informational
AI articles (papers, model launches, lab/startup announcements) are handled in a
parallel lane so they don't pollute the opportunity funnel: they're still read on
the real page, but `enrich.py`'s `_vet_news` judges **recency + on-topic** instead
of expiry/eligibility, `ranker.py` scores them on alignment alone (no urgency), and
the pipeline caps them at `settings.news_max` in a separate "Worth Reading" section.
News is lower-precision than the gated opportunity categories by nature — the cap and
`news_recency_days` window keep it from getting noisy.

## Models

The enrich/vet step is a per-candidate extract-and-judge call, so it defaults to a
small, fast model (Haiku). Scoring is lower-volume and benefits from nuance, so it
defaults to a stronger model (Sonnet). Both are overridable in `mission.yaml`.

## Storage

All state — dedup hashes, scored items, sent digests, and run logs — lives in a
single local SQLite database (`scanner.db`). There is no server component; the
database, your mission, and your keys never leave your machine except for the
LLM scoring calls (to Anthropic) and search queries (to Tavily).

## Scheduling

`init` generates a daily scheduler entry for the host OS — a `launchd` agent on
macOS or a `cron` line on Linux — that runs the pipeline each morning. The
generated scheduler file contains machine-specific paths and is gitignored.
