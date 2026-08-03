# TennisAI — Full Project Handover

**Last updated:** 2026-08-03
**User:** Jack Price (jack.p14370@gmail.com)
**Project root:** `C:\Users\jackp\tennis_app\`

This document replaces the previous HANDOVER.md, which was last updated 2026-07-31 and had drifted significantly from reality (it predates the DTW rewrite, the entire premium-feature frontend, and the auth system). Everything below was verified directly against the current filesystem and codebase while writing this — not recalled from memory.

---

## What This App Does

AI-powered tennis swing analysis mobile app (iOS/Android/web via Expo).

**Core loop (fully working):** user uploads a short video of their swing → marks the exact contact frame (rough scrub + frame-by-frame fine adjustment) → backend extracts MediaPipe pose landmarks → compares the full swing trajectory (not just contact frame) against a database of 631 professional swing clips using Dynamic Time Warping → returns the closest pro match, a 0–100 similarity score, camera-angle context, and coaching tips.

**Also present as frontend-only previews (no backend behind them yet):** direct 1-vs-1 video comparison ("upload a video you want to copy"), and a highlight-archive tool that's meant to auto-clip individual shots out of a full match video.

**Also present as a real, working system:** email/password authentication with a free/premium tier flag on each account — but nothing currently checks that tier to gate anything, and there's no payment processing.

---

## ⚠️ Read This First

1. **The Anthropic API key in `backend/.env` is still the one that was exposed in chat earlier in this project and has never been rotated.** It has been sitting in plaintext, re-read by tooling, for the entire project so far. Rotate it at console.anthropic.com before doing anything else security-sensitive.
2. **Nothing beyond the very first commit ("Initial project structure") is committed to git.** `git status --short` currently shows the entire backend auth system, the entire data/ pipeline output, the entire frontend screen set, and this handover file as untracked/modified. If something goes wrong with the working directory, there is no version history to fall back on. Commit before doing anything destructive.
3. The database is **SQLite** (`backend/data/app.db`), not the Postgres that `backend/.env`'s `DATABASE_URL` implies. Postgres was never installed on this machine. See the Backend section for why and what would need to change to migrate.

---

## Environment

| Tool | Version | Notes |
|---|---|---|
| Node.js | 22.18.0 | |
| Python | 3.13.6 | venv at `scripts/venv/` — activate before running any script |
| Expo SDK | 54 | Matches user's Expo Go on iPhone |
| Database | SQLite (`backend/data/app.db`) | Not Postgres — see Backend section |
| Docker | Installed, `docker-compose.yml` present | **Not currently needed.** Nothing in the running app depends on Docker, Postgres, or Redis right now, despite `pg`, `redis`, and `bull` being installed as backend dependencies — they're unused leftovers from initial scaffolding. |

**Python venv** — activate before running any script directly:
```powershell
cd C:\Users\jackp\tennis_app\scripts
.\venv\Scripts\activate
```

**MediaPipe** — `mp.solutions.pose` is not used anywhere in this codebase; everything goes through the Tasks API:
```python
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
# Model file: scripts/pose_landmarker.task
```

---

## API Keys & Secrets (`backend/.env`)

```
PORT=5000
NODE_ENV=development
DATABASE_URL=postgresql://...        # UNUSED — see Backend/Database section
JWT_SECRET=<random 32-byte hex>       # generated this session, used to sign auth tokens
ANTHROPIC_API_KEY=<LEAKED, NOT ROTATED>
AWS_REGION / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / S3_BUCKET   # placeholders, never configured
STRIPE_SECRET_KEY / STRIPE_PUBLISHABLE_KEY                          # placeholders, never configured
REDIS_URL                                                            # placeholder, Redis is not used
```

`.env` is gitignored (confirmed). `frontend/.env.example` was deleted at some point (shows as `D` in git status) and never replaced.

---

## Architecture Overview

```
┌─────────────────────┐     multipart/JSON      ┌──────────────────────┐
│   Expo frontend      │ ───────────────────────▶│  Express backend      │
│   (React Native, web │ ◀─────────────────────── │  (Node, port 5000)    │
│   + native)           │      JSON responses      └──────────┬───────────┘
└─────────────────────┘                                       │
                                                    child_process.spawn
                                                                │
                                                                ▼
                                                    ┌──────────────────────┐
                                                    │  Python ML pipeline   │
                                                    │  (scripts/venv)       │
                                                    │  MediaPipe pose +     │
                                                    │  DTW comparison       │
                                                    └──────────┬───────────┘
                                                                │ reads
                                                                ▼
                                                    data/06_pro_database/
                                                    pro_database.json
                                                    (631 pre-computed pro
                                                     swing trajectories)
