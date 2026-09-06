# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app is

RallyMax: an AI-powered tennis swing analysis app (Expo — iOS/Android/web). Core loop: a user uploads a short video of their swing, marks the contact frame, the backend runs MediaPipe pose extraction on it, and compares the full swing trajectory against a database of 631 professional swing clips using Dynamic Time Warping (DTW) — returning the closest pro match, a 0–100 similarity score, and coaching tips.

**Before doing anything else, read `HANDOVER.md`** (the "Quick status" line near the top and "⚠️ Read This First") and `TODO_MANUAL.md` (things only a human can do — struck-through items are resolved). Both are actively maintained, append-only project logs with the real current state, known gaps, and in-flight work. This file documents structure and commands; it does not duplicate that narrative and will not be kept in sync with it session-to-session.

**If you're a human catching up, not a Claude session picking up work:** read `STATUS.md` instead first. It's a short, hand-curated, actively-overwritten snapshot (not a log) — the other two docs above are comprehensive but long (1000+ lines each of chronological history), and `STATUS.md` exists specifically to answer "where do things stand?" in under 2 minutes.

## Commands

### Backend (`backend/`)
```
cd backend
npm run dev       # nodemon, hot-reload, port 5000
npm start         # node src/server.js, no reload
npm test          # jest + supertest
npm run verify:db # read-only check of backend/data/app.db against src/domain/invariants.js; exits 1 on violation, safe against production
npx jest src/routes/drills.test.js   # run a single test file
```
Tests are colocated with routes (e.g. `src/routes/drills.test.js`, `history.test.js`, `highlights.test.js`, `dev.drills.test.js`, and the newer `*.validation.test.js` files). Most route files still have **zero** behavioral test coverage beyond input validation — a known, tracked gap, not an oversight to silently "fix" at scale.

**Shared validation/invariant layer** (`src/domain/invariants.js`, `src/validation/validateBody.js`, `src/domain/integrityChecks.js`): domain rules (vocabularies, cross-field constraints) are defined once in `invariants.js` and consumed two ways — `validateBody.js` rejects bad input at write time (400s), `integrityChecks.js` re-checks the same rules against data already at rest (`npm run verify:db` / `backend/scripts/verifyIntegrity.js`). When adding a new field constraint, add it to `invariants.js` rather than inlining an `if` check in a route, so both consumers stay in sync.

**Route auth convention is enforced, not just documented** (`src/routeAuthConvention.test.js`, `src/domain/routeAuthExceptions.js`): every route must carry `requireAuth` or `optionalAuth` in its actual Express middleware chain, or be explicitly listed with a reason in `routeAuthExceptions.js`. This guards against a real free-tier-cap bypass (2026-08-22) caused by a route silently missing both. A new route with neither will fail this test at CI/`npm test` time rather than shipping unauthenticated by accident — add auth middleware, or add a reasoned exception if it's deliberately public (e.g. pre-login auth routes, the RevenueCat webhook).

### Frontend (`frontend/`)
```
cd frontend
npm start           # expo start
npm run web         # expo start --web
npm run android
npm run ios
```
**`frontend/AGENTS.md` is a standing instruction, not optional context: Expo has changed significantly — read the versioned docs at https://docs.expo.dev/versions/v54.0.0/ before writing any frontend code.** `frontend/CLAUDE.md` just points here (`@AGENTS.md`). One specific trap it flags: `expo-av` is deprecated on SDK 54 (removed in 55) but is still used deliberately (`components/PlatformVideo.native.js`, `utils/sounds.js`) — don't "helpfully" migrate it to `expo-video`/`expo-audio`; that's a deferred item tracked in `TODO_MANUAL.md` for the SDK 55 upgrade.

### Python ML pipeline (`scripts/`)
```powershell
cd scripts
.\venv\Scripts\activate
pytest
```
`pytest.ini` restricts collection to `test_*_pytest.py`. Other files matching `test_*.py` (e.g. `test_net_detector_labeled_set.py`) are manual diagnostic scripts (argparse-driven, print results, hardcoded paths) — not real pytest suites. Don't try to make pytest collect them; new automated suites should follow the `*_pytest.py` naming so they're picked up automatically.

