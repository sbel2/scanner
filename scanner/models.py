from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, computed_field, field_validator

Category = Literal["event", "funding", "research", "internship", "other"]


class Opportunity(BaseModel):
    title: str
    url: str
    source: str
    category: Category = "other"
    summary: str = ""
    deadline: Optional[date] = None
    starts_at: Optional[date] = None
    location: Optional[str] = None
    eligibility_raw: Optional[str] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("title", "url", "source", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @property
    def id(self) -> str:
        key = f"{self.url.lower()}|{self.title.lower()}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        key = "|".join([
            self.title,
            self.summary,
            str(self.deadline or ""),
            str(self.starts_at or ""),
            self.location or "",
        ])
        return hashlib.sha256(key.encode()).hexdigest()[:16]


class EligibilityVerdict(BaseModel):
    eligible: Literal["yes", "no", "unclear"]
    reason: str


class AlignmentScore(BaseModel):
    score: float  # 0-10
    dim_relevance: float = 0
    dim_impact: float = 0
    dim_eligibility_fit: float = 0
    dim_geo: float = 0
    dim_credits: float = 0
    reasoning: str


class ScoredOpportunity(BaseModel):
    opportunity: Opportunity
    eligibility: EligibilityVerdict
    alignment: AlignmentScore
    final_score: float = 0.0

    @computed_field  # type: ignore[misc]
    @property
    def deadline_soon(self) -> bool:
        d = self.opportunity.deadline
        return bool(d and (d - date.today()).days <= 14)
