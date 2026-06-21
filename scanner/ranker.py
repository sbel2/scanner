from __future__ import annotations

from datetime import date

from .config import ALIGNMENT_WEIGHT, URGENCY_WEIGHT
from .models import ScoredOpportunity


def _deadline_urgency(deadline: date | None) -> float:
    if deadline is None:
        return 5.0
    days = (deadline - date.today()).days
    if days < 0:
        return 0.0
    if days <= 7:
        return 10.0
    if days <= 14:
        return 8.0
    if days <= 30:
        return 6.0
    if days <= 60:
        return 4.0
    return 2.0


def rank(items: list[ScoredOpportunity]) -> list[ScoredOpportunity]:
    for s in items:
        if s.opportunity.category == "news":
            # News has no deadline/urgency — rank it purely on how relevant the
            # article is to the user's mission.
            s.final_score = round(s.alignment.score, 2)
        else:
            urgency = _deadline_urgency(s.opportunity.deadline)
            s.final_score = round(
                s.alignment.score * ALIGNMENT_WEIGHT + urgency * URGENCY_WEIGHT, 2
            )
    return sorted(items, key=lambda s: s.final_score, reverse=True)