```

The backend never runs ML code in-process — it always shells out to a Python script via `child_process.spawn`, reads stdout as JSON, and forwards it to the client. This is true both for the working pro-database matcher and for the built-but-unwired 1v1 comparison engine.

---

## The Data Pipeline (`scripts/`, numbered by stage)

This is the offline pipeline that built the 631-entry pro database. All of it has already been run — you should not need to re-run stages 1–6 unless adding new source footage. Every script lives under `scripts/<NN>_<name>/`.

### `01_data_collection/`
- **`download_videos.py`** — downloads source compilation videos via `yt-dlp`. Requires `--js-runtimes node` flag (fixed this project — YouTube 403s without it; `deno` isn't installed on this machine so `node` is the working runtime). Format string simplified to `best[ext=mp4]/best` because `ffmpeg` (needed for the usual `bestvideo+bestaudio` merge) isn't installed.
- **`process_new_videos.py`** — orchestrates pose extraction → swing detection → clip extraction for a batch of newly downloaded videos in one call, with a `swing_id_offset` parameter so IDs don't collide with existing compilations.

Source videos currently on disk (`data/01_source_videos/<shot>/`): 3 forehand compilations, 4 backhand compilations, 2 serve compilations.

### `02_pose_extraction/`
- **`extract_poses.py`** — runs MediaPipe Tasks API pose detection across a full source video. **Samples every 3rd frame** (`sample_every=3`, ~20fps effective from 60fps source) — this exact stride matters, see the DTW calibration bug below.
- **`test_mediapipe.py`** — throwaway sanity-check script, not part of the pipeline.

Output: `data/02_pose_extraction/<shot>_poses.json` (and `_2`, `_3` etc. for additional compilations), each a list of `{frame, timestamp, landmarks}` where `landmarks` is a dict of the 33 MediaPipe landmark names to `{x, y, z, visibility}`.

### `03_swing_detection/`
- **`detect_swings.py`** — finds swing peaks via smoothed wrist velocity (a local maximum in wrist speed = the contact moment). `PRE_SWING_SEC=1.0`, `POST_SWING_SEC=2.0` define the clip window around each detected peak. `build_swing_clips()` computes `start_frame`/`end_frame`/timestamps for each detected swing. Accepts a `swing_id_offset` param (1000/2000/3000 etc.) so multiple compilations per shot type don't collide on swing IDs.
- **`dry_run_confidence.py`**, **`preview_confidence.py`** — diagnostic/tuning helpers, not part of the production path.

Output: `data/03_swing_detection/<shot>_swings*.json` — each swing has `swing_id`, `peak_frame`, `peak_time_sec`, `start_frame`, `end_frame`, `confidence`, etc. **Note: this stage only detects *that* a swing happened (via wrist velocity) — it has no concept of forehand vs. backhand vs. serve.** Shot type is always known from which source video/compilation the swing came from, assigned manually per `JOBS` entry in `build_pro_database.py`. There is no automatic shot classifier anywhere in this codebase.

### `04_clip_extraction/`
- **`extract_clips.py`** — validates each detected swing (checks pose signals are sane) and cuts a ~3s clip per swing using the window from `detect_swings.py`.
- **`review_swings.py`** — manual review helper for spot-checking clips.

Output: `data/04_clips/<shot>/<shot>_swing_NNNN_confXXX.mp4` (rejected candidates go to `<shot>_rejected/` subfolders), plus `data/03_swing_detection/<shot>_swings*_validated.json` with `clip_path` added to each swing record.

### `05_angle_detection/`
- **`infer_angle.py`** — infers camera angle (0–90°) from a video using **Hough line net detection** — explicitly *not* MediaPipe's z-depth, which was found unreliable. Detects the tennis net as a horizontal line in the middle 25–75% of the frame; `angle = arccos(net_width / 0.80)`. Samples 3 frames and uses the median net width. Has a banner-rejection heuristic (a wide, *consistent*-across-frames line is an advertising board, not a net — real nets vary in apparent width as the player moves; `MAX_NET_FRACTION=0.75` rejects anything wider). Falls back to sampling a wider window in the *source* video (`infer_angle_from_source()`) when clip-level detection fails, at lower confidence (0.6 vs 0.7 base).
- Known limitation carried over from before: a camera positioned behind the baseline looks geometrically identical to a true side view (narrow net either way) — some high-angle (>65°) entries may be misclassified. Never manually audited.

### `06_database_build/`
- **`build_pro_database.py`** — the stage that assembles the actual pro database.
  - `KEY_LANDMARKS` = 9 upper-body points (nose, shoulders, elbows, wrists, hips) — legs are ignored.
  - `normalise_landmarks(lm_dict, scale)` — translates landmarks so the shoulder midpoint is `(0,0)`, then divides by `scale`. **This was rewritten this session** — see "The DTW Score Calibration Fix" below for why `scale` is now a required, precomputed parameter instead of each frame computing its own shoulder width.
  - `trajectory_scale(lm_dicts)` — **new this session.** Computes the *median* shoulder width across an entire swing's frame window, used as the single stable `scale` for every frame in that trajectory.
  - `extract_swing_trajectory(swing, pose_index, fps)` — samples every available pose frame from `PRE_SEC=0.5` before to `POST_SEC=1.0` after the peak/contact frame (not fixed snapshots — the full motion path, for DTW). Requires `MIN_TRAJECTORY_POINTS=5` or returns `None`.
  - `JOBS` — a hardcoded list of 9 entries (one per source compilation), each mapping a pose-extraction file + validated-swings file + shot type. This is where shot-type labeling actually happens (manually, by construction, per compilation).
  - `build_database()` — runs the above across all 9 jobs, also invoking `infer_camera_angle()` per swing, and writes `data/06_pro_database/pro_database.json`.
- **`trajectory_compare.py`** — the DTW machinery:
  - `_frame_dist(a, b, key_landmarks)` — average per-landmark Euclidean distance between two landmark snapshots.
  - `dtw_distance(traj_a, traj_b, key_landmarks)` — classic DTW cost-matrix alignment, returns total path cost normalized by `max(n, m)`.
  - `contact_landmarks(trajectory)` — returns the snapshot closest to `t=0` (the contact frame) from a trajectory, used for tip generation.

**Current database state (verified):** `data/06_pro_database/pro_database.json` — **631 entries** (forehand 320, backhand 221, serve 90), each with a full ~29-point trajectory (not fixed 3-snapshot vectors). 5 backup snapshots preserved in the same folder from earlier filtering/rebuild passes, most recently `pro_database_backup_pre_normalization_fix.json` (the pre-fix version, kept in case the fix needs to be reverted or compared against).

### `07_ball_racket_tracking/` — racket keypoint ML (built, working, not integrated into the live comparison)
This subfolder has the most files because it went through multiple failed approaches before landing on one that worked:
- **`sample_racket_crops.py`** — samples racket-detected frames from clips (using YOLO's pretrained `yolo11n.pt`/`yolo11s.pt` for racket bounding boxes) and crops around the racket for keypoint labeling.
- **`labels.json`** (`data/09_racket_keypoints/labels.json`) — **220 total labeled crops**, 5 keypoints each (handle, throat, tip, left_edge, right_edge), labeled via Claude's vision across many turns of an earlier session.
- **`train_racket_keypoints.py`** — **abandoned approach**: direct-regression model (frozen MobileNetV3-Small backbone + custom head). With 84 examples got val MSE 0.044 (~21% pixel error); retraining with all 127 usable examples made it *worse* (val MSE 0.064). Direct regression on this small a dataset didn't scale.
- **`prepare_yolo_pose_dataset.py`** — converts `labels.json` into YOLO-pose training format. Had a bug (fixed): didn't clamp keypoints to image bounds, so ~1/3 of images were silently rejected by YOLO's loader as "corrupt" whenever a labeled point was extrapolated slightly outside the crop (for partially cut-off features). Fixed by clamping before computing bbox/normalized keypoints.
- **`train_yolo_pose_racket.py`** — **the approach that worked**: fine-tunes `yolo11n-pose.pt` for a 5-point racket skeleton (`kpt_shape=[5,3]`, `flip_idx=[0,1,2,4,3]` to correctly swap left/right edge under horizontal flip augmentation).
  - **Verified final result** (read directly from `data/09_racket_keypoints/yolo_pose_run/results.csv`, epoch 150/150): **Box mAP50 = 0.927, Pose mAP50 = 0.485.** (Note: an earlier session summary cited 0.947/0.412 for these two numbers — the values above are read directly from the actual results file and should be treated as authoritative.)
  - Trained weights: `data/09_racket_keypoints/yolo_pose_run/weights/best.pt` and `last.pt`.
- **`validate_racket_keypoints.py`**, **`validate_yolo_pose_racket.py`** — visualization/validation scripts; visually confirmed the YOLO-pose model as a real, usable (if imperfect — handle placement is the weakest point) result.
- **`audit_ball_visibility.py`** / **`filter_by_ball_visibility.py`** — a separate, orthogonal filter: excludes pro-database entries where the ball isn't visible near the estimated contact point (those clips can't be reliably calibrated against a user's manually-marked contact frame). This filter is what turns the ~914 raw database entries into the final 631 — see "How to rebuild the pro database" below. Filter decisions live in `data/07_audits/ball_visibility_audit.json`.
- **`batch_validate_contact.py`** — batch contact-point validation helper.

**This entire racket-keypoint model is trained and sitting on disk but is not called from anywhere in the live comparison pipeline.** `compare_swing.py` and `compare_videos.py` only use the 9 body landmarks, not racket position.

### `08_comparison_engine/` — the live inference entry points
- **`compare_swing.py`** — **the core comparison engine, and the one thing this whole project revolves around.** Full flow of `compare()`:
  1. `extract_user_poses(video_path)` — runs MediaPipe on the uploaded video, sampling **every 3rd frame** (fixed this session — see below; previously every 2nd frame, which mismatched the database's density).
  2. `build_user_trajectory(frames, fps, contact_time_sec)` — if the user (or the frontend's contact-marking UI) supplied a contact time, snaps to the nearest available frame; otherwise falls back to `find_peak_wrist_frame()` (wrist-velocity peak, same heuristic as the database-build stage). Computes `trajectory_scale()` over the window and normalizes every frame with that single stable scale (this session's fix).
  3. `infer_camera_angle()` on the user's video at the contact frame.
  4. Loads `pro_database.json`, filters candidates to the requested `shot_type`, then **angle-filters** to `abs(pro_angle - user_angle) <= angle_window` (default 20°) — falls back to the unfiltered set if fewer than 5 candidates survive.
  5. For every surviving candidate: `dtw_distance()` → `similarity_score(dist, scale=0.4)` = `100 * exp(-dist/0.4)`, clamped ≥0.
  6. Sorts descending, takes top N.
  7. `generate_tips(user_contact, pro_contact, shot_type)` — compares normalized contact-frame landmark positions against a hardcoded `COACHING_TIPS` dict (per shot type → per landmark → per axis/direction phrasing, threshold 0.15 normalized units). **This is the old, single-phrasing hardcoded tip system — not the new 216-tip database (see Coaching AI section). Never wired together.**
  8. Writes progress to stderr, the final JSON result to stdout (required so the Node backend can pipe it cleanly), and also saves a copy to `data/runtime/last_comparison.json`.
  - CLI: `python compare_swing.py <video_path> <shot_type> [--top N] [--angle-window N] [--contact-time SEC]`
- **`compare_videos.py`** — **new this session, built but never wired to a backend route.** Same DTW/pose machinery as `compare_swing.py`, but compares two arbitrary user-supplied videos directly instead of doing a pro-database lookup — the engine behind the (currently frontend-mock-only) "1v1 Comparison" premium feature. `compare_videos(reference_path, your_path, shot_type, contact_a, contact_b)` returns similarity score, both videos' inferred camera angles, an `angle_mismatch_deg` + `angle_mismatch_warning` flag (warns above 25° difference — note this is a *soft* warning, not the strict 30–45° hard enforcement the premium feature spec calls for), and tips generated the same way as the main engine. CLI mirrors `compare_swing.py`'s shape.

### `09_coaching_ai/` — teacher-student coaching-tip selector (fully built, never run with real data, not wired in)
- `data/08_coaching_ai/coaching_tips_database.json` — **216 curated tip phrasings**: verified structure is `_meta` + `forehand`/`backhand`/`serve`, each shot type having **8 issue types**, each issue having 3 severity bands × 3 phrasings = 9 phrasings per issue (8 × 9 × 3 shots = 216). Hand-written, not API-generated (explicit choice).
- **`tip_selector.py`** — the rule-based "student": `score_issues()` scores every possible issue against the user-vs-pro deviation, `select_top_tips()` picks the top N. Uses `SEVERITY_BANDS` (mild 0.12, moderate 0.25, severe 0.40) and a `PHASE_TARGET_T` mapping.
- **`tip_verifier.py`** — the Claude-as-teacher verifier. `verify_picks()` sends the same candidate issues + the student's picks to `claude-sonnet-5` and asks it to independently rank the top 3, returning `{top_picks, agrees_with_selector, reasoning}`. **Explicitly gated: the module docstring says not to call `verify_picks()` until the leaked Anthropic key is rotated** — still true, key still not rotated.
- **`tip_training_log.py`** — logs every (student pick, teacher pick, agreement) event; `should_trust_student()` decides when the system can stop calling Claude (`AGREEMENT_THRESHOLD=0.90` over `MIN_EXAMPLES_BEFORE_TRUST=50` logged examples).
- **`select_coaching_tips.py`** — orchestrator tying the above three together.
- **Verified this session: `data/08_coaching_ai/` contains only `coaching_tips_database.json` — no training log file exists.** Zero real examples have ever been logged, because no real user traffic has been generated and the verifier has never been called. **Explicitly deferred by Jack this session** — decided this needs real user footage to train against, not synthetic pro-vs-pro data (comparing pro footage to itself would be a trivial, self-referential match and wouldn't teach the selector anything about real deviations). See the estimated cost if/when this resumes: roughly $0.002–0.003 per Claude verification call (grounded in the actual prompt size in `tip_verifier.py`), so reaching the 50-example trust threshold would cost well under $1 — cost was never the blocker, data and the API key were.

### `10_net_detection/` — net-end keypoint ML (built, working, unrelated to net-based camera-angle inference in `infer_angle.py`)
A smaller, separate effort from the racket-keypoint work — detecting the two end-posts of the net (not the same as the Hough-line net-width detection used for camera angle).
- **`sample_own_footage_frames.py`** — samples 12 frames per source compilation (108 total candidates) from the project's own footage. Pivoted here after external image sourcing (Openverse/Wikimedia) proved to have <20% yield for the needed "full net + visible end-post" framing.
- `data/10_net_keypoints/own_footage_labels.json` — **36 hand-labeled examples** (2 points: left_end, right_end), all from the `*_compilation_1` videos (near-100% labeling yield within those specific videos due to fixed camera framing).
- **`train_net_keypoints.py`** — same transfer-learning architecture that failed for the racket (frozen backbone + regression head), but **worked well here**: val MSE 0.0067 (~8% pixel error), visually validated as accurate.
- **`source_net_images.py`** — the (mostly abandoned) external-image sourcing script; had a filename-collision bug (fixed: compute the starting index from the max existing filename index, not the count, since gaps from failed downloads broke that assumption).
- **`validate_net_keypoints.py`** — visualization/validation helper.
- **Also unused in the live comparison pipeline** — exists as a standalone trained model, not called by anything else.

---

## The DTW Score Calibration Fix (this session's main backend fix)

**Symptom (from before this session):** comparing a swing against *itself* (the same clip, re-run through pose extraction) scored only ~56/100 instead of something close to 100.

**Root cause 1 — unstable normalization scale.** `normalise_landmarks()` divided every landmark by *that frame's own* shoulder width. Shoulder width fluctuates by roughly 30% frame-to-frame during a swing as the torso rotates (empirically verified this session: 0.092–0.122 across nearby frames of the same clip). Dividing by a wildly fluctuating per-frame value amplifies ordinary pose-detection noise — including the noise between two *independent* MediaPipe runs on the same physical video — into large coordinate swings at exactly the frames that matter (mid-swing, near contact).

**Root cause 2 — mismatched sampling density.** The pro database was built from pose data extracted at `sample_every=3` (~20fps from a 60fps source), but `compare_swing.py`'s live extraction was sampling every 2nd frame (~30fps). Comparing a denser user trajectory against a sparser pro trajectory forces extra DTW warping even for identical content.

**Fix, verified empirically with a real self-match test on `forehand_0005`:**
1. `normalise_landmarks()` now takes an explicit `scale` parameter; `trajectory_scale()` (new function) computes the *median* shoulder width across the whole swing window once, and that single value is used for every frame's normalization.
2. `compare_swing.py`'s `extract_user_poses()` now samples every 3rd frame, matching `extract_poses.py`'s stride exactly.
3. Both `build_pro_database.py` (database-build side) and `compare_swing.py` (live-inference side) were updated, since they share `normalise_landmarks()`.
4. **The entire pro database was rebuilt from scratch** (914 raw entries → 631 after reapplying the ball-visibility filter — exactly matching the pre-fix entry counts, confirming nothing was lost).

**Result:** self-match distance dropped from 0.227 → 0.091 (score 56.7 → 79.6). Cross-swing distances for genuinely different swings stayed in the 0.49–2.1 range, confirming the fix didn't collapse the score's discriminative power — it just stopped punishing a correct match. Verified via the actual `compare_swing.py` CLI end-to-end, not just the isolated DTW function.

Backup of the pre-fix database: `data/06_pro_database/pro_database_backup_pre_normalization_fix.json`.

---

## Backend (`backend/`)

Express 5 server on port 5000, started via `node src/server.js` (or `npm run dev` for nodemon hot-reload).

### Routes

**`src/routes/analyse.js`** — `POST /api/analyse`
- `multer` disk storage, 200MB limit, saves to `backend/uploads/`.
- Body: multipart form with `video` file, `shotType` (must be forehand/backhand/serve), optional `contactTime`.
- Spawns `scripts/venv/Scripts/python.exe backend/src/services/pro_matcher.py <video> <shotType> --top 3 [--contact-time N]`, 2-minute timeout.
- `pro_matcher.py` is a thin CLI wrapper — literally just calls `compare_swing.compare()` and prints the JSON result.
- Cleans up the uploaded temp file in all cases (success, failure, timeout).
- **This is the only endpoint the live app actually uses**, and it's confirmed working end-to-end (tested via curl and full browser automation).

**`src/routes/auth.js`** — new this session, real (not mocked):
- `POST /api/auth/signup` — body `{email, password, name}`. Validates email format, password ≥8 chars, name non-empty. Hashes password with bcrypt (cost 10), rejects duplicate emails with 409. Returns `{token, user}`.
- `POST /api/auth/login` — body `{email, password}`. Constant-time-ish: compares against a dummy bcrypt hash when the user doesn't exist, so response timing doesn't leak whether an email is registered. Returns `{token, user}` or 401.
- `GET /api/auth/me` — requires `Authorization: Bearer <token>`, returns the current user. Used by the frontend on app boot to restore a session from a saved token.
- All three verified directly with curl this session (signup, duplicate-signup rejection, wrong-password rejection, valid/missing/garbage token handling on `/me`).

**`src/middleware/requireAuth.js`** — reads the Bearer token, verifies with `jsonwebtoken` against `JWT_SECRET`, attaches `req.user`, or 401s.

### Database (`src/db.js`)

**SQLite via `better-sqlite3`**, not Postgres. File: `backend/data/app.db` (+ `-shm`/`-wal` files from WAL mode), gitignored.

```sql
CREATE TABLE users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  name          TEXT NOT NULL,
  tier          TEXT NOT NULL DEFAULT 'free' CHECK (tier IN ('free', 'premium')),
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
```

**Why SQLite and not the Postgres already referenced in `.env`:** Postgres was never actually installed on this machine (verified — no `psql`, no `pg_ctl`, no running service) despite `DATABASE_URL` pointing at `localhost:5432`. Jack chose SQLite this session for zero-install velocity, with Postgres remaining the intended eventual production target. `pg` is still an installed backend dependency for whenever that migration happens. **There is only one table.** No `analyses` table exists — results from `/api/analyse` are never persisted per-user; the History screen is still entirely mock data (see Frontend section).

### Unused-but-installed backend dependencies
`pg`, `redis`, `bull` — none are `require()`'d anywhere in `backend/src/`. Left over from initial project scaffolding before this session's SQLite decision.

---

## Frontend (`frontend/`) — Expo SDK 54

### Navigation structure (`App.js`)

Root is a `createNativeStackNavigator` with native headers (dark background, green tint, real platform back chevrons — no more custom "← Back" text links, removed this session). Inside it:

- **`MainTabs`** (`createBottomTabNavigator`, headerShown false) — the primary app shell, 4 tabs:
  - **Home** → `HomeScreen.js`
  - **History** → `HistoryScreen.js`
  - **Premium** → `PremiumScreen.js`
  - **Profile** → `ProfileScreen.js`
- Stack screens pushed on top of the tabs (native header, back chevron):
  - **Upload** → `ContactMarkingScreen.js` — reused for *both* the single-video flow and (via an `onConfirmed` callback param) the 1v1 comparison flow's two contact-marking steps
  - **Results** → `ResultsScreen.js`
  - **Login** → `LoginScreen.js`
  - **Signup** → `SignupScreen.js`
  - **VersusPick** → `VersusPickScreen.js`
  - **VersusResults** → `VersusResultsScreen.js`
  - **HighlightUpload** → `HighlightUploadScreen.js`
  - **HighlightReview** → `HighlightReviewScreen.js`
  - **HighlightArchive** → `HighlightArchiveScreen.js`

The whole app is wrapped in `<AuthProvider>` (from `context/AuthContext.js`).

**This session's design overhaul, for context:** the app used to be a single scrolling `LandingScreen` structured like a SaaS marketing page (hero copy, feature grid, "how it works" list, CTA banner, footer) with top-corner text links for navigation — it read as a website, not an app. `LandingScreen.js` was deleted and replaced with the tab-based structure above, specifically to fix that.

### Screens

**`HomeScreen.js`** — the app's actual dashboard (replaces the old marketing landing page). Greeting header, a primary "Analyse your swing" CTA card, three quick shot-type pills that jump straight into Upload with `shotType` pre-set, a stats strip (analyses/avg score/great swings, computed from mock data), and a 2-item "recent activity" preview with a "See all" link into the History tab (`navigation.jumpTo('History')`).

**`HistoryScreen.js`** — full list view of past analyses, stats strip, a "+ New" button that opens an inline upload panel. **Still entirely driven by `frontend/data/mockAnalyses.js`'s `MOCK_ANALYSES` array** (3 hardcoded entries) — nothing from a real `/api/analyse` call is ever saved here. Its own upload flow (`handleUpload`) adds a "pending" placeholder card and navigates to Upload, but that placeholder is never actually filled in with the real result.

**`ContactMarkingScreen.js`** — 3-phase contact-marking UI (pick video → rough scrub → frame-by-frame fine adjustment with 0.25× slow-mo preview). Unchanged in core logic from before this session except: removed the duplicate custom back link (native header covers it now), and added an `onConfirmed` callback escape hatch in `confirmFrame()` — if `route.params.onConfirmed` is present it's called with `{videoUri, shotType, contactFrame, contactTimeSec}` instead of the default `navigation.navigate('Results', ...)`. This is what lets `VersusPickScreen` reuse this exact screen twice (via `navigation.push`) for the 1v1 flow without duplicating any of the video-scrubbing logic.

**`ResultsScreen.js`** — the real results screen for the working single-video flow. Loading/error/done states; `buildFormData()` handles the web-vs-native difference in how a picked video URI needs to be packaged for `fetch`. Calls `POST /api/analyse` via `API_BASE` from `frontend/config/api.js` (currently hardcoded to `http://192.168.1.162:5000` — **this is the dev machine's LAN IP and will need updating if the Wi-Fi network reassigns it**; check with `ipconfig`). Shows score, both angle labels, coaching tips, other close matches.

