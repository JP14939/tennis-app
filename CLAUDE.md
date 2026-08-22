# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app is

RallyMax: an AI-powered tennis swing analysis app (Expo — iOS/Android/web). Core loop: a user uploads a short video of their swing, marks the contact frame, the backend runs MediaPipe pose extraction on it, and compares the full swing trajectory against a database of 631 professional swing clips using Dynamic Time Warping (DTW) — returning the closest pro match, a 0–100 similarity score, and coaching tips.

**Before doing anything else, read `HANDOVER.md`** (the "Quick status" line near the top and "⚠️ Read This First") and `TODO_MANUAL.md` (things only a human can do — struck-through items are resolved). Both are actively maintained, append-only project logs with the real current state, known gaps, and in-flight work. This file documents structure and commands; it does not duplicate that narrative and will not be kept in sync with it session-to-session.

## Commands

### Backend (`backend/`)
```
cd backend
npm run dev     # nodemon, hot-reload, port 5000
npm start       # node src/server.js, no reload
npm test        # jest + supertest
npx jest src/routes/drills.test.js   # run a single test file
```
Tests are colocated with routes (e.g. `src/routes/drills.test.js`, `history.test.js`, `highlights.test.js`, `dev.drills.test.js`). Most route files have **zero** test coverage — this is a known, tracked gap, not an oversight to silently "fix" at scale.

### Frontend (`frontend/`)
```
cd frontend
npm start           # expo start
npm run web         # expo start --web
npm run android
npm run ios
```
**`frontend/AGENTS.md` is a standing instruction, not optional context: Expo has changed significantly — read the versioned docs at https://docs.expo.dev/versions/v54.0.0/ before writing any frontend code.** `frontend/CLAUDE.md` just points here (`@AGENTS.md`).

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

## Database

SQLite via `better-sqlite3`, at `backend/data/app.db` — **not** the Postgres implied by `DATABASE_URL` in `backend/.env`. Postgres was never installed; SQLite was chosen for zero-install dev velocity, with Postgres as the intended eventual production target. `pg`, `redis`, and `bull` are installed backend dependencies but unused (`require()`'d nowhere) — leftovers from initial scaffolding.

## Deployment gotcha

The hosted backend does **not** auto-deploy. A `git push` does not reach it. Going live requires SSH'ing into the server, `git pull`, then `docker compose up --build app` — and if `data/` gained new files, those need a manual copy over too (see `DEPLOY.md` and `HANDOVER.md` item #41 for the full mechanics and past gotchas encountered doing this).
