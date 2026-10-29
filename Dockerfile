FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
# Erst nur die Abhängigkeiten (besseres Layer-Caching), dann den Code
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-editable --no-install-project --no-dev
COPY src ./src
RUN uv sync --frozen --no-editable --no-dev

# stdio -> HTTP-Bridge (/mcp = Streamable HTTP, /sse = SSE)
RUN pip install --no-cache-dir mcp-proxy

ENV PATH="/app/.venv/bin:${PATH}"
WORKDIR /exports
EXPOSE 8096

CMD ["mcp-proxy", "--host", "0.0.0.0", "--port", "8096", "--pass-environment", "--", "/app/.venv/bin/onshape-mcp"]
