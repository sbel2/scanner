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

### 1. Clone and Install
```bash
git clone https://github.com/sbel2/scanner.git
cd scanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Initialize
Run the setup wizard. This will generate your `mission.yaml` and `.env` files, and (on macOS) set up your daily background schedule.
```bash
python -m scanner init
```

### 3. Configure
1. **API Keys:** Open `.env` and paste your keys. You will need:
   - **Anthropic:** https://console.anthropic.com/
   - **Tavily:** https://app.tavily.com/ (1,000 free searches/month)
   - **Resend:** https://resend.com/ (free tier; use `onboarding@resend.dev` as sender to skip domain verification)
2. **Mission File:** Open `mission.yaml` and fill out your profile, background, alignment context, and search queries. This is the single source of truth for the scanner.

### 4. Test
Run a dry-run to see what the scanner finds without sending an email:
```bash
SCANNER_DRY_RUN=1 python -m scanner run
```

### 5. Run
```bash
python -m scanner run
```

*(If you used `python -m scanner init`, the scanner is already scheduled to run daily at 08:00 in the background.)*

---

## Architecture & Storage

- **Single file state:** All state (deduplication hashes, scored items, sent digests, run logs) is stored locally in a single SQLite database (`scanner.db`).
- **Cost:** At typical volumes (~150 candidates/day), the LLM cost is roughly $0.20–0.50/day.
- **Privacy:** Your `mission.yaml` and `.env` are ignored by git. Your data stays on your machine and is only sent to the LLM providers (Anthropic) for scoring.

For full design details, see [architecture_v1.md](architecture_v1.md).
