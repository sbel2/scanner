"""
scoring.py — LLM-based alignment scorer.

The scoring rubric is built dynamically from the user's mission.yaml so that
every dimension reflects their actual goals, not hardcoded personal details.
"""
from __future__ import annotations

import json
import re

from .config import ALIGNMENT_CONTEXT, MODEL_SCORE, PREFERRED_LOCATIONS, USER_PROFILE
from .llm import complete
from .models import AlignmentScore, Opportunity


def _build_geo_rubric(locations: list[str]) -> str:
    """Build the geo dimension description from the user's preferred locations."""
    if not locations:
        return (
            "- geo: geographic fit. Score higher for in-person opportunities in the user's "
            "preferred locations, lower for remote or distant locations."
        )
    lines = ["- geo: geographic fit based on the user's location preferences (high → low):"]
    scores = [
        (10, 9),
        (8, 7),
        (6, 5),
        (4, 3),
    ]
    for i, loc in enumerate(locations):
        lo, hi = scores[i] if i < len(scores) else (2, 1)
        lines.append(f"  * {loc}: {lo}–{hi}")
    lines.append("  * Remote / online: 3–5 (acceptable for high-value opportunities)")
    lines.append("  * Other locations not listed: 1–4")
    return "\n".join(lines)


def _build_rubric() -> str:
    geo_rubric = _build_geo_rubric(PREFERRED_LOCATIONS)
    return f"""\
Score the opportunity on a 0–10 scale on each of these dimensions, then return an overall score (also 0–10).

DIMENSIONS:
- relevance: how directly relevant is this opportunity to the user's stated mission, projects, and goals?
  Score 9–10 only if it is a clear, actionable fit. Score 1–3 if it is only tangentially related.
- impact: how much could this opportunity accelerate the user's work? Consider: credits/resources provided,
  network access, learning, visibility, or funding.
- eligibility_fit: how well does the user's profile match the typical target audience of this opportunity?
  Score 9–10 if it is clearly designed for someone like them. Score 1–3 if it is a stretch.
{geo_rubric}
- credits: does this opportunity provide AI compute credits or cloud resources?
  Self-serve programs (no referral required) score high. Partner-gated or VC-referral-required programs
  score low even if the credits would be valuable.

OVERALL: a 0–10 weighted intuition combining the above. Strong overall scores (>=7) require the
opportunity to be a clear, actionable fit for the user based on their mission and profile.

Return STRICT JSON ONLY in this shape:
{{
  "score": <0-10 float>,
  "dim_relevance": <0-10 float>,
  "dim_impact": <0-10 float>,
  "dim_eligibility_fit": <0-10 float>,
  "dim_geo": <0-10 float>,
  "dim_credits": <0-10 float>,
  "reasoning": "<one or two short sentences explaining the score>"
}}
"""


RUBRIC: str = _build_rubric()


def _build_system_prompt() -> str:
    return (
        "# CANDIDATE PROFILE\n"
        + USER_PROFILE
        + "\n\n# ALIGNMENT CONTEXT\n"
        + ALIGNMENT_CONTEXT
        + "\n\n# SCORING RUBRIC\n"
        + RUBRIC
    )


class AlignmentScorer:
    def __init__(self):
        self._system = _build_system_prompt()

    def score(self, opp: Opportunity) -> AlignmentScore:
        user_msg = (
            f"TITLE: {opp.title}\n"
            f"CATEGORY: {opp.category}\n"
            f"LOCATION: {opp.location or '(unspecified)'}\n"
            f"DEADLINE: {opp.deadline.isoformat() if opp.deadline else '(unspecified)'}\n"
            f"SUMMARY: {opp.summary}\n"
            f"URL: {opp.url}\n\n"
            "Score this opportunity using the rubric above. Return JSON only."
        )
        try:
            text = complete(self._system, user_msg, MODEL_SCORE)
            data = json.loads(_extract_json(text))
            return AlignmentScore(
                score=float(data["score"]),
                dim_agents=float(data.get("dim_relevance", data.get("dim_agents", 0))),
                dim_research=float(data.get("dim_impact", data.get("dim_research", 0))),
                dim_founder=float(data.get("dim_eligibility_fit", data.get("dim_founder", 0))),
                dim_geo=float(data.get("dim_geo", 0)),
                dim_credits=float(data.get("dim_credits", 0)),
                reasoning=str(data.get("reasoning", "")),
            )
        except Exception as e:
            return AlignmentScore(score=0.0, reasoning=f"scoring failed: {e}")


def _extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text
