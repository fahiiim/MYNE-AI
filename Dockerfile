FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install .

RUN useradd --create-home --uid 10001 myne
USER myne

EXPOSE 8000
CMD ["uvicorn", "myne.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