**`LoginScreen.js` / `SignupScreen.js`** — **real auth this session**, not mocked. Call `useAuth().login()` / `.signup()` from `AuthContext`, show real backend error messages (wrong password, duplicate email, etc.), navigate into `MainTabs`/`Home` on success.

**`ProfileScreen.js`** — shows the real signed-in user (avatar initial, name, email) with a FREE/PREMIUM tier badge and working "Log out" when authenticated; shows a "Guest / Not signed in" state with Login/Signup menu items otherwise. Also has static Settings/Help menu items (no-ops).

**`PremiumScreen.js`** — entry point for the two premium feature previews. Two cards ("1v1 Comparison" → `VersusPick`, "Highlight Archive" → `HighlightUpload`), each with icon/description/CTA. Has a "✨ PREMIUM" badge at the top but **does not actually check `isPremium` or gate anything** — any user, including a logged-out guest, can currently tap into both flows freely.

**`VersusPickScreen.js`** — pick shot type + a reference video ("video you want to copy") + your own video, then chains through `ContactMarkingScreen` twice via `navigation.push('Upload', {videoUri, shotType, onConfirmed: ...})`, nesting a second `onConfirmed` inside the first's callback, finally landing on `VersusResults` with both marked videos' data.

**`VersusResultsScreen.js`** — shows a loading spinner (~1.8s fake delay) then a mock result: random-ish similarity score, hardcoded angle labels, 2 mock tips pulled from a small per-shot-type dict in the file itself. **Explicitly marked with a TODO to replace with a real call to `/api/compare-videos`** — no such backend route exists; `compare_videos.py` (the real engine) exists in `scripts/08_comparison_engine/` but was never wired to a Node route, per Jack's explicit direction to build frontend-only for the premium features first.

