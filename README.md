# <img src="https://img.shields.io/badge/🔍-detekt-black?style=for-the-badge&labelColor=0d1117" height="40" />

```
██████╗ ███████╗████████╗███████╗██╗  ██╗████████╗
██╔══██╗██╔════╝╚══██╔══╝██╔════╝██║ ██╔╝╚══██╔══╝
██║  ██║█████╗     ██║   █████╗  █████╔╝    ██║
██║  ██║██╔══╝     ██║   ██╔══╝  ██╔═██╗    ██║
██████╔╝███████╗   ██║   ███████╗██║  ██╗   ██║
╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝
```

> **TikTok AI & deepfake detection bot. Mention it on a video or slideshow, get a verdict.**

<p>
<img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/temporal-1.24-000000?style=flat-square&logo=temporal&logoColor=white" />
<img src="https://img.shields.io/badge/sightengine-AI%20scan-FF6F00?style=flat-square" />
<img src="https://img.shields.io/badge/playwright-browser-2EAD33?style=flat-square&logo=playwright&logoColor=white" />
<img src="https://img.shields.io/badge/camoufox-stealth-orange?style=flat-square" />
<img src="https://img.shields.io/badge/firestore-cache-FFCA28?style=flat-square&logo=firebase&logoColor=black" />
<img src="https://img.shields.io/badge/GCS-media-4285F4?style=flat-square&logo=googlecloud&logoColor=white" />
<img src="https://img.shields.io/badge/doppler-secrets-000000?style=flat-square" />
<img src="https://img.shields.io/badge/docker-GCE-2496ED?style=flat-square&logo=docker&logoColor=white" />
<img src="https://img.shields.io/badge/terraform-infra-7B42BC?style=flat-square&logo=terraform&logoColor=white" />
</p>

```
┌──────────────────────────────────────────────────────────────────────────┐
│  TikTok mention ──► Worker polls ──► Download media ──► Sightengine      │
│                                                                          │
│  @orkavilabs in comments     polled via TikTok notification API          │
│  Videos                  downloaded via yt-dlp, uploaded to GCS          │
│  Slideshows              images extracted, uploaded to GCS               │
│  AI + deepfake scan      Sightengine genai + deepfake models             │
│  Reply                   Camoufox browser posts result as comment        │
│  Rate limiting           per-user via Upstash Redis                      │
│  Caching                 Firestore dedup + result cache                  │
└──────────────────────────────────────────────────────────────────────────┘
```

## What it is

A TikTok bot that detects AI-generated content and deepfakes. Someone mentions the bot in a comment on any TikTok video or slideshow. The bot downloads the media, runs it through Sightengine's AI generation and deepfake detection models, and replies with a verdict — "AI (92%)", "real (97%)", "deepfake detected", or "not sure".

Supports videos and multi-image slideshows (carousels). Each image in a carousel is scanned individually and results are reported per-slide.

## Architecture

```
┌─────────────────┐                           ┌─────────────────┐
│  detekt_worker   │◄── Temporal workflows ──►│  detekt_replier  │
│  (GCE VM)        │                          │  (GCE VM)        │
│                  │                          │                  │
│  Poll mentions   │                          │  Receive reply   │
│  Download media  │                          │  task via        │
│  Upload to GCS   │                          │  Temporal        │
│  Scan via        │                          │                  │
│  Sightengine     │                          │  Open TikTok in  │
│  Dispatch reply  │                          │  Camoufox        │
│                  │                          │  Type & post     │
└────────┬─────────┘                          │  comment reply   │
         │                                    └─────────────────┘
         │
    ┌────┴────────────────────────────────┐
    │  Firestore    GCS bucket    Upstash │
    │  (scan cache  (media        Redis   │
    │   + dedup)     staging)   (rate lim)│
    └─────────────────────────────────────┘
```

Two services, both Docker containers on GCE VMs running Container-Optimized OS:

**detekt_worker** — Temporal worker that runs two workflows. `PollerWorkflow` polls TikTok's notification API on a loop, filters for trigger-word mentions, then spawns a `ProcessMentionWorkflow` per mention. That workflow downloads the media (yt-dlp for videos, httpx for slideshow images), uploads to GCS, scans via Sightengine (AI generation + deepfake detection), caches results in Firestore, and dispatches a reply task to the replier's Temporal queue.

**detekt_replier** — Temporal worker that receives reply tasks. Uses Camoufox (anti-fingerprint Firefox) with Playwright to open the TikTok video page, click "Reply" on the original comment, @mention the user, type the result message with human-like typing delays, and post. Handles session rotation (12h TTL), status-8 detection, and automatic reboots.

## How scanning works

| Content type | Download | Scan |
|---|---|---|
| Video | yt-dlp → bytes → GCS `vids/{id}/video.mp4` | Sightengine `genai` + `deepfake` video sync (frame-by-frame, averaged) |
| Slideshow | httpx per image → GCS `pics/{id}/{n}.{ext}` | Sightengine `genai` + `deepfake` per image, max score across carousel |

Results are cached in Firestore by comment ID. Duplicate mentions are deduped by `mention:{cid}` documents.

The reply message is randomized from a pool of templates based on confidence level:
- High confidence AI → "yep, that's AI (92% sure)"
- High confidence deepfake → "real video but the face is swapped (87% sure)"
- Low confidence → "not sure on this one (54% AI generated/manipulated)"
- Real → "looks real to me (96% sure)"

## Secrets management

