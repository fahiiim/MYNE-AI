from decimal import Decimal

import pytest

from myne.ai.schemas import CandidateRanking, RankedCandidate
from myne.core.errors import InvalidImageError
from myne.domain.models import BagAttributes, Money
from myne.integrations.types import LensMatch
from myne.services.contracts import IdentificationRequest
from myne.services.identification import BagIdentifier, IdentificationPolicy
from myne.services.images import ImagePreprocessor
from myne.services.progress import AnalysisStage
from tests.fakes import ScriptedLLM


def _attributes(*, brand: str | None = "Hermès", is_handbag: bool = True) -> BagAttributes:
    return BagAttributes(
        is_handbag=is_handbag,
        brand=brand,
        model_family="Birkin",
        size="30",
        material="Togo",
        color="Gold",
        hardware="Gold",
        apparent_condition="excellent",
        distinctive_features=["turn-lock", "padlock"],
        visible_text=["HERMES PARIS"],
        confidence=1.4,
    )


def _candidate(brand: str, model: str, confidence: float) -> RankedCandidate:
    return RankedCandidate(
        brand=brand,
        model=model,
        size="30",
        material=None,
        color=None,
        hardware=None,
        confidence=confidence,
        rationale="test",
        evidence_ids=[99],
    )


def _identifier(llm: ScriptedLLM) -> BagIdentifier:
    return BagIdentifier(
        llm=llm,
        preprocessor=ImagePreprocessor(max_upload_bytes=5_000_000),
        policy=IdentificationPolicy(),
    )


async def test_uncited_and_uncorroborated_candidates_are_penalized(jpeg_bytes: bytes) -> None:
    llm = ScriptedLLM(
        {
            BagAttributes: _attributes(),
            CandidateRanking: CandidateRanking(
                candidates=[
                    _candidate("Hermès", "Birkin", 0.95),
                    _candidate("Gucci", "Bamboo", 0.9),
                    _candidate("Hermes", "Birkin", 0.5),
                ]
            ),
        }
    )

    stages: list[AnalysisStage] = []

    async def record(stage: AnalysisStage, payload: dict[str, object]) -> None:
        stages.append(stage)

    outcome = await _identifier(llm).identify(
        IdentificationRequest(image=jpeg_bytes, notes="bought in Paris"), progress=record
    )
    result = outcome.result

    assert stages == [
        AnalysisStage.ATTRIBUTES_EXTRACTED,
        AnalysisStage.EVIDENCE_COLLECTED,
        AnalysisStage.CANDIDATES_RANKED,
    ]

    assert [c.identity.brand for c in result.candidates] == ["Hermès", "Gucci"]
    hermes, gucci = result.candidates
    assert hermes.confidence == pytest.approx(0.95 * 0.6)
    assert gucci.confidence == pytest.approx(0.9 * 0.6 * 0.75)
    assert result.needs_confirmation is True
    assert result.attributes.confidence == 1.0
    assert any("Google Lens is not configured" in w for w in result.warnings)


async def test_non_handbag_short_circuits_before_ranking(jpeg_bytes: bytes) -> None:
    llm = ScriptedLLM({BagAttributes: _attributes(brand=None, is_handbag=False)})

    result = (await _identifier(llm).identify(IdentificationRequest(image=jpeg_bytes))).result

    assert result.candidates == []
    assert result.needs_confirmation is True
    assert llm.calls == [BagAttributes]


class StubLens:
    def __init__(self, matches: list[LensMatch]) -> None:
        self._matches = matches
        self.lens_calls: list[dict[str, str | None]] = []

    async def upload_image(self, data: bytes, mime_type: str) -> str:
        return "image-id"

    async def google_lens(
        self,
        *,
        image_id: str | None = None,
        image_url: str | None = None,
        query: str | None = None,
    ) -> list[LensMatch]:
        self.lens_calls.append({"image_id": image_id, "image_url": image_url, "query": query})
        return self._matches


async def test_lens_matches_with_prices_become_market_offers(jpeg_bytes: bytes) -> None:
    lens = StubLens(
        [
            LensMatch(
                title="Hermès Birkin 30 Togo Gold",
                url="https://www.fashionphile.com/p/birkin-30",
                source="Fashionphile",
                thumbnail_url=None,
                price=Money(amount=Decimal("14500"), currency="USD"),
            ),
            LensMatch(
                title="Birkin street style",
                url="https://blog.example.com/birkin",
                source="Blog",
                thumbnail_url=None,
                price=None,
            ),
        ]
    )
    llm = ScriptedLLM(
        {
            BagAttributes: _attributes(),
            CandidateRanking: CandidateRanking(candidates=[_candidate("Hermès", "Birkin", 0.9)]),
        }
    )
    identifier = BagIdentifier(
        llm=llm,
        preprocessor=ImagePreprocessor(max_upload_bytes=5_000_000),
        policy=IdentificationPolicy(),
        serpapi=lens,  # type: ignore[arg-type]
    )

    outcome = await identifier.identify(
        IdentificationRequest(
            image=jpeg_bytes, image_url="https://cdn.example.com/b.jpg", lens_query="Birkin"
        )
    )

    assert lens.lens_calls == [
        {"image_id": None, "image_url": "https://cdn.example.com/b.jpg", "query": "Birkin"}
    ]
    assert [offer.seller for offer in outcome.lens_offers] == ["Fashionphile"]
    assert outcome.result.candidates[0].identity.model == "Birkin"


async def test_rejects_non_image_payload() -> None:
    llm = ScriptedLLM({})
    with pytest.raises(InvalidImageError):
        await _identifier(llm).identify(IdentificationRequest(image=b"definitely not an image"))
