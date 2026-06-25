# Rule: Webhook contract (mirror of the mailkube API)

`webhook-inspector` implements the *receiver* side of two mailkube contracts. The **mailkube API is
the source of truth** — if it changes, update this tool to match. Keep both behaviors
byte-compatible; a drift here silently breaks endpoint creation or signature verification for
every user of the tool.

## 1. Verification handshake (endpoint create / `endpoint_url` change)

mailkube issues a synchronous probe:

```
GET <endpoint_url>?hub.mode=subscribe&hub.challenge=<one-time-token>
User-Agent: Mailkube-Webhook/<version>
```

The receiver **must** respond:

- HTTP **200** (exactly 200 — not any 2xx), and
- a body equal to `<one-time-token>` after trimming surrounding whitespace.

Anything else (wrong body, non-200, TLS error, timeout) causes mailkube to reject creation
with `400`. Implemented in [`src/webhook_inspector/app.py`](../src/webhook_inspector/app.py) `verify()`,
which echoes the challenge on **any** path.

## 2. Delivery signature (`X-Webhook-Sig`)

Deliveries are `POST`s with header:

```
X-Webhook-Sig: sha256=<hex>
```

where `<hex> = hmac_sha256(secret, raw_request_body).hexdigest()` and `secret` is the
`plain_secret` returned once at endpoint creation. Verification rules:

- Compute the HMAC over the **raw body bytes as received** — never a re-serialized JSON
  (whitespace differences break the digest).
- Compare with `hmac.compare_digest` (constant-time).

Implemented in `_check_signature()` in [`src/webhook_inspector/app.py`](../src/webhook_inspector/app.py);
guarded by `tests/test_app.py`, which reproduces the sender's algorithm independently.

## Changing this code

- Update the tests in `tests/test_app.py` to reproduce the new contract from the API side
  (don't assert against the tool's own output — assert against an independent recomputation).
- Note any user-visible change in `README.md`.
