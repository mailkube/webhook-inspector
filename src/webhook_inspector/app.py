# SPDX-License-Identifier: Apache-2.0
"""FastAPI receiver: verification handshake, delivery logging, and signature checks.

This is the heart of webhook_inspector. It answers the mailkube verification handshake so
endpoint creation (and ``endpoint_url`` changes) succeed, then logs incoming deliveries and —
when ``WEBHOOK_SECRET`` is set — verifies the ``X-Webhook-Sig`` HMAC-SHA256 signature and rejects
bad deliveries with ``400``.

Verification and parsing are delegated to the published ``mailkube`` SDK
(``verify_signature`` / ``parse_event``) rather than reimplemented here, so this tool stays
byte-compatible with the signing contract by construction and doubles as a live SDK example.
See ``.rules/WEBHOOK_CONTRACT.md`` for the wire contract the SDK mirrors.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from mailkube import SignatureVerificationError, UnknownEvent, parse_event, verify_signature
from pydantic import ValidationError

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


def _summarize(raw: bytes) -> tuple[str, str]:
    """Return ``(event-type headline, pretty body)`` for a delivery via the SDK's typed models.

    Falls back to the raw decoded text when the body is not a parseable webhook event, so the
    inspector still shows arbitrary test POSTs. ``model_dump(by_alias=True)`` re-emits the wire
    field names (``from``, ``scheduled_at``) and, because the SDK models allow extra keys,
    preserves any fields a newer server version added.
    """
    try:
        event = parse_event(raw)
    except ValidationError:
        return "unparseable (not a JSON event)", raw.decode("utf-8", "replace")
    headline = event.type + (" [unrecognized type]" if isinstance(event, UnknownEvent) else "")
    body = json.dumps(event.model_dump(by_alias=True), indent=2, default=str)
    return headline, body


def _log_delivery(headers: Mapping[str, str], raw: bytes, *, verified: bool) -> None:
    """Print a received delivery: identity headers, verification state, typed event summary."""
    headline, body = _summarize(raw)
    signature = "verified ✅" if verified else "unverified (no WEBHOOK_SECRET)"
    print(
        "\n📨 delivery received"
        f"\n   Webhook-Id : {headers.get('x-webhook-id', '')}"
        f"\n   Webhook-Ts : {headers.get('x-webhook-ts', '')}"
        f"\n   Signature  : {signature}"
        f"\n   Event      : {headline}"
        f"\n   Body       : {body}\n"
    )


# NOTE: this handler is named ``verify`` — do not import the SDK's ``mailkube.verify`` into this
# module or it will collide. The signature gate below deliberately uses ``verify_signature``.
@app.get("/{_path:path}")
async def verify(request: Request) -> Response:
    """Verification handshake — echo ``hub.challenge`` verbatim with HTTP 200.

    Matches any path, so any URL under the tunnel works as a webhook ``endpoint_url``. The SDK
    ships no helper for this handshake, so it stays hand-written.
    """
    challenge = request.query_params.get("hub.challenge")
    if challenge:
        print(f"🤝 verification probe → echoing challenge {challenge!r}")
        return Response(content=challenge, status_code=200, media_type="text/plain")
    return Response(content="webhook-inspector alive", status_code=200, media_type="text/plain")


@app.post("/{_path:path}")
async def receive(request: Request) -> Response:
    """Verify (when a secret is set) and log a delivery; reject a bad signature with 400.

    With ``WEBHOOK_SECRET`` set, the ``mailkube`` SDK checks the HMAC-SHA256 signature and the
    ``X-Webhook-Ts`` freshness window (~5 min); a missing, stale, or mismatched signature is
    rejected. Without a secret, verification is skipped and the delivery is logged unverified so
    the tool can still inspect arbitrary POSTs.
    """
    raw = await request.body()
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if secret:
        try:
            verify_signature(raw, request.headers, secret)
        except SignatureVerificationError as exc:
            print(f"\n🚫 delivery rejected: {exc}\n")
            return Response(content=str(exc), status_code=400, media_type="text/plain")
    _log_delivery(request.headers, raw, verified=bool(secret))
    return Response(content="received", status_code=200, media_type="text/plain")
