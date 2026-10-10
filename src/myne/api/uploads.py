from fastapi import UploadFile

from myne.core.errors import InvalidImageError, PayloadTooLargeError, UnsupportedMediaTypeError

_ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


async def read_image_upload(upload: UploadFile, *, max_bytes: int) -> bytes:
    if upload.content_type not in _ALLOWED_CONTENT_TYPES:
        raise UnsupportedMediaTypeError(
            f"Expected one of {sorted(_ALLOWED_CONTENT_TYPES)}, got {upload.content_type!r}"
        )
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Image exceeds {max_bytes} bytes")
    if not data:
        raise InvalidImageError("Uploaded file is empty")
    return data
