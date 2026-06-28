# webhook-inspector

[![CI](https://github.com/mailkube/webhook-inspector/actions/workflows/ci.yml/badge.svg)](https://github.com/mailkube/webhook-inspector/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code of Conduct](https://img.shields.io/badge/Contributor%20Covenant-2.1-purple.svg)](CODE_OF_CONDUCT.md)

A tiny local receiver for testing [**mailkube**](https://mailkube.com) webhooks and getting
familiar with how they work. It starts a FastAPI server and opens a
[cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
**quick tunnel** (account-less, no signup), then prints a public HTTPS URL you can use as a
webhook `endpoint_url`.

It does two things:

- **Answers the verification handshake** so endpoint creation (and `endpoint_url` changes) succeed.
- **Logs deliveries** and verifies the `X-Webhook-Sig` signature when a secret is configured.

> This is a developer tool — it is **not** published as a package and cuts no releases. Run it
> with [uv](https://docs.astral.sh/uv/) or Docker.

## Contents

- [Requirements](#requirements)
- [Run with uv](#run-with-uv)
- [Run with Docker](#run-with-docker)
- [Use it](#use-it)
- [How it works](#how-it-works)
- [Configuration](#configuration)
- [Notes](#notes)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## Requirements

- [uv](https://docs.astral.sh/uv/) **or** Docker
- The [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/)
  binary on your `PATH` (e.g. `brew install cloudflared`) — no Cloudflare account needed.
  Not required for `--no-tunnel`, and already bundled in the Docker image.

Optionally create a local config (only needed to set `WEBHOOK_SECRET`):

```bash
cp .env.example .env
```

## Run with uv

```bash
uv run webhook-inspector                 # opens a cloudflared quick tunnel
uv run webhook-inspector --no-tunnel     # serve locally only, no tunnel
```

`uv` creates the environment and installs everything on first run. Flags: `--host`,
`--port <n>`, `--no-tunnel`.

It prints a public URL:

```
==================================================================
  Public URL : https://random-words-here.trycloudflare.com
  Use it as your webhook endpoint_url (the https:// URL above).
==================================================================
```

## Run with Docker

```bash
docker compose up --build
```

or a plain `docker run`:

```bash
docker build -t webhook-inspector .
docker run --rm --env-file .env -p 5000:5000 webhook-inspector
```

The image binds `0.0.0.0` so the mapped port is reachable. Configure it via `.env` (or `-e`).

## Use it

1. Create a mailkube webhook endpoint with `endpoint_url` set to the printed URL (any path
   works, e.g. `…trycloudflare.com/inbox`). The verification probe hits this server, which echoes
   the challenge → creation returns **201** with a `plain_secret`.
2. To verify delivery signatures, put that `plain_secret` into `.env` as `WEBHOOK_SECRET` and
   restart. Each delivery then logs `Signature: valid ✅`.
3. Watch deliveries stream in the console as they arrive.

## How it works

**Verification handshake.** mailkube sends a `GET` to your `endpoint_url`:

```
GET <endpoint_url>?hub.mode=subscribe&hub.challenge=<one-time-token>
```

The receiver must answer `200` with the body equal to `<one-time-token>`. webhook-inspector echoes
it on any path.

**Signature.** Deliveries arrive as `POST`s carrying `X-Webhook-Sig: sha256=<hmac>`, where the
HMAC is SHA-256 over the **raw** request body using your signing secret. webhook-inspector recomputes
and compares it when `WEBHOOK_SECRET` is set.

## Configuration

All via environment variables (see [.env.example](.env.example)):

| Variable         | Default     | Purpose                                                        |
| ---------------- | ----------- | -------------------------------------------------------------- |
| `WEBHOOK_SECRET` | —           | Signing secret (the `plain_secret` from create). Empty = skip. |
| `HOST`           | `127.0.0.1` | Bind address (Docker sets `0.0.0.0`).                          |
| `PORT`           | `5000`      | Local port to listen on (the tunnel forwards to it).           |
| `USE_TUNNEL`     | `true`      | Set `false` to serve locally only (no tunnel).                 |
| `TUNNEL_PROTOCOL`| `http2`     | cloudflared edge transport. `http2` (TCP 443) survives networks that block QUIC's UDP 7844; use `quic`/`auto` only if UDP 7844 is open. |

## Notes

- **Quick-tunnel URLs change on every run.** When the URL changes, point your endpoint at the new
  one — a `PATCH` of `endpoint_url` re-runs the handshake, which this server handles
  automatically.
- mailkube caps **verification probes at 80/hour per org**; don't loop-create endpoints faster
  than that or you'll get `429`s before the probe even reaches here.
- **On macOS, port `5000` is taken by AirPlay Receiver** (Control Center). Either disable it
  (System Settings → General → AirDrop & Handoff → AirPlay Receiver) or run on another port,
  e.g. `--port 5005`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By contributing you agree to the
[Apache-2.0](LICENSE) license (no CLA, inbound = outbound) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md). Do not open a public
issue for security problems.

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Mailtactic, Corp.
