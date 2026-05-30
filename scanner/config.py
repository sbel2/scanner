"""
config.py — loads all runtime configuration from mission.yaml + .env.

The mission.yaml file is the single source of truth for user-specific settings.
API keys and secrets are loaded from .env.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# ---------------------------------------------------------------------------
# API keys (from .env only — never put secrets in mission.yaml)
# ---------------------------------------------------------------------------
TAVILY_API_KEY: str = os.environ.get("TAVILY_API_KEY", "")
RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# Runtime flags (env-var overrides still work)
# ---------------------------------------------------------------------------
DRY_RUN: bool = os.environ.get("SCANNER_DRY_RUN", "0") == "1"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DB_PATH = ROOT / "scanner.db"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

MISSION_FILE = ROOT / "mission.yaml"


def _load_mission() -> dict[str, Any]:
    """Load and parse mission.yaml. Exit with a helpful message if missing."""
    if not MISSION_FILE.exists():
        print(
            "[scanner] ERROR: mission.yaml not found.\n"
            "          Run `python -m scanner init` to set up your scanner.",
            file=sys.stderr,
        )
        sys.exit(1)
    with MISSION_FILE.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        print("[scanner] ERROR: mission.yaml is empty. Please fill it out.", file=sys.stderr)
        sys.exit(1)
    return data


_mission: dict[str, Any] = _load_mission()

# ---------------------------------------------------------------------------
# User profile — built from mission.yaml
# ---------------------------------------------------------------------------
_profile = _mission.get("profile", {})
_name = _profile.get("name", "the user")
_role = _profile.get("role", "")
_location = _profile.get("location", "")
_background = _profile.get("background", "").strip()

# Build the USER_PROFILE string injected into LLM prompts
USER_PROFILE: str = f"""\
Name: {_name}
Role: {_role}
Location: {_location}

{_background}
""".strip()

# ---------------------------------------------------------------------------
# Alignment context — built from mission.yaml alignment sections
# ---------------------------------------------------------------------------
_alignment_sections = _mission.get("alignment", [])


def build_alignment_context() -> str:
    """Return the full alignment context string for the scoring prompt."""
    parts = []
    for section in _alignment_sections:
        title = section.get("title", "Untitled")
        content = section.get("content", "").strip()
        parts.append(f"## {title}\n{content}")
    return "\n\n".join(parts)


ALIGNMENT_CONTEXT: str = build_alignment_context()

# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
_prefs = _mission.get("preferences", {})

PREFERRED_LOCATIONS: list[str] = _prefs.get("locations", [])
PREFERRED_CATEGORIES: list[str] = _prefs.get("categories", ["event", "funding", "research", "internship"])
TAVILY_QUERIES: list[str] = _prefs.get("search_queries", [])
LUMA_CALENDAR_IDS: list[str] = _prefs.get("luma_calendar_ids", [])
ICAL_FEEDS: list[dict] = _prefs.get("ical_feeds", [])

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------
_scoring = _mission.get("scoring", {})
ALIGNMENT_WEIGHT: float = float(_scoring.get("alignment_weight", 0.7))
URGENCY_WEIGHT: float = float(_scoring.get("urgency_weight", 0.3))
MIN_SCORE_TO_SEND: float = float(_scoring.get("min_score_to_send", 4.0))

# ---------------------------------------------------------------------------
# Email settings
# ---------------------------------------------------------------------------
_email = _mission.get("email", {})
EMAIL_TO: str = os.environ.get("EMAIL_TO") or _email.get("to", "")
EMAIL_FROM: str = os.environ.get("EMAIL_FROM") or _email.get("from", "onboarding@resend.dev")

# ---------------------------------------------------------------------------
# Runtime settings
# ---------------------------------------------------------------------------
_settings = _mission.get("settings", {})
TOP_N: int = int(os.environ.get("SCANNER_TOP_N") or _settings.get("top_n", 8))
MODEL_SCORE: str = _settings.get("model_score", "claude-sonnet-4-6")
MODEL_FILTER: str = _settings.get("model_filter", "claude-haiku-4-5-20251001")
