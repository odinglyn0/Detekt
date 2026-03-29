# Maintaining

## Rotating TikTok sessions

The worker uses a `sessionid` cookie (`DTKT_TT_SESSIONID` in Doppler). When TikTok invalidates it, polling will start returning status 3102/3006. Update the secret in Doppler; the worker's background refresh thread picks it up within 30 seconds.

The replier uses a Netscape cookie file in GCS (`DTKT_GCS_COOKIES_PATH`) — upload a fresh one there.

## Session reboots

The replier's Camoufox browser session rotates every 12 hours and reboots immediately on TikTok status-8 responses. If replies start failing consistently, check Sentry for `SessionRebootError` patterns — usually means cookies are stale.

## Updating dependencies

Both services pin Temporal at `1.24.0` and Playwright at their respective versions. Bump carefully — TikTok's DOM selectors in `detekt_replier/tiktok.py` are fragile and may break across Playwright versions or TikTok frontend deploys.

## Terraform state

State is local (`terraform/terraform.tfstate`). Back it up or migrate to a remote backend before collaborating.

## Debug screenshots

Set `DTKT_DBG_ENA=true` and `DTKT_GCS_DBGSC_PATH` in Doppler to capture 0.5s-interval screenshots of the replier's browser session to GCS. Useful for diagnosing reply failures.

## Pushing
Run black . on all of your code, and do not PR or push with any code comments, I hate code comments.