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
- **What they want to find:** which of event / funding / research / internship matter.
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
- `preferences.locations`: priority-ordered; `preferences.categories`: the ones they chose.
- `preferences.search_queries`: **generate 15–25 specific Tavily queries.** Include the year
  (`2026`), their city, their tech stack, and intent words like "application open", "credits",
  "self-serve", "student", "travel grant". This list is what actually surfaces opportunities —
  make it good.
- `preferences.watch_urls`: the specific pages/orgs they named to track each run (conference
  landing pages, lab/community event pages, accelerator program pages). Leave `[]` if none.
- `eligibility.rules`: 2–5 natural-language reject rules from their disqualifiers.
- `eligibility.hard_reject_patterns`: matching case-insensitive regexes for the obvious ones
  (these skip the LLM call, so only patterns that should ALWAYS reject this specific user).
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
| Different / more opportunities | `preferences.search_queries` |
| Track a specific site / org / conference page | add it to `preferences.watch_urls` |
| Better scoring fit | `alignment` sections + `profile.background` |
| Stop seeing X | add an `eligibility.rules` entry (+ `hard_reject_patterns` if it's a clear phrase) |
| More/fewer items per email | `settings.top_n` |
| Stricter/looser cutoff | `scoring.min_score_to_send` |
| Location weighting | `preferences.locations` |

## How the code is wired (so you edit the right place)
- `scanner/config.py` — reads every key from `mission.yaml` into module constants.
- `scanner/eligibility.py` — `rules` + `hard_reject_patterns` feed the eligibility gate.
- `scanner/scoring.py` — builds the scoring rubric from `profile` + `alignment` + `locations`.
- `scanner/pipeline.py` — orchestrates collect → filter → score → rank → email.
- See `DESIGN.md` for the full architecture.

## Conventions
- Use `python3`/`pip3`, not `python`/`pip`.
- `mission.yaml` and `.env` are gitignored — they hold personal data; never commit them.
- The scoring/eligibility behaviour is mission-driven by design: change `mission.yaml`, not prompts.