## Architecture

```
Expo frontend  ──multipart/JSON──▶  Express backend (port 5000)
                ◀──JSON response──   │
                                     │ child_process.spawn
                                     ▼
                          Python ML pipeline (scripts/venv)
                          MediaPipe pose + DTW comparison
                                     │ reads
                                     ▼
                    data/06_pro_database/pro_database.json
                    (631 pre-computed pro swing trajectories)
```

The backend **never runs ML code in-process** — it always shells out to a Python script via `child_process.spawn`, reads stdout as JSON, and forwards it to the client. Two live entry points in `scripts/08_comparison_engine/`:
- **`compare_swing.py`** — pro-database match, invoked from `backend/src/routes/analyse.js` via a thin CLI wrapper (`backend/src/services/pro_matcher.py`). This is the only endpoint the live app actually uses.
- **`compare_videos.py`** — direct 1-vs-1 video comparison (premium feature), invoked from `backend/src/routes/compareVideos.js`.

## The numbered `scripts/` pipeline

`scripts/` is organized into numbered stages, each in its own `scripts/NN_<name>/` folder. Stages `01_data_collection` through `06_database_build` are the **offline pipeline that already built the 631-entry pro database** — you should not need to re-run them unless adding new source footage. `07_ball_racket_tracking` and `10_net_detection` are auxiliary trained keypoint models used by later stages. `08_comparison_engine` is the live inference code described above. `09_coaching_ai` is the (currently unused) teacher-student coaching-tip selector. `11`–`17` cover highlight clipping, video crop/overlay utilities, shot classification, batch analysis, shot verification, and amateur-footage evaluation. See `HANDOVER.md`'s "The Data Pipeline" section for a per-stage breakdown of what each script does and why — it's detailed enough that re-deriving it from the code alone is slower than reading it there first.

## Find Games (courts, clubs, watches)

Courts are sourced from OpenStreetMap (`backend/src/utils/overpassCourts.js`, Overpass API) and clustered into clubs via `backend/scripts/clusterCourts.js`: courts are nodes in a graph, an edge connects two courts ≤100m apart (`backend/src/utils/geo.js` haversine distance), and a club is one connected component — not a running-centroid heuristic, so a long line of closely-spaced courts correctly becomes one club. Postcodes are resolved via postcodes.io (free, no API key — chosen over paid Google Geocoding) and backfilled onto existing court/club rows with `backend/scripts/backfillPostcodes.js`. Club naming is crowd-sourced the same way court verification already worked: a user proposes a name, two others confirm it — no paid lookup needed. Users can watch a specific court, an entire club, or an arbitrary map area (pin + radius); `GET /courts` reports which are already watched so the map can render watched-state on load.

## Database

SQLite via `better-sqlite3`, at `backend/data/app.db` — **not** the Postgres implied by `DATABASE_URL` in `backend/.env`. Postgres was never installed; SQLite was chosen for zero-install dev velocity, with Postgres as the intended eventual production target. `pg`, `redis`, and `bull` are installed backend dependencies but unused (`require()`'d nowhere) — leftovers from initial scaffolding.

## Deployment

Since 2026-08-25 the hosted backend **does** auto-deploy: a `git push` to `master` that touches `backend/**`, `scripts/**`, `Dockerfile`, `docker-compose.yml`, or `Caddyfile` triggers `.github/workflows/deploy.yml`, which SSHes in, runs `git pull && docker compose up --build -d app`, and polls `/health`. Doc-only commits don't trigger it; it can also be run manually from the Actions tab. What's still manual: transferring new files under `data/` to the server (gitignored, never touched by CD) and editing `backend/.env` on the server directly. See `DEPLOY.md`'s "Continuous deployment" section for the full mechanics.
