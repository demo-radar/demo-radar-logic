FROM ghcr.io/astral-sh/uv:0.12.10@sha256:2bb3ebca0a796a155094a27773d290c4b074572e6107f171d88d086682fd2500 AS uv
FROM python:3.13-slim@sha256:bf44cdfcb76cd3b41e879bc058fc37ec5872002ccfde7fcb765e218cde0cd79c
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev --group service --no-install-project
COPY service ./service
COPY configs/inference ./configs/inference
COPY configs/gems ./configs/gems
COPY configs/summary ./configs/summary
COPY docs/rubrics/tagging-rubric-v4.md ./docs/rubrics/tagging-rubric-v4.md
RUN uv sync --locked --no-dev --group service --no-editable \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /app/data/service \
    && chown -R app:app /app/data
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "75", "--no-access-log"]