**`HighlightUploadScreen.js`** — pick a match video (messaging caps it at "10 minutes" — not actually enforced anywhere, just copy), a fake "Finding your shots..." processing state (~2.2s), then navigates to Review with hardcoded mock detected clips from `frontend/data/mockHighlights.js`'s `MOCK_DETECTED_CLIPS` (6 entries with fake timestamps).

**`HighlightReviewScreen.js`** — swipe-tag UI: each mock detected clip gets a Forehand/Backhand/Serve/Skip pill. "Save to archive" only enables once at least one clip is tagged something other than Skip.

**`HighlightArchiveScreen.js`** — grid of archived clips: newly tagged clips (passed via navigation params) merged with a small hardcoded starter list (`MOCK_ARCHIVE_CLIPS`, 3 entries). Each row has an "Analyse" button that currently just shows an `Alert` saying this needs the backend clipping pipeline first — intentionally not wired to the real analyse flow, since these are mock timestamps, not real detected swings.

### `context/AuthContext.js`

React Context wrapping the whole app. On boot, tries to restore a saved token (`expo-secure-store` on native, `localStorage` on web — `expo-secure-store`'s native APIs don't exist on web, so there's a small platform-conditional storage shim at the top of the file) and validates it against `GET /api/auth/me`; if that fails (expired/invalid), clears it silently rather than blocking app startup. Exposes `user`, `token`, `loading`, `isAuthenticated`, `isPremium` (`user?.tier === 'premium'`), and `signup`/`login`/`logout` methods.

### `config/api.js`
Single source of truth for `API_BASE` (was previously duplicated inline in `ResultsScreen.js`; now imported from here by both `ResultsScreen.js` and `AuthContext.js`).

### `data/mockAnalyses.js`, `data/mockHighlights.js`
All the hardcoded mock data described above, factored into shared files so `HomeScreen`/`HistoryScreen` (analyses) and `HighlightUpload`/`HighlightReview`/`HighlightArchive` (highlight clips) aren't each maintaining their own duplicate copy.

### Installed-but-unused frontend dependencies
`expo-auth-session`, `expo-web-browser`, `expo-crypto` — installed this session while investigating Google Sign-In, then left in place when the plan changed. **Important finding from that investigation, confirmed directly against Expo's current official docs (not assumption):** Google/OIDC OAuth does not work in plain Expo Go at all — it requires a custom development client (EAS Build). The old `expo-auth-session/providers/google` convenience hooks are also marked deprecated in the currently-installed version (7.0.11). Jack explicitly deferred Google Sign-In as a result — decided to ship email/password now and revisit Google once ready to move off plain Expo Go testing. `expo-secure-store` (also installed this session) *is* actively used, for token storage.

---

## Known Gaps — Full Status Against the Premium Feature Spec

Cross-referenced against the 7-item premium feature list Jack provided this session:

| # | Feature | Status |
|---|---|---|
| 1 | Unlimited Uploads (2/day free vs. paid) | **Not started.** No usage counter anywhere. The "2 analyses per day" text on Signup is static copy, enforces nothing. |
| 2 | Unlimited History + Progression | **UI shell only.** `HistoryScreen` renders correctly but nothing is persisted server-side (no `analyses` table); no progression/trend view exists. |
| 3 | Positional Movement Analysis | **Not started.** No court coordinate system, no footwork tracking. Jack's own spec already flags this as V2/research-stage. |
| 4 | Auto-Crop Shots from Match Footage | **Frontend UI shell only** (Highlight Archive, described above). Real backend (shot detection on raw match video + classifier) doesn't exist. |
| 5 | 1-on-1 Coaching Mode | **Frontend UI shell + unwired backend engine.** `compare_videos.py` is real and complete; no Node route calls it. Strict 30–45° angle enforcement from the spec is not implemented (only a soft >25° warning). |
| 6 | Video Playback with Overlay Annotations | **Not started.** All current results are text/score only, no video playback with drawn annotations. |
| 7 | Coach Collaboration Mode | **Not started.** No user roles beyond the free/premium tier flag, no coach-specific login or notes system. |

**The structural gap underneath all of these:** there is no real payment processing (Stripe keys are placeholders) and nothing anywhere checks `isPremium` to actually gate a feature. The tier flag exists and is real (set on signup, defaults `'free'`, readable everywhere via `useAuth()`), but the only way to become `'premium'` today is editing the SQLite row directly.

## Other Known Gaps (not from the premium list)

- **Coaching tips**: the live app still uses the old hardcoded single-phrasing `COACHING_TIPS` dict in `compare_swing.py`, not the 216-tip database + teacher-student selector system (built, described above, never wired in — and explicitly blocked on both real training data and the unrotated API key).
- **`ResultsScreen`'s `API_BASE`** is a hardcoded LAN IP, not derived automatically — will silently break if the dev machine's IP changes.
- **No automatic shot-type classifier** exists anywhere (forehand/backhand/serve is always either hand-assigned per source compilation, or hand-tagged by a user in the Highlight Review UI).
- **High-angle pro database entries (>65°) have never been manually audited** for behind-baseline false positives, per the original angle-detection limitation.
- **Racket keypoint model and net-end keypoint model are both trained and validated but not used by anything** in the live comparison — they were built as exploratory/future capability, not integrated.

---

## Planned Features — Research Brief (GolfFix-Inspired, not yet implemented)

Jack supplied this brief this session, referencing GolfFix (a golf-swing-analysis competitor product) as the model to take cues from. **None of this is built yet.** Recorded here verbatim-in-substance so the reasoning and specifics aren't lost, with notes on how each piece would connect to the existing codebase.

### 1. Slider Synchronization Feature (side-by-side synced comparison)

A comparison mode where the user's video and the matched pro's video play **simultaneously, side by side, sharing one scrubber**. Described as GolfFix's most credibility-building feature — seeing your own frame next to the pro's frame at the exact same swing phase makes AI feedback tangible in a way a text tip alone doesn't.

Specified behavior:
- **Dual playhead** — one shared slider position drives both videos' playback position at once.
- **Variable-speed scrubbing** — keyboard/touch controls, 0.5×/1×/2×.
- **Milestone markers** on the timeline — address, backswing, top-of-swing, impact, follow-through — so a user can jump straight to "show me both players at contact" rather than scrubbing manually.

**How this would connect to what exists:** `VersusPickScreen` / `VersusResultsScreen` (this session's 1v1 comparison frontend, currently mock-only) already establish the *pairing* of a reference video and the user's video with a marked contact frame for each — that contact-frame alignment is exactly the anchor a synced slider would need (t=0 for both videos should be their respective marked contact points, not their raw start times, so "milestone: impact" lines up correctly even if the two clips have different lengths/framerates). `PlatformVideo.web.js` / `.native.js` already expose `setPositionAsync(ms)` and `setRateAsync(rate)`, which is most of what variable-speed synced scrubbing needs — a shared-slider component would drive both instances' `setPositionAsync` off one offset value (`contactTimeSec_A + offset`, `contactTimeSec_B + offset`). Would replace `VersusResultsScreen`'s current text-only mock result with an actual video-comparison view.

### 2. Camera Angle Calibration

GolfFix's spec: camera "facing directly at the center of your body at address, positioned 8–13 feet away (face-on) or 6–10 feet away (down-the-line)." Proposed for this app:
- User selects recording angle intent (face-on vs. side/down-the-line) before recording or uploading.
- System analyzes the first frame to check camera height (should be roughly chest height) and perpendicularity to the player.
- Uses pose keypoints (shoulders, hips, feet) to verify alignment — if spine angle or stance width reads as distorted, that's a signal the framing is off — and gives an actionable warning (e.g. "Move camera 2 feet to the left").
- Rationale given: bad camera angles are a direct cause of pose-detection failure, so catching this *before* or immediately after upload should meaningfully improve downstream analysis quality.

**How this would connect to what exists:** This is a natural extension of `05_angle_detection/infer_angle.py`, which already infers camera angle (0–90°) from Hough-line net detection and buckets it into labels (Front/Semi-front/Diagonal/Semi-side/Side) — the inference half of this already exists and runs on every upload today (surfaced in `ResultsScreen` as "Your angle" / "Pro's angle"). What's missing is (a) doing this check *before* committing to a full analysis run rather than after, (b) translating a bad angle into an actionable framing instruction rather than just a label, and (c) the shoulder/hip/stance-width distortion check, which is new — `infer_angle.py` only looks at the net, not the player's own pose geometry. The pose landmarks it would need (shoulders, hips) are already extracted by every pipeline path (`extract_user_poses` in `compare_swing.py` / `compare_videos.py`), so this is a matter of adding a new check function, not a new extraction step.

### 3. Skeleton Overlay — Implementation Strategy (deliberately deferred)

**Decision as specified: do not build this for MVP.** GolfFix uses a rendered stick-figure skeleton overlay (synced to video, user-vs-pro in different colors) as a core credibility mechanism, but the brief's explicit call is to ship pose detection + text feedback only first, and gate the skeleton-rendering work behind real user testing:

> After week 2 user testing with 10 real players: if users don't trust the AI analysis without seeing the skeleton, add it post-MVP. If users say the text feedback is clear and actionable on its own, defer it indefinitely.

**Implementation options recorded for when/if this is greenlit:**
- Render keypoints as SVG lines/circles overlaid on the video via Canvas or Three.js (2D visualization), **or**
- Use a pose-visualization library (e.g. a `tfjs-pose`-style renderer) to draw the skeleton in real time.
- For the pro comparison view specifically: overlay both skeletons in different colors, on the slider/side-by-side view from item 1 above.

**Discrepancy worth flagging:** the brief describes pose detection via **AWS Rekognition or Google Cloud Vision**, returning ~17 COCO-style joints. **This project does not use either** — the actual pipeline is MediaPipe Tasks API throughout (`pose_landmarker.task`, 33 landmarks, all local/offline, no AWS or GCP calls anywhere in the codebase — confirmed, `AWS_REGION`/`AWS_ACCESS_KEY_ID`/`S3_BUCKET` in `backend/.env` are unconfigured placeholders, never wired to any code path). MediaPipe's 33 landmarks are a superset of the ~17 the brief describes, so nothing here is blocked by that mismatch — a skeleton overlay would draw from the same `landmarks` dicts already being extracted — but any future implementer following the brief literally would go looking for an AWS integration that was never actually part of this build.

---

## How to Run Everything

```powershell
# Backend
cd C:\Users\jackp\tennis_app\backend
npm run dev
# → http://localhost:5000/health

# Frontend (Expo)
cd C:\Users\jackp\tennis_app\frontend
npx expo start
# Scan the QR with Expo Go on your phone (same Wi-Fi network required),
# or press 'w' for a web build at localhost.

# Python scripts (only needed for pipeline/offline work, not for running the app)
cd C:\Users\jackp\tennis_app\scripts
.\venv\Scripts\activate
python 08_comparison_engine\compare_swing.py <video_path> forehand --top 3
```

No Docker, no Postgres, no Redis needed for any of the above.

### Rebuilding the pro database (only if source footage changes)
```powershell
cd C:\Users\jackp\tennis_app\scripts
.\venv\Scripts\activate
python 06_database_build\build_pro_database.py          # rebuilds ALL entries (~914, unfiltered)
python 07_ball_racket_tracking\filter_by_ball_visibility.py   # drops entries with no visible ball near contact → 631
```

---

## File Structure (Verified Current State)

```
C:\Users\jackp\tennis_app\
├── docker-compose.yml                     # present, currently unused by the running app
├── HANDOVER.md                            # this file
│
├── backend/
│   ├── .env                               # JWT_SECRET (real), ANTHROPIC_API_KEY (LEAKED, unrotated), Stripe/AWS/Postgres/Redis placeholders
│   ├── .gitignore                         # node_modules/, uploads/*, .env, data/*.db*
│   ├── data/
│   │   └── app.db (+ -shm/-wal)           # SQLite — the only database in use
│   ├── uploads/                           # multer temp storage, cleaned up per-request
│   └── src/
│       ├── server.js                      # Express app: /health, /api (analyse + auth routers)
│       ├── db.js                          # SQLite connection + users table schema
│       ├── middleware/
│       │   └── requireAuth.js             # JWT verification middleware
│       ├── routes/
│       │   ├── analyse.js                 # POST /api/analyse — the working core endpoint
│       │   └── auth.js                    # POST /api/auth/signup, /login, GET /me
│       └── services/
│           └── pro_matcher.py             # thin CLI wrapper around compare_swing.compare()
│
├── frontend/                              # Expo SDK 54
│   ├── App.js                             # Tab nav (Home/History/Premium/Profile) + stack screens, wrapped in AuthProvider
│   ├── app.json                           # name: TennisAI, bundle com.jackp.tennisai
│   ├── package.json
│   ├── components/
│   │   ├── PlatformVideo.web.js           # real DOM <video>, explicit pixel sizing
│   │   └── PlatformVideo.native.js        # expo-av Video wrapper, same interface
│   ├── config/
│   │   └── api.js                         # API_BASE (hardcoded LAN IP)
│   ├── context/
│   │   └── AuthContext.js                 # token persistence, signup/login/logout, isPremium
│   ├── data/
│   │   ├── mockAnalyses.js                # MOCK_ANALYSES, SHOT_ICONS
│   │   └── mockHighlights.js              # MOCK_DETECTED_CLIPS, MOCK_ARCHIVE_CLIPS
│   └── screens/
│       ├── HomeScreen.js                  # real dashboard (replaces old LandingScreen)
│       ├── HistoryScreen.js               # mock data
│       ├── PremiumScreen.js               # entry point, not gated by tier
│       ├── ProfileScreen.js               # real auth state
│       ├── LoginScreen.js / SignupScreen.js   # real auth
│       ├── ContactMarkingScreen.js        # reused by both single-video and versus flows
│       ├── ResultsScreen.js               # real /api/analyse call — the working end-to-end path
│       ├── VersusPickScreen.js / VersusResultsScreen.js       # 1v1 comparison, mock results
│       └── HighlightUploadScreen.js / HighlightReviewScreen.js / HighlightArchiveScreen.js   # highlight archive, all mock
│
├── scripts/                               # numbered pipeline stages, see full walkthrough above
│   ├── venv/                              # Python 3.13.6
│   ├── pose_landmarker.task               # MediaPipe model
│   ├── yolo11n.pt / yolo11s.pt            # pretrained YOLO (racket/ball detection)
│   ├── 01_data_collection/
│   ├── 02_pose_extraction/
│   ├── 03_swing_detection/
│   ├── 04_clip_extraction/
│   ├── 05_angle_detection/
│   ├── 06_database_build/                 # includes this session's normalization fix
│   ├── 07_ball_racket_tracking/           # racket keypoint ML — trained, unintegrated
│   ├── 08_comparison_engine/              # compare_swing.py (live) + compare_videos.py (built, unwired)
│   ├── 09_coaching_ai/                    # teacher-student tip selector — built, never trained
│   └── 10_net_detection/                  # net-end keypoint ML — trained, unintegrated
│
└── data/
    ├── 01_source_videos/                  # 3 forehand, 4 backhand, 2 serve compilations
    ├── 02_pose_extraction/                # raw MediaPipe pose JSONs
    ├── 03_swing_detection/                # swing peak detection + validated swings
    ├── 04_clips/                          # extracted ~3s clips (+ *_rejected/)
    ├── 05_review_samples/                 # manual review JPEGs
    ├── 06_pro_database/
    │   ├── pro_database.json              # THE live database — 631 entries, full trajectories, post-fix
    │   └── pro_database_backup_*.json     # 5 historical snapshots, most recent = pre-normalization-fix
    ├── 07_audits/
    │   └── ball_visibility_audit.json     # drives the 914→631 filter
    ├── 08_coaching_ai/
    │   └── coaching_tips_database.json    # 216 tips — no training log file exists yet
    ├── 09_racket_keypoints/
    │   ├── labels.json                    # 220 labeled crops
    │   └── yolo_pose_run/weights/best.pt  # trained racket keypoint model, Box mAP50 0.927 / Pose mAP50 0.485
    ├── 10_net_keypoints/
    │   └── own_footage_labels.json        # 36 labeled examples
    └── runtime/
        └── last_comparison.json           # most recent live inference output
```
