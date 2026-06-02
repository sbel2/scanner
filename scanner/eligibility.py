"""
eligibility.py — two-stage eligibility filter.

Stage 1: optional, user-supplied regex pre-filter (mission.yaml).
Stage 2: profile-aware LLM check using the user's profile from mission.yaml.

Stage 1 defaults to empty because every audience constraint is relative to the
user (e.g. "undergraduate only" excludes a PhD applicant but is exactly what an
undergrad wants). Stage 2 is what generalizes; Stage 1 is just a fast, optional
shortcut for rejects that always apply to a specific user.
"""
from __future__ import annotations

import json
import re
from datetime import date

from .config import ELIGIBILITY_RULES, HARD_REJECT_PATTERNS, MODEL_FILTER, USER_PROFILE
from .llm import complete
from .models import EligibilityVerdict, Opportunity


def rule_based_reject(opp: Opportunity) -> tuple[bool, str]:
    blob = " ".join(filter(None, [opp.title, opp.summary, opp.eligibility_raw or ""])).lower()
    for pat in HARD_REJECT_PATTERNS:
        if re.search(pat, blob):
            return True, f"matched hard-reject pattern: {pat}"
    return False, ""


def _build_system_prompt() -> str:
    # Mission-specific rejection rules are appended to (not a replacement for) the
    # base yes/no/unclear contract, so the JSON answer set is always well defined.
    custom_rules = ""
    if ELIGIBILITY_RULES:
        rules_list = "\n".join(f"- {rule}" for rule in ELIGIBILITY_RULES)
        custom_rules = (
            '\n\nAdditional rejection rules specific to this candidate '
            '(answer "no" if any apply):\n'
            f"{rules_list}"
        )
    return f"""You evaluate whether a specific candidate is eligible for an opportunity.

CANDIDATE PROFILE:
{USER_PROFILE}

You will receive an opportunity title, summary, and any eligibility text.
Return strict JSON: {{"eligible": "yes" | "no" | "unclear", "reason": "<one short sentence>"}}.

Rules:
- "no" only if the opportunity explicitly excludes this candidate (e.g. undergrad-only,
  must be graduating in <12 months, citizenship/residency mismatch, age cap, role mismatch).
- "unclear" if eligibility text is missing or ambiguous.
- "yes" if there is positive evidence the candidate qualifies, OR the opportunity is broadly
  open and nothing in the text excludes them.{custom_rules}
Output ONLY the JSON object, no prose.
"""


def llm_eligibility(opp: Opportunity) -> EligibilityVerdict:
    system = _build_system_prompt()
    user_msg = (
        f"TODAY'S DATE: {date.today().isoformat()}\n"
        f"TITLE: {opp.title}\n"
        f"CATEGORY: {opp.category}\n"
        f"SUMMARY: {opp.summary}\n"
        f"ELIGIBILITY_RAW: {opp.eligibility_raw or '(none provided)'}\n"
        "If the text shows the event has already happened or the application "
        'deadline has passed relative to today, answer "no".'
    )
    try:
        text = complete(system, user_msg, MODEL_FILTER)
        data = json.loads(_extract_json(text))
        return EligibilityVerdict(eligible=data["eligible"], reason=data["reason"])
    except Exception as e:
        return EligibilityVerdict(eligible="unclear", reason=f"eligibility check failed: {e}")


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def check(opp: Opportunity) -> EligibilityVerdict:
    rejected, reason = rule_based_reject(opp)
    if rejected:
        return EligibilityVerdict(eligible="no", reason=reason)
    return llm_eligibility(opp)
