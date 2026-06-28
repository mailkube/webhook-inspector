# SPDX-License-Identifier: Apache-2.0
"""FastAPI receiver: verification handshake, delivery logging, and signature checks.

This is the heart of webhook_inspector. It answers the mailkube verification handshake so
endpoint creation (and ``endpoint_url`` changes) succeed, then logs incoming deliveries
and — when ``WEBHOOK_SECRET`` is set — verifies the ``X-Webhook-Sig`` HMAC-SHA256 header.
See ``.rules/WEBHOOK_CONTRACT.md`` for the contract this mirrors.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

from webhook_inspector.tunnel import close_tunnel, open_tunnel

load_dotenv()

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5000"))
USE_TUNNEL = os.environ.get("USE_TUNNEL", "true").lower() == "true"
TUNNEL_PROTOCOL = os.environ.get("TUNNEL_PROTOCOL", "http2")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Open the cloudflared tunnel on startup (when enabled); close it on shutdown."""
    tunnel = await open_tunnel(PORT, TUNNEL_PROTOCOL) if USE_TUNNEL else None
    try:
        yield
    finally:
        await close_tunnel(tunnel)


app = FastAPI(title="webhook-inspector", lifespan=lifespan)


def _check_signature(raw_body: bytes, sig_header: str) -> str:
    """Verify ``X-Webhook-Sig`` against ``WEBHOOK_SECRET``; return a human verdict.

    Mirrors the sender side exactly: ``hmac_sha256(secret, raw_body)`` hex-encoded, sent
    as ``sha256=<hex>``. The raw body bytes must be used as-received (never a re-serialized
    JSON) or the digest won't match.
    """
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return "skipped (set WEBHOOK_SECRET to verify)"
    expected = sig_header.removeprefix("sha256=")
    actual = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return "valid ✅" if hmac.compare_digest(actual, expected) else "INVALID ❌"


@app.get("/{_path:path}")
async def verify(request: Request) -> Response:
    """Verification handshake — echo ``hub.challenge`` verbatim with HTTP 200.

    Matches any path, so any URL under the tunnel works as a webhook ``endpoint_url``.
    """
    challenge = request.query_params.get("hub.challenge")
    if challenge:
        print(f"🤝 verification probe → echoing challenge {challenge!r}")
        return Response(content=challenge, status_code=200, media_type="text/plain")
    return Response(content="webhook-inspector alive", status_code=200, media_type="text/plain")


@app.post("/{_path:path}")
async def receive(request: Request) -> Response:
    """Log a webhook delivery; always answers 200 so mailkube marks it delivered."""
    raw = await request.body()
    verdict = _check_signature(raw, request.headers.get("x-webhook-sig", ""))
    try:
        body = json.dumps(json.loads(raw), indent=2)
    except ValueError:
        body = raw.decode("utf-8", "replace")
    print(
        "\n📨 delivery received"
        f"\n   Webhook-Id : {request.headers.get('x-webhook-id')}"
        f"\n   Webhook-Ts : {request.headers.get('x-webhook-ts')}"
        f"\n   Signature  : {verdict}"
        f"\n   Body       : {body}\n"
    )
    return Response(content="received", status_code=200, media_type="text/plain")
