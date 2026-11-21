FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-cache

FROM python:3.12-slim
WORKDIR /srv
RUN useradd --system --uid 10001 app && mkdir -p /data && chown app /data
COPY --from=build /srv/.venv /srv/.venv
COPY app ./app
ENV PATH="/srv/.venv/bin:$PATH" PYTHONUNBUFFERED=1 LITELLM_LOCAL_MODEL_COST_MAP=True
COPY entrypoint.py /usr/local/lib/chat-entrypoint.py
ENTRYPOINT ["/usr/local/bin/python", "-I", "/usr/local/lib/chat-entrypoint.py"]
EXPOSE 8000
CMD ["sh","-c","exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
