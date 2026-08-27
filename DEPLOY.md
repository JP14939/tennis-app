# Deploying the backend

This covers running the backend (Node + its Python ML pipeline) on a real
server via Docker. It does **not** cover the frontend (that's a separate
Expo app — see `frontend/.env.example` for pointing a build at whatever
server you deploy here), a database migration off SQLite, or payment
integration — those are separate, later decisions.

## Before anything else

**Rotate `ANTHROPIC_API_KEY` in `backend/.env`.** It's been sitting exposed
since early in this project. That's been an accepted risk for solo,
dev-time use — it is not an acceptable risk once real user traffic hits
this server. Get a fresh key from console.anthropic.com before going
further.

## One-time setup on the server

1. Install Docker.
2. Copy the repo to the server (git clone, or however you prefer).
3. **Transfer `data/` to the server.** It's gitignored (12GB+, not suited
   for git without LFS — see `.gitignore`), so it never lands on the server
   via `git clone`. `rsync -avz data/ user@server:/path/to/tennis_app/data/`
   (or scp, or a cloud storage bucket — whatever fits your bandwidth) from
   this machine. Without this, the app starts fine but every request that
   needs the pro database or trained model weights will fail.
4. Create `backend/.env` on the server (it's gitignored, same as local dev)
   with a real `JWT_SECRET`, the rotated `ANTHROPIC_API_KEY`, and `PORT=5000`.
   The Stripe/AWS/Postgres/Redis placeholders can stay empty — unused today.

## Build and run

```bash
docker compose up --build app
```

This builds the image from the repo-root `Dockerfile` (Node 22 + Python
3.13 + the exact dependency set in `scripts/requirements.txt`, installed
into a venv at `scripts/venv` — the same layout the code already expects
locally) and starts it with `data/` and `backend/data/` mounted as volumes,
per the `app` service in `docker-compose.yml`.

Confirm it's up:
```bash
curl http://localhost:5000/health
```

## What's intentionally *not* in the image

- `data/` and `backend/data/app.db` — mounted as volumes (see step 3 above),
  not baked in. This is a direct consequence of `data/` being gitignored;
  if that ever changes (e.g. moving to a proper artifact store), this can
  be revisited.
- `.env` — never copied into the image (`.dockerignore`); supplied at
  runtime via `env_file` in `docker-compose.yml` so secrets don't end up
  baked into an image layer.
- The `frontend/` app — this Dockerfile is backend-only.

## Current host

The live backend runs on a small paid Hetzner VPS (a few $/month, x86_64) —
this requires **zero** changes to the `Dockerfile` or `docker-compose.yml`
above, the same `docker compose up --build app` runs unchanged on any Docker
host. Sizing note: this app's Python stack (torch/mediapipe/ultralytics)
wants at least 2 vCPU / 4GB+ RAM comfortably, more if serving concurrent
analysis requests. Nothing about the app or this Dockerfile is tied to any
specific cloud provider — the generic steps above are all that's needed on
a fresh VPS from any provider.

## Continuous deployment (added 2026-08-25)

A `git push` to `master` (or a merge landing on it) now auto-redeploys, via
`.github/workflows/deploy.yml`. It's scoped to only fire on paths that actually
affect the running app (`backend/**`, `scripts/**`, `Dockerfile`,
`docker-compose.yml`, `Caddyfile`) so doc-only commits — including the scheduled
docs-round-up routine's direct pushes to master — don't trigger a pointless
rebuild. It can also be triggered manually from the Actions tab
(`workflow_dispatch`), useful right after merging one of the scheduled review
PRs if you don't want to wait for the merge-commit push to fire it.

**What's automatic now:** SSH into the server as a dedicated, restricted deploy
user/key (not the personal `rallymax_key`), run the same `git pull && docker
compose up --build -d app` this doc already documents, then poll `/health` and
fail the workflow loudly if the app doesn't come back up.

**What's still manual (unchanged):**
- The one-time `data/` transfer to a fresh server, and any later `data/`
  additions (new ML model weights, pro-database rebuilds) — these files are
  gitignored and large, so CD only ever redeploys *code*, never `data/`. Same
  `rsync`/`scp`/`tar` steps as above.
- `backend/.env` changes — CD doesn't touch environment variables; edit them
  on the server directly and restart if needed.
- The very first setup of the deploy key + `authorized_keys` restriction on a
  new server (see the repo's CD plan / commit for the exact
  `command="..."` forced-command line) — one-time per server, not part of the
  automated flow.

Fallback: the manual `docker compose up --build app` flow above still works
unchanged if the automated pipeline is ever down or you want to sanity-check
a deploy by hand.

---

## Known gaps this doesn't address

- **Database**: still SQLite (`backend/data/app.db`), fine for a single
  container but doesn't support multiple app instances or heavy concurrent
  writes. Migrate to the `postgres` service already sitting (unused) in
  `docker-compose.yml` if/when that becomes necessary.
- **Payments**: no Stripe/StoreKit integration exists yet — `tier` is a
  real column but nothing charges anyone.
- **Persistent calibration server**: `calibration_server.py` is spawned by
  `server.js` on boot and holds a ~300MB model in memory. If the container
  restarts often (e.g. a rolling-deploy setup), confirm this doesn't leak
  processes the way it did once during local dev (see the port-conflict
  guard already in `calibration_server.py` and the "already running" check
  in `server.js` — both exist specifically because of that incident).
