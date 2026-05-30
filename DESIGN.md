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
3. **Preferences** — geographic priorities, target categories, explicit Tavily
   search queries, and optional calendar feeds.
4. **Settings** — email addresses, scoring weights, model selection, and digest
   size.

`mission.yaml` is gitignored; `mission.example.yaml` is the committed blank
that `init` copies for new users.

## Pipeline

```
collect → dedupe → filter (eligibility) → score (alignment) → rank → deliver
```

1. **Collect** (`sources/`) — pulls raw opportunities from Lu.ma calendars,
   institutional ICS feeds, Devpost hackathons, and long-tail web search
   (Tavily). Each source is independent and failures are isolated.
2. **Dedupe** (`db.py`) — a content hash per opportunity is stored in SQLite so
   only new or changed items are scored.
3. **Filter** (`eligibility.py`) — a fast regex pass rejects structurally
   incompatible opportunities, then a cheap LLM call checks the user's profile
   against the eligibility text.
4. **Score** (`scoring.py`) — a stronger LLM grades each eligible item 0–10
   across relevance, impact, eligibility fit, geographic fit, and credits, using
   a rubric built dynamically from `mission.yaml`.
5. **Rank** (`ranker.py`) — combines the alignment score with deadline urgency
   using configurable weights.
6. **Deliver** (`emailer.py`) — renders an HTML digest of the top N items and
   sends it via Resend.

## Models

The eligibility filter is a high-volume yes/no gate, so it defaults to a small,
fast model (Haiku). Scoring is lower-volume and benefits from nuance, so it
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
