# Security

This project handles TikTok session cookies, API keys, and service account credentials. A few things to keep in mind:

- All secrets live in Doppler, never in the repo or Docker images. The `.env` file only holds Doppler service tokens and the GCP project ID.
- Proxy credentials rotate on every request via the Webshare pool — no hardcoded IPs.
- GCS media is auto-deleted after 7 days via bucket lifecycle rules.
- Worker and replier run under separate GCP service accounts with least-privilege IAM roles (worker gets storage admin + firestore, replier only gets storage read/write).
- Sightengine API calls are rate-limited to 1 request per second.
- The replier's TikTok cookies are stored in GCS (not baked into the image) and loaded at boot.

## Reporting a vulnerability

Please open a private security advisory on this repo rather than a public issue. Include steps to reproduce and any relevant logs (redact secrets).
