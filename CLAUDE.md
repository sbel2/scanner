# Scanner — Setup & Operating Guide for Claude

Scanner is an autonomous daily agent that finds AI opportunities (events, funding,
research, internships), filters out anything the user is ineligible for, scores the
rest against their personal mission, and emails a ranked digest every morning.

**Everything user-specific lives in one file: `mission.yaml`.** Secrets live in `.env`.
Your job is to set both up through a natural conversation, then get the first digest sent.

---

## Initialization trigger

When the user says **"Hi Claude, I'm ready to build."** — the kickoff command from the
README — begin onboarding immediately. Treat any equivalent ("set me up", "let's build my
scanner") the same way. This phrase is the canonical signal to start Phase 1 below.

Drive the whole onboarding as a conversation. Do NOT make the user hand-edit YAML.
Work through these phases in order. Keep each step short; ask one cluster of questions
at a time.

### Phase 1 — Install
1. Confirm Python 3.11+ (`python3 --version`).
2. Create a venv and install deps if not already done:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   ```
3. Run `python -m scanner init` once — it copies `.env.example` → `.env` and
   `mission.example.yaml` → `mission.yaml` and prints key-setup guidance. (It's safe to
   re-run; it skips files that already exist.)

### Phase 2 — Let the user tell their story, then fill gaps
**Open with ONE warm, open-ended prompt and let them write freely.** Do NOT present
multiple-choice or checkbox questions, and do NOT march them through a Q&A survey — that
flattens the mission, which is the single most important input. Invite a long-form answer,
e.g.:

> "Tell me your story. What are you building or working toward, and what kind of
> opportunities would actually move the needle for you? Write as much or as little as you
> like — a paragraph or three is perfect. I'll pull out the details and ask about anything
> I'm still missing."

Most of what you need is usually in that paragraph. **Parse it first**, then ask brief,
targeted follow-ups ONLY for the facts they didn't cover. The facts you ultimately need:
- **Who they are:** name, role (PhD student / founder / researcher / etc.), home city/region.
- **What they're building / their goal:** the 2–4 sentence core mission (usually already in
  their story — this is the most important input).
- **What they want to find:** which of event / funding / research / internship matter — and
  whether they also want **news** (informational AI articles/papers/announcements to read,
  not opportunities to act on). News is opt-in; only add the `news` category if they say they
  want a "what's happening in AI" reading section, since it's lower-precision than the gated
  opportunity categories.
- **Specific sites or orgs to track:** ALWAYS ask this explicitly — most people have a few
  in mind (a favourite conference's page, a lab/org events page, an accelerator, a local
  community group like an AI Tinkerers chapter). These become `preferences.watch_urls`,
  which get scraped every run for opportunities that keyword search and calendars miss.
  Optional — fine to leave empty if they truly have none, but prompt for it; don't skip it.
- **Where:** preferred locations in priority order (default `Remote` if they don't care).
- **Hard disqualifiers:** anything that should ALWAYS reject an opportunity for them
  (e.g. "undergrad-only", "must be a US citizen", "PhD-graduates-only"). These become
  both natural-language `rules` and fast-path `hard_reject_patterns`.
- **Email:** a REAL inbox to receive the digest. Never leave `you@example.com` — the first
  digest sends there. Ask explicitly if it isn't in their story.

When you do need to follow up, ask in prose (a short clustered question is fine) — still no
multiple-choice menus. Keep it to one round of follow-ups if you can.

### Phase 3 — Write `mission.yaml`
Generate the complete file from the interview. Rules:
- Fill `profile` (name, role, location, background paragraph).
- Write 2–3 `alignment` sections (e.g. "Core Mission", "Current Project") — these drive scoring.
- `preferences.locations`: priority-ordered; `preferences.categories`: the ones they chose
  (include `news` ONLY if they asked for a reading section — see below).
- **Balance the buckets in `search_strategy`:** near-term local events drain fastest, so don't
  let them eat the whole query budget — explicitly reserve queries for the evergreen categories
  the user chose (internships, fellowships, funding, research), which refill steadily and keep
  the digest from going empty on quiet days. If `news` is enabled, add ~2 news queries aimed at
  real publications/lab blogs (phrased as news searches, not "apply").
- `preferences.search_strategy`: **write a natural-language search directive, NOT a fixed
  query list.** The scanner reads this every morning and has the LLM generate a fresh,
  exploratory batch of queries from it + that day's date — so signals stay varied instead of
  repeating the same terms daily. Brief it like a research assistant: state their priorities
  in order (most important first), name the real event surfaces to hit (lu.ma, partiful,
  eventbrite, devpost, their key org/university domains), give concrete local anchors
  (neighborhoods, venues, labs, community chapters), and tell it to AVOID aggregator/listicle
  phrasings ("discover events", "top 25...", "best ... 2026"). Encourage a few queries that
  explore angles the user didn't explicitly name. See `mission.example.yaml` for the shape.
  (Backward-compatible: a `search_queries:` list still works as a fallback if `search_strategy`
  is absent, but prefer the directive.)
- `preferences.watch_urls`: the specific pages/orgs they named to track each run (conference
  landing pages, lab/community event pages, accelerator program pages). Leave `[]` if none.
- `eligibility.rules`: 2–5 natural-language reject rules from their disqualifiers. Note that
  **location is already enforced automatically** — the eligibility check is handed
  `preferences.locations` and rejects in-person events outside them unless remote/virtual, so
  you don't need a generic geo rule. Add one only to make it explicit or stricter (e.g. a user
  who will NEVER travel). Likewise the check already drops items it can tell are past; add an
  explicit "reject expired" rule if they're date-sensitive.
- `eligibility.hard_reject_patterns`: matching case-insensitive regexes for the obvious ones
  (these skip the LLM call, so only patterns that should ALWAYS reject this specific user).
  Avoid broad patterns like a bare city name — they can silently drop legitimately-remote
  opportunities; lean on the LLM rules for nuanced cases like location.
- `email.to`: the real address they gave you. Leave `email.from` as `onboarding@resend.dev`
  unless they have a verified Resend domain.
- Leave `scoring` and `settings` at defaults unless they ask.

Keep the structure and key names exactly as in `mission.example.yaml` (config.py reads these
exact keys). After writing, show the user a plain-language summary of what you configured and
let them correct it.

### Phase 4 — Keys
Walk them through `.env` (open `.env.example` for the canonical instructions):
- **Claude auth:** `claude setup-token` → paste into `CLAUDE_CODE_OAUTH_TOKEN` (uses their
  Pro/Max subscription, no API billing). Do NOT set `ANTHROPIC_API_KEY` unless they have no
  subscription.
- **Tavily:** free key from https://app.tavily.com/ → `TAVILY_API_KEY`.
- **Resend:** free key from https://resend.com/ → `RESEND_API_KEY`.
Confirm each is filled before moving on.

### Phase 5 — Go live
1. **Once all API keys are present, go straight to a real, fun welcome send:**
   `python -m scanner run --welcome`. Don't gate on a dry run — the user wants the first
   digest to actually land in their inbox as a celebratory "Scanner is live" moment. Make
   it feel like one (warm framing in your message; the `--welcome` flag already gives the
   email its welcome treatment).
2. **Watch the run and address any issues as they come up** — if the send errors (bad key,
   Resend domain, empty results, etc.), diagnose it, fix it, and re-run until the welcome
   email genuinely lands. Don't hand the user a broken first impression.
3. Fall back to the dry run (`SCANNER_DRY_RUN=1 python -m scanner run`) ONLY when keys are
   still missing/placeholder, or if the user explicitly wants a no-send preview first.
4. The daily 08:00 schedule (launchd on macOS, cron on Linux) is installed by
   `python -m scanner init`; confirm it's in place. No further action is needed after this.

---

## Tuning later (when an existing user asks for changes)
Map the request to `mission.yaml` and edit it directly — never touch code for config changes:
| User wants… | Edit |
|---|---|
| Different / more opportunities | `preferences.search_strategy` (the morning query-generation directive) |
| Track a specific site / org / conference page | add it to `preferences.watch_urls` |
| Better scoring fit | `alignment` sections + `profile.background` |
| Stop seeing X | add an `eligibility.rules` entry (+ `hard_reject_patterns` if it's a clear phrase) |
| More/fewer items per email | `settings.top_n` |
| Stricter/looser cutoff | `scoring.min_score_to_send` |
| Location weighting | `preferences.locations` |
| Read more/fewer pages per run (recall vs. speed) | `settings.enrich_candidates` (default 40) |
| Add / remove an AI news reading section | add/remove `news` in `preferences.categories` |
| More/fewer news items, or how fresh they must be | `settings.news_max` (default 3) / `settings.news_recency_days` (default 14) |

## How the code is wired (so you edit the right place)
- `scanner/config.py` — reads every key from `mission.yaml` into module constants.
- `scanner/eligibility.py` — `hard_reject_patterns` feed the fast regex pre-gate
  (`rule_based_reject`); `rules` are injected into the page-vet prompt.
- `scanner/prerank.py` — cheap no-LLM triage that picks which candidates get a page read.
- `scanner/enrich.py` — the accuracy core: reads each candidate's REAL page (robust
  fetch with fallbacks) and in one LLM call extracts date/location/audience AND judges
  freshness + eligibility. `rules` + `locations` + `profile` shape its prompt. When the
  page exposes no date (JS-rendered Partiful/Luma pages), it falls back to a web search to
  verify whether the event is upcoming or already past before the item can ship. Items in the
  `news` category take a separate branch (`_vet_news`) that still reads the page but judges
  recency + on-topic instead of expiry/eligibility — news is informational, not an opportunity.
- News lane wiring: `sources/tavily.py` classifies articles as `news` (publication domain /
  news-verb headline, unless an event/apply signal overrides); `ranker.py` scores news on
  alignment only (no urgency); `pipeline.py` caps it to `news_max` in a separate lane so it
  never displaces opportunities; `emailer.py` renders it in a "Worth Reading" section.
- `scanner/scoring.py` — builds the scoring rubric from `profile` + `alignment` + `locations`;
  scores the enriched (real-page) opportunity.
- `scanner/pipeline.py` — orchestrates collect → cheap gates → prerank → enrich/vet →
  score → rank → email.
- See `DESIGN.md` for the full architecture.

## Why the pipeline reads pages (do not regress this)
The decisive design choice is that freshness, eligibility, and scoring all run on the
opportunity's **actual page content**, not the search snippet. Snippets almost never
contain the date/location/audience, so snippet-based judging silently shipped stale and
ineligible items (everything came back "unclear" and "unclear" was allowed through). If a
future change moves judgement back onto snippets to "save calls," it will reintroduce that
bug — keep the read-the-page-then-judge order, and tune cost via `enrich_candidates`, not
by skipping the read.

## Conventions
- Use `python3`/`pip3`, not `python`/`pip`.
- `mission.yaml` and `.env` are gitignored — they hold personal data; never commit them.
- The scoring/eligibility behaviour is mission-driven by design: change `mission.yaml`, not prompts.
