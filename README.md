# Scanner

Scanner is an autonomous, daily AI-opportunity agent. It scours the internet for events, funding, research programs, and internships, filters out anything you are ineligible for, scores the rest against your personal mission, and emails you a ranked shortlist every morning.

Instead of generic newsletters, Scanner acts like a personal chief of staff. You write a single `mission.yaml` file describing who you are and what you are building, and Scanner dynamically builds its scoring rubric around your exact goals.

## How it works

1. **Collect:** Pulls raw opportunities from Lu.ma calendars, institutional ICS feeds, Devpost hackathons, and long-tail web search (Tavily).
2. **Filter:** Rejects opportunities you aren't eligible for using a fast regex pass and a Claude Haiku check against your profile.
3. **Score:** Grades each eligible opportunity (0–10) across relevance, impact, geographic fit, and credits using Claude Sonnet.
4. **Rank:** Combines the alignment score with deadline urgency.
5. **Deliver:** Sends a beautiful HTML digest of the top N items to your inbox.

---

## Quickstart

### 1. Prerequisites

Scanner uses **Claude Code** for LLM scoring. If you don't have it yet:

- Install Claude Code: https://claude.ai/download
- You need a **Claude Pro or Max** subscription.

### 2. Clone and Install

```bash
git clone https://github.com/sbel2/scanner.git
cd scanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Initialize

Run the setup wizard. It will generate your `mission.yaml` and `.env` files, walk you through Claude auth, set up your daily background schedule, and — once all keys are filled in — **automatically send your first digest**.

```bash
python -m scanner init
```

### 4. Get Your Claude Token

Scanner uses a **long-lived OAuth token** from Claude Code — no separate API billing. This token is tied to your Claude Pro/Max subscription and lasts 1 year.

```bash
claude setup-token
```

Copy the token it prints and paste it into your `.env` file:

```
CLAUDE_CODE_OAUTH_TOKEN=<your token here>
```

> **Why this approach?** `claude setup-token` generates a token specifically designed for automated, headless use. It draws from your existing subscription rather than pay-per-token API billing.

### 5. Get Your Other API Keys

You also need two more keys (both have free tiers):

| Key | Where to get it | Free tier |
|---|---|---|
| `TAVILY_API_KEY` | https://app.tavily.com/ | 1,000 searches/month |
| `RESEND_API_KEY` | https://resend.com/ | 100 emails/day |

Paste them into your `.env` file alongside the Claude token.

> **Tip:** Use `onboarding@resend.dev` as your `EMAIL_FROM` to skip domain verification on Resend.

### 6. Configure Your Mission

Open `mission.yaml` and fill it out. This is the single file that controls everything — your profile, what you are building, your location preferences, and the search queries Scanner runs every day.

### 7. You're done

Once `python -m scanner init` detects that all keys are filled in and `mission.yaml` has been completed, it fires the first real scan automatically and sends your first digest. That email includes a welcome note explaining that future digests will arrive every morning at 08:00 without any further action from you.

If you want to test without sending an email first:

```bash
SCANNER_DRY_RUN=1 python -m scanner run
```

To trigger a send manually at any time:

```bash
python -m scanner run
```

---

## Architecture & Storage

- **Single file state:** All state (deduplication hashes, scored items, sent digests, run logs) is stored locally in a single SQLite database (`scanner.db`).
- **Cost:** The Claude token draws from your subscription. Tavily costs ~$0.15/day at typical query volumes. Resend is free.
- **Privacy:** Your `mission.yaml` and `.env` are ignored by git. Your data stays on your machine and is only sent to Anthropic (for scoring) and Tavily (for search).

For full design details, see [architecture_v1.md](architecture_v1.md).

---

## Tuning

| What to change | Where |
|---|---|
| Search queries | `preferences.search_queries` in `mission.yaml` |
| Scoring rubric context | `alignment` sections in `mission.yaml` |
| Minimum score threshold | `scoring.min_score_to_send` in `mission.yaml` |
| Top N results per digest | `settings.top_n` in `mission.yaml` |
| Geographic preferences | `preferences.locations` in `mission.yaml` |
