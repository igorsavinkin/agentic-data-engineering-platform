# Shared Dockerfile for all application services.
# Build context: repository root.
#
# Usage:
#   docker build \
#     --build-arg SERVICE_MODULE=services.ingestion \
#     -t ai-data-platform/ingestion:dev .
#
# Each service is a thin layer over the same Python environment;
# only the entrypoint module differs.

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim AS base

ARG SERVICE_MODULE
ENV SERVICE_MODULE=${SERVICE_MODULE} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY services/ services/
COPY libs/ libs/
COPY warehouse/ warehouse/
COPY pyproject.toml .

CMD ["sh", "-c", "python -m ${SERVICE_MODULE}"]
