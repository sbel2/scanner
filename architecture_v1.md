# Scanner — Public Product Architecture

This document outlines the redesign of the `scanner` project from a personal, hardcoded tool into a general-purpose, open-source product.

## The Goal
To allow any user to clone the repository, run a single `init` command, fill out a single configuration file (`mission.yaml`), and immediately have a personalized autonomous AI-opportunity scanner running.

## The `mission.yaml` Concept
Instead of scattering personal context across `.env`, `config.py`, Python strings, and local Obsidian files, the system will rely on a single source of truth: `mission.yaml`.

This file will contain:
1. **User Profile**: Name, role, location, and a free-form background/mission statement.
2. **Alignment Context**: Instead of pointing to local Obsidian files, users will paste their core goals, research interests, or startup pitches directly into the YAML as multiline strings.
3. **Preferences**: Geographic preferences, target opportunity categories (events, funding, internships), and explicit search queries for Tavily.
4. **Settings**: Email addresses (to/from), model selections, and schedule preferences.

## Initialization Flow
1. User clones the repo: `git clone ... && cd scanner`
2. User runs: `python -m scanner init`
3. The `init` command:
   - Generates a heavily commented `mission.yaml` from a template.
   - Generates a `.env` file for API keys.
   - Prompts the user to fill them out.
   - (Optional) Sets up the local `launchd` or cron job based on the current OS.

## Refactoring Plan
- **`config.py`**: Rewrite to load `mission.yaml`. Remove all hardcoded `USER_PROFILE`, `ALIGNMENT_DOCS`, `TAVILY_QUERIES`, and `LUMA_CALENDAR_IDS`.
- **`scoring.py`**: Rewrite `RUBRIC` to be dynamic based on the user's `mission.yaml` goals rather than hardcoded MyStartup/ProjectA/Boston logic.
- **`eligibility.py`**: Make the LLM prompt use the dynamic `mission.yaml` profile. Keep standard hard-reject patterns but allow user overrides.
- **`sources/tavily.py`**: Read queries directly from `mission.yaml`.
- **`.env`**: Add `ANTHROPIC_API_KEY` to support standard SDK usage if `claude-agent-sdk` requires it, or document the `claude` CLI login requirement clearly.

## Configuration Schema

```yaml
profile:
  name: ""
  role: ""
  location: ""
  background: |
    Write a paragraph about who you are and what you are building.
  
alignment:
  - title: "Core Mission"
    content: |
      What are you trying to achieve?
  - title: "Current Project"
    content: |
      Details about your startup or research.

preferences:
  locations:
    - "San Francisco, CA"
    - "Remote"
  categories:
    - event
    - funding
    - internship
  search_queries:
    - "AI hackathon San Francisco 2026"
    - "AI startup accelerator application open"

settings:
  email_to: "you@example.com"
  email_from: "onboarding@resend.dev"
  top_n: 8
```
