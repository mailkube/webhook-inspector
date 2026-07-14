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
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response

from webhook_inspector.tunnel import close_tunnel, open_tunnel

load_dotenv()

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5000"))
USE_TUNNEL = os.environ.get("USE_TUNNEL", "true").lower() == "true"
TUNNEL_PROTOCOL = os.environ.get("TUNNEL_PROTOCOL", "http2")
TUNNEL_NAME = os.environ.get("TUNNEL_NAME") or None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Open the cloudflared tunnel on startup (when enabled); close it on shutdown."""
    tunnel = await open_tunnel(PORT, TUNNEL_PROTOCOL, TUNNEL_NAME) if USE_TUNNEL else None
    try:
        yield
    finally:
        await close_tunnel(tunnel)


app = FastAPI(title="webhook-inspector", lifespan=lifespan)


FRESHNESS_TOLERANCE_SECONDS = 300


def _timestamp_age(ts: str) -> str:
    """Return a human note about how old ``X-Webhook-Ts`` is, for replay-window awareness.

    Informational only — this dev tool always accepts the delivery. A production receiver
    would *reject* a timestamp older than its tolerance (see ``.rules/WEBHOOK_CONTRACT.md``).
    """
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except ValueError:
        return ""
    flag = "fresh" if abs(age) <= FRESHNESS_TOLERANCE_SECONDS else f"stale > {FRESHNESS_TOLERANCE_SECONDS}s"
    return f"  (age {age:.0f}s, {flag})"


def _check_signature(raw_body: bytes, sig_header: str, webhook_id: str, ts: str) -> str:
    """Verify ``X-Webhook-Sig`` against ``WEBHOOK_SECRET``; return a human verdict.

    Mirrors the sender side exactly: the HMAC-SHA256 is computed over the signing input
    ``f"{X-Webhook-Id}.{X-Webhook-Ts}.".encode() + raw_body`` and sent as ``sha256=<hex>``.
    The raw body bytes must be used as-received (never a re-serialized JSON) or the digest
    won't match. ``X-Webhook-Id``/``X-Webhook-Ts`` are read from the delivery headers.
    """
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        return "skipped (set WEBHOOK_SECRET to verify)"
    expected = sig_header.removeprefix("sha256=")
    signing_input = f"{webhook_id}.{ts}.".encode() + raw_body
    actual = hmac.new(secret.encode(), signing_input, hashlib.sha256).hexdigest()
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
    webhook_id = request.headers.get("x-webhook-id", "")
    ts = request.headers.get("x-webhook-ts", "")
    verdict = _check_signature(raw, request.headers.get("x-webhook-sig", ""), webhook_id, ts)
    try:
        body = json.dumps(json.loads(raw), indent=2)
    except ValueError:
        body = raw.decode("utf-8", "replace")
    print(
        "\n📨 delivery received"
        f"\n   Webhook-Id : {webhook_id}"
        f"\n   Webhook-Ts : {ts}{_timestamp_age(ts)}"
        f"\n   Signature  : {verdict}"
        f"\n   Body       : {body}\n"
    )
    return Response(content="received", status_code=200, media_type="text/plain")
