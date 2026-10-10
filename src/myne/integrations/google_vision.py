import base64
import re
from typing import Any

from myne.core.errors import UpstreamServiceError
from myne.core.http import HttpClient
from myne.integrations.types import WebDetection, WebPage

_TAGS = re.compile(r"<[^>]+>")


class GoogleVisionClient:
    _ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
    _SERVICE = "google_vision"

    def __init__(self, http: HttpClient, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def detect(self, image: bytes, *, max_results: int = 15) -> WebDetection:
        body = {
            "requests": [
                {
                    "image": {"content": base64.b64encode(image).decode("ascii")},
                    "features": [
                        {"type": "WEB_DETECTION", "maxResults": max_results},
                        {"type": "LOGO_DETECTION", "maxResults": 5},
                    ],
                }
            ]
        }
        payload = await self._http.request_json(
            self._SERVICE, "POST", self._ENDPOINT, params={"key": self._api_key}, json=body
        )
        responses = payload.get("responses") if isinstance(payload, dict) else None
        result: dict[str, Any] = responses[0] if responses else {}
        if error := result.get("error"):
            raise UpstreamServiceError(self._SERVICE, str(error.get("message", "unknown error")))

        web: dict[str, Any] = result.get("webDetection", {})
        return WebDetection(
            best_guess_labels=tuple(
                label["label"] for label in web.get("bestGuessLabels", []) if label.get("label")
            ),
            entities=tuple(
                (entity["description"], float(entity.get("score", 0.0)))
                for entity in web.get("webEntities", [])
                if entity.get("description")
            ),
            logos=tuple(
                (logo["description"], float(logo.get("score", 0.0)))
                for logo in result.get("logoAnnotations", [])
                if logo.get("description")
            ),
            pages=tuple(
                WebPage(title=_TAGS.sub("", page.get("pageTitle", "")).strip(), url=page["url"])
                for page in web.get("pagesWithMatchingImages", [])
                if page.get("url")
            ),
        )
