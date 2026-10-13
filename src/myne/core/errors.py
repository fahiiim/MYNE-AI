from typing import ClassVar


class MyneError(Exception):
    status_code: ClassVar[int] = 500
    code: ClassVar[str] = "internal_error"
    title: ClassVar[str] = "Internal server error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidRequestError(MyneError):
    status_code = 422
    code = "invalid_request"
    title = "Invalid request"


class InvalidImageError(MyneError):
    status_code = 422
    code = "invalid_image"
    title = "Invalid image"


class InvalidImageUrlError(MyneError):
    status_code = 422
    code = "invalid_image_url"
    title = "Invalid image URL"


class ImageFetchError(MyneError):
    status_code = 422
    code = "image_unreachable"
    title = "Image could not be downloaded"


class UnsupportedMediaTypeError(MyneError):
    status_code = 415
    code = "unsupported_media_type"
    title = "Unsupported media type"


class PayloadTooLargeError(MyneError):
    status_code = 413
    code = "payload_too_large"
    title = "Payload too large"


class ConfigurationError(MyneError):
    status_code = 503
    code = "service_misconfigured"
    title = "Service misconfigured"


class UpstreamServiceError(MyneError):
    status_code = 502
    code = "upstream_unavailable"
    title = "Upstream service error"

    def __init__(self, service: str, detail: str, *, status: int | None = None) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.upstream_status = status
