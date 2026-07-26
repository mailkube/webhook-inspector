# SPDX-License-Identifier: Apache-2.0
"""Tests for the webhook-inspector receiver.

The handshake and delivery endpoints are exercised through FastAPI's TestClient with the tunnel
disabled. ``_sign`` reproduces the mailkube sender's HMAC algorithm independently — on the
receiver side of the trust boundary — so these tests guard interoperability with the ``mailkube``
SDK rather than merely re-asserting its behavior.
"""

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime

os.environ.setdefault("USE_TUNNEL", "false")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402  (env must be set before import)

from webhook_inspector.app import app  # noqa: E402

client = TestClient(app)

SECRET = b"test-secret"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sign(body: bytes, *, webhook_id: str = "d1", ts: str | None = None) -> dict[str, str]:
    # Reproduce the sender contract independently: HMAC over "id.ts." + raw body.
    timestamp = ts or _now_iso()
    signing_input = f"{webhook_id}.{timestamp}.".encode() + body
    digest = hmac.new(SECRET, signing_input, hashlib.sha256).hexdigest()
    return {"X-Webhook-Id": webhook_id, "X-Webhook-Ts": timestamp, "X-Webhook-Sig": f"sha256={digest}"}


def _delivered_payload() -> bytes:
    return json.dumps(
        {
            "type": "email.delivered",
            "created_at": "2026-07-13T10:00:00+00:00",
            "data": {
                "email_id": "e1",
                "created_at": "2026-07-13T10:00:00+00:00",
                "domain": "acme.com",
                "subject": "Hi",
                "to": ["b@y.com"],
                "from": "a@x.com",
                "delivery": {"recipient": "b@y.com", "timestamp": "2026-07-13T10:00:00+00:00"},
            },
        }
    ).encode()


def _post(body: bytes, headers: dict[str, str]) -> "object":
    return client.post("/inbox", content=body, headers={**headers, "Content-Type": "application/json"})


# --- Handshake ---------------------------------------------------------------------


def test_handshake_echoes_challenge_at_root() -> None:
    r = client.get("/", params={"hub.mode": "subscribe", "hub.challenge": "abc123"})
    assert r.status_code == 200
    assert r.text == "abc123"


def test_handshake_echoes_challenge_on_subpath() -> None:
    r = client.get("/inbox", params={"hub.mode": "subscribe", "hub.challenge": "deadbeef"})
    assert r.status_code == 200
    assert r.text == "deadbeef"


def test_liveness_without_challenge() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "alive" in r.text


# --- Delivery with a secret set (strict verification) ------------------------------


def test_valid_signature_accepted() -> None:
    body = _delivered_payload()
    r = _post(body, _sign(body))
    assert r.status_code == 200
    assert r.text == "received"


def test_tampered_body_rejected_400() -> None:
    body = _delivered_payload()
    headers = _sign(body)
    r = _post(b'{"type":"email.delivered"}', headers)  # signature bound to the original body
    assert r.status_code == 400


def test_wrong_id_rejected_400() -> None:
    body = _delivered_payload()
    headers = _sign(body)
    headers["X-Webhook-Id"] = "other"
    r = _post(body, headers)
    assert r.status_code == 400


def test_missing_signature_headers_rejected_400() -> None:
    r = _post(_delivered_payload(), {})
    assert r.status_code == 400


def test_stale_timestamp_rejected_400() -> None:
    body = _delivered_payload()
    stale = "2020-01-01T00:00:00+00:00"
    r = _post(body, _sign(body, ts=stale))
    assert r.status_code == 400


# --- Delivery with no secret (verification skipped, still logged) ------------------


def test_json_delivery_without_secret_returns_200(monkeypatch) -> None:
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    r = _post(_delivered_payload(), {})
    assert r.status_code == 200
    assert r.text == "received"


def test_non_json_delivery_without_secret_returns_200(monkeypatch) -> None:
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    r = client.post("/inbox", content=b"not-json", headers={"Content-Type": "text/plain"})
    assert r.status_code == 200


def test_unknown_event_type_without_secret_returns_200(monkeypatch) -> None:
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    body = json.dumps({"type": "email.reopened", "created_at": "2026-07-13T10:00:00+00:00", "data": {}}).encode()
    r = _post(body, {})
    assert r.status_code == 200


# --- Lifespan ----------------------------------------------------------------------


def test_lifespan_runs_without_tunnel() -> None:
    # Entering the context manager runs startup/shutdown; USE_TUNNEL=false → no tunnel opened.
    with TestClient(app) as ctx_client:
        assert ctx_client.get("/").status_code == 200