All secrets are managed via [Doppler](https://www.doppler.com/). Both containers run with `doppler run --` as the entrypoint, which injects secrets as environment variables. A background thread refreshes the secret cache every 30 seconds with a 120-second TTL.

## Infrastructure

Terraform manages all GCP resources:

| Resource | What |
|---|---|
| `google_compute_instance.dtkt_worker` | GCE VM (c2-standard-4), COS image, runs worker container |
| `google_compute_instance.dtkt_replier` | GCE VM (c2-standard-4, 30GB disk), COS image, runs replier container |
| `google_storage_bucket.dtkt_media` | GCS bucket for downloaded media, 7-day lifecycle delete |
| `google_firestore_database.dtkt_default` | Firestore Native database for scan results + dedup |
| Service accounts | Separate SAs for worker (storage admin, firestore, logging) and replier (storage read/write, logging) |

Region defaults to `europe-west2` (London).

## Deploying

```bash
# set up .env from example
cp .env.example .env
# edit with your GCP project and Doppler tokens

# deploy everything (builds both images, pushes to GCR, runs terraform)
deploy.bat

# or deploy a single service
deploy.bat worker
deploy.bat replier
```

PowerShell alternative:
```powershell
.\deploy.ps1 -Target all
.\deploy.ps1 -Target worker
.\deploy.ps1 -Target replier
```

This builds Docker images, pushes to GCR, and runs `terraform apply` with auto-approve.

## Environment variables

**Root** (`.env`):

| Var | What |
|---|---|
| `DTKT_GCP_PROJECT` | GCP project ID |
| `DTKT_WORKER_DOPPLER_TOKEN` | Doppler service token for the worker |
| `DTKT_REPLIER_DOPPLER_TOKEN` | Doppler service token for the replier |

**Worker secrets** (via Doppler):

| Var | What |
|---|---|
| `DTKT_TEMPORAL_HOST` | Temporal Cloud host |
| `DTKT_TEMPORAL_NAMESPACE` | Temporal namespace |
| `DTKT_TEMPORAL_API_KEY` | Temporal API key |
| `DTKT_TEMPORAL_TASK_QUEUE` | Replier's Temporal task queue name |
| `DTKT_POLL_INTERVAL_SECONDS` | Polling interval |
| `DTKT_TRIGGER_WORD` | Word that triggers the bot in comments |
| `DTKT_USER_BLACKLIST` | Comma-separated usernames to ignore |
| `DTKT_TT_SESSIONID` | TikTok session cookie |
| `DTKT_SENTRY_DSN` | Sentry DSN |
| `DTKT_BUCKET_NAME` | GCS bucket name |
| `DTKT_FIRESTORE_DATABASE` | Firestore database name |
| `DTKT_FIRESTORE_SCANS_COLLECTION` | Firestore collection name |
| `DTKT_SIGHTENGINE_ACC_POOL` | Enable Sightengine account pool (`true`/`false`) |
| `DTKT_SIGHTENGINE_ACCS` | JSON map of `{api_user: api_secret}` pairs |
| `DTKT_SIGHTENGINE_API_USER` | Single Sightengine API user (if not using pool) |
| `DTKT_SIGHTENGINE_API_SECRET` | Single Sightengine API secret |
| `DTKT_AI_THRESHOLD` | Score threshold for AI/deepfake classification |
| `DTKT_LOW_CONFIDENCE_MIN` | Lower bound for "unsure" range |
| `DTKT_LOW_CONFIDENCE_MAX` | Upper bound for "unsure" range |
| `DTKT_VIDEO_ENA` | Enable video scanning |
| `DTKT_PHOTO_ENA` | Enable photo/slideshow scanning |
| `DTKT_MAX_CAROUSEL_PHOTOS` | Max photos per carousel to scan |
| `DTKT_SUPPORTED_TYPES` | Comma-separated TikTok aweme types to process |
| `DTKT_UPSTASH_REDIS_URL` | Upstash Redis URL |
| `DTKT_UPSTASH_REDIS_TOKEN` | Upstash Redis token |
| `DTKT_RATE_LIMIT_WINDOW` | Rate limit window in seconds |
| `DTKT_RATE_LIMIT_MAX` | Max scans per user per window |
| `DTKT_WEBSHARE_API_KEY` | Webshare proxy API key |
| `DTKT_WEBSHARE_COUNTRY` | Proxy country code |
| `DTKT_WEBSHARE_PROXY_COUNT` | Number of proxy slots |
| `DTKT_PROXY_ENABLED` | Enable/disable proxy |

**Replier secrets** (via Doppler):

| Var | What |
|---|---|
| `DTKT_TEMPORAL_HOST` | Temporal Cloud host |
| `DTKT_TEMPORAL_NAMESPACE` | Temporal namespace |
| `DTKT_TEMPORAL_API_KEY` | Temporal API key |
| `DTKT_TEMPORAL_TASK_QUEUE` | Task queue to listen on |
| `DTKT_SENTRY_DSN` | Sentry DSN |
| `DTKT_BUCKET_NAME` | GCS bucket (for cookies + debug screenshots) |
| `DTKT_GCS_COOKIES_PATH` | GCS path to Netscape cookie file |
| `DTKT_GCP_SERVICE_ACCOUNT_JSON` | GCP SA JSON for GCS access |
| `DTKT_DBG_ENA` | Enable debug screenshots |
| `DTKT_GCS_DBGSC_PATH` | GCS path prefix for debug screenshots |
| Proxy vars | Same as worker |

## Security

See [SECURITY.md](SECURITY.md).

## Maintaining

See [MAINTAINING.md](MAINTAINING.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).
