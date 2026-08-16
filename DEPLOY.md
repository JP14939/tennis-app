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

## Deploying on an Oracle Cloud "Always Free" VM

Oracle's Always Free tier (an Ampere A1 ARM instance: up to 4 OCPUs, 24GB
RAM, 200GB block storage, free forever) is a genuinely free fit for this
app's storage (~12GB+ of pro clips) and compute (torch/mediapipe/
ultralytics) needs, where most free PaaS tiers aren't. A few things the
generic steps above don't cover:

1. **Open the port.** Oracle's default security list blocks all inbound
   traffic. In the VM's VCN → Security List (or Network Security Group),
   add an ingress rule for TCP port 5000 (or whatever `PORT` is set to),
   source `0.0.0.0/0`, plus TCP 22 if not already open for SSH. Skipping
   this is the most common reason a freshly-deployed Oracle instance is
   unreachable even though the container is running fine.
2. **ARM architecture.** Ampere A1 is aarch64, not x86_64. The pinned
   versions in `scripts/requirements.txt` (torch, opencv-contrib-python,
   ultralytics, mediapipe) all ship aarch64 wheels as of the versions
   pinned here, but confirm with a `docker compose build` on the VM before
   relying on it — a missing wheel would force a slow from-source compile
   or fail outright.
3. **Survive reboots.** `docker-compose.yml`'s `app` service already has
   `restart: unless-stopped`, so a VM reboot (Oracle occasionally reboots
   free-tier instances for host maintenance) brings the container back up
   without manual intervention.
4. **Data transfer.** Same caveat as step 3 above — `rsync -avz data/
   ubuntu@<vm-ip>:/path/to/tennis_app/data/` from your dev machine. This
   is the slowest part of the whole setup; consider transferring only the
   subset actually needed at runtime (`04_clips/`, `04_clips_cropped/`,
   `06_pro_database/`) rather than the full `data/` directory if bandwidth
   is limited — the rest (source videos, pose-extraction intermediates,
   training artifacts) is only needed for rebuilding the pro database, not
   for serving requests.

## Working around Ampere capacity errors

Oracle's Ampere A1 "Always Free" shape is popular enough that "Out of host
capacity" on instance creation is one of the most common things people hit
with this exact free tier — it's not a sign anything above was configured
wrong. In roughly increasing order of effort:

1. **Try every Availability Domain in your home region.** Capacity is
   tracked per-AD, not per-account/region. The instance-creation screen
   (Compute → Instances → Create Instance → Placement) lets you pick
   AD-1/2/3 explicitly instead of "Let Oracle choose" — cycle through all of
   them before concluding the region itself is out.
2. **Request a smaller Ampere shape.** Ask for e.g. 2 OCPU / 12GB or
   1 OCPU / 6GB instead of the max 4 OCPU / 24GB (the "Specialty and
   previous generation" → `VM.Standard.A1.Flex` shape lets you set OCPU
   count and memory independently). Partial allocations succeed more often
   than the full-size request, and you can flex it back up later once
   capacity allows, without recreating the instance. Tradeoff worth
   weighing: this app's torch/mediapipe/ultralytics stack wants real
   headroom, so 1 OCPU / 6GB is a genuine constraint on request/analysis
   throughput, not just a formality — treat it as a temporary step, not the
   final target.
3. **Try a different home region**, if your account allows it. This is a
   one-way choice if you already have any resource (including a VCN) in
   your current home region, so check Governance → Tenancy Details →
   "Home Region" and confirm nothing's provisioned there yet before
   switching.
4. **Run a scripted retry loop.** This is the standard community
   workaround for this specific error. With the OCI CLI installed and
   configured (`oci setup config`, using an API key generated from your
   user's console profile), something like:

   ```bash
   #!/usr/bin/env bash
   # retry-launch.sh -- keeps attempting an Ampere A1 instance launch until
   # Oracle has capacity. Fill in the OCIDs from your tenancy first.
   set -u
   while true; do
     oci compute instance launch \
       --availability-domain "<AD-name>" \
       --compartment-id "<compartment-ocid>" \
       --shape "VM.Standard.A1.Flex" \
       --shape-config '{"ocpus":4,"memoryInGBs":24}' \
       --image-id "<ubuntu-arm-image-ocid>" \
       --subnet-id "<subnet-ocid>" \
       --assign-public-ip true \
       --display-name "tennis-app-vm" \
       --wait-for-state RUNNING && break
     echo "$(date): still out of capacity, retrying in 5m..."
     sleep 300
   done
   ```

   Leave it running in a terminal (or `tmux`/background) — it'll exit once
   the launch actually succeeds. Expect this to take anywhere from minutes
   to days depending on region/shape demand.

## If none of that works in a reasonable time

Fall back to a small paid VPS (Hetzner CX-class, DigitalOcean, Linode — a
few $/month) instead of continuing to wait on Oracle. This requires **zero**
changes to the `Dockerfile` or `docker-compose.yml` above — the same
`docker compose up --build app` runs unchanged on any Docker host. You lose
the "free forever" property and need to size the box yourself (this app's
Python stack wants at least 2 vCPU / 4GB+ RAM comfortably, more if you're
serving concurrent analysis requests), but you gain a VM that's actually
available today. Migrating to Oracle later, if capacity frees up, is just
repeating the "one-time setup on the server" steps above on the new host —
nothing about the app or this Dockerfile is Oracle-specific.

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
