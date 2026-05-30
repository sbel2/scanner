# scanner

Welcome to scanner — you miss every shot you don't take.

Scanner is an autonomous daily agent. It scours the web for AI events, funding, research
programs, and internships, throws out anything you're ineligible for, scores the rest
against your personal mission, and emails you a ranked shortlist every morning.

You don't configure it by hand. You **describe yourself to Claude in plain English**, and
Claude writes your config (`mission.yaml`) — your profile, search queries, eligibility
rules, and scoring context — for you.

## Setup (recommended: let Claude do it)

```bash
git clone https://github.com/sbel2/scanner.git
cd scanner
```

Open the folder in [Claude Code](https://claude.ai/download) and say **"set me up."**
Claude follows [CLAUDE.md](./CLAUDE.md): it installs dependencies, interviews you about your
mission, generates `mission.yaml`, walks you through your three API keys, and sends your first
digest — all in conversation.

Not using Claude Code? [CLAUDE_PROMPT.md](./CLAUDE_PROMPT.md) has a prompt you can paste into
any Claude chat to generate your `mission.yaml`.

## Setup (manual fallback)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scanner init                     # creates .env + mission.yaml, sets daily schedule
# fill in mission.yaml (see mission.example.yaml) and the 3 keys in .env (see .env.example)
SCANNER_DRY_RUN=1 python -m scanner run    # preview without sending
python -m scanner run --welcome            # send your first digest
```

**You need three keys** (all have free tiers — `.env.example` says where to get each):

| Key | Source | Free tier |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` (uses your Claude Pro/Max sub) | included |
| `TAVILY_API_KEY` | https://app.tavily.com/ | 1,000 searches/mo |
| `RESEND_API_KEY` | https://resend.com/ | 100 emails/day |

## Daily operation

After setup, a digest arrives every morning at 08:00 (launchd on macOS, cron on Linux —
installed by `python -m scanner init`). To change what you receive, just tell Claude
("stop sending me undergrad stuff", "add more funding queries") or edit `mission.yaml`.

---

*For the full architecture, see [DESIGN.md](./DESIGN.md).*
