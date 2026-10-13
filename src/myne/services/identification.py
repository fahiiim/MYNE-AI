import asyncio
import logging
from collections import Counter
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from myne.ai import prompts
from myne.ai.llm import StructuredLLM
from myne.ai.schemas import CandidateRanking, RankedCandidate
from myne.core.errors import MyneError
from myne.domain.brands import brand_aliases
from myne.domain.models import (
    BagAttributes,
    BagCandidate,
    BagIdentity,
    Evidence,
    EvidenceSource,
    IdentificationResult,
)
from myne.domain.text import contains_phrase, normalize_text
from myne.integrations.google_vision import GoogleVisionClient
from myne.integrations.serpapi import SerpApiClient
from myne.integrations.serper import SerperClient
from myne.integrations.types import LensMatch, MarketListing
from myne.services.contracts import Identification, IdentificationRequest
from myne.services.images import ImagePreprocessor, PreparedImage
from myne.services.progress import AnalysisStage, ProgressCallback, emit

logger = logging.getLogger(__name__)

# Confidence multipliers applied when the LLM's claim is not backed by retrieved evidence.
_UNCITED_PENALTY = 0.6
_UNCORROBORATED_BRAND_PENALTY = 0.75
_MIN_ENTITY_SCORE = 0.4


@dataclass(frozen=True, slots=True)
class IdentificationPolicy:
    max_candidates: int = 3
    auto_confirm_confidence: float = 0.85
    auto_confirm_margin: float = 0.2
    max_evidence: int = 40
    max_lens_matches: int = 15
    max_vision_pages: int = 10
    max_web_results: int = 8


