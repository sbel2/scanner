# One-Prompt Setup for Scanner

There are two ways to set up Scanner. Both are a normal conversation — you describe
yourself, Claude does the configuration.

---

## Option A — Inside Claude Code (recommended)

1. Clone the repo and open the folder in Claude Code:
   ```bash
   git clone https://github.com/sbel2/scanner.git
   cd scanner
   ```
2. Tell Claude: **"Set me up."**

Claude will read `CLAUDE.md`, install dependencies, interview you about your mission,
write your `mission.yaml`, walk you through your API keys, and send your first digest —
all in conversation. You never hand-edit YAML.

---

## Option B — Plain Claude (claude.ai chat)

If you're not using Claude Code, paste the prompt below into a Claude chat. It generates
your `mission.yaml`; you then save it and run two commands.

---

I want to set up "scanner", an automated opportunity-discovery agent. Interview me, then
generate a complete `mission.yaml`.

**About me:** [Describe yourself in a sentence or two — e.g. "I'm a 2nd-year AI PhD student
in Boston building an agent framework, looking for research internships, hackathons with
compute credits, and pre-seed funding that doesn't require a VC referral."]

Based on that, ask me for anything you still need (real email address for the digest,
preferred locations, hard disqualifiers), then produce a `mission.yaml` following these rules:

1. **profile** — my name, role, location, and a 2–4 sentence background paragraph.
2. **alignment** — 2–3 sections (e.g. "Core Mission", "Current Project") summarizing my goals.
   These drive scoring, so make them specific.
3. **preferences**
   - `locations`: priority-ordered (default `["Remote"]` if I don't care).
   - `categories`: any of event / funding / research / internship that apply.
   - `search_queries`: **15–25 specific Tavily queries.** Include `2026`, my city, my tech
     stack, and intent words like "application open", "credits", "self-serve", "student".
4. **eligibility**
   - `rules`: 2–5 natural-language reject rules (e.g. "Reject if undergrad-only",
     "Reject if it requires US citizenship and I'm not a citizen").
   - `hard_reject_patterns`: matching case-insensitive regexes for the obvious phrases
     (e.g. `undergrad(uate)? (only|students only)`).
5. **email** — `to:` must be a REAL inbox I give you (never `you@example.com`);
   `from:` stays `onboarding@resend.dev`.
6. Leave `scoring` and `settings` at their defaults.

Return ONLY the YAML block, using the exact key names from `mission.example.yaml`.

---

**After Claude returns the YAML:**
```bash
git clone https://github.com/sbel2/scanner.git && cd scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scanner init          # creates .env + mission.yaml, prints key setup
# 1) paste the generated YAML into mission.yaml (overwrite the template)
# 2) fill in the 3 keys in .env  (see .env.example for where to get them)
SCANNER_DRY_RUN=1 python -m scanner run   # preview without sending
python -m scanner run --welcome           # send your first digest
```
