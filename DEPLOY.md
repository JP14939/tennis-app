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
