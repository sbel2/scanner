# scanner

You miss every shot you don't take.

**Scanner is an autonomous agent that scans for opportunities and emails your inbox every day.**

All you have to do to get started is open Claude Code in any folder and send it this message:

> Hi Claude, I'm ready to build.
> ```bash
> git clone https://github.com/sbel2/scanner.git
> cd scanner
> ```

Claude clones the repo and takes it from there.

That's it. Claude interviews you about your
mission and sends your first digest.

You'll need to generate three keys manually, and add to .env:

| Key | Source |
|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | `claude setup-token` (uses your Claude Pro/Max sub) |
| `TAVILY_API_KEY` | https://app.tavily.com/ |
| `RESEND_API_KEY` | https://resend.com/ |

## If you prefer to set up yourself. Here is what you do:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scanner init                     # creates .env + mission.yaml, sets daily schedule
# fill in mission.yaml (see mission.example.yaml) and the 3 keys in .env
python -m scanner run --welcome            # send your first digest
```

## Daily operation

After setup, a digest arrives every morning at 08:00 (launchd on macOS, cron on Linux —
installed by `python -m scanner init`). To change what you receive, just tell Claude
("stop sending me undergrad stuff", "add more funding queries") or edit `mission.yaml`.

---

*For the full architecture, see [DESIGN.md](./DESIGN.md).*
