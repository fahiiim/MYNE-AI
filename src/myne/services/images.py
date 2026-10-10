import asyncio
import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from myne.ai.llm import ImageInput
from myne.core.errors import InvalidImageError, PayloadTooLargeError

_JPEG = "image/jpeg"
# (max side in px, JPEG quality) tried in order until the encoded image fits the byte budget.
_SEARCH_ENCODING_LADDER = ((1600, 85), (1280, 80), (1024, 75), (800, 70), (640, 60))


@dataclass(frozen=True, slots=True)
class PreparedImage:
    analysis: ImageInput
    search: ImageInput
    sha256: str


class ImagePreprocessor:
    """Validates uploads and produces normalized JPEG variants.

    `analysis` feeds vision models; `search` fits SerpApi's 500 KB upload cap.
    """

    def __init__(
        self,
        *,
        max_upload_bytes: int,
        analysis_max_side: int = 1600,
        search_max_bytes: int = 480_000,
    ) -> None:
        self._max_upload_bytes = max_upload_bytes
        self._analysis_max_side = analysis_max_side
        self._search_max_bytes = search_max_bytes

    async def prepare(self, raw: bytes) -> PreparedImage:
        return await asyncio.to_thread(self._prepare, raw)

    def _prepare(self, raw: bytes) -> PreparedImage:
        if len(raw) > self._max_upload_bytes:
            raise PayloadTooLargeError(f"Image exceeds {self._max_upload_bytes} bytes")
        image = self._decode(raw)
        analysis = self._encode(image, max_side=self._analysis_max_side, quality=90)
        return PreparedImage(
            analysis=ImageInput(analysis, _JPEG),
            search=ImageInput(self._encode_within_budget(image), _JPEG),
            sha256=hashlib.sha256(raw).hexdigest(),
        )

    @staticmethod
    def _decode(raw: bytes) -> Image.Image:
        try:
            with Image.open(io.BytesIO(raw)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(raw)) as source:
                return ImageOps.exif_transpose(source).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
            raise InvalidImageError("File is not a readable image") from exc

    @staticmethod
    def _encode(image: Image.Image, *, max_side: int, quality: int) -> bytes:
        resized = image.copy()
        resized.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        resized.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

    def _encode_within_budget(self, image: Image.Image) -> bytes:
        encoded = b""
        for max_side, quality in _SEARCH_ENCODING_LADDER:
            encoded = self._encode(image, max_side=max_side, quality=quality)
            if len(encoded) <= self._search_max_bytes:
                break
        return encoded
