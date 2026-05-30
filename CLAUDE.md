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

### Phase 2 — Interview the user for their mission
Ask, conversationally, for whatever you can't infer:
- **Who they are:** name, role (PhD student / founder / researcher / etc.), home city/region.
- **What they're building / their goal:** 2–4 sentences. This is the most important input.
- **What they want to find:** which of event / funding / research / internship matter.
- **Where:** preferred locations in priority order (default `Remote` if they don't care).
- **Hard disqualifiers:** anything that should ALWAYS reject an opportunity for them
  (e.g. "undergrad-only", "must be a US citizen", "PhD-graduates-only"). These become
  both natural-language `rules` and fast-path `hard_reject_patterns`.
- **Email:** a REAL inbox to receive the digest. Never leave `you@example.com` — the first
  digest sends there. Ask explicitly.

If the user gives you a single paragraph ("I'm a 2nd-year PhD building X, looking for Y"),
extract as much as you can and only ask follow-ups for what's missing.

### Phase 3 — Write `mission.yaml`
Generate the complete file from the interview. Rules:
- Fill `profile` (name, role, location, background paragraph).
- Write 2–3 `alignment` sections (e.g. "Core Mission", "Current Project") — these drive scoring.
- `preferences.locations`: priority-ordered; `preferences.categories`: the ones they chose.
- `preferences.search_queries`: **generate 15–25 specific Tavily queries.** Include the year
  (`2026`), their city, their tech stack, and intent words like "application open", "credits",
  "self-serve", "student", "travel grant". This list is what actually surfaces opportunities —
  make it good.
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

### Phase 5 — Verify, then go live
1. Dry run first (no email sent): `SCANNER_DRY_RUN=1 python -m scanner run`. Show them what
   it would have sent and sanity-check the results with them.
2. Send for real: `python -m scanner run --welcome`.
3. The daily 08:00 schedule (launchd on macOS, cron on Linux) is installed by
   `python -m scanner init`; confirm it's in place. No further action is needed after this.

---

## Tuning later (when an existing user asks for changes)
Map the request to `mission.yaml` and edit it directly — never touch code for config changes:
| User wants… | Edit |
|---|---|
| Different / more opportunities | `preferences.search_queries` |
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