class BagIdentifier:
    """Photo -> ranked brand/model candidates.

    Pipeline: visual attribute extraction (LLM) runs concurrently with reverse-image
    retrieval (Google Vision web detection, Google Lens); a targeted web search adds
    catalog titles; the LLM then re-ranks against the numbered evidence, and the
    result is grounded by penalizing claims the evidence does not support.
    """

    def __init__(
        self,
        *,
        llm: StructuredLLM,
        preprocessor: ImagePreprocessor,
        policy: IdentificationPolicy,
        vision: GoogleVisionClient | None = None,
        serpapi: SerpApiClient | None = None,
        serper: SerperClient | None = None,
    ) -> None:
        self._llm = llm
        self._preprocessor = preprocessor
        self._policy = policy
        self._vision = vision
        self._serpapi = serpapi
        self._serper = serper

    async def identify(
        self, request: IdentificationRequest, *, progress: ProgressCallback | None = None
    ) -> Identification:
        prepared = await self._preprocessor.prepare(request.image)
        warnings = self._configuration_warnings()

        vision_task = asyncio.create_task(
            self._optional("Google Vision", self._vision_evidence(prepared), warnings)
        )
        lens_task = asyncio.create_task(
            self._optional("Google Lens", self._lens_matches(prepared, request), warnings)
        )
        try:
            attributes = await self._llm.generate(
                system=prompts.ATTRIBUTES_SYSTEM,
                prompt=prompts.attributes_prompt(request.notes),
                schema=BagAttributes,
                images=[prepared.analysis],
            )
        except BaseException:
            vision_task.cancel()
            lens_task.cancel()
            raise
        await emit(
            progress,
            AnalysisStage.ATTRIBUTES_EXTRACTED,
            {"attributes": attributes.model_dump(mode="json")},
        )
        lens_matches = (await lens_task)[: self._policy.max_lens_matches]
        retrieved = [*await vision_task, *map(self._lens_evidence, lens_matches)]
        lens_offers = tuple(
            MarketListing(
                title=match.title,
                url=match.url,
                seller=match.source,
                price=match.price,
                condition_hint=None,
            )
            for match in lens_matches
            if match.price is not None
        )

        if not attributes.is_handbag and not retrieved:
            warnings.append("The photo does not appear to show a handbag.")
            return Identification(self._result(prepared, attributes, [], warnings))

        web = await self._optional("Web search", self._web_evidence(attributes), warnings)
        evidence = self._dedupe([*retrieved, *web])[: self._policy.max_evidence]
        await emit(
            progress,
            AnalysisStage.EVIDENCE_COLLECTED,
            {"total": len(evidence), "by_source": Counter(e.source.value for e in evidence)},
        )

        ranking = await self._llm.generate(
            system=prompts.RANKING_SYSTEM.format(max_candidates=self._policy.max_candidates),
            prompt=prompts.ranking_prompt(attributes, evidence, request.notes),
            schema=CandidateRanking,
            images=[prepared.analysis],
        )
        candidates = self._ground(ranking.candidates, evidence, attributes)
        await emit(
            progress,
            AnalysisStage.CANDIDATES_RANKED,
            {"candidates": [c.model_dump(mode="json") for c in candidates]},
        )
        return Identification(self._result(prepared, attributes, candidates, warnings), lens_offers)

    async def _vision_evidence(self, prepared: PreparedImage) -> list[Evidence]:
        if self._vision is None:
            return []
        detection = await self._vision.detect(prepared.analysis.data)
        evidence = [
            Evidence(source=EvidenceSource.VISION_LABEL, title=label)
            for label in detection.best_guess_labels
        ]
        evidence += [
            Evidence(
                source=EvidenceSource.VISION_LOGO, title=f"Logo: {name}", detail=f"{score:.2f}"
            )
            for name, score in detection.logos
        ]
        evidence += [
            Evidence(source=EvidenceSource.VISION_ENTITY, title=name, detail=f"{score:.2f}")
            for name, score in detection.entities
            if score >= _MIN_ENTITY_SCORE
        ]
        evidence += [
            Evidence(source=EvidenceSource.VISION_PAGE, title=page.title, url=page.url)
            for page in detection.pages[: self._policy.max_vision_pages]
            if page.title
        ]
        return evidence

    async def _lens_matches(
        self, prepared: PreparedImage, request: IdentificationRequest
    ) -> list[LensMatch]:
        if self._serpapi is None:
            return []
        if request.image_url:
            try:
                return await self._serpapi.google_lens(
                    image_url=request.image_url, query=request.lens_query
                )
            except MyneError as exc:
                logger.info("Lens by URL failed; uploading", extra={"ctx": {"error": exc.detail}})
        image_id = await self._serpapi.upload_image(prepared.search.data, prepared.search.mime_type)
        return await self._serpapi.google_lens(image_id=image_id, query=request.lens_query)

    @staticmethod
    def _lens_evidence(match: LensMatch) -> Evidence:
        return Evidence(
            source=EvidenceSource.LENS,
            title=match.title,
            url=match.url,
            thumbnail_url=match.thumbnail_url,
            detail=match.source,
        )

    async def _web_evidence(self, attributes: BagAttributes) -> list[Evidence]:
        if self._serper is None or not attributes.brand:
            return []
        terms = (attributes.brand, attributes.model_family, attributes.material, attributes.color)
        query = " ".join(t for t in terms if t) + " bag"
        results = await self._serper.search(query, num=self._policy.max_web_results)
        return [
            Evidence(
                source=EvidenceSource.WEB_SEARCH,
                title=result.title,
                url=result.url,
                detail=result.snippet[:160] or None,
            )
            for result in results
        ]

    def _ground(
        self,
        ranked: Sequence[RankedCandidate],
        evidence: Sequence[Evidence],
        attributes: BagAttributes,
    ) -> list[BagCandidate]:
        corpus = [normalize_text(item.title) for item in evidence]
        corpus += [
            normalize_text(text) for text in (attributes.brand, *attributes.visible_text) if text
        ]

        candidates: dict[str, BagCandidate] = {}
        for item in ranked:
            try:
                identity = BagIdentity(
                    brand=item.brand,
                    model=item.model,
                    size=item.size,
                    material=item.material,
                    color=item.color,
                    hardware=item.hardware,
                )
            except ValidationError:
                logger.info("Discarding malformed candidate", extra={"ctx": {"brand": item.brand}})
                continue

            cited = [
                evidence[i] for i in dict.fromkeys(item.evidence_ids) if 0 <= i < len(evidence)
            ]
            confidence = min(max(item.confidence, 0.0), 1.0)
            if not cited:
                confidence *= _UNCITED_PENALTY
            if not self._brand_corroborated(identity.brand, corpus):
                confidence *= _UNCORROBORATED_BRAND_PENALTY

            key = identity.cache_key()
            if key not in candidates or candidates[key].confidence < confidence:
                candidates[key] = BagCandidate(
                    identity=identity,
                    confidence=round(confidence, 3),
                    rationale=item.rationale,
                    evidence=cited,
                )

        ordered = sorted(candidates.values(), key=lambda c: c.confidence, reverse=True)
        return ordered[: self._policy.max_candidates]

    @staticmethod
    def _brand_corroborated(brand: str, corpus: Sequence[str]) -> bool:
        aliases = brand_aliases(brand)
        return any(contains_phrase(text, alias) for text in corpus for alias in aliases)

    def _needs_confirmation(self, candidates: Sequence[BagCandidate]) -> bool:
        if not candidates:
            return True
        top = candidates[0].confidence
        runner_up = candidates[1].confidence if len(candidates) > 1 else 0.0
        return (
            top < self._policy.auto_confirm_confidence
            or top - runner_up < self._policy.auto_confirm_margin
        )

    def _result(
        self,
        prepared: PreparedImage,
        attributes: BagAttributes,
        candidates: list[BagCandidate],
        warnings: list[str],
    ) -> IdentificationResult:
        attributes = attributes.model_copy(
            update={"confidence": min(max(attributes.confidence, 0.0), 1.0)}
        )
        return IdentificationResult(
            image_sha256=prepared.sha256,
            attributes=attributes,
            candidates=candidates,
            needs_confirmation=self._needs_confirmation(candidates),
            warnings=warnings,
        )

    def _configuration_warnings(self) -> list[str]:
        missing = [
            name
            for name, client in (
                ("Google Vision", self._vision),
                ("Google Lens", self._serpapi),
                ("Web search", self._serper),
            )
            if client is None
        ]
        return [f"{name} is not configured; accuracy may be reduced." for name in missing]

    @staticmethod
    async def _optional[T](
        label: str, operation: Awaitable[list[T]], warnings: list[str]
    ) -> list[T]:
        try:
            return await operation
        except MyneError as exc:
            logger.warning(
                "Evidence source failed", extra={"ctx": {"source": label, "error": exc.detail}}
            )
            warnings.append(f"{label} was unavailable for this request.")
            return []

    @staticmethod
    def _dedupe(evidence: Sequence[Evidence]) -> list[Evidence]:
        seen: set[tuple[str, str | None]] = set()
        unique: list[Evidence] = []
        for item in evidence:
            key = (normalize_text(item.title), item.url)
            if key[0] and key not in seen:
                seen.add(key)
                unique.append(item)
        return unique
