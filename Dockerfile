FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY reviewhub_core ./reviewhub_core
COPY services ./services
RUN pip install --no-cache-dir 'uv==0.13.6' && uv sync --locked --no-dev --no-editable

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/services /app/services
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "services.identity.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
