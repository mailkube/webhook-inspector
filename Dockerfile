FROM python:3.14-slim

# uv from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# cloudflared (static Go binary) for the quick tunnel — arch-matched to the build target.
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${TARGETARCH}" \
       -o /usr/local/bin/cloudflared \
    && chmod +x /usr/local/bin/cloudflared \
    && apt-get purge -y curl && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install dependencies first (cached layer), without the project or dev group.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Then the project itself.
COPY . .
RUN uv sync --frozen --no-dev

# Activate the venv and default to a container-friendly bind address.
ENV PATH="/app/.venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=5000

EXPOSE 5000

# Override env (WEBHOOK_SECRET, USE_TUNNEL) at runtime.
ENTRYPOINT ["webhook-inspector"]
