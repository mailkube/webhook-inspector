# SPDX-License-Identifier: Apache-2.0
"""Tests for the webhook-inspector receiver.

The handshake and signature logic are exercised through FastAPI's TestClient with the
ngrok tunnel disabled. The signature assertions mirror the mailkube sender's algorithm
exactly (``sha256=hmac_sha256(secret, raw_body)``), guarding interoperability.
"""

import hashlib
import hmac
import json
import os

os.environ.setdefault("USE_NGROK", "false")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402  (env must be set before import)

from webhook_inspector.app import _check_signature, app  # noqa: E402

client = TestClient(app)


def _sign(secret: bytes, body: bytes) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


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


def test_signature_valid_matches_sender_algorithm() -> None:
    raw = json.dumps({"type": "email.delivered", "data": {"id": 1}}).encode()
    assert _check_signature(raw, _sign(b"test-secret", raw)).startswith("valid")


def test_signature_invalid_is_rejected() -> None:
    assert "INVALID" in _check_signature(b"{}", "sha256=deadbeef")


def test_signature_skipped_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    assert "skipped" in _check_signature(b"{}", "sha256=whatever")


def test_post_json_delivery_returns_200() -> None:
    raw = json.dumps({"type": "email.opened"}).encode()
    r = client.post(
        "/inbox",
        content=raw,
        headers={"X-Webhook-Sig": _sign(b"test-secret", raw), "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.text == "received"


def test_post_non_json_delivery_returns_200() -> None:
    r = client.post("/inbox", content=b"not-json", headers={"Content-Type": "text/plain"})
    assert r.status_code == 200


def test_lifespan_runs_without_tunnel() -> None:
    # Entering the context manager runs startup/shutdown; USE_NGROK=false → no tunnel opened.
    with TestClient(app) as ctx_client:
        assert ctx_client.get("/").status_code == 200
