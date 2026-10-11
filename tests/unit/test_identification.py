import pytest

from myne.ai.schemas import CandidateRanking, RankedCandidate
from myne.core.errors import InvalidImageError
from myne.domain.models import BagAttributes
from myne.services.contracts import IdentificationRequest
from myne.services.identification import BagIdentifier, IdentificationPolicy
from myne.services.images import ImagePreprocessor
from myne.services.progress import IdentificationStage
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

    stages: list[IdentificationStage] = []

    async def record(stage: IdentificationStage, payload: dict[str, object]) -> None:
        stages.append(stage)

    result = await _identifier(llm).identify(
        IdentificationRequest(image=jpeg_bytes, notes="bought in Paris"), progress=record
    )

    assert stages == [
        IdentificationStage.ATTRIBUTES_EXTRACTED,
        IdentificationStage.EVIDENCE_COLLECTED,
        IdentificationStage.CANDIDATES_RANKED,
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

    result = await _identifier(llm).identify(IdentificationRequest(image=jpeg_bytes))

    assert result.candidates == []
    assert result.needs_confirmation is True
    assert llm.calls == [BagAttributes]


async def test_rejects_non_image_payload() -> None:
    llm = ScriptedLLM({})
    with pytest.raises(InvalidImageError):
        await _identifier(llm).identify(IdentificationRequest(image=b"definitely not an image"))
