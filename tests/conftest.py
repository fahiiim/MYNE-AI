import io

import pytest
from PIL import Image

from myne.core.config import Settings


@pytest.fixture
def jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), color=(180, 120, 60)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, openai_api_key="test-key")  # type: ignore[call-arg, arg-type]
