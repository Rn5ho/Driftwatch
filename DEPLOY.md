# Deploying DriftWatch to the Hetzner VPS

One Docker container runs everything: the FastAPI backend (scheduler included) serving the built React dashboard. SQLite persists in `./data/` on the host.

## First deploy

```bash
# On the VPS (Ubuntu/Debian), once:
curl -fsSL https://get.docker.com | sh

# From your Mac — copy the project (or use git):
rsync -av --exclude backend/.venv --exclude frontend/node_modules --exclude backend/driftwatch.db \
  ~/Desktop/my-project/driftwatch/ user@VPS_IP:~/driftwatch/

# On the VPS:
cd ~/driftwatch
cp backend/.env.example backend/.env   # then edit: add ANTHROPIC_API_KEY
docker compose up -d --build
docker compose logs -f                 # watch ingestion start
```

## Access the dashboard

The container is bound to `127.0.0.1` on the VPS — it is **not** reachable from the internet (the dashboard has no authentication; keep it that way). From your Mac:

```bash
ssh -L 8000:127.0.0.1:8000 user@VPS_IP
# then open http://localhost:8000
```

Nicer long-term option: install Tailscale on the VPS and your Mac, then bind to the tailnet IP instead.

## Operations

```bash
docker compose logs -f --tail 100     # logs (scheduler, analyst, trades)
docker compose restart                # restart
docker compose up -d --build          # redeploy after code changes

# Backup — do NOT plain-copy the DB while the app is writing (torn copy risk).
# sqlite3's online backup is safe against a live database:
sqlite3 data/driftwatch.db ".backup 'backups/driftwatch-$(date +%F).db'"
```

## Notes

- The forecast ledger in `data/driftwatch.db` is the product — set up a daily backup cron using `sqlite3 .backup` (safe while running; a plain `cp` of a live DB can produce a torn, corrupt copy).
- Cost control: the analyst model is set in `backend/.env` (`DRIFTWATCH_ANALYST_MODEL`). Watch the first day of logs to see call volume before leaving it unattended on Opus.
- Without `ANTHROPIC_API_KEY` the system still ingests and snapshots markets; analysis waits (events queue unprocessed).
