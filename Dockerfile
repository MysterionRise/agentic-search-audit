# syntax=docker/dockerfile:1.7
# Targets:
#   cli   (default)  `search-audit` with Playwright Chromium
#   saas             cli + the experimental API/worker layer ([saas] extra)
# Build:  docker build -t agentic-search-audit .
#         docker build --target saas -t agentic-search-audit-saas .
# Add Google Chrome for `--browser undetected`:  --build-arg INSTALL_CHROME=1
# The cdp and bridge backends attach to a Chrome on the host; they are not built into images.

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

FROM base AS cli
ARG INSTALL_CHROME=0
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable $( [ "$INSTALL_CHROME" = "1" ] && echo "--extra undetected" )
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
RUN if [ "$INSTALL_CHROME" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends wget gnupg2 ca-certificates && \
      wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg && \
      echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
      apt-get update && apt-get install -y --no-install-recommends google-chrome-stable && \
      rm -rf /var/lib/apt/lists/*; \
    fi
COPY configs/ ./configs/
COPY data/ ./data/
RUN useradd -m -u 1000 auditor && mkdir -p /app/runs && chown -R auditor:auditor /app /ms-playwright
USER auditor
ENTRYPOINT ["search-audit"]
CMD ["--help"]

FROM cli AS saas
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY alembic.ini ./
COPY alembic/ ./alembic/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra saas
USER auditor
EXPOSE 8000
ENTRYPOINT []
CMD ["search-audit-api", "--host", "0.0.0.0", "--port", "8000"]
