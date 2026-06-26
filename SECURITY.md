# Security Policy

## Supported versions

`webhook-inspector` is a developer tool for testing webhooks locally. It is not released
or versioned — fixes land on the `main` branch, so always run the latest `main`.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report vulnerabilities privately through GitHub's
[**"Report a vulnerability"**](https://github.com/mailkube/webhook-inspector/security/advisories/new)
flow (Security → Advisories). This opens a private advisory visible only to the
maintainers.

When reporting, please include:

- a description of the issue and its impact,
- steps to reproduce (a minimal proof of concept if possible),
- the affected version/commit, and
- any suggested remediation.

### What to expect

- **Acknowledgement** within 3 business days.
- **Triage and severity assessment** within 7 business days.
- We will keep you updated on remediation progress and coordinate a disclosure
  timeline with you. Credit is given to reporters who wish to be named.

## Scope notes

`webhook-inspector` is meant to run **locally** for testing. Keep in mind:

- The signing secret (`WEBHOOK_SECRET`) belongs in your local `.env`, which is
  git-ignored — never commit it.
- A cloudflared tunnel exposes your local server to the public internet for its
  lifetime. Run it only while testing and stop it when done.
