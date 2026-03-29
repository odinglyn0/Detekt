# Contributing

1. Fork the repo and create a branch from `main`.
2. Keep changes scoped — worker and replier are independent services with their own Dockerfiles and dependency sets.
3. Don't commit secrets, `.env` files, or Terraform state. The `.gitignore` already covers these.
4. If you're touching `detekt_replier/tiktok.py`, test against a real TikTok page — the selectors (`[data-e2e="comment-reply-1"]`, `[data-e2e="comment-post"]`, etc.) are reverse-engineered and change without notice.
5. Open a PR with a clear description of what changed and why.
