# SPDX-License-Identifier: Apache-2.0
"""Tests for the webhook-inspector receiver.

The handshake and signature logic are exercised through FastAPI's TestClient with the
tunnel disabled. The signature assertions mirror the mailkube sender's algorithm
exactly (``sha256=hmac_sha256(secret, raw_body)``), guarding interoperability.
"""

import hashlib
import hmac
import json
import os

os.environ.setdefault("USE_TUNNEL", "false")
os.environ.setdefault("WEBHOOK_SECRET", "test-secret")

from fastapi.testclient import TestClient  # noqa: E402  (env must be set before import)

from webhook_inspector.app import _check_signature, app  # noqa: E402

client = TestClient(app)


def _sign(secret: bytes, body: bytes, webhook_id: str = "d1", ts: str = "2026-07-13T10:00:00+00:00") -> str:
    # Reproduce the sender contract independently: HMAC over "id.ts." + raw body.
    signing_input = f"{webhook_id}.{ts}.".encode() + body
    return "sha256=" + hmac.new(secret, signing_input, hashlib.sha256).hexdigest()


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
    sig = _sign(b"test-secret", raw, "d1", "2026-07-13T10:00:00+00:00")
    assert _check_signature(raw, sig, "d1", "2026-07-13T10:00:00+00:00").startswith("valid")


def test_signature_invalid_when_id_or_ts_differs() -> None:
    raw = json.dumps({"type": "email.delivered"}).encode()
    sig = _sign(b"test-secret", raw, "d1", "2026-07-13T10:00:00+00:00")
    # A tampered id or timestamp must not verify against a signature bound to the originals.
    assert "INVALID" in _check_signature(raw, sig, "d2", "2026-07-13T10:00:00+00:00")
    assert "INVALID" in _check_signature(raw, sig, "d1", "2026-07-13T11:00:00+00:00")


def test_signature_invalid_is_rejected() -> None:
    assert "INVALID" in _check_signature(b"{}", "sha256=deadbeef", "d1", "2026-07-13T10:00:00+00:00")


def test_signature_skipped_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)
    assert "skipped" in _check_signature(b"{}", "sha256=whatever", "d1", "2026-07-13T10:00:00+00:00")


def test_post_json_delivery_returns_200() -> None:
    raw = json.dumps({"type": "email.opened"}).encode()
    ts = "2026-07-13T10:00:00+00:00"
    r = client.post(
        "/inbox",
        content=raw,
        headers={
            "X-Webhook-Sig": _sign(b"test-secret", raw, "d1", ts),
            "X-Webhook-Id": "d1",
            "X-Webhook-Ts": ts,
            "Content-Type": "application/json",
        },
    )
    assert r.status_code == 200
    assert r.text == "received"


def test_post_non_json_delivery_returns_200() -> None:
    r = client.post("/inbox", content=b"not-json", headers={"Content-Type": "text/plain"})
    assert r.status_code == 200


def test_lifespan_runs_without_tunnel() -> None:
    # Entering the context manager runs startup/shutdown; USE_TUNNEL=false → no tunnel opened.
    with TestClient(app) as ctx_client:
        assert ctx_client.get("/").status_code == 200
