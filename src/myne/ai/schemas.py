"""Structured-output contracts for LLM calls.

Kept free of defaults and numeric constraints so they are accepted by both OpenAI
strict JSON-schema mode and Gemini response schemas; values are clamped and
verified by the calling service instead.
"""

from typing import Literal

from pydantic import BaseModel


class RankedCandidate(BaseModel):
    brand: str
    model: str
    size: str | None
    material: str | None
    color: str | None
    hardware: str | None
    confidence: float
    rationale: str
    evidence_ids: list[int]


class CandidateRanking(BaseModel):
    candidates: list[RankedCandidate]


class PriceClaim(BaseModel):
    snippet_id: int
    amount: float
    currency: str
    price_type: Literal["retail", "resale"]
    as_of_month: str | None
    quote: str


class PriceClaimExtraction(BaseModel):
    claims: list[PriceClaim]
