import json
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import ValidationError

from myne.core.errors import InvalidRequestError
from myne.domain.brands import brand_aliases
from myne.domain.market import normalize_condition
from myne.domain.models import (
    AnalysisInput,
    AnalysisMode,
    BagAnalysis,
    BagIdentity,
    Condition,
    IdentificationResult,
    PriceReport,
    Valuation,
)
from myne.domain.text import normalize_text
from myne.domain.valuation import build_valuation
from myne.services.contracts import (
    BagIdentificationService,
    Identification,
    IdentificationRequest,
    ImageSource,
    PriceReportService,
)
from myne.services.progress import AnalysisStage, ProgressCallback, emit

_MAX_CONTEXT_CHARS = 2000
LENS_SOURCE = "google_lens"


class BagAnalysisService:
    """Single entry point: identify the bag (if a photo is given), then price and value it."""

    def __init__(
        self,
        *,
        images: ImageSource,
        identifier: BagIdentificationService,
        prices: PriceReportService,
        default_currency: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._images = images
        self._identifier = identifier
        self._prices = prices
        self._default_currency = default_currency
        self._clock = clock

    async def analyze(
        self, request: AnalysisInput, *, progress: ProgressCallback | None = None
    ) -> BagAnalysis:
        currency = request.currency or self._default_currency
        warnings: list[str] = []
        identification = await self._identify(request, progress) if request.image_url else None

        bag = self._bag(request, identification, warnings)
        report: PriceReport | None = None
        valuation: Valuation | None = None
        if bag is None:
            warnings.append(
                "The bag could not be identified; provide `brand` and `model` to price it."
            )
        else:
            await emit(
                progress, AnalysisStage.PRICING_STARTED, {"bag": bag.model_dump(mode="json")}
            )
            lens_offers = identification.lens_offers if identification else ()
            report = await self._prices.report(
                bag,
                currency=currency,
                search_query=request.search_query,
                extra_listings={LENS_SOURCE: lens_offers} if lens_offers else None,
            )
            await emit(
                progress,
                AnalysisStage.PRICING_COMPLETED,
                {"sources": [s.model_dump(mode="json") for s in report.sources]},
            )
            valuation = build_valuation(
                report, self._condition(request, identification), request.purchase_price
            )

        return BagAnalysis(
            mode=self._mode(request),
            user_id=request.user_id,
            currency=currency,
            generated_at=report.generated_at if report else self._clock(),
            input=request,
            bag=bag,
            identification=identification.result if identification else None,
            valuation=valuation,
            market_prices=report.current if report else [],
            price_history=report.history if report else [],
            sources=report.sources if report else [],
            warnings=[*warnings, *(report.warnings if report else [])],
        )

    async def identify(
        self,
        image_url: str,
        *,
        search_query: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> IdentificationResult:
        request = AnalysisInput(image_url=image_url, search_query=search_query)
        return (await self._identify(request, progress)).result

    async def _identify(
        self, request: AnalysisInput, progress: ProgressCallback | None
    ) -> Identification:
        assert request.image_url is not None
        image = await self._images.fetch(request.image_url)
        await emit(progress, AnalysisStage.IMAGE_FETCHED, {"bytes": len(image)})
        return await self._identifier.identify(
            IdentificationRequest(
                image=image,
                image_url=request.image_url,
                notes=self._owner_context(request),
                lens_query=self._lens_query(request),
            ),
            progress=progress,
        )

    @staticmethod
    def _mode(request: AnalysisInput) -> AnalysisMode:
        if not request.image_url:
            return AnalysisMode.DETAILS
        return AnalysisMode.IMAGE_WITH_DETAILS if request.has_bag_details else AnalysisMode.IMAGE

    @staticmethod
    def _bag(
        request: AnalysisInput, identification: Identification | None, warnings: list[str]
    ) -> BagIdentity | None:
        provided = {
            key: value
            for key, value in {
                "brand": request.brand,
                "model": request.model,
                "size": request.size,
                "material": request.leather,
                "color": " / ".join(request.color) or None,
                "hardware": request.hardware,
                "construction": request.construction,
                "variant": request.special_variant,
            }.items()
            if value
        }
        candidates = identification.result.candidates if identification else []
        identified = candidates[0].identity if candidates else None

        base: dict[str, str | None] = {}
        if identified is not None:
            conflict = (request.brand and not _same_brand(identified.brand, request.brand)) or (
                request.model and not _same_model(identified.model, request.model)
            )
            if conflict:
                warnings.append(
                    f"The photo looks like {identified.display_name}, which differs from the "
                    "details provided; pricing uses the provided details."
                )
            else:
                base = identified.model_dump()

        merged = {**base, **provided}
        if not merged.get("brand") or not merged.get("model"):
            return None
        try:
            return BagIdentity.model_validate(merged)
        except ValidationError as exc:
            raise InvalidRequestError(f"Invalid bag details: {exc.errors()[0]['msg']}") from exc

    @staticmethod
    def _condition(request: AnalysisInput, identification: Identification | None) -> Condition:
        if request.condition:
            return normalize_condition(request.condition)
        if identification is not None:
            return normalize_condition(identification.result.attributes.apparent_condition)
        return Condition.UNKNOWN

    @staticmethod
    def _lens_query(request: AnalysisInput) -> str | None:
        if request.search_query:
            return request.search_query
        return " ".join(p for p in (request.brand, request.model) if p) or None

    @staticmethod
    def _owner_context(request: AnalysisInput) -> str | None:
        details = {
            "brand": request.brand,
            "model": request.model,
            "condition": request.condition,
            "size": request.size,
            "material": request.leather,
            "color": ", ".join(request.color) or None,
            "hardware": request.hardware,
            "construction": request.construction,
            "variant": request.special_variant,
            "search hint": request.search_query,
            "notes": request.notes,
        }
        lines = [f"{key}: {value}" for key, value in details.items() if value]
        if request.extra:
            lines.append(f"other fields: {json.dumps(request.extra, default=str)}")
        if not lines:
            return None
        context = "Details supplied by the owner (unverified):\n" + "\n".join(lines)
        return context[:_MAX_CONTEXT_CHARS]


def _same_brand(a: str, b: str) -> bool:
    return bool(set(brand_aliases(a)) & set(brand_aliases(b)))


def _same_model(a: str, b: str) -> bool:
    left, right = set(normalize_text(a).split()), set(normalize_text(b).split())
    return bool(left) and bool(right) and (left <= right or right <= left)
