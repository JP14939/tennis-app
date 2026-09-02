# RallyMax — Full Project Handover

**Last updated:** 2026-08-03, corrected 2026-08-10, extended 2026-08-10 (same-day follow-up session), extended again 2026-08-11, extended again 2026-08-13 (social/gamification roadmap + Phase 1), extended again 2026-08-13 (same-day follow-up: Find Games), extended again 2026-08-13 (same-day follow-up: Friends + match tracking), extended again 2026-08-13 (same-day follow-up: send-to-friend + persisted annotations), extended again 2026-08-13 (same-day follow-up: leaderboards), extended again 2026-08-13 (same-day follow-up: navigation restructure + Find Games data fix), extended again 2026-08-13 (same-day follow-up: community court submission + confirmation), extended again 2026-08-13 (same-day follow-up: app icon + mascot), extended again 2026-08-13 (same-day follow-up: skeleton offset fix, video-error visibility, racket swing-path overlay), extended again 2026-08-13 (same-day follow-up: sound effects), extended again 2026-08-13 (same-day follow-up: sound effects expanded app-wide), extended again 2026-08-13 (same-day follow-up: analysis-complete/achievement/notification sounds), extended again 2026-08-13 (same-day follow-up: History payload-bloat fix, found via real in-app testing), extended again 2026-08-13 (same-day follow-up: Sync Compare video-unavailable fix, England court seed + 20km render radius), extended again 2026-08-14 (batch-analyzed 2 full match videos into 85 History rows; fixed a live angle-wraparound bug in body-rotation scoring; z-depth rotation signal retried with real measurements and shipped live), extended again 2026-08-15 (legal review prep docs; fixed a live account-deletion bug; added message block/report), extended again 2026-08-18 (Wimbledon/Pine & Lime theme rollout completed across all screens; new mascot-based Android icon/splash; 4th teacher-student training loop for exact contact-frame detection, incl. a live production hook; Drills & Lessons feature shipped — free Drills live now, paid Lessons deferred; Swing Review rough-pick contact marking + clip prefetch; Rally Boundary Review lazy video loading; a full DB audit added missing indexes, fixed a real practice-history data-loss bug, and added 21 regression tests) — **social/gamification roadmap fully complete, bottom nav consolidated to 5 tabs, sound effects fully rolled out, theme rollout complete, first real Drills content live**, extended again 2026-08-19 (RevenueCat live + backend hosted on Hetzner; shot-classifier ML model trained; Tip Review + Pro Clip Review Dev Page tools; camera-angle sideline fallback; skeleton-overlay real fix; tip severity shown to users — see items #34-36), extended again 2026-08-20/21 (ball detector project Phase 1/2; Premium folded into Home + Lessons with a responsive tab bar; app-wide fix for `Alert.alert` being a silent no-op on web across 20 files; self-serve password reset via Resend; a full Hetzner redeploy fixing a server that was never actually a git repo, broken SSH access, and missing data — see items #37-41) — **hosting is real and working end-to-end now, but has no CI/CD: every push needs a manual redeploy, see item #41**, extended again 2026-08-22 (a database-verification framework with 48 live integrity checks; two rounds of bug/optimization audits; a clean security review; and — the big one — the first real device-native testing this app has had, which surfaced and fixed a cluster of native-only bugs invisible to every prior web-only testing session, plus a live production SQL bug in Find Games, now fixed and deployed — see item #42), extended again 2026-08-23 (docs round-up of same-day scheduled-routine PR activity, and — later the same day — a manual review/merge of all four resulting PRs: security rate-limiting, a bug sweep, a logic review, plus the 2026-08-22 uncommitted work above finally committed — see "Scheduled-routine PR round-up" below), extended again 2026-08-24 (docs round-up: 4 more scheduled-routine PRs opened — logic review, bug sweep, security review, brainstorm — all still open awaiting human review, none titled 🚨 CRITICAL — see "Scheduled-routine PR round-up (2026-08-24)" below), extended again 2026-08-25 (docs round-up: 4 more scheduled-routine PRs opened — logic review, bug sweep, security review, brainstorm — all still open awaiting human review, none titled 🚨 CRITICAL, and yesterday's `future-ideas/2026-08-24` PR is also still unmerged — see "Scheduled-routine PR round-up (2026-08-25)" below), extended again 2026-08-25 (same-day follow-up: all 8 branches from the 2026-08-24/25 PR round-ups reviewed and merged; pose-overlay jitter fixed with a One Euro Filter; a real gap found in the manual ball-label data (5 clips flagged, needs Jack's review); ball detector reliability re-confirmed unchanged (53%/0.40); a new shared Kalman-filter ball tracker built; the ball-speed feature scoped but not built; hosted server found 2 days stale and redeployed — see item #43), extended again 2026-08-26 (docs round-up: 4 more scheduled-routine PRs opened — logic review, bug sweep, security review, brainstorm — all still open awaiting human review, none titled 🚨 CRITICAL — see "Scheduled-routine PR round-up (2026-08-26)" below), extended again 2026-09-01 (competitive analysis of SevenSix — teardown + ideas logged to `docs/future-ideas.md` `### 2026-09-01`; `STATUS.md` refreshed; the "Read This First" auto-deploy caveat corrected)
**User:** Jack Price (jack.p14370@gmail.com)
**Project root:** `C:\Users\jackp\tennis_app\`

**Quick status (2026-09-01):** built, hosted, and auto-deploying (Hetzner + Docker, CD on push to `master`), feature-complete well past MVP, **pre-launch — no external user has ever used the live product**. Core loop + payments + social/gamification all live. Open items that matter: the `detect_rallies.py` serve-gate bug (blocks rally/highlight grouping), the shot-classifier retrain, and a real beta. For the current curated snapshot read `STATUS.md`; this doc is the full dated history.

This document replaces the previous HANDOVER.md, which was last updated 2026-07-31 and had drifted significantly from reality (it predates the DTW rewrite, the entire premium-feature frontend, and the auth system). Everything below was verified directly against the current filesystem and codebase while writing this — not recalled from memory.

**2026-08-10 correction pass:** several claims below had themselves gone stale by the time this update happened — most notably around History (it's real, not mock), the progression/trend chart (it exists), and the coaching-tips system (the real 216-tip selector is wired in, not the old hardcoded dict). Each corrected spot is marked inline with "**Update (2026-08-10, corrected...)**". This session also fixed the tips-button interaction bug, added a real/SVG-fallback tip photo system, added a "Watch & compare" shortcut from History straight into the synced video view, added per-shot-type progression + an Overall Improvement view, and added a Drills & Exercises tab (structural stub only).

**2026-08-10 follow-up session (same day):** the leaked `ANTHROPIC_API_KEY` has now actually been rotated (see updated "Read This First" below — this was the longest-standing open item in the doc). `SyncCompareScreen.js` gained a draggable zoom slider (replacing a fixed 1.3× constant), a skeleton show/hide toggle, and a full annotation toolbar (freehand pen/line/arrow/circle drawing, per-pane, via a new `AnnotationCanvas.js`). A "Wrong shot type?" correction picker was added to `ResultsScreen.js`/`HistoryScreen.js`, feeding real human labels into `shot_classifier_training_log.py`. The share flow (`ResultShareCard.js`) gained a preview popup with an animated score-fill ring and a swing-breakdown list before sharing. Deployment work also started this session — see the new "Deployment / Hosting" item under Planned Features.

**2026-08-18 session:** several separate threads of work, now committed together:
- **Theme rollout finished.** Every screen still using the old black-theme literals (`VersusPickScreen.js`, `SyncCompareScreen.js`, the Highlight* screens, the Dev Page screens) is now on the shared Pine & Lime tokens (`frontend/theme.js`). The Android adaptive icon and splash screen (`frontend/assets/android-icon-*.png`, `splash-icon.png`) were also replaced — they were still the pre-rebrand placeholder art (a generic blue chevron and 3 plain circles) despite the app icon/favicon already being updated to the mascot.
- **A 4th teacher-student training loop**, for `find_contact_frame()` (`scripts/07_ball_racket_tracking/racket_tracker.py`) — previously a completely untrained heuristic with no logged ground truth anywhere. New `contact_frame_training_log.py` (frame-distance based, not binary agreement like the other 3 loops). Two ways it gets trained: (1) the Dev Page's Swing Review tool gained a 3rd step reusing `ContactMarkingScreen.js`'s slider pattern, and (2) a live hook — every real user who manually marks a contact time through the normal upload flow now also feeds this log, via a **detached background process** spawned from `analyse.js` after the response is already sent (an inline version was measured at ~5s added latency per request, which was unacceptable, hence detached).
- **Drills & Lessons** (new feature): `drill_items`/`drill_routine_steps`/`drill_practice_attempts` tables, `routes/drills.js` (free items fully visible, premium items list-but-strip-content and 403 on direct access for non-premium users), and a Dev Page editor (`DevDrillsEditorScreen.js`) for managing content without a redeploy. Seeded 30 real free drills (10 each forehand/backhand/serve) directly from the existing `coaching_tips_database.json`, reusing its diagrams via `TipDiagram`. **Lessons (paid, structured watch→learn→practice routines) are deferred** — the UI/backend support both `kind`s already, but no lesson content exists yet; Jack wants this as a bigger feature later.
- **Two real UX bugs found and fixed**: Swing Review's contact-frame slider was hard-capped at ±50 frames from the automatic guess with no way to reach a contact frame further away — fixed with a rough-pick phase (mirrors `ContactMarkingScreen.js`) before the fine slider. Rally Boundary Review was mounting every pending clip's video simultaneously on load (a job with 30+ clips tried to buffer 30+ videos at once) — fixed to lazy-load a clip's video only once tapped.
- **A full DB audit**: added indexes for foreign keys with confirmed real query traffic across `analyses`, `messages`, `rally_clips`, `highlight_jobs`, `coach_notes`, `push_tokens`, and the new `drill_practice_attempts` (most of the 31-table schema had zero indexes beyond courts, which got fixed in an earlier session). Found and fixed a real data-loss bug: editing a lesson in the Dev editor used to delete-and-recreate all its routine steps on every save, silently orphaning practice-attempt history since SQLite foreign keys aren't enforced in this app — steps are now reconciled by id instead. Added 21 new regression tests for the previously-untested Drills & Lessons routes (`drills.test.js`, `dev.drills.test.js`). **Known gap, not done**: the other ~14 route files (auth, courts, friends, messages, coach, etc.) still have zero test coverage.
- Everything above is committed (see `git log` — this was previously the single biggest outstanding risk per item 2 below, now resolved).

---

## What This App Does

AI-powered tennis swing analysis mobile app (iOS/Android/web via Expo).

**Core loop (fully working):** user uploads a short video of their swing → marks the exact contact frame (rough scrub + frame-by-frame fine adjustment) → backend extracts MediaPipe pose landmarks → compares the full swing trajectory (not just contact frame) against a database of 631 professional swing clips using Dynamic Time Warping → returns the closest pro match, a 0–100 similarity score, camera-angle context, and coaching tips.

**Also present as frontend-only previews (no backend behind them yet):** direct 1-vs-1 video comparison ("upload a video you want to copy"), and a highlight-archive tool that's meant to auto-clip individual shots out of a full match video.

**Also present as a real, working system:** email/password authentication with a free/premium tier flag on each account, and (update 2026-08-10, this line was significantly stale) **real RevenueCat payment processing** — web checkout is fully wired, a billing-sync endpoint and webhook both update the tier in real time, and two real routes (`compare-videos`, `highlights/upload`) actually gate on it. See the corrected "Known Gaps" table and the new Planned Features item below for the full picture.

---

## ⚠️ Read This First

1. **Update (2026-08-10, follow-up session): the Anthropic API key has been rotated.** The key that was exposed in chat earlier in the project (and sat in plaintext, re-read by tooling, for the entire project up to this point) has been replaced with a fresh one at console.anthropic.com. This was the first prerequisite in `DEPLOY.md` before any real deploy, and it's now done — no outstanding action here.
2. **Update (2026-08-18): this is now stale — the repo has real commit history.** What used to be a single "Initial project structure" commit is now 7 commits, each bundling a full work session (`git log --oneline` to see them; latest as of this update is the 2026-08-18 theme/Drills & Lessons/DB-audit session). Still worth keeping the habit of committing before anything destructive, but the "no version history to fall back on" risk described here no longer applies.
3. The database is **SQLite** (`backend/data/app.db`), not the Postgres that `backend/.env`'s `DATABASE_URL` implies. Postgres was never installed on this machine. See the Backend section for why and what would need to change to migrate.
4. **Update (2026-08-25): the hosted backend DOES auto-deploy now.** Since `.github/workflows/deploy.yml` landed (Planned Features item #44), a `git push` to `master` touching `backend/**` / `scripts/**` / `Dockerfile` / `docker-compose.yml` / `Caddyfile` triggers the workflow — it SSHes into the VPS, runs `git pull && docker compose up --build -d app`, and polls `/health`. Doc-only pushes don't trigger it; it can also be run manually from the Actions tab. Superseded the old manual `ssh … git pull … docker compose up` dance for code. **Still manual:** transferring new files under `data/` to the server (gitignored, never touched by CD) and editing `backend/.env` on the server directly. Note there is **no test gate** before deploy — a red suite still ships.
5. **Update (2026-09-01): the SSH+docker permission-classifier note now only matters for the remaining manual operations.** This environment's permission classifier refuses to run `docker compose up --build -d app` over SSH even after verbal approval (a standalone `git pull` over SSH is fine). Routine code deploys no longer need it (CD handles them, item 4). But if a `data/` transfer or `.env` edit ever needs a manual container rebuild on the box, either add an explicit Bash permission rule for the SSH+docker pattern or have Jack run that one line himself. See items #41 and #43 for the history.

---

## Environment

| Tool | Version | Notes |
|---|---|---|
| Node.js | 22.18.0 | |
| Python | 3.13.6 | venv at `scripts/venv/` — activate before running any script |
| Expo SDK | 54 | Matches user's Expo Go on iPhone |
| Database | SQLite (`backend/data/app.db`) | Not Postgres — see Backend section |
| Docker | Installed, `docker-compose.yml` + root `Dockerfile` present | **Not needed for local dev** (`npm run dev` / `npx expo start` are all you need day to day) — Postgres/Redis remain unused, `pg`/`redis`/`bull` are still leftover deps. **Now used for deployment**: a repo-root `Dockerfile` (Node 22 + Python 3.13 + venv) builds the backend into a container; `docker compose build app` was verified to build cleanly end-to-end on this machine (x86_64) as of 2026-08-10. See `DEPLOY.md` and the new "Deployment / Hosting" item under Planned Features. |

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
ANTHROPIC_API_KEY=<rotated 2026-08-10, no longer the leaked one>
AWS_REGION / AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / S3_BUCKET   # placeholders, never configured
STRIPE_SECRET_KEY / STRIPE_PUBLISHABLE_KEY                          # placeholders, never configured
REDIS_URL                                                            # placeholder, Redis is not used
REVENUECAT_PROJECT_ID / REVENUECAT_SECRET_API_KEY /
REVENUECAT_WEBHOOK_SECRET / REVENUECAT_ENTITLEMENT_ID                # real, live since 2026-08-19 (item #34)
RESEND_API_KEY / RESEND_FROM_EMAIL   # added 2026-08-20 for self-serve password reset (item #40) —
                                      # NOT actually set yet, email sending silently no-ops until it is
PUBLIC_BASE_URL                      # added 2026-08-20 — this backend's own public URL, used to build
                                      # the password-reset email's link (https://rallymax.167-233-107-31.sslip.io)
```

`.env` is gitignored (confirmed). `frontend/.env.example` was deleted at some point (shows as `D` in git status) and never replaced. `backend/.env.example` was missing `JWT_SECRET` entirely (a real gap — the running app requires it) until the 2026-08-10 follow-up session added it, with a comment to generate a fresh random value rather than reuse the local dev one for any real deploy.

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

The backend never runs ML code in-process — it always shells out to a Python script via `child_process.spawn`, reads stdout as JSON, and forwards it to the client. This is true both for the pro-database matcher and for the 1v1 comparison engine (wired 2026-08-12).

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

Output: `data/03_swing_detection/<shot>_swings*.json` — each swing has `swing_id`, `peak_frame`, `peak_time_sec`, `start_frame`, `end_frame`, `confidence`, etc. **Note: this stage only detects *that* a swing happened (via wrist velocity) — it has no concept of forehand vs. backhand vs. serve.** Shot type is always known from which source video/compilation the swing came from, assigned manually per `JOBS` entry in `build_pro_database.py`.

**Update (2026-08-10, corrected — this was stale):** "there is no automatic shot classifier anywhere in this codebase" is no longer true — `scripts/14_shot_classifier/` classifies a *user's* uploaded swing (not pro database entries, which stay manually assigned as described above). Separately, this same wrist-velocity-only detection approach (a bare local-maximum peak, no verification that a real racket-to-ball strike happened) turned out to have a serious real-world accuracy problem when run against actual match footage — see the new "Verify that a detected swing is a real shot" item under Planned Features for the full story and the fix.

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

### `07_ball_racket_tracking/` — racket keypoint ML (built, working, and now used live in two places)
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

**Update (2026-08-10, corrected — this was stale):** the fine-tuned YOLO-pose model (`yolo_pose_run/weights/best.pt`) *is* called live, in two places now:
1. **`track_racket_in_clip.py`** → `track_racket_body()`, called from `compare_swing.py` (~line 354) to score the `body_rotation` phase — the `handle` keypoint vs. hip-midpoint distance signal. `ResultsScreen.js`'s `has_racket_data === false` fallback note is this real, sometimes-missing signal, not a dead flag. `_detect_racket_handle()` was generalized this session into `_detect_racket_keypoints()`, returning all 5 points (not just `handle`) — the original function is now a thin wrapper for backward compatibility.
2. **`scripts/16_shot_verification/verify_shot_contact.py`**'s `track_racket_tip_and_ball_cropped()` uses the `tip`/`left_edge`/`right_edge` keypoints (the string-bed points, where contact actually happens) as one signal in the geometric "is this actually a shot" student — see the new Planned Features item below for the full story of why that was needed and how it works.

The *other* racket model in this folder, `train_racket_keypoints.py`'s direct-regression MobileNetV3 (`data/09_racket_keypoints/racket_keypoint_model.pt`), genuinely is unused — that's the "abandoned approach" already described above, unaffected by this correction.

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
- **`compare_videos.py`** — **update (2026-08-12): now wired to a real backend route AND computes a phase breakdown.** Same DTW/pose machinery as `compare_swing.py`, but compares two arbitrary user-supplied videos directly instead of doing a pro-database lookup — the engine behind the "1v1 Comparison" premium feature, called via `backend/src/routes/compareVideos.js` → `/api/compare-videos`. `compare_videos(reference_path, your_path, shot_type, contact_a, contact_b)` returns similarity score, both videos' inferred camera angles, an `angle_mismatch_deg` + `angle_mismatch_warning` flag (warns above 25° difference — note this is a *soft* warning, not the strict 30–45° hard enforcement the premium feature spec calls for), tips generated the same way as the main engine, and — new this session — a real `phases`/`overall_score`/`phase_markers` breakdown (backswing/contact/follow-through/body-rotation), mirroring what `compare_swing.py` already computes for its top pro-database match, using the reference video in place of a pro-database entry. CLI mirrors `compare_swing.py`'s shape.

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
- **Added 2026-08-20 (item #40): `POST /api/auth/forgot-password`** `{email}` — always 204, never reveals whether the account exists; generates a reset token (only its sha256 hash is stored, in the new `password_resets` table, 1-hour expiry) and emails a link via Resend (`backend/src/utils/email.js`) if the user exists. **`POST /api/auth/reset-password`** `{token, newPassword}` — validates the token, updates the password, marks it used. Verified end-to-end against the dev DB; real email delivery still needs `RESEND_API_KEY` set.

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

**Why SQLite and not the Postgres already referenced in `.env`:** Postgres was never actually installed on this machine (verified — no `psql`, no `pg_ctl`, no running service) despite `DATABASE_URL` pointing at `localhost:5432`. Jack chose SQLite this session for zero-install velocity, with Postgres remaining the intended eventual production target. `pg` is still an installed backend dependency for whenever that migration happens.

**Update (2026-08-10, corrected — this section was stale):** an `analyses` table exists and is real (see `backend/src/routes/history.js`). `POST /api/history` persists every saved result per-user (`user_id, shot_type, similarity, pro_id, angle_label, tip, result_json`), `GET /api/history` returns them, `DELETE /api/history/:id` removes one. `HistoryScreen.js` is driven entirely by this real API, not mock data — see the corrected Frontend section below.

### Unused-but-installed backend dependencies
`pg`, `redis`, `bull` — none are `require()`'d anywhere in `backend/src/`. Left over from initial project scaffolding before this session's SQLite decision.

---

## Frontend (`frontend/`) — Expo SDK 54

### Navigation structure (`App.js`)

Root is a `createNativeStackNavigator` with native headers (dark background, green tint, real platform back chevrons — no more custom "← Back" text links, removed this session). Inside it:

- **`MainTabs`** (`createBottomTabNavigator`, headerShown false). **Update (2026-08-13, navigation restructure session): now 5 tabs**, consolidated down from a 6-tab bar that had grown one-feature-per-tab (Home/History/Drills/FindGames/Premium/Profile) — Jack asked for Leaderboard to live on Home, History to absorb Drills, and a new Friends tab to absorb Messages, so nothing new got bolted onto the tab bar as gamification features shipped:
  - **Home** → `HomeScreen.js` — now also renders the full leaderboard inline (`components/LeaderboardSection.js`) below Recent Activity, not just swing stats
  - **History** → `HistoryScreen.js` — gained a History/Drills segmented toggle at the top; Drills content lives in `components/DrillsSection.js` and renders in-place when that segment is selected (still a structural stub, no real drill data — see item 6 below)
  - **Friends** → `FriendsScreen.js` — gained a Friends/Messages segmented toggle at the top; Messages content lives in `components/MessagesSection.js`. `ProfileScreen.js`'s "Messages" menu item now deep-links here via `navigation.navigate('Friends', { initialSegment: 'messages' })`
  - **FindGames** → `FindGamesScreen.js`
  - **Profile** → `ProfileScreen.js`
  - `DrillsScreen.js`, `LeaderboardScreen.js`, and `MessagesScreen.js` (the old standalone screens) were deleted outright now that their content is embedded elsewhere — not kept around as dead code.
- Stack screens pushed on top of the tabs (native header, back chevron):
  - **Upload** → `ContactMarkingScreen.js` — reused for *both* the single-video flow and (via an `onConfirmed` callback param) the 1v1 comparison flow's two contact-marking steps
  - **Results** → `ResultsScreen.js`
  - **Login** → `LoginScreen.js`
  - **Signup** → `SignupScreen.js`
  - **VersusPick** → `VersusPickScreen.js`
  - **VersusResults** → `VersusResultsScreen.js`
  - **SyncCompare** → `SyncCompareScreen.js` — dual synced video playback with a shared scrubber, reachable from Results' "Compare side-by-side" button and, as of 2026-08-10, directly from a History card's "Watch & compare" button too
  - **HighlightUpload** → `HighlightUploadScreen.js`
  - **HighlightReview** → `HighlightReviewScreen.js`
  - **HighlightArchive** → `HighlightArchiveScreen.js`
  - **FenceTutorial** → `FenceTutorialScreen.js`
  - **Settings** → `SettingsScreen.js`
  - **Coach** → `CoachScreen.js`
  - **Premium** → `PremiumScreen.js` — **Update (2026-08-13): moved here from a `MainTabs` tab** as part of the same restructure; all `navigation.navigate('MainTabs', { screen: 'Premium' })` call sites (`ProfileScreen.js`, `ResultsScreen.js` ×2, `HistoryScreen.js`) were updated to the simpler `navigation.navigate('Premium')`
  - **MessageThread** → `MessageThreadScreen.js` — individual conversation view, still pushed from wherever a thread/court-availability row is tapped (Friends' Messages segment, or a court's "who's free" list on Find Games)

The whole app is wrapped in `<AuthProvider>` (from `context/AuthContext.js`).

**This session's design overhaul, for context:** the app used to be a single scrolling `LandingScreen` structured like a SaaS marketing page (hero copy, feature grid, "how it works" list, CTA banner, footer) with top-corner text links for navigation — it read as a website, not an app. `LandingScreen.js` was deleted and replaced with the tab-based structure above, specifically to fix that.

### Screens

**`HomeScreen.js`** — the app's actual dashboard (replaces the old marketing landing page). Greeting header, a primary "Analyse your swing" CTA card, three quick shot-type pills that jump straight into Upload with `shotType` pre-set, a stats strip (analyses/avg score/great swings), and a 2-item "recent activity" preview with a "See all" link into the History tab (`navigation.jumpTo('History')`). Like History, this pulls from the real `GET /api/history`, not mock data.

**`HistoryScreen.js`** — full list view of past analyses, stats strip, a "+ New" button that opens an inline upload panel. **Update (2026-08-10, corrected — this was stale):** driven entirely by the real `GET /api/history` (`frontend/api/history.js`'s `fetchHistory`), not mock data — reloaded on every focus via `useFocusEffect`. Each `AnalysisCard` opens the full `ResultsScreen` on tap, and (new this session) shows a "Watch & compare →" shortcut straight into `SyncCompareScreen`'s synced dual-video view when the saved entry has both clip URLs, skipping the extra tap through Results. Also contains `ProgressSection` — a real trend chart (`TrendChart.js`, hand-rolled `react-native-svg`, no chart library installed) computed client-side from the fetched history, with an "Overall Improvement" pill (all shot types combined) and per-shot-type pills (forehand/backhand/serve) that filter the chart and show that type's average score — no separate aggregation endpoint, the full history list already has everything needed.

**`ContactMarkingScreen.js`** — 3-phase contact-marking UI (pick video → rough scrub → frame-by-frame fine adjustment with 0.25× slow-mo preview). Unchanged in core logic from before this session except: removed the duplicate custom back link (native header covers it now), and added an `onConfirmed` callback escape hatch in `confirmFrame()` — if `route.params.onConfirmed` is present it's called with `{videoUri, shotType, contactFrame, contactTimeSec}` instead of the default `navigation.navigate('Results', ...)`. This is what lets `VersusPickScreen` reuse this exact screen twice (via `navigation.push`) for the 1v1 flow without duplicating any of the video-scrubbing logic.

**`ResultsScreen.js`** — the real results screen for the working single-video flow. Loading/error/done states; `buildFormData()` handles the web-vs-native difference in how a picked video URI needs to be packaged for `fetch`. Calls `POST /api/analyse` via `API_BASE` from `frontend/config/api.js` (currently hardcoded to `http://192.168.1.162:5000` — **this is the dev machine's LAN IP and will need updating if the Wi-Fi network reassigns it**; check with `ipconfig`). Shows score, both angle labels, coaching tips, other close matches.

**`LoginScreen.js` / `SignupScreen.js`** — **real auth this session**, not mocked. Call `useAuth().login()` / `.signup()` from `AuthContext`, show real backend error messages (wrong password, duplicate email, etc.), navigate into `MainTabs`/`Home` on success.

**`ProfileScreen.js`** — shows the real signed-in user (avatar initial, name, email) with a FREE/PREMIUM tier badge and working "Log out" when authenticated; shows a "Guest / Not signed in" state with Login/Signup menu items otherwise. Also has static Settings/Help menu items (no-ops).

**`PremiumScreen.js`** — **update (2026-08-10, corrected — this was stale): actually gates now.** Renders `PremiumCheckout` (real RevenueCat web checkout, see the new Planned Features item) when `!isPremium`; the two premium-feature cards ("1v1 Comparison" → `VersusPick`, "Highlight Archive" → `HighlightUpload`) are the gated destination reachable *after* checkout, not freely tappable by a guest as previously documented here.

**`VersusPickScreen.js`** — pick shot type + a reference video ("video you want to copy") + your own video, then chains through `ContactMarkingScreen` twice via `navigation.push('Upload', {videoUri, shotType, onConfirmed: ...})`, nesting a second `onConfirmed` inside the first's callback, finally landing on `VersusResults` with both marked videos' data.

**`VersusResultsScreen.js`** — **update (2026-08-12, corrected — this was stale): real, not mock.** Posts to the real `/api/compare-videos` route (auth-bug fixed the same session — the fetch was missing its `Authorization` header, so every request 401'd until this was caught), and now uses the same shared `ScoreCard`/`AngleRow`/`PhaseBreakdown`/`TipsSection` components as `ResultsScreen.js` (hoisted into `frontend/components/` this session) so a 1v1 comparison looks and behaves like a normal single-swing result — score card, angle row with real degrees, a real phase breakdown (new backend addition, see item 13), and a working tips accordion (this also fixed a real rendering bug: tips used to be printed as raw objects, `[object Object]`, instead of their `tip_text`).

**`HighlightUploadScreen.js`** — pick a match video (messaging caps it at "10 minutes" — not actually enforced anywhere, just copy), a fake "Finding your shots..." processing state (~2.2s), then navigates to Review with hardcoded mock detected clips from `frontend/data/mockHighlights.js`'s `MOCK_DETECTED_CLIPS` (6 entries with fake timestamps).

**`HighlightReviewScreen.js`** — swipe-tag UI: each mock detected clip gets a Forehand/Backhand/Serve/Skip pill. "Save to archive" only enables once at least one clip is tagged something other than Skip.

**`HighlightArchiveScreen.js`** — grid of archived clips: newly tagged clips (passed via navigation params) merged with a small hardcoded starter list (`MOCK_ARCHIVE_CLIPS`, 3 entries). Each row has an "Analyse" button that currently just shows an `Alert` saying this needs the backend clipping pipeline first — intentionally not wired to the real analyse flow, since these are mock timestamps, not real detected swings.

### `context/AuthContext.js`

React Context wrapping the whole app. On boot, tries to restore a saved token (`expo-secure-store` on native, `localStorage` on web — `expo-secure-store`'s native APIs don't exist on web, so there's a small platform-conditional storage shim at the top of the file) and validates it against `GET /api/auth/me`; if that fails (expired/invalid), clears it silently rather than blocking app startup. Exposes `user`, `token`, `loading`, `isAuthenticated`, `isPremium` (`user?.tier === 'premium'`, sourced purely from the backend — no client-side RevenueCat entitlement check), and `signup`/`login`/`logout` methods, plus `refreshUser()` (re-pulls `/api/auth/me` — called right after a successful purchase so `isPremium` updates without a full re-login, see the new Planned Features item on payments).

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
| 2 | Unlimited History + Progression | **Built, and now really gated (2026-08-10 correction).** Real `analyses` table, real save/list/delete API, real progression chart (overall + per-shot-type, with average score) in `HistoryScreen.js`. `FREE_TIER_LIMIT = 3` in `history.js` is enforced against a real `isPremium`, which is now backed by a real, working payment flow — not a placeholder (see the structural gap note below and the new Planned Features item). |
| 3 | Positional Movement Analysis | **Not started.** No court coordinate system, no footwork tracking. Jack's own spec already flags this as V2/research-stage. |
| 4 | Auto-Crop Shots from Match Footage | **Frontend UI shell only** (Highlight Archive, described above). Real backend (shot detection on raw match video + classifier) doesn't exist. |
| 5 | 1-on-1 Coaching Mode | **Update (2026-08-12, corrected — this was stale): fully wired and now at layout/feature parity with single-swing Results.** `compare_videos.py` is called by a real route (`backend/src/routes/compareVideos.js` → `/api/compare-videos`) and `VersusResultsScreen.js` posts a real `Authorization` header (a real bug — it was missing, causing every 1v1 request to 401 — found and fixed 2026-08-12). The backend now also computes a real phase breakdown for 1v1 comparisons (previously only the pro-database flow had one). See new Planned Features item 13 for the full writeup. Strict 30–45° angle enforcement from the spec is still not implemented (only a soft >25° warning, by design — see `compare_videos.py`'s own comments). |
| 6 | Video Playback with Overlay Annotations | **Built.** `SyncCompareScreen.js` plays the user's clip and the matched pro's clip synced to a shared scrubber with variable-speed control and milestone markers (offset from each clip's marked contact time), reachable from Results and History. Trajectory overlay data (`overlayA`/`overlayB`) is rendered as a real stick-figure skeleton overlay (`SkeletonOverlay.js`, upper-body only) in different colors for user vs. pro (see item 3 in "Planned Features" below — corrected 2026-08-10, this was wrongly marked deferred). |
| 7 | Coach Collaboration Mode | **Update (2026-08-11, corrected — this was stale, but only spot-checked, not fully investigated):** `backend/src/routes/coach.js` is real and mounted, and `coach_invite_codes`/`coach_links` tables exist in `db.js` (invite-code generation + coach/student linking between ordinary accounts, no separate role). `coach_notes` (per-analysis notes tied to a phase/timestamp) is also real — `ResultsScreen.js`'s `NotesBlock` already uses it. This was only confirmed via a quick file-existence check while triaging outstanding work, not a full read of the actual endpoints/frontend wiring — treat "how complete this is" as still an open question, just not "not started." |

**Update (2026-08-10, this whole note was stale): real payment processing exists and is wired.** Not Stripe (those placeholders are genuinely unused) — **RevenueCat**, with real (non-placeholder) credentials already in both `.env` files. See the new "Payment integration (RevenueCat)" item under Planned Features for the full picture: what's live, what's deliberately parked, and two real bugs found and fixed this session. The tier flag (`users.tier`) is real and now kept in sync by both a client-triggered sync endpoint and a server-side webhook, not just a manual SQLite edit.

## Other Known Gaps (not from the premium list)

- **Coaching tips**: **update (2026-08-10, corrected — this was stale)** — the live app *does* use the real 216-tip database + selector: `compare_swing.py` imports and calls `get_coaching_tips()` (`scripts/09_coaching_ai/select_coaching_tips.py`) for every top match, confirmed by real saved history rows (e.g. analysis id 151's tips are genuine multi-phrasing selections, not the old single-phrasing dict). The Claude-verifier half of that system is a separate, still-open question — see the new "Improve the shot classifier" item under Planned Features, which covers the sibling teacher-student system for shot classification specifically.
  - **Tips button fix (2026-08-10):** the "Tips & drills to fix" panel and individual tip rows in `ResultsScreen.js` were reported as not expanding on press. Root cause found in the shared `Collapsible` helper: its `onLayout` height-measuring child was a plain flow child inside an `Animated.View` clipped to `height: 0` — on native this can skip laying out a zero-height parent's children entirely, so `contentHeight` never got measured and the open/close animation always animated to `0`. Fixed by making the measuring child `position: 'absolute'` so it's laid out independent of the parent's clipped height. Data/diagram coverage was checked and is not the issue — all 30 real tip `issue_id`s have a matching SVG diagram in `tipVisuals.js`.
  - **Tip photos (2026-08-10):** `TipDiagram.js` now checks `tipDiagrams/tipPhotos.js` for a real photo by `issue_id` first, falling back to the SVG diagram when none exists yet. Real photos are being generated externally and dropped into `frontend/assets/tipPhotos/` (see that folder's README for the naming convention) — each one needs one `require(...)` line manually added to `tipPhotos.js` (Metro can't require by variable), so photo coverage fills in incrementally without breaking anything.
- **`ResultsScreen`'s `API_BASE`** is a hardcoded LAN IP, not derived automatically — will silently break if the dev machine's IP changes.
- **Update (2026-08-10, corrected — this was stale):** "no automatic shot-type classifier exists anywhere" is no longer accurate — `scripts/14_shot_classifier/` classifies user-uploaded swings live (pro database entries are still hand-assigned per source compilation, that part is unchanged).
- **High-angle pro database entries (>65°) have never been manually audited** for behind-baseline false positives, per the original angle-detection limitation.
- **Update (2026-08-10, corrected — this was stale):** the racket keypoint model *is* used live now (body_rotation phase scoring, and the new shot-contact verifier — see the "racket keypoint ML" section above and the new Planned Features item below). The net-end keypoint model (`data/10_net_detection/`) remains genuinely unintegrated — that part of the original claim still holds.

---

## Planned Features — Research Brief (GolfFix-Inspired)

Jack supplied this brief this session, referencing GolfFix (a golf-swing-analysis competitor product) as the model to take cues from. Recorded here verbatim-in-substance so the reasoning and specifics aren't lost, with notes on how each piece would connect to the existing codebase.

### 1. Slider Synchronization Feature (side-by-side synced comparison)

**Update (2026-08-10, fully built now — this whole item is done.** `SyncCompareScreen.js` plays the user's clip and the matched pro's clip synced to one shared `PanResponder` scrubber, offset from each clip's own marked contact time so "impact" lines up even with different clip lengths — reachable from `ResultsScreen`'s "Compare side-by-side" button and from a `HistoryScreen` card's "Watch & compare" button. **Update (2026-08-12): `VersusResultsScreen`'s "Compare side-by-side" button now lands on this exact same screen too** — the 1v1 flow was wired to the real backend the same session (see item 13), so both paths share one synced-comparison implementation, including the pinch/pan zoom gesture added that session.

Both originally-missing pieces are now shipped too:
- **Variable-speed scrubbing** (0.5×/1×/2×) — `SPEEDS` buttons in `SyncCompareScreen.js`, calling `setRateAsync(rate)` on both video refs. `PlatformVideo.native.js` needed a small wrapper (`useImperativeHandle`) to normalize its signature to match web's, since expo-av's own `setRateAsync` takes extra pitch-correction args web doesn't.
- **Milestone markers** on the timeline (backswing/contact/follow-through — not the full address/top-of-swing/impact/follow-through 5-point brief, see below) — `phase_breakdown.py`'s `compute_phase_breakdown()` already used fixed relative-to-contact offsets (`PHASE_TARGET_T = {backswing: -0.5, contact: 0.0, followthrough: 1.0}`) internally for scoring; these are now literal-restated as a `phase_markers` field in the response (`compare_swing.py` → `ResultsScreen.js`/`HistoryScreen.js` → `SyncCompareScreen` route param) and rendered as tappable ticks on the scrubber track. No new backend computation was needed — `address`/`top-of-swing` aren't derivable from current data and were deliberately left out rather than faked.

A comparison mode where the user's video and the matched pro's video play **simultaneously, side by side, sharing one scrubber**. Described as GolfFix's most credibility-building feature — seeing your own frame next to the pro's frame at the exact same swing phase makes AI feedback tangible in a way a text tip alone doesn't.

### 2. Camera Angle Calibration

GolfFix's spec: camera "facing directly at the center of your body at address, positioned 8–13 feet away (face-on) or 6–10 feet away (down-the-line)." Proposed for this app:
- User selects recording angle intent (face-on vs. side/down-the-line) before recording or uploading.
- System analyzes the first frame to check camera height (should be roughly chest height) and perpendicularity to the player.
- Uses pose keypoints (shoulders, hips, feet) to verify alignment — if spine angle or stance width reads as distorted, that's a signal the framing is off — and gives an actionable warning (e.g. "Move camera 2 feet to the left").
- Rationale given: bad camera angles are a direct cause of pose-detection failure, so catching this *before* or immediately after upload should meaningfully improve downstream analysis quality.

**Update (2026-08-10, corrected — (a) and (b) were already built, this section understated it):** `05_angle_detection/infer_angle.py` infers camera angle (0–90°) from net detection (Hough-line, or the trained net-keypoint model when available) and buckets it into labels (Front/Semi-front/Diagonal/Semi-side/Side) — used for the live "Your angle"/"Pro's angle" surfaced in `ResultsScreen`, but that's not the only use. A **pre-flight check already exists and already runs before committing to full analysis**: `ContactMarkingScreen.js` calls `/api/check-setup` (`backend/src/routes/calibration.js` → `scripts/00_utils/check_camera_setup.py` → `infer_camera_angle()`) the moment a video is picked/recorded, and there's also a **live-camera positioning guide** (`/api/check-setup-live` → a persistent `calibration_server.py` process on port 5055 → `LiveCalibrationCamera.js`/`FenceTutorialScreen.js`) giving real-time feedback *before* the player even starts recording — both already translate the angle + an elevation heuristic into an actionable `message` string (e.g. camera-too-low guidance), not just a raw label.

**(c), the shoulder/hip/stance-width pose-geometry distortion check, was the one genuinely missing piece — built this session, see below.** `infer_angle.py`'s `_angle_from_frame()`/`check_camera_setup_frame()` already ran cheap single-frame MediaPipe pose extraction (shoulders, ankles) for a different purpose (player-x, elevation), so adding hip landmarks and a stance-width/shoulder-tilt check reused that same primitive rather than needing new extraction — though where it actually ended up shipping live turned out narrower than first planned, for a real reason found by testing it, not by design.

**Pose-geometry stance/tilt check — built 2026-08-10:** `infer_angle.py`'s `IDX` dict gained `left_hip`/`right_hip` (23/24, standard MediaPipe indices). `_angle_from_frame()` now also computes `stance_width_ratio` (hip-width ÷ shoulder-width) and `shoulder_tilt_deg` (shoulder line's angle from horizontal, wrapped into 0–90°), both `None` when hips/shoulders aren't confidently visible or when the shoulder line is closer to vertical than horizontal (see below for why that guard exists). `framing_label()` buckets these into `'ok'` / `'tilted'` / `'compressed_stance'` / `'unknown'`, mirroring `elevation_label()`'s pattern, with thresholds (`STANCE_WIDTH_RATIO_LOW = 0.30`, `SHOULDER_TILT_MAX_DEG = 15.0`) chosen from real data, not guessed (see below).

**Empirical finding that shaped where this actually shipped:** first attempt computed `shoulder_tilt_deg` from `atan2` without wrapping mod 180°, and spot-checking against ~60 real swing clips (this session's now-standard discipline, not skipped this time either) immediately found real, obviously-wrong results — 5 clips reported as "tilted" at 100–160°, physically impossible for a real shoulder line. Root cause, confirmed by pulling the actual frame: the player was mid-rotation through their swing (or in a back-view frame where MediaPipe's anatomical left/right flips on-screen), which the naive formula misread as camera tilt. **Fixed the math** (wrap to [0,90], plus a guard: only trust the reading when the shoulder line is closer to horizontal than vertical) — but even after the fix, sampling from an already-recorded *swing clip* (this pipeline's actual input, at fixed 25/50/75%-of-clip fractions) still occasionally lands mid-motion and produces a real but misleading tilt reading (e.g. 19.8° on a visibly level-camera clip where the player was just turning into their shot). Testing the same signal on frames from *before* the swing starts (a proxy for the live pre-recording calibration context, where the player is standing still positioning their camera — the actual assumption this check needs) gave a clean, tight distribution (44/44 samples 0–26°, all but 2 under 15°) — confirming the signal is sound, just not from mid-swing-clip sampling.

**Net result:** the check is fully wired and live in `check_camera_setup_frame()` (the live pre-recording path — `/check-setup-live` → `calibration_server.py` → `LiveCalibrationCamera.js`), where the standing-still assumption holds and the signal was validated clean. `check_camera_setup.py` (the post-*upload* swing-clip path, `/check-setup`) still computes and returns `framing_status`/`stance_width_ratio`/`shoulder_tilt_deg` as raw data, but deliberately does **not** fold it into the user-facing `message` there — real testing showed it produces misleading "camera tilted" text on perfectly level-camera footage when read from an already-recorded stroke. No frontend changes were needed either way — `LiveCalibrationCamera.js`/`ContactMarkingScreen.js` already just display `message`, and the new field is purely additive.

### 3. Skeleton Overlay

**Update (2026-08-10, corrected — this was wrongly marked "deliberately deferred, not built for MVP." It is actually already built and live.** The original decision recorded below (gate skeleton rendering behind real user testing) appears to have been superseded without this doc being updated — `frontend/components/SkeletonOverlay.js` was added in commit `8d4223d` and is a real, working stick-figure renderer: 8 bone-lines + joint circles via `react-native-svg`, driven by precomputed per-frame trajectories (`compare_swing.py`'s `build_overlay_trajectory()`, 9 upper-body joints: nose/shoulders/elbows/wrists/hips), synced to `SyncCompareScreen`'s scrubber via linear interpolation between the two bracketing `{t, landmarks}` samples, and mounted twice with different colors for a real user-vs-pro overlay — exactly what the brief asked for. Reachable from both `ResultsScreen` and `HistoryScreen` via the "Compare side-by-side"/"Watch & compare" buttons into `SyncCompareScreen`.

**One real, named limitation:** upper-body only — no hips-down (knees/ankles). Legs aren't tracked anywhere in this app's pose pipeline at all (a scope choice made elsewhere, not a bug in the overlay itself). Only shown on the *uncropped* video, since overlay coordinates are in original-video pixel space and the crop-to-subject transform was never persisted. Closing the legs gap would mean adding hip(already tracked)/knee/ankle landmarks to `compare_swing.py`'s `KEY_LANDMARKS` and extending `SkeletonOverlay.js`'s `BONES` array — not currently planned, flagged as an open option rather than committed work.

**Update (2026-08-10, follow-up session): `SyncCompareScreen.js` reworked further.** The pre-cropped ("cropped"/"original" toggle) video variant was dropped entirely — both panes now always show the original, uncropped video (zoomed in to compensate, see below), since the skeleton overlay only ever worked on originals anyway and the toggle was extra UI for no real benefit. Three new interactive controls were added:
- **Zoom slider** — the previous fixed `ZOOM = 1.3` constant is now a draggable slider (`zoom` state, range 1.0×–2.5×, default 1.6×), built with the same `PanResponder` + `Animated.Value` track/handle pattern already used for the scrubber (no new dependency).
- **Skeleton show/hide toggle** — `showSkeleton` state; `showOverlay` becomes `hasOverlayData && showSkeleton`, so hiding it actually unmounts `SkeletonOverlay` rather than just visually covering it.
- **Annotation toolbar** — new `frontend/components/AnnotationCanvas.js`, an `react-native-svg`-based freehand drawing layer (pen/line/arrow/circle), one independent instance per pane (drawing on your own frame doesn't affect the pro's). **Update (2026-08-13): now persisted, not local-only** — see Planned Features item 17 for the full `getStrokes()`/`loadStrokes()` + `swing_annotations` table writeup; a "Save annotation" button in the toolbar saves both panes, and any saved set is auto-loaded back in on return. Entering annotate mode auto-pauses both videos. Uses `pointerEvents='none'` when inactive so it never steals touches from the scrubber/scroll when off. The canvas reads `tool`/`color`/`active` from refs updated via `useEffect` rather than closing over the props directly inside the memoized `PanResponder` — a real stale-closure bug that would otherwise freeze the tool/color at whatever they were on first render (`PanResponder.create()` inside `useRef` only runs once).

The pane layout also grew taller (`videoWidth * 1.85` vs. the old `* 1.5`) and the whole screen is now wrapped in a `ScrollView` (`scrollEnabled` toggled off while the scrubber/zoom-slider/annotation canvas is actively being dragged, to avoid gesture-capture competition) — deliberately requires more scrolling to reach the timeline in exchange for bigger, more legible video panes.

**Original decision, recorded for context (apparently superseded — see above):** the brief's explicit call was to ship pose detection + text feedback only first, gated behind real user testing:

> After week 2 user testing with 10 real players: if users don't trust the AI analysis without seeing the skeleton, add it post-MVP. If users say the text feedback is clear and actionable on its own, defer it indefinitely.

**Discrepancy worth flagging:** the brief describes pose detection via **AWS Rekognition or Google Cloud Vision**, returning ~17 COCO-style joints. **This project does not use either** — the actual pipeline is MediaPipe Tasks API throughout (`pose_landmarker.task`, 33 landmarks, all local/offline, no AWS or GCP calls anywhere in the codebase — confirmed, `AWS_REGION`/`AWS_ACCESS_KEY_ID`/`S3_BUCKET` in `backend/.env` are unconfigured placeholders, never wired to any code path). MediaPipe's 33 landmarks are a superset of the ~17 the brief describes, and the built overlay draws from that same landmark data.

### 4. Improve the shot classifier (added 2026-08-10)

`scripts/14_shot_classifier/` — a rule-based "student" classifier plus a Claude vision "teacher" verifier, mirroring the coaching-tips teacher-student pattern in `scripts/09_coaching_ai/`. Empirical testing against 7 known-labeled clips found only **57% final accuracy**, with the teacher flipping roughly as many correct student picks to wrong as it fixed — i.e. the vision verifier is not currently a clear improvement over the rule-based classifier alone at this sample size. Currently kept active (every classification goes through both student and teacher, logged to `shot_classifier_training_log.jsonl`) per Jack's explicit call: keep the verifier running and logging until the student is proven trustworthy on its own (`should_trust_student()` in `shot_classifier_training_log.py` — `AGREEMENT_THRESHOLD=0.90` over a rolling window of 100, needs `MIN_EXAMPLES_BEFORE_TRUST=50` logged examples first), not before. The overnight batch runs against real match footage (see below) are what's building up that log. Next step here is accuracy work on the rule-based student itself, and/or a larger labeled sample to properly judge whether the Claude teacher is worth the API cost at all for this specific task.

### 5. Improve match highlights / rally detection (added 2026-08-10)

Jack's own definition of a rally, to build toward: **a consistent stretch of time where the ball is being struck at a steady cadence, without too long a gap between hits.**

**Update (2026-08-10, largely done):** the swing-detection-noise half of this problem (item 7 below) turned out to be most of it. `scripts/11_highlight_clipping/detect_rallies.py` (the real implementation — `backend/src/services/rally_detector.py` is a thin CLI shim that just calls it) now gates every wrist-velocity candidate through the shot-contact verifier (`scripts/16_shot_verification/`) *before* grouping, via a new `filter_to_real_rally_shots()`: non-real shots (camera fiddling, ball bounces) are dropped, and shot-typed candidates that resolve to `'serve'` are also excluded, since a serve shouldn't anchor or extend a rally group (falls back to `14_shot_classifier/`'s classifier when the verifier's teacher wasn't called, i.e. student was trusted and skipped Claude). `group_into_rallies()`'s gap-based split logic itself is unchanged — it now naturally means "extended gap with no *verified real* shot," and the existing pre/post padding around the first/last verified swing produces a tighter, noise-trimmed crop than padding around raw peaks did. Tested against a real clip: correctly filtered camera-fiddling and a serve, produced valid grouped output.

Still open: cadence *consistency* (not just raw gap size) isn't factored in yet, so a rally with one unusually long pause could still split incorrectly, or vice versa — worth revisiting once there's a larger sample of real match uploads through the new gated pipeline to see whether this is still a real problem in practice.

### 6. Drills & Exercises page (added 2026-08-10)

New 5th bottom tab, `DrillsScreen.js`, built this session as a **structural stub only** — real navigation, a visual shell matching `HistoryScreen`/`HomeScreen`'s card patterns, placeholder categories (forehand/backhand/serve/footwork) with an empty state. Deliberately no real drill content yet, per Jack. Next step: a real drills database, most naturally mirroring `data/08_coaching_ai/coaching_tips_database.json`'s shape — drills tied to specific `issue_id`s so a tip's "Drill —" text (currently free-form per-tip copy in the coaching tips database) could eventually link out to a fuller drill entry on this page instead of just showing inline. **Update (2026-08-13, navigation restructure, item 19): `DrillsScreen.js` no longer exists as a standalone tab** — the same stub content was extracted into `components/DrillsSection.js` and now renders inside `HistoryScreen.js` behind a History/Drills segmented toggle. Still just a placeholder; the real-content next step above is unchanged.

### 7. Verify that a detected swing is a real shot (built 2026-08-10)

**The problem, confirmed directly by Jack against his own real history:** "a shot" was defined purely as a wrist-velocity local-maximum (`detect_swings.py`'s `find_swing_peaks()`) — no check that a real racket-to-ball strike happened. Real consequence: several "great swings" (score ≥75) in Jack's saved history turned out to be camera fiddling or ball-bouncing, not real shots at all.

**Three geometric-only attempts this session did not converge**, each trading one failure mode for another against the same real test candidates (`data/runtime/highlight_clips/13/3/rally_030.mp4`, cross-checked by pulling and visually inspecting the actual frames every time, not assumed):
1. Cropping tightly around the player before running the generic pretrained COCO racket/ball detector (`racket_tracker.py`, `yolo11n.pt` classes 38/32) — a real, kept improvement (fixed real missed-ball detections), but not sufficient alone.
2. Three different "is the racket actually moving" checks on top of that (raw frame-to-frame centroid delta, windowed before/after average, a proper polynomial trajectory fit) — each failed differently. The last one found something informative rather than just "needs more tuning": at a visually-confirmed real contact frame, racket speed was only ~20% of the window's peak speed, suggesting peak racket speed often lands *after* contact (follow-through), undermining the "contact ≈ peak speed" premise the whole line of attempts was built on.
3. Swapping the generic bbox detector for the fine-tuned racket-*keypoint* model (see item 4's "used live now" note above) didn't fix it either — same pattern of failures, confirming the ceiling was the geometric approach itself, not detector precision.

**What actually worked: a Claude teacher-student loop, mirroring `scripts/14_shot_classifier/`'s pattern exactly** — new folder `scripts/16_shot_verification/`:
- `verify_shot_contact.py` — the "student" (the geometric detector from attempts above, kept as-is; doesn't need to be good, only cheap — same as the shot-type classifier's own ~57% student).
- `shot_contact_verifier.py` — the Claude vision "teacher." Sends a **sequence** of 7 frames spanning the candidate window (not one still — a single frame can't distinguish "mid-swing" from "bouncing the ball," motion across frames can), and answers **both** "is this a real shot" and "what shot type" in one call (combined with the shot-type classifier's own question, since both look at the same frames — halves the API cost of running them separately).
- `shot_contact_training_log.py` — same agreement-rate/trust-threshold mechanics as `shot_classifier_training_log.py`, separate log/threshold from the shot-type classifier's. Also accepts real human labels (`source='user_flag'`) from the app, not just Claude's.
- `verify_shot_contact_verified.py` — orchestrator (mirrors `classify_shot_verified.py`).
- `batch_verify_all.py` — ran this across **all 89 real rally clips** for Jack's two match videos, checkpointed/resumable (`data/runtime/shot_verification_batch/verified_swings.jsonl`). **Result: 349 total wrist-velocity candidates, only 111 (32%) were real shots** — hard confirmation of the scale of the original problem. Final student/teacher agreement rate: **~51%** (in the same honest range as the shot-type classifier's own 57% — Claude stays authoritative, `should_trust_student()` correctly reports `False`).

**Real human ground truth, not just Claude's:** `HistoryScreen.js` now has a two-way "Yes, real shot" / "No, not a shot" button pair on every history card (`confirmed_real_shot`/`flagged_not_shot` columns on `analyses`, mutually exclusive, `PATCH /api/history/:id`) — any user's own verdict logs into the same training log as `source='user_flag'`, real ground truth for training/validating the verifier over time, available to every user, not just Jack.

**Applied back to Jack's real history** (`apply_verification_to_history.py`, one-off but rerunnable): of 245 existing saved analyses, **89 auto-flagged as not real shots** (Claude-confirmed, visible in the app with a red banner), **36 re-cropped** to a tight 2-second-before/2-second-after window around the verified contact moment (replacing the original, sometimes-mistimed window), 120 unmatched (swing-index numbering didn't line up between the original overnight run and this session's fresh detection pass on the same clips — good candidates for Jack to spot-check with the new confirm/flag buttons).

**Full pipeline retrain**, `analyze_rallies_parallel.py`: `build_worklist()` now gates every candidate through the verified-shot check *before* spending any classification/comparison work on it, reusing `batch_verify_all.py`'s already-paid-for Claude verdicts when available (same rally clips, deterministic detection — no duplicate API calls) rather than re-verifying live. `_batch_source` now also records `shot_verified_source` for traceability. Jack's full history was deleted (backed up first to `data/backups/`) and regenerated from scratch through this gated pipeline.

**Also fixed along the way:** `crop_to_subject.py`'s pose-driven crop (`MARGIN`, used for both the "Watch & compare" sync view and this new verifier's cropped-frame detection) was clipping the racket/ball right out of frame — the margin only accounted for body landmarks, not how far a racket extends beyond the wrist during a real swing. Raised `0.35 → 1.6`, confirmed visually on real clips, and re-ran `recrop_user_clips.py`/`precrop_pro_database.py --force` to regenerate all existing cropped clips (both user and pro) with the fix.

**Retrain completed (2026-08-10):** an Anthropic API credit outage killed the first retrain attempt partway through (caught via log inspection, process killed proactively before any degraded fallback data could be saved — nothing had reached the `analyses` table yet at that point). After topping up, the retrain reran clean — **105 saved, 0 failed**, down from the old unverified 245 (roughly matching `batch_verify_all.py`'s 111/349 real-shot rate). "Great swings" (score ≥75) dropped from 6 to 3 — the fake ones are gone. Spot-checked several of the new entries by pulling frames at/near the labeled contact time against the actual clip: all showed genuine swings, though a couple of `contact_time_sec` labels landed a few frames after the real strike (into follow-through) — a minor timing-precision note, not a false-positive-verification issue.

**Cost investigation and fix (2026-08-10):** `detect_rallies.py` (above) now calls the verifier on every candidate swing in every future match upload — an ongoing cost, not a one-time batch job, which Jack flagged directly. Backtesting the 213 examples already logged in `shot_contact_training_log.jsonl` (zero new API calls) found the student's logic was **actively broken, not just weak**: 49.8% accuracy, worse than always guessing "real" (55.4% base rate). Root cause: `verify_shot_contact.py`'s `static_hold(...)` reclassification (reject a candidate when the racket wasn't near its fastest tracked speed at the contact point) was wrong 63–83% of the time — consistent with the earlier finding that real contact often lands well below peak racket speed. **Fixed**: removed that rejection rule (speed data still computed/logged as diagnostic, just no longer drives an auto-reject) — lifts blended accuracy to 65.7%, zero additional API cost.

Also replaced the single global `should_trust_student()` gate with **per-evidence-type trust gating** (`shot_contact_training_log.py`): `bucket_for(contact_method)` collapses the noisy fine-grained method strings into three stable categories (`no_evidence`/`proximity`/`occlusion_gap`), each independently gated by `should_trust_bucket()` using a **Wilson score interval lower bound** (95% confidence, deliberately more conservative than the raw percentage — several sub-buckets showed misleading 100% on N=1-3 samples) rather than one pooled rate that a noisy bucket can permanently cap. `verify_shot_contact_verified.get_verified_shot_contact()` now checks the swing's own bucket, not the global gate. **Honest result, not yet a cost saving**: with current data no bucket clears the 90% Wilson-bound bar (`no_evidence` 65%/N=72, `proximity` 66%/N=29, `occlusion_gap` 66%/N=112, all well below) — this is real infrastructure for *future* savings as more usage accumulates real examples through the gated rally-detection pipeline and user flags, not a claim that Claude calls have gone down today. If geometry's ceiling really is ~65-70% (consistent with all of this session's earlier geometric attempts), it's possible no bucket ever clears 90%.

**Verify buttons also on ResultsScreen now (2026-08-10):** the two-way "Yes, real shot"/"No, not a shot" buttons were previously only on `HistoryScreen` cards. Now also on `ResultsScreen` — the first place a user actually watches their swing back. Along the way, fixed a real gap: `ResultsScreen` never captured a freshly-analyzed result's own `analysisId` after `saveToHistory()` saved it (only had one when navigated in from History), which also silently broke coach notes on a just-analyzed result. `saveToHistory()` now captures the saved row's id into a `savedAnalysisId` state var that notes, verify buttons, and the Compare button all use — fixing notes for fresh results as a side effect, not just adding the new buttons.

### 8. "Wrong shot type?" correction + animated share popup (added 2026-08-10, follow-up session)

Two smaller frontend features, both feeding real human ground truth back into training data or improving the existing share flow:

- **Shot-type correction.** `ResultsScreen.js` and `HistoryScreen.js` both gained a "Wrong shot type?" button (bordered pill, upgraded from an earlier plain-text version that was hard to notice) revealing a 3-way forehand/backhand/serve picker. `correctShotType()` (`frontend/api/history.js`) `PATCH`es `/api/history/:id` with `{shot_type}`; the backend (`history.js`) validates it, updates the `analyses` row, and — only on a genuine change — logs a `source: 'user_flag'` record to `data/14_shot_classifier/shot_classifier_training_log.jsonl` via a new `logShotTypeCorrection()`. This is the same real-human-label pattern already used for `flagNotShot`/`confirmRealShot` (item 7 above), now extended to shot-type. Found and fixed a real bug while wiring this: `shot_classifier_training_log.py`'s `agreement_rate()`/`should_trust_student()` had no filter for unpaired (`agreed=None`) records — the same bug already fixed earlier in `shot_contact_training_log.py` but not mirrored here — which would have let the new unpaired `user_flag` entries silently deflate the trust rate. Fixed with the same `[r for r in read_log() if r.get('agreed') is not None]` filter, verified with a unit test (5 paired agree=True + 3 unpaired still returns `1.0`).
- **Animated share popup.** Tapping the share icon on `ResultsScreen.js` now opens a popup (not an immediate native share sheet) showing an animated score-fill ring — `ScoreRing.js` gained an `animate` prop that sweeps the SVG ring from 0 to the final score over ~1.1s with the number counting up in sync — plus a "Swing breakdown" list of every phase and its score/25 below it. The actual PNG captured for the native share sheet (`ResultShareCard.js` → `captureAndShare`) still renders fully filled/static, so the exported image is never caught mid-animation; only the in-app preview animates.

### 9. Deployment / Hosting (started 2026-08-10, follow-up session — in progress)

The backend already has a full Docker-based deploy story, targeting an Oracle Cloud "Always Free" Ampere A1 VM (chosen specifically because it's the only real free tier with enough RAM/storage for this app's torch/mediapipe/ultralytics stack and ~12GB+ of pro-clip data):
- Repo-root `Dockerfile` (Node 22 + Python 3.13, builds the same `scripts/venv` layout the app already expects locally, pre-downloads YOLO weights) and `docker-compose.yml` (`app` service with `data/`+`backend/data/` mounted as volumes, plus unused `postgres`/`redis` services reserved for later).
- `DEPLOY.md` (repo root) documents the full one-time server setup: rotate the API key (now done, see "Read This First"), install Docker, `rsync` the gitignored `data/` directory to the server, create `backend/.env` with a real `JWT_SECRET`, then `docker compose up --build app`.
- **Verified this session**: `docker compose build app` completes cleanly end-to-end on this Windows dev machine (image `tennis_app-app:latest`, 6.87GB) — confirms the Dockerfile and every pinned Python/Node dependency resolve correctly. **Not yet verified**: this build ran on x86_64, not Oracle's aarch64 Ampere shape — `DEPLOY.md` already flags confirming the ARM build separately once actually on the VM.
- **Current blocker**: Oracle's Ampere A1 free shape is hitting "Out of host capacity" on instance creation — a known, common issue with that specific free tier, not a config mistake. `DEPLOY.md` gained a new "Working around Ampere capacity errors" section covering, in order of effort: trying every Availability Domain in the home region (capacity is per-AD), requesting a smaller Ampere shape (e.g. 2 OCPU/12GB instead of 4/24 — partial allocations succeed more often), trying a different home region (one-way choice, check nothing's provisioned yet first), and a scripted `oci compute instance launch` retry loop (the standard community workaround for this exact error). A paid-VPS fallback (Hetzner/DigitalOcean/Linode) is documented as the escape hatch if none of that works in a reasonable time — requires zero Dockerfile/compose changes, same `docker compose up --build app` on any Docker host.
- Also fixed along the way: `backend/.env.example` was missing `JWT_SECRET` despite the app requiring it at runtime and `DEPLOY.md` telling you to set it — added, with a comment to generate a real random value.
- **Not yet done**: actually provisioning a reachable server (blocked on the above), transferring `data/` to it, opening the inbound port, and confirming `/health` responds from outside the VM. Frontend hosting (a web deploy, or EAS submit to app stores) has no plan yet either — `DEPLOY.md` explicitly scopes itself to the backend only; `frontend/config/api.js`'s `API_BASE` is already configurable via `EXPO_PUBLIC_API_BASE`, so once a backend URL exists, pointing a build at it needs no frontend code changes.

### 10. Payment integration (RevenueCat) — verified and two real bugs fixed (2026-08-10, follow-up session)

The user asked to "get payment setup," expecting to start from scratch (matching what this doc used to say). That was wrong — investigation found a **nearly-complete RevenueCat integration already built**, with real (non-placeholder) credentials already in both `.env` files. Not Stripe — those keys really are unused placeholders, as previously documented; RevenueCat is the real, live provider, using raw `fetch` against its REST API (no SDK on the backend, `@revenuecat/purchases-js`/`react-native-purchases` on the frontend).

**What's actually live:**
- **Frontend**: `PremiumCheckout.web.js` is a complete, working RevenueCat web SDK checkout flow (`Purchases.configure()` → `getOfferings()` → `purchase()` → `POST /api/billing/sync` → `refreshUser()`), rendered from `PremiumScreen.js` (which now genuinely gates on `isPremium`, correcting the "does not gate anything" note this doc previously had). `HistoryScreen.js`'s `FREE_TIER_LIMIT = 3` is a real, working gate, not cosmetic.
- **Backend**: `POST /api/billing/sync` (`billing.js`) and `POST /api/webhooks/revenuecat` (`webhooks.js`) are both real and mounted (`server.js`). `requirePremium` middleware is genuinely applied to two real routes (`compareVideos.js`, `highlights.js`), not built-and-unused. A `payment_events` table logs every webhook delivery as an audit trail.
- **Native checkout is deliberately parked, not missing**: `PremiumCheckout.native.ready.js` is a complete native purchase flow, kept off the `.native.js` extension Metro auto-resolves (currently a no-op stub) because `react-native-purchases` is a native module unsupported in plain Expo Go — activating it needs an EAS dev client build, a real decision point, not just an oversight. Its own header comment documents the exact activation steps (rename over `.native.js`, delete itself, uncomment `initPurchases()` in `App.js:16`).

**Two real bugs found and fixed, both live-tested against the real RevenueCat API and a real local backend (not just code review):**
1. `billing.js`'s entitlement-list parsing (`data.active_entitlements || data.items || []`) was checked against RevenueCat's real API v2 docs + community-reported real responses — the array is actually nested at `active_entitlements.items`, not `active_entitlements` itself (that's an object: `{object, items, next_page, url}`). Since the object is truthy, the `||` chain never reached the correct fallback, and `.some()` was called on a plain object — **every real `/billing/sync` call was broken**. Fixed to `data.active_entitlements?.items || data.items || []`.
2. Found *while* live-testing the fix above: a customer who's never made a purchase doesn't exist in RevenueCat yet — confirmed directly (`curl`ing RevenueCat's real API for a real test user returned `404 resource_missing`) — and the old code treated any non-2xx as a hard error, returning `502 Could not reach billing provider` to the frontend. Since "never purchased" is the single most common case this endpoint will ever see (every free user), this would have broken sync for the overwhelming majority of real users. Fixed: a `404` now resolves to `tier: 'free'` directly, same as an empty entitlements list, instead of erroring.

**Verified end-to-end this session** (real backend restarted to pick up the fix, real DB, real RevenueCat API calls — not simulated): webhook `INITIAL_PURCHASE` → `tier` flips to `premium`; webhook `EXPIRATION` → flips back to `free`; webhook `CANCELLATION` alone → tier stays `premium` (correct RevenueCat semantics — access persists until the period actually ends); wrong/missing webhook auth header → `401`; every event appends a `payment_events` row; `/api/billing/sync` for a real free test user (id 1, never purchased) now correctly returns `200 {"tier":"free"}` instead of `502`. Test user's tier was reset back to `'free'` afterward; the throwaway JWT-minting script used to test `/billing/sync` (same no-secret-printing pattern as earlier sessions) was deleted after use.

**Genuinely still open, not silently glossed over:**
- `frontend/.env` is missing `EXPO_PUBLIC_REVENUECAT_WEB_API_KEY` (the iOS/Android RevenueCat keys are present and real; the web one isn't) — without it, `PremiumCheckout.web.js` won't render locally. This needs the user to pull it from RevenueCat's dashboard (Project → API keys → Web Billing key) — not something obtainable from inside this session.
- Activating native checkout is a real, not-yet-made decision (needs an EAS dev client build).
- No subscription-expiry date is stored anywhere (`users.tier` is a flat free/premium flag) — the webhook's `EXPIRATION` handling covers revocation reactively and correctly, but there's nothing to show a user "renews on X" in the UI without adding a column.
- The webhook's shared-secret `Authorization` header check (not HMAC signature verification) was confirmed to be RevenueCat's actual documented method, not a shortcut needing hardening — flagged here only so it isn't mistaken for an open gap later.

### 11. Shot-type classifier scorer fix (2026-08-11)

The amateur-dataset evaluation (item 10's sibling work, `scripts/17_amateur_eval/`) found the shot-type classifier scoring only **37.1%** against 116 real labeled amateur swings — barely above the 33% random-chance floor for 3 classes. Visual inspection of real misclassifications (pulled actual video frames, zero API calls) confirmed genuine classifier errors, not bad labels — a clear serve scored as forehand, a clear forehand scored as backhand.

**Two root causes found by reading `scripts/04_clip_extraction/extract_clips.py`'s `score_forehand()`/`score_backhand()`/`score_serve()`** (the rule-based scorers `classify_shot.py` runs head-to-head and argmaxes):
1. `score_backhand()`'s two-handed-grip signal (`wrist_sep < 0.15`) was loose enough to fire on genuine one-handed forehands, likely because MediaPipe wrist estimates are noisier on real, more-distant amateur match video than the curated close-up pro-compilation clips these thresholds were originally tuned against.
2. `score_serve()`'s overhead-credit formula (`min(0.55, best_overhead * 2.5)`) barely rewarded the overhead margins real amateur serves actually show (~0.11-0.13 y-units) — while `score_forehand()`/`score_backhand()` only check "not overhead" at the single peak-wrist-*velocity* frame (a serve's downswing, wrist already back down by then, not the toss/contact moment), so they never got penalized for a real serve's earlier overhead moment. Serves were losing the argmax to forehand/backhand almost by default.

**Fixed, tuned entirely offline with zero new Claude API calls** (per the user's explicit constraint for this work) — a new script, `scripts/17_amateur_eval/tune_shot_scorers.py`, reused the pose landmarks already cached from the amateur eval run (`data/17_amateur_eval/poses/*.json`) to test candidate threshold/formula changes as fast local JSON math, no video decoding or MediaPipe re-runs needed. Winning combination applied to the real `extract_clips.py`: `wrist_sep` threshold tightened `0.15 → 0.09`, and `score_serve`'s overhead credit changed to `min(0.7, 0.25 + best_overhead * 4.5)`.

**Sanity-checked the shared-function risk before finalizing**: these scorers are also used by `extract_clips.py`'s own `process_job()`, which validated each already-known shot type against `MIN_CONFIDENCE=0.5` back when the 631-entry pro database's clips were originally accepted/rejected (a one-time, already-materialized process — changing the scorers now doesn't retroactively touch the existing database, only a future rebuild). Re-scored the 9 original compilation jobs' recorded swings with the new logic: forehand unaffected (untouched by this fix), backhand dipped only slightly (a few more correctly rejected), serve acceptance rate actually improved substantially (41.3%→59.1%, 72.9%→82.2%) since more genuine serves now clear the bar. Total accept rate ticked up (55.2%→57.7%), no collapse.

**Verified end-to-end on the real production pipeline** (not just the tuning harness): re-ran `evaluate_amateur_dataset.py` after the fix — **37.1% → 50.0%** real classifier accuracy against the same 116 labeled examples. `serve` correct-predictions roughly doubled (14→30 of 57).

**Still genuinely weak, not fixed this pass**: the shot-contact verifier's `occlusion_gap` bucket (55.6% agreement, the largest bucket at N=126 — visually confirmed one real false positive, a player standing still between points) is untouched — this session's fix was scoped to the classifier only, per explicit direction. Backhand also only has 10 labeled examples in this dataset — real signal, but too small to be confident in isolation.

### 12. Reel-stitch endpoint: job+polling fix (2026-08-11)

`/code-review` flagged `POST /highlights/jobs/:id/reel` (`backend/src/routes/highlights.js`) as blocking the HTTP request/response synchronously for up to `REEL_TIMEOUT_MS` while `stitch_clips.py` ran — every other long-running operation in the same file (`POST /highlights/upload` → `runJob()`) instead uses a DB job row + client polling. A client timeout or disconnect during a slow stitch left no server-side record at all — no way to check status, resume, or avoid a duplicate retrigger.

**Fixed** to match the existing `highlight_jobs`/`runJob()` pattern: new `reel_jobs` table (`db.js`), `POST /highlights/jobs/:id/reel` now enqueues a row and returns `202 {reelJobId}` immediately (the actual stitch runs in a new `runReelJob()`, unawaited, mirroring `runJob()`'s structure), and a new `GET /highlights/reel-jobs/:id` for polling (`{status, reel_url, rally_ids, error}`). `HighlightArchiveScreen.js`'s `ReelCard` switched from one `await fetch()` to POST-then-poll-every-2s, guarded by a `mountedRef` so it stops cleanly if the screen unmounts mid-poll rather than calling `setState` on an unmounted component.

**A second real bug caught while live-testing the fix** (not simulated — tested against 3 real 40-58MB rally clips from an actual user's saved match footage): the old `REEL_TIMEOUT_MS = 2 * 60 * 1000` was measured wrong. `stitch_clips.py` re-encodes every frame via OpenCV (no ffmpeg on this machine), and a direct CLI run of the same 3 clips needed 130+ seconds — meaning the *original* synchronous endpoint would have been killing genuinely-still-working stitches at the 2-minute mark, on top of the blocking problem itself. Confirmed live: the job hit exactly this failure at t=127s under the old timeout. Since the endpoint no longer needs to keep an HTTP connection open, raised `REEL_TIMEOUT_MS` to 10 minutes and re-ran — completed cleanly at t=158s with a real 156MB reel served correctly at its URL.

### 13. 1v1 Comparison: wired to backend, auth bug fixed, full layout parity + pinch/pan zoom (2026-08-12)

Went looking to "wire up `compare_videos.py`" per Jack's request and found the whole pipeline was already built end-to-end (script → `video_matcher.py` → `compareVideos.js` route → `VersusPickScreen`/`VersusResultsScreen`/`SyncCompareScreen`, all registered) — not the standalone/unwired script HANDOVER.md previously (and wrongly) described. The real gap: `VersusResultsScreen.js`'s POST to `/api/compare-videos` never attached an `Authorization` header, so despite the route requiring `requireAuth`, **every 1v1 comparison request was silently 401ing** — the feature was unusable end-to-end despite being fully coded. Fixed: added `useAuth()` + the header, matching the pattern already used elsewhere (`HighlightUploadScreen.js` etc.).

Jack then asked for two follow-ups:

**(a) Pinch-zoom on the swing video screens.** `SyncCompareScreen.js` is the only screen that renders actual video pixels anywhere in the app (both `ResultsScreen` and `VersusResultsScreen` are data/score screens that open it via "Compare side-by-side") — so this was the only place that needed it. Added `react-native-gesture-handler` (`expo install`, resolves against the pinned Expo `~54.0.0`, no SDK bump), wrapped the app root in `GestureHandlerRootView` (`App.js`), and wired a `Gesture.Pinch()` + `Gesture.Pan()` composed gesture onto both video panes in `VideoPane`, driving one **shared** `zoom`/`panX`/`panY` state (so pinching either video keeps both at the same zoomed-in region for a fair side-by-side comparison), clamped so panning can't reveal empty space past the frame edge. The pre-existing `PanResponder` zoom slider is kept as a fallback (useful on web, where gesture-handler doesn't reliably map trackpad pinch) and resets pan to 0 when used.

**(b) Full layout parity for 1v1 results, "as if the database was just that one video."** `VersusResultsScreen.js` was a bespoke dark-themed screen (local hardcoded palette, plain-string tips) that looked and behaved nothing like the real `ResultsScreen.js`. Hoisted `ScoreCard`, `AngleRow`, `PhaseBreakdown`, and `TipsSection` out of `ResultsScreen.js` into standalone `frontend/components/` files (behavior-preserving refactor — `ResultsScreen.js` now imports them instead of defining them inline), then rebuilt `VersusResultsScreen.js` on top of the same shared components + `theme.js` tokens + `CourtBackground`. This also fixed a real bug found along the way: tips were being rendered as `<Text>{tip}</Text>` where `tip` was actually a `{tip_text, drill}` object (the backend never returned plain strings) — printing `[object Object]` in the UI. Switching to the shared `TipsSection` component fixed it for free.

One genuine blocker for full parity: `compare_videos.py` had no phase-breakdown computation (`compare_swing.py` computes one, but only for its top pro-database match). Jack confirmed: add it to the backend rather than omit the section. Implemented by mirroring `compare_swing.py`'s exact approach — `track_racket_body`/`avg_racket_body_distance` on both videos' contact windows, then `phase_breakdown.compute_phase_breakdown()` with the reference video's trajectory standing in for a pro-database entry. **Verified live** via direct CLI run against two real forehand clips — correctly returned `overall_score: 53.3` with real per-phase scores (backswing 20.7, contact 10.2, follow_through 12.6, body_rotation 9.8), wrapped in a non-fatal try/except matching `compare_swing.py`'s own pattern (a phase-breakdown failure doesn't kill the whole comparison).

Intentionally kept absent from `VersusResultsScreen.js`, per explicit confirmation this is correct: save-to-history banners, verify/correct-shot-type row, coach notes (all need an `analysisId` a 1v1 comparison doesn't have), and the "other matches" list (doesn't conceptually apply — there's only one comparison target, which *is* the "as if the database was just that one video" framing Jack asked for).

Not live-tested end-to-end in a running app this session (would need Expo + a device/simulator + real test videos) — backend endpoints and every touched file were syntax/byte-compile-checked, and the phase-breakdown addition was verified via a real CLI run, but the full pinch/pan gesture UX itself wasn't exercised on a device.

### 14. Social/gamification roadmap + Phase 1: usernames, rank tiers, player type (2026-08-13)

Jack laid out a big vision: rank tiers ("player card" that upgrades with great-swing count), usernames, a friends system (with set-tracking and sending swings to friends), sending swings to coaches with annotation tools, local-court matchmaking, leaderboards (friends + worldwide incl. pros/celebrities, daily-updating), and a "player type" classifier (pusher, net-rusher, etc.).

**Research before planning found almost none of this has real backend logic today**, with one exception: the coach-linking system (`coach_invite_codes`/`coach_links`/`coach_notes` in `db.js`, wired through `backend/src/routes/coach.js`) is fully built — invite-code-based linking, student history viewing, and *text* coach notes are all real. Coach *drawing* annotation (`AnnotationCanvas.js`, the freehand pen/line/arrow/circle tool on `SyncCompareScreen.js`) was explicitly local-only/ephemeral by its own header comment at the time of this research — not persisted anywhere, so "coach annotates with built-in tools" was only half-true. **Fixed the same day, see item 17.** Everything else on the list — usernames, friends, matchmaking, leaderboards, player type, match/set score tracking — was entirely greenfield: no `username` column, no social graph, no location data, no leaderboard table, no play-style classification anywhere.

**Scoping decisions Jack confirmed, in order:** (1) build a first phase now rather than just document — usernames + rank tiers + player type, since none of those need a new social graph and all reuse data already being stored (`analyses.similarity`, `rally_clips.outcome_tag`/`swing_count`/`duration_sec`); (2) rank tiers are **count-based** (matches his own "1 great swing = beginner, 10 = intermediate" example, not percentage-based) with **tennis-lore-themed names**; (3) player type ships now as an explicitly-labeled **first-pass estimate**, not a real tactical classifier — the app has no court-position/rally-pattern data (see item 3 in the Known Gaps table above), so true pusher/net-rusher detection isn't feasible yet; (4) for the future friends/set-tracking feature, scores will be **manually entered** by the user after playing, not computer-vision-detected.

**What shipped this phase:**
- `users.username` (nullable, unique index, set later via Settings — not required at signup). `PATCH /auth/me` validates `^[a-z0-9_]{3,20}$`, normalizes to lowercase, returns `409` on a real conflict (live-tested against two different real accounts).
- `backend/src/routes/profile.js` (new): `GET /api/profile/rank` — counts `analyses` with `similarity >= 75` (the same "great swing" threshold already duplicated in `theme.js`/`HomeScreen.js`/`HistoryScreen.js`, reused not reinvented) against an 8-tier ladder (`Rookie → Rally Starter → Baseliner → Contender → Circuit Player → Tour Regular → Grand Slammer → Legend of the Game`, thresholds 0/1/5/15/40/100/250/600 — a first-pass geometric spacing with no real usage data behind it yet). `GET /api/profile/player-type` — rule-based estimate: prefers highlight-reel `rally_clips.outcome_tag` data (winner/ace/error rate + avg rally length → Grinder vs. Finisher vs. All-Court, needs ≥5 tagged rallies), falls back to `analyses` shot-type mix (serve-heavy → Big Server, needs ≥10 analyses) when reel data is thin, and returns `{type: null, reason: 'not_enough_data'}` below both thresholds — every response includes `confidence: 'estimated'` so it's never mistaken for a real classifier.
- Frontend: `frontend/api/profile.js` (thin fetch wrappers), `frontend/components/PlayerCard.js` (new — rank name + progress bar to next rank + player-type chip, or a locked "log N more swings" state), wired into `HomeScreen.js` (replacing the old bare "Great swings" stat tile, which was now redundant with the card's own count+progress) and `ProfileScreen.js` (username + a second rank badge next to the existing FREE/PREMIUM subscription badge — kept visually distinct so it doesn't read as a second payment tier). Username editing lives in `SettingsScreen.js`, matching where display-name editing already lives, using the same generic `updateUser()`/`updateProfile()` plumbing (`frontend/api/account.js`) with zero API-layer changes needed.
- **Verified live**: `PATCH /auth/me` username set/normalize/409-conflict all tested against the real running backend and two real accounts; `GET /api/profile/rank` and `/player-type` tested against a real test user's data. Not tested in a running Expo app this session (frontend files syntax-checked only).

**What's next, roughly in order (not started yet):**
1. ~~**Friends system**~~ — **built 2026-08-13, see item 16 below.**
2. ~~**Manual set/match score entry**~~ — **built the same pass as item 1, see item 16 below.**
3. ~~**Send-to-friend**~~ — **built 2026-08-13, see item 17 below.** Explicit per-swing sharing, not full-access-once-friends (a deliberate divergence from the coach model — see item 17's writeup).
4. ~~**Persisting coach freehand annotations**~~ — **built the same pass as item 3, see item 17 below.** Also opened up to friends the swing was shared with, not just coaches.
5. ~~**Leaderboards**~~ — **built 2026-08-13, see item 18 below.** Both friends and worldwide (incl. admin-added pros/celebrities) — the "much bigger lift" framing turned out to not apply once Jack confirmed celebrity scores would be manually curated by him, not scraped, which removed the need for any external data source or daily cron job.
6. ~~**Local-court matchmaking**~~ — **built same day, see item 15 below.** Turned out simpler than originally flagged once scoped down to a court map + opt-in notifications + manual availability posting, rather than live GPS-based "people near me" matching.

### 15. Find Games: court map, availability posting, notifications, messaging (2026-08-13, same-day follow-up)

Built out roadmap item 6 the same day it was written, after Jack scoped it down from "live GPS matchmaking" (the harder, more privacy-sensitive version) to: a map of real courts with crowdsourced cost info, opt-in "notify me" watching per court, manual availability posts ("I'm free to play here at 6pm"), broadcast notifications to watchers, and simple 1:1 messaging to organise. This version never broadcasts a user's live location — only public court locations and availability windows users actively choose to post — sidestepping the harder privacy problem real-time matchmaking would have raised.

**Key technical finding before building anything**: this codebase has real precedent for native modules being blocked in plain Expo Go (RevenueCat's native checkout is parked for exactly that reason — needs an EAS dev client). Checked whether maps would hit the same wall: **`react-native-maps` works fine in plain Expo Go** (confirmed via Expo's own docs, no dev-client build needed) as long as it's pinned to the SDK-54-bundled version (`1.20.1` — `expo install` resolved this automatically, same as `expo-location`). Expo's newer `expo-maps` does *not* work in Expo Go at all — deliberately avoided in favor of `react-native-maps`.

**Backend** — 4 new tables (`courts`, `court_watches`, `availability_posts`, `messages`) in `db.js`; new `backend/src/routes/courts.js` (list courts by lat/lng/radius via a bounding-box prefilter + exact haversine sort, add a court, edit its cost — last-write-wins, wiki-style, watch/unwatch, post/list/cancel availability) and `backend/src/routes/messages.js` (thread list with unread counts, per-pair history, send — normalized `[min(id), max(id)]` pair storage so a thread is one simple query regardless of who sent what). Both reuse `sendPushNotification()`/`push_tokens` as-is (already real, working infra from the highlights feature) — posting availability broadcasts to every other watcher of that court (confirmed model: broadcast, not smart time-overlap matching); sending a message pings the recipient the same way.

**Court data**: no free API reliably has court *cost* data, only location. `backend/scripts/seedCourts.js` (new, plain Node, no Python) queries OpenStreetMap's free Overpass API for `sport=tennis` elements within a bounding box (`node scripts/seedCourts.js --lat=X --lng=Y --radiusKm=15`), upserts on `osm_id` so re-running is safe. Cost info is then crowdsourced — any user can add/edit a court's `cost_info` field once they know it.

**A real bug caught during live verification** (not simulated — two real test accounts, real backend, real DB): the `GET /messages/threads` query's `ORDER BY created_at DESC` had no tiebreaker, so when two messages in the same thread landed in the same SQLite-timestamp second (easy to hit when testing quickly), the thread list showed the *older* message as the "last message" for both participants — confirmed by sending two messages back-to-back and seeing the first one displayed instead of the second. Fixed with a secondary `, id DESC` sort key; re-verified both users' thread lists now show the actual latest message.

**Frontend**: `FindGamesScreen.js` (new "Find Games" tab, 4th position) — `MapView` centered on the user's location (`expo-location`, foreground-only permission), court markers, a bottom-sheet modal per court (cost edit, watch toggle, who's-free list with per-poster "Message" buttons, a lightweight availability-posting form using day-quick-picks + an HH:MM text field rather than pulling in a date-picker library). `MessagesScreen.js` (thread list) + `MessageThreadScreen.js` (one conversation, polls every 3s while focused using the same `mountedRef`-guarded pattern as `HighlightArchiveScreen.js`'s reel-job polling — no websocket layer needed) — reachable from a new "Messages" entry in `ProfileScreen.js`'s menu and directly from any availability post's "Message" button. Two new icons added to `icons.js` (`MapPinIcon`, `MessageIcon`) matching the existing hand-rolled SVG icon set. `app.json` updated with the `expo-location` config plugin + Android location permissions.

**Web platform note**: `react-native-maps` has no web implementation at all. Since this app also runs via `react-native-web` (`expo start --web`), `FindGamesScreen.js` explicitly detects `Platform.OS === 'web'` and shows a "open on your phone" fallback instead of crashing — the map itself is native-only for now.

**Not premium-gated** — a core social feature, not one of the premium-spec items.

**Verified live** (real backend, two real test accounts, cleaned up afterward): add a court → list it by lat/lng → set its cost → second account watches it → first account posts availability → listed correctly with poster identity → messaging round-trip both directions, including the thread-ordering bug found and fixed mid-verification. **Not yet tested in a running Expo app on a device** (would need a real device/simulator with location + the map actually rendering) — every file was syntax-checked, but the map UI itself, the location-permission flow, and the bottom-sheet interactions haven't been visually confirmed.

### 16. Friends system + manual head-to-head match tracking (2026-08-13, same-day follow-up)

Built roadmap items 1 and 2 together, right after Find Games, since match tracking only makes sense once friends exist.

**Friends**: directly copied the coach-linking pattern (`coach_invite_codes`/`coach_links`, `routes/coach.js`) and adapted it from asymmetric (coach/student) to symmetric (friend/friend) — new `friend_codes`/`friend_links` tables in `db.js`, new `backend/src/routes/friends.js`. Same 8-char collision-checked invite code (`generateCode()`, reused verbatim — same alphabet, same `do...while` uniqueness loop), same self-link guard, same `INSERT OR IGNORE` pattern. The one real adaptation: `friend_links` stores the pair as `[min(id), max(id)]` (a local `sortedPair()` helper) since friendship has no inherent coach/student direction — one row covers the relationship regardless of who redeemed whose code, unlike `coach_links`' directional `coach_id`/`student_id` columns.

**Match tracking**: new `friend_matches` table — `sets_won`/`sets_lost` stored relative to whoever logged the match (`logged_by`), not a fixed side. `GET /friends/:userId/matches` normalizes every row to the *viewer's* perspective in JS (flips the numbers when the friend was the logger), and the same normalization aggregates into a `record: {wins, losses}` on each entry in `GET /friends`. **Explicit, honest limitation, not solved this pass**: entry is single-sided with no confirmation step — if both friends separately log the same real match, it shows as two results, not deduplicated. This was a deliberate scope call (consistent with Find Games' availability-posting being single-sided too) rather than building a confirm/dispute flow.

**Frontend**: `FriendsScreen.js` directly mirrors `CoachScreen.js`'s structure (its `Section` wrapper, `codeDisplay`/`input`/`actionBtn` styles, generate-code / paste-code-and-submit / chevron-row list, and the local-state list↔detail-view swap instead of a nested nav route) — "Your friend code," "Add a friend," and a friends list where each row shows a live head-to-head badge (e.g. "3–1") and taps into a detail view with the full match log and a "Log a match" form (date, sets won/lost, optional score detail like "6-4, 3-6, 7-5"). New `FriendsIcon` added to `icons.js`. Reachable from a new "Friends" entry in `ProfileScreen.js`'s menu, next to "Coach mode" — same placement logic (not on Home, matching Coach mode's own precedent).

**Verified live** (real backend, two real test accounts, cleaned up afterward): generate code → self-link correctly rejected → redeem → both sides see each other in `GET /friends` → redeeming the same code again correctly 404s. Logged 3 matches including a deliberate double-logged case (same real match, both sides logged it independently) plus one real additional match — confirmed both accounts' head-to-head records normalize consistently and correctly from their own perspective (2W–1L vs. 1W–2L, summing correctly across 3 total logged rows), and the documented double-logging limitation shows exactly as expected rather than silently corrupting anything. Confirmed match-delete respects ownership (non-owner correctly 404s) and unfriending correctly 403s subsequent match queries between the pair. **Not yet tested in a running Expo app on a device** — frontend syntax-checked only, same caveat as every other UI piece built this session.

### 17. Send-to-friend (explicit sharing) + persisted coach/friend annotations (2026-08-13, same-day follow-up)

Built roadmap items 3 and 4 together, right after friends existed to send swings to.

**Key product decision, made explicitly rather than assumed**: coach linking today is "full access once linked" — no per-swing send step, a linked coach can already see/note any of a student's saved analyses (`isLinked()` in `coach.js`, no separate sharing table). Jack confirmed friend-sharing should work differently: **explicit, per-swing sharing** — a friend only ever sees a swing you actively chose to send them, matching "send them your high-skilled shots" rather than opening your whole history. New `shared_analyses` table (`analysis_id, owner_id, friend_id`, unique per pair) backs this — genuinely different from `coach_links`, not just a rename.

**Sharing** — 3 new routes in `friends.js` (kept there, not a separate file, same as `friend_matches`): `POST /friends/:userId/share` (owner-only — you can't re-share someone else's swing, requires `isFriends()`, pushes a notification via the existing `sendPushNotification()`), `GET /friends/:userId/shared` (both directions, tagged `sent`/`received`), `GET /friends/shared/:analysisId` (returns the full parsed analysis in the exact same shape `coach.js`'s student-history endpoint already returns — `{id, shot_type, similarity, created_at, result, owner_name}` — so the frontend feeds it straight into `ResultsScreen`'s existing `savedResult` prop with zero new rendering logic).

**Annotation persistence** — the real gap: `AnnotationCanvas.js` (the pen/line/arrow/circle telestrator on `SyncCompareScreen.js`) held strokes in plain component-local `useState` with only `clear()`/`undo()` exposed — no way to even read strokes out, let alone save them. Added `getStrokes()`/`loadStrokes()` to its `useImperativeHandle`. New `swing_annotations` table (`analysis_id, author_id, pane_a_strokes, pane_b_strokes`, one upserted row per analysis+author — saving again overwrites your own previous save). New `backend/src/routes/annotations.js`, deliberately decoupled from `coach.js`/`friends.js` (checks both linkage tables directly rather than importing across route files, matching this codebase's existing convention of each route file owning its own access-check helper) — `canAccessAnalysis(userId, analysisId)` is true for the owner, a linked coach, **or** a friend the swing was explicitly shared with (item 3's new table) — one consistent access rule for both viewing and saving annotations, not a coach-only special case.

**Frontend**: `FriendPickerModal.js` (new, small, reusable) — a friend list picker, used by a new "Send to a friend" button on `ResultsScreen.js` (gated on `analysisId` existing, i.e. the swing is saved) and a per-card send action on `HistoryScreen.js`. `FriendsScreen.js`'s `FriendDetail` gained a "Shared swings" section (parallel to match history) — tapping a shared swing fetches it and navigates into the real `ResultsScreen`, same params shape `CoachScreen.js`'s student-history view already uses. `SyncCompareScreen.js` now loads any saved annotation sets for the current `analysisId` on mount (auto-loading the viewer's own set if they have one), exposes a "Save annotation" button in the existing annotate toolbar, and — when more than one person has saved annotations on the same swing (e.g. two coaches) — a small chip row to switch whose set is displayed.

**Verified live** (real backend, three real test accounts — owner, friend, and an unrelated third account — cleaned up afterward): shared a swing, confirmed the recipient can fetch the full analysis via `GET /friends/shared/:id` and the unrelated account correctly 403s. Saved annotations as the owner, then separately as a temporarily-linked coach account — confirmed both upsert independently (`GET` returns both sets) and a **re-save by the same author correctly overwrites rather than duplicating** (row count stayed at 2 after a second save by the owner, content updated). Confirmed the unrelated account is correctly denied both reading and writing annotations. **Not yet tested in a running Expo app on a device** — same caveat as every other frontend piece this session, backend-verified only.

### 18. Leaderboards: friends + worldwide with admin-added pros/celebrities (2026-08-13, same-day follow-up) — closes out the social/gamification roadmap

Last item on the original roadmap. Jack's own scoping decisions materially changed the shape of this from what was originally flagged as "the much bigger lift":
1. **Ranking metric**: highest swing score per shot category (forehand/backhand/serve) — a personal-best leaderboard, not head-to-head match wins (that's what `friend_matches`, item 16, already covers separately) and not the Phase-1 rank-tier system.
2. **No daily job needed, for either leaderboard**: confirmed live computation is fine for friends. For worldwide, the framing changed entirely — Jack wants to **manually add real pros'/celebrities' scores himself** ("I will add in the celebrities and pros too so make marketing videos ranking people everyone knows"), not scrape them from anywhere. Since there's no external data source, there's nothing to batch-sync on a schedule — the same "live is fine" reasoning just applies to worldwide too. This removed the actual blocker that made worldwide look like a big lift; it was never really about scale, it was about needing an external data feed that (by Jack's own choice) doesn't exist.

**Backend**: new `celebrity_scores` table (`name, shot_type, score, note, added_by`) — manually-curated, not scraped. New `backend/src/routes/leaderboard.js`: `GET /leaderboard/friends?shotType=` (you + your `friend_links` partners, each person's `MAX(similarity)` in that category, sorted descending); `GET /leaderboard/worldwide?shotType=` (every real user's personal best in that category, `GROUP BY user_id`, merged with all `celebrity_scores` rows for that category and sorted together); `POST`/`GET`/`DELETE /leaderboard/celebrities` for managing entries. All three celebrity-management routes are gated by a new `isAdmin()` helper — checks the requester's email against an `ADMIN_EMAILS` env var, **defaulting to Jack's own email if unset** so it works immediately without needing a `.env` edit first. No broader admin-role system exists or was needed — this is scoped to exactly the one person who asked to add entries.

**Frontend** (original build): `LeaderboardScreen.js` — Friends/Worldwide toggle, a forehand/backhand/serve pill row (same 3-way pattern as `HomeScreen.js`'s `QUICK_SHOTS`), a ranked list with the viewer's own row highlighted and celebrity rows tagged with a small "PRO" badge (text badge, not an emoji, matching the app's existing FREE/PREMIUM pill-badge style). When the logged-in user's email matches the (client-side convenience copy of the) admin check, an "Add a pro/celebrity score" form appears at the bottom of the Worldwide tab. New `LeaderboardIcon` in `icons.js`. **Update (2026-08-13, navigation restructure session): `LeaderboardScreen.js` no longer exists** — the exact same UI (toggle, pills, ranked list, admin form) was extracted verbatim into `components/LeaderboardSection.js` and is now embedded directly on `HomeScreen.js` instead of living behind a menu tap. See item 19.

**Verified live** (real backend, an admin test account using Jack's real email and a non-admin test account, cleaned up afterward): non-admin correctly 403s on add/list/delete of celebrity entries; admin successfully added real celebrity entries across categories (Federer/Nadal on forehand, Serena on serve); `GET /leaderboard/worldwide` correctly interleaved real user scores and celebrity scores sorted together by score, per category, with `is_me` accurate; `GET /leaderboard/friends` correctly excluded a friend with no analyses in the queried category rather than fabricating a zero score (confirmed this is correct personal-best semantics, not a bug); bad `shotType` values correctly 400.

**This closes the full social/gamification roadmap** first laid out earlier the same day (item 14): rank tiers, player type, usernames, Find Games (court map/availability/messaging), friends + match tracking, send-to-friend + persisted annotations, and now leaderboards — all shipped in one continuous session.

### 19. Navigation restructure + Find Games court data fix (2026-08-13, same-day follow-up)

Jack started the live in-app verification pass for everything above and immediately asked for two changes instead: consolidate the tab bar (it had grown to 6 tabs, one per feature), and fix Find Games — which turned out to only ever show his own location with no court pins.

**Find Games was a data problem, not a code problem.** `backend/scripts/seedCourts.js` (written earlier this session, pulls real tennis courts from OpenStreetMap's Overpass API) had never actually been run, so the `courts` table had 0 rows — the map, marker rendering, and `GET /courts` endpoint were all already correct. Two fixes: (1) actually ran the seed script for the London area (the app's existing fallback region), inserting 4,407 real courts; (2) made `GET /courts` self-healing — extracted the fetch/upsert logic into `backend/src/utils/overpassCourts.js`, shared by both the CLI script and a new lazy-seed path in `routes/courts.js` that fires automatically the first time a query for an area returns zero local rows, so any future area someone opens the map in auto-populates instead of silently staying empty forever. Verified live: queried a fresh, never-seeded area (New York) via `GET /courts` and confirmed it auto-populated 876 real courts on the first request. One non-obvious fix needed: Overpass returns a bare `406` to Node's default `fetch` headers — needs an explicit `Accept: application/json` and `User-Agent`.

**Navigation consolidation**, per Jack's explicit spec ("press on history and there will be a drills section in it, then press on friends and there will be a messages section in it"): bottom tab bar went from 6 tabs (Home/History/Drills/FindGames/Premium/Profile) to 5 (Home/History/Friends/FindGames/Profile). Leaderboard moved from its own screen to an inline section on Home (`components/LeaderboardSection.js`, see item 18's update note). History gained a segmented History/Drills toggle (`components/DrillsSection.js` holds the extracted Drills content). Friends gained a segmented Friends/Messages toggle (`components/MessagesSection.js` holds the extracted Messages content); `ProfileScreen.js`'s "Messages" menu item now deep-links straight to Friends' Messages segment via a `initialSegment` route param, the same pattern `HistoryScreen.js` already used for its `initialFilter` param from Home's "Great swings" tile. Premium moved from a tab to a normal pushed stack screen (all 4 call sites that navigated to it via `MainTabs → Premium` were updated). `DrillsScreen.js`, `LeaderboardScreen.js`, and `MessagesScreen.js` were deleted outright — not kept as dead code — now that their content lives in the components above. Full detail in the "Navigation structure" section above.

**Verified**: backend court-seeding and lazy-seed path tested live against the real DB (see above); every new/edited frontend file syntax-checked with `node --check`, **and** the full Metro bundle was force-built via `curl http://localhost:8081/index.bundle?platform=ios&dev=true` and confirmed `hasError: false` with no module-resolution errors — this exercises every import path across all changed files, including the three deleted screens, in a way `node --check` alone can't (JSX tag mismatches often parse as valid-but-nonsensical plain JS under `node --check` since `<`/`>` are valid operators). **Still not yet clicked through in a live Expo Go session on a device** — that in-app verification pass is next.

### 20. Community-submitted courts: drop a pin, verify by community confirmation (2026-08-13, same-day follow-up)

OSM doesn't have every court — local/private/informal courts are missing from Find Games. Jack wants players to add a missing court themselves by dropping a pin, verified crowd-source style (like a Waze report) rather than an admin-review queue: it goes live once enough *other* players independently confirm it's really there.

**Backend**: two new columns on `courts` (via the same `PRAGMA table_info` + `ALTER TABLE` migration-guard pattern already used for `notifications_enabled`/`boundary_note`/etc.) — `verified` (`INTEGER NOT NULL DEFAULT 1`, so every existing OSM-seeded court stays trusted) and `submitted_by` (`INTEGER REFERENCES users(id)`, null for OSM rows). New `court_confirmations` table (`court_id, user_id`, `UNIQUE` pair) — one row per independent confirmation. `POST /courts` (already existed, previously went live immediately) now inserts with `verified = 0, submitted_by = req.user.id` instead. New `POST /courts/:id/confirm`: 404s if the court doesn't exist, 400s if the requester is the original submitter ("You can't confirm a court you submitted yourself"), otherwise `INSERT OR IGNORE`s a confirmation row (the `UNIQUE` constraint makes double-confirming from the same account silently harmless) and flips `verified` to `1` once distinct confirmations reach `CONFIRMATION_THRESHOLD = 2` (a top-of-file const in `routes/courts.js`, easy to retune). `GET /courts` now returns `verified`, `submitted_by`, `confirmation_count`, and a per-viewer `already_confirmed` flag on every court so the frontend knows exactly what to show without extra round-trips.

**Frontend** (`FindGamesScreen.js`): long-pressing the map drops a draggable green pin (`<Marker draggable onDragEnd=.../>`) and opens a bottom-sheet form showing the exact coordinates plus a name field; submitting calls the existing `addCourt()` API wrapper (it already existed in `api/courts.js` from the original Find Games build — just wasn't wired to any UI yet) and the new court appears on the map immediately as unverified. Unverified courts render with a gold `pinColor` instead of the default, so pending pins are visually distinct at a glance. Tapping into `CourtSheet` for an unverified court shows a "Not yet verified — n/2 confirmations" banner with a "Confirm this court exists" button — hidden if you're the submitter (shows "waiting on other players" instead) or you've already confirmed (shows a thank-you line instead), matching what the backend's `submitted_by`/`already_confirmed` fields tell it. New `confirmCourt()` wrapper added to `api/courts.js` alongside the pre-existing `addCourt()`.

**Verified live** against the real backend with three real distinct test accounts (A, B, C): A submits a court → comes back `verified: 0`; A tries to confirm their own submission → correctly 400s; B confirms → count 1, still unverified; C confirms → count 2, `verified` flips to `1`; B confirms again → no-op, count stays at 2. Confirmed `GET /courts` returns all the new fields correctly per-viewer (the submitter's `already_confirmed` correctly reads `false` since they never confirmed their own court, only B and C did). Test court and its confirmation rows cleaned up afterward. Frontend: `node --check` on all edited files, plus the same Metro-bundle-force-build trick from item 19 (`hasError: false`, no unresolved imports). **Not yet tested in a live Expo Go session on a device** — same standing caveat as everything else built this session.

### 21. App icon + profile mascot, sourced from Jack's Downloads folder (2026-08-13, same-day follow-up)

Jack asked for the app icon and a "mascot for people's profiles" to be picked directly from his `Downloads` folder by recency — second-most-recently-downloaded image for the icon, most-recently-downloaded for the mascot — rather than naming files himself. Both turned out to be a matching pair of ChatGPT-generated pixel-art tennis-ball characters (already square/rounded-corner-composited for the icon one, full-body on white for the other), so no cropping/resizing was needed.

- `frontend/assets/icon.png` and `frontend/assets/favicon.png` replaced with `Downloads/ChatGPT Image Aug 13, 2026, 04_29_20 PM.png` (the 2nd-most-recent download at the time) — no `app.json` changes needed, both paths were already correct. Android's separate adaptive-icon layers (`android-icon-foreground/background/monochrome.png`) were deliberately left untouched — they're expected to be a transparent-background foreground layer + separate background, and this new art already has its own baked-in background, so swapping it in there would double-layer incorrectly.
- New `frontend/assets/mascot.png` from `Downloads/ChatGPT Image Aug 13, 2026, 04_30_49 PM.png` (the most-recent download) — wired in as the replacement for every letter-in-a-circle user avatar in the app, per Jack's choice to apply it everywhere rather than just the Profile screen: `ProfileScreen.js`'s large profile avatar, `HomeScreen.js`'s small top-right avatar, and `components/MessagesSection.js`'s per-thread avatar. Each spot swapped its `<Text>{initial}</Text>` for an `<Image source={require('../assets/mascot.png')} />`, with the existing circular `avatar` style gaining `overflow: 'hidden'` so the square source image clips to the circle. `HomeScreen.js`'s now-unused `playerInitial` variable was removed.

**Verified**: `node --check` on all 3 edited screens/components; force-built the Metro bundle and confirmed no `Unable to resolve`/`Module not found` errors for the new `require('../assets/mascot.png')` calls; separately fetched `http://localhost:8081/assets/assets/mascot.png` from the running Metro server and confirmed it serves the correct 1254×1254 PNG byte-for-byte. **Not yet seen rendered in a live Expo Go session** — same standing caveat.

### 22. Skeleton-overlay offset fix, video-load error visibility, racket swing-path overlay (2026-08-13, same-day follow-up)

Jack actually used the app and reported three things: the skeleton overlay in Sync Compare sits noticeably higher than the real person; his own uploaded video sometimes shows as a permanent black box (pro clips load fine) with no error; and he wants a racket swing-path trace, similar to the skeleton.

**Skeleton offset — root cause found and fixed, high confidence.** `PlatformVideo` renders with `resizeMode: CONTAIN` (native) / `objectFit: contain` (web) inside a box with a forced aspect ratio (`videoHeight = videoWidth * 1.85`, chosen to approximate a portrait phone recording). When a video's real aspect ratio doesn't match that forced ratio, CONTAIN letterboxes it (black bars), and the actual visible content sits in a smaller, centered sub-rect than the full box. `SkeletonOverlay.js` mapped landmark coordinates (normalized against the full original video frame) directly against the full box's pixel dimensions, with zero accounting for letterbox offset — whenever there's vertical letterboxing, every point lands systematically higher than the real content. Fixed: `PlatformVideo.native.js`/`.web.js` gained an `onVideoSize({width, height})` callback (native: `onReadyForDisplay`'s `naturalSize`; web: `loadedmetadata`'s `videoWidth`/`videoHeight`) plus an `onError` callback (neither existed before at all — a video failure had no way to surface as anything but an eternal black box). `SyncCompareScreen.js`'s `VideoPane` now computes the actual CONTAIN-derived content rect from the video's native size and passes *that* (not the raw box) to `SkeletonOverlay`/the new racket overlay — the component itself needed no changes, since it already just multiplies against whatever width/height it's given.

**Video-not-appearing — investigated, not conclusively root-caused.** Ruled out "corrupted upload" as the cause: if the file were actually broken, `cv2.VideoCapture` in pose extraction would have failed and the whole analysis would have errored — but a real score comes back, so the file is provably readable server-side by the time analysis runs. Rather than guess a fix for an unconfirmed cause, added real error visibility instead: the new `onError` callback now shows a per-pane "Video unavailable" message instead of a silent black box, and `backend/src/routes/analyse.js` now verifies the persisted user clip actually exists and has non-zero size before returning its URL (`user_clip_url`/`user_clip_cropped_url` come back `null` instead of a URL that 404s, if the check fails, logged server-side). This doesn't claim to fix the actual bug — it converts the failure from silent to diagnosable, so the next real occurrence produces an actual signal to chase.

**Racket swing-path overlay — new feature, built on existing racket-keypoint infra.** The racket-keypoint model already used live for body-rotation scoring (`track_racket_in_clip.py`) already detects all 5 racket points (`handle`, `throat`, `tip`, `left_edge`, `right_edge`) per frame — only the single `handle` point was being kept, and only for the user's video. New `track_racket_path()` keeps every point per sampled frame; new `build_racket_overlay_trajectory()` in `compare_swing.py` reshapes that into the same `[{t, points}]` convention the existing skeleton overlay already uses (raw 0–1 frame-normalized, `t` = video-relative seconds), so both overlays share one interpolation/sync scheme. Computed for **both panes**, per Jack's choice: user side reuses the same frame window already computed for phase-breakdown scoring (cheap, that pass was already running); pro side is a new live pass against the actual matched pro clip file (`top_entry['clip_path']`, the same file `pro_clip_url` is served from) — genuinely new compute, not "already running" the way the user side is, since nothing tracked racket keypoints on pro clips before. New `frontend/components/RacketPathOverlay.js` draws the *whole* swing's path (not just the current scrub position) as a series of line segments through the `tip` point (falling back to `throat`/`handle` per-frame when tip wasn't detected), fading from faint at the start of the window to bright near the end, plus a bright current-position dot synced to the playhead; gaps in detection break the trail rather than interpolating a fake straight line across them. New independent "Show racket path" toggle next to "Show skeleton" in `SyncCompareScreen.js`, wired through `ResultsScreen.js` and `HistoryScreen.js`'s "Watch & compare" (both places that already thread skeleton-overlay data through to Sync Compare).

**A real bug caught live, not by inspection:** running the full CLI end-to-end after wiring this in threw `TypeError: Object of type float32 is not JSON serializable` — `_detect_racket_keypoints()`'s coordinates come from a numpy array and were always `numpy.float32`, not plain Python floats. This was harmless before (the only consumer, `avg_racket_body_distance()`, does `round()`/`sum()`/division that produces a native float either way), but the new racket-path feature puts these tuples directly into the JSON response for the first time, which is what actually surfaced it. Fixed at the source (`float(...)` cast in `_detect_racket_keypoints()`) so every consumer gets plain floats, not just this new one.

**Verified**: full CLI run of `compare_swing.py` against a real clip end-to-end (~74s total, including the 2 new racket-tracking passes) — confirmed `racket_overlay_trajectory` (user, 30 frames, 20 with a real detected point) and `pro_racket_overlay_trajectory` (pro, 60 frames, 50 with a detected point) both contain genuine, sane (x,y) coordinates, not nulls or garbage, and the JSON serializes cleanly. `node --check` + a forced Metro bundle rebuild on every touched frontend file, confirming the new `RacketPathOverlay` import resolves with no bundler errors. **Can't verify the skeleton actually lines up, or that the racket path looks right, or reproduce the original black-box bug, without a real device pass** — flagging clearly rather than claiming more than what command-line verification can actually confirm.

### 23. Sound effects: primary CTA tap sound (2026-08-13, same-day follow-up)

Jack asked whether the app should have sound effects; scoped down to a first pass — a tap sound on primary CTAs only (not every button, not the other candidate moments like analysis-complete/achievements/notifications yet), sourced from a real royalty-free library rather than generated tones or files Jack would have to provide.

**Sound sourcing**: searched Mixkit's free sound-effects library (royalty-free, no attribution required, commercial use allowed — confirmed via their license page and search results). Mixkit's site is JS-rendered, so `WebFetch` alone couldn't extract real download links — worked around it by `curl`-ing the raw HTML directly (a plain user-agent request returns the actual server-rendered markup, including `data-audio-player-preview-url-value` attributes with real `assets.mixkit.co/.../[id]-preview.mp3` URLs) and pairing each ID with its title/duration text also present in the raw HTML. Picked **"Select click"** (id 1109, ~1s) — short, subtle, not sci-fi/gamey. Saved to `frontend/assets/sounds/tap.mp3`.

**Infrastructure**: new `frontend/utils/sounds.js` wraps `expo-av`'s `Audio` API (already a dependency, already used for video — no new package). `playTapSound()` lazily preloads the sound once (`Audio.Sound.createAsync`, module-level) and calls `replayAsync()` on every subsequent tap rather than reloading. Calls `Audio.setAudioModeAsync({ playsInSilentModeIOS: false })` once, deliberately — UI sound effects should be silenced by the phone's hardware mute switch (like iOS's own keyboard clicks), the opposite of what video playback wants, so this is scoped to this module rather than a global app default. Every failure path is swallowed (`.catch(() => {})`) — a missing/failed tap sound should never break the button it's attached to.

**Local preference, not backend-synced**: this is a device-level UI preference, not data the server or other devices need — stored via the existing `frontend/utils/storage.js` (already wraps `expo-secure-store`/`localStorage` identically, used today for the auth token), key `sound_effects_enabled`, default on. New "Sound effects" toggle in `SettingsScreen.js`, same `Switch`/row pattern as the existing "Push notifications" toggle, but reads/writes local storage directly instead of calling `updateUser()`.

**Wired into a bounded first-pass list of primary CTAs** (pattern: `onPress={() => { playTapSound(); existingHandler(); }}`, no component wrapper, no restructuring — there's no shared `Button` component anywhere in the app, 28 files use `TouchableOpacity` directly): `HomeScreen.js`'s "Start analysis" card, `LoginScreen.js`/`SignupScreen.js` submit buttons, `ContactMarkingScreen.js`'s confirm-contact-frame button, `SettingsScreen.js`'s "Save name"/"Save username". Deliberately not swept across every screen — expanding later is the same one-line pattern repeated, not new infrastructure.

**A real bug caught live, not by inspection**: the first Metro bundle-rebuild check 500'd with `Unable to resolve module ../assets/sounds/tap.mp3` even though the file genuinely existed on disk at the right path. Root cause: the `assets/sounds/` directory was created *while the Expo dev server was already running*, and Metro's file watcher hadn't picked up the new directory — confirmed by checking `metro-config`'s actual defaults (`mp3` is a supported `assetExt` out of the box, ruling out a config gap) and then confirming a full dev-server restart fixed it immediately, clean rebuild, no errors. Same class of "watcher missed a new directory" issue worth remembering if a future new-file-in-new-folder addition mysteriously 404s/fails to resolve in dev.

**Verified**: `node --check` on every touched file; forced Metro bundle rebuild (after the restart above) confirmed `HTTP 200`, no `Unable to resolve` errors; separately fetched the served asset from Metro and confirmed it's byte-identical (35,602 bytes) to the source file, a real playable MPEG Layer III audio file (confirmed via `file`), not a corrupt/truncated download. **Can't verify how the sound actually sounds, or that it fires correctly on a real tap, without a real device pass** — same standing caveat as everything else this session.

### 24. Sound effects expanded to the rest of the app's primary buttons (2026-08-13, same-day follow-up)

Jack asked to extend the tap sound (item 23) beyond the original 5-screen first pass. Clarified via question: scope stays "primary actions only" (same discipline as before — no tab-bar taps, no cancel/back/destructive buttons), just applied to the remaining ~17 files that had a real primary CTA and hadn't been touched yet.

**No new infrastructure** — purely the same one-line pattern (`onPress={() => { playTapSound(); existingHandler(); }}`) repeated across: `HistoryScreen.js` (embedded upload panel's "Analyse swing" submit), `ResultsScreen.js` ("Try another shot"), `SyncCompareScreen.js` ("▶ Play both"), `FindGamesScreen.js` ("Add this court" drop-pin submit), `FriendsScreen.js` (both "Generate friend code" and "Add friend"), `LeaderboardSection.js` (admin "Add to [x] leaderboard"), `FriendPickerModal.js` (selecting a friend row — the modal's whole purpose), `MessageThreadScreen.js` ("Send"), `VersusResultsScreen.js` ("Compare another video"), `HighlightArchiveScreen.js` ("Create highlight reel"), `PremiumCheckout.web.js` ("Subscribe" — the actual purchase button; `PremiumScreen.js` itself has no standalone CTA of its own, its `FeatureCard` buttons are just gated navigation into already-covered screens, so nothing was added there), `HighlightReviewScreen.js` ("Save N reviewed"), `HighlightUploadScreen.js` ("Find my rallies"), `VersusPickScreen.js` ("Continue"), `FenceTutorialContent.js` ("Got it" tutorial dismiss), `CoachScreen.js` (both "Generate invite code" and "Link", mirroring Friends' pattern).

**Deliberately still skipped**, matching the original scoping discipline: `FloatingTabBar.js` (tab taps are frequent navigation, not CTAs — sound there is exactly the noise problem this feature was scoped to avoid), `ProfileScreen.js`/`MessagesSection.js`/`TipsSection.js` (pure list/menu navigation, no discrete primary action), `PremiumCheckout.native.ready.js` (parked/inactive, not part of the live app), and every destructive/secondary/cancel button app-wide.

**Verified**: `node --check` on all 17 touched files; forced Metro bundle rebuild confirmed `HTTP 200`, no `Unable to resolve` errors across the full set. **Can't verify how each one actually sounds/feels without a real device pass** — same standing caveat as items 21–23.

### 25. The remaining sound moments: analysis-complete, achievements, message notifications (2026-08-13, same-day follow-up)

Jack asked for the three moments deliberately deferred back in item 23 (analysis-complete, achievements, notifications). Rather than invent generic triggers, re-read the actual code first to find moments that are genuinely, cheaply detectable from state already flowing through the app — landed on 5 concrete triggers, not the originally-vaguer 3-bucket framing.

**3 new sounds**, sourced the same way as the tap sound (raw HTML `curl` against Mixkit, license confirmed, each URL HEAD-checked `200` before committing): `complete.mp3` ("Crystal chime", id 3108), `achievement.mp3` ("Achievement bell", id 600), `notification.mp3` ("Positive notification", id 951). One retry needed — the first `achievement.mp3` download got a transient TLS handshake failure (`HTTP 000`), succeeded cleanly on retry; not a real bug, included here only because it briefly looked like one.

**`frontend/utils/sounds.js` generalized**: the single-sound preload/play logic that used to be hardcoded to `tap.mp3` is now a `createPlayer(loadAsset)` factory — each of the 4 sounds (`playTapSound`, `playCompleteSound`, `playAchievementSound`, `playNotificationSound`) gets its own cached `Audio.Sound` instance and its own literal `require(...)` call (Metro needs a static string per asset, can't be data-driven by path), but shares the enable-check/mute-switch/never-throw machinery. No existing call site needed to change — `playTapSound`'s external behavior is identical.

**The 5 triggers, each tied to a real, already-existing piece of state**:
1. **Analysis complete** — `ResultsScreen.js`'s `runAnalysis()` success path: `playAchievementSound()` if the top match's `similarity >= 75` (great swing), else `playCompleteSound()`. Scoped to the fresh-analysis code path only — opening an already-saved result via the `savedResult` route param takes a different branch entirely and never replays either sound, so browsing History doesn't re-trigger it.
2. **Rank up** — `HomeScreen.js`'s `getRank()` fetch: new `checkRankUp()` compares the freshly-fetched rank name against a locally-stored last-seen value (`utils/storage.js`, key `last_seen_rank`, same mechanism as the sound-enabled preference). Rank tiers only ever increase (earned by cumulative great-swing count, no demotion path exists), so any change from a *previously-stored* value is a genuine promotion — guarded so the very first-ever check (nothing stored yet) doesn't fire.
3. **Friend/coach code redeemed** — `FriendsScreen.js`'s `submitLink()` and `CoachScreen.js`'s equivalent: `playAchievementSound()` right before the existing `Alert.alert('Added!'/'Linked!', ...)`, marking the successful outcome rather than the button press (which already has the tap sound from item 23).
4. **Court verified by your confirmation** — `FindGamesScreen.js`'s `handleConfirmCourt()`: checks whether the court was unverified *before* the confirm call and comes back `verified: true` after — a real "your action tipped it over the threshold" moment, using data the response already returns, no extra polling added.
5. **New message notification** — `MessageThreadScreen.js`'s `load(silent)`: a `lastSeenIdRef` tracks the newest message id, set (but not compared) on the initial non-silent load, then compared on every subsequent silent poll — fires `playNotificationSound()` only when the newest message is both new and not sent by the viewer themselves, so sending your own message never notifies you and opening a thread with existing unread history doesn't retroactively fire.

**Leaderboard climb explicitly left out** — unlike the other 4, there's no existing snapshot of "your previous position" anywhere to diff against (the leaderboard is computed fresh on every fetch); doing it honestly would mean building new comparison infrastructure, not just wiring a sound onto existing state. Noted as a real gap rather than faked with a shortcut.

**Verified**: `node --check` on all 7 touched files; Metro dev server restarted (same "new files in an already-watched directory" issue as item 23 — now a recognized pattern, not a surprise) and a forced bundle rebuild confirmed `HTTP 200` with no resolution errors; separately fetched all 3 new assets from the running Metro server and confirmed each is byte-identical to its source file. **Can't verify the actual trigger logic under real multi-session conditions (a real rank change over time, live message delivery between two real devices, a real second/third court confirmation) without a real device pass** — same standing caveat as every sound-related item this session.

### 26. `GET /history` payload bloat fix — found live, during Jack's actual in-app testing (2026-08-13, same-day follow-up)

First real bug found by Jack actually using the app end-to-end: History looked like it wasn't loading at all ("I don't think the database is connecting"), then turned out to load — just after nearly a full minute.

**Root cause, confirmed by measuring, not guessing**: `GET /api/history` returned the complete `result_json` blob — including full per-frame pose overlay trajectories (`user_overlay_trajectory`, and each match's `pro_overlay_trajectory`, now also `racket_overlay_trajectory`/`pro_racket_overlay_trajectory` since items 22/25) — for every saved analysis, every time the list loaded. Measured directly against Jack's real account (105 saved analyses): **2.9MB total payload, ~28KB average per row, of which ~25KB (90%) was overlay-trajectory data alone** — data the History *list* view never renders at all; it's only ever used by the skeleton/racket-path overlays in Sync Compare, reachable by opening one specific item. The backend itself answered in 0.14s locally — the actual cost was the phone downloading + JSON-parsing a 3MB blob on a mobile JS thread.

**Fixed**: `backend/src/routes/history.js` — `GET /history` now runs each row through a new `stripHeavyOverlays()` (drops the two trajectory fields at the top level and from every entry in `matches`, keeps everything else — clip URLs, tips, phase scores, contact times, `player_name`, etc., all needed by the card UI's "Watch & compare" visibility check and by `formatProId()`). New `GET /history/:id` returns one analysis' *untouched* full result, scoped to `user_id` the same way the existing `PATCH`/`DELETE` routes already are (verified: a different account's token gets a 404, not someone else's data). Frontend: new `fetchHistoryItem(token, id)` in `api/history.js`; `HistoryScreen.js`'s card tap (`openResult()`) and "Watch & compare" (`navigateToWatchCompare()`, now async) both fetch the full item on demand instead of trusting the now-slimmed `item.result` already in memory. `HomeScreen.js` also calls `fetchHistory()` but only ever reads `similarity`/`shot_type`/`created_at` from the list — confirmed unaffected, no changes needed there.

**Verified live against the real account**: list payload **2.9MB → 493KB** (~6x smaller) at 0.045s server time; confirmed the slimmed response still carries `pro_clip_url`/`user_clip_url`/`phase_markers`/`tips` (everything the card UI needs) while `user_overlay_trajectory`/`pro_overlay_trajectory` are genuinely gone; confirmed `GET /history/:id` returns the full trajectories intact; confirmed the ownership check rejects a different user's token with 404. **Still not a small payload at 493KB for 105 rows** (~4.7KB/row of tips/phase/clip-URL text) — reasonable for now, but if History keeps growing this large per account, the same "does the list view actually need this per row" question is worth revisiting again (e.g. pagination) rather than assuming this fix is the end of the story.

### 27. Sync Compare "Video unavailable" fix — the 24h runtime sweep was deleting still-referenced History clips (2026-08-13, same-day follow-up)

Second real bug found live: Jack reported Sync Compare *always* showing "Video unavailable" now, not just occasionally.

**Root cause, confirmed by direct filesystem/DB inspection**: `server.js`'s `sweepOldRuntimeDirs()` deletes any subdirectory of `data/runtime/user_clips/` older than 24h — a leftover from when uploaded videos were genuinely per-request scratch data (`videoCrop.js`'s own comment: "used to be deleted right after comparison"). Since then, `analyse.js` started persisting every upload there permanently and storing its `/user-clips/<dir>/...` URL in the saved History row's `result_json` (item 22's video-error-visibility work), so History could let users watch old swings indefinitely — but the sweep was never updated to match, and kept deleting the file out from under any History row older than a day. Confirmed directly: the newest saved analysis in Jack's account was 3 days old (Aug 10), `data/runtime/user_clips/` was empty except for a directory dated after the sweep last ran, and curling the stored `user_clip_url` for a real saved analysis returned a 404 while the paired `pro_clip_url` (served from the never-swept `04_clips` database) returned 200 — the pro pane always played, the user's own pane never did, for every row without exception, exactly matching what Jack saw.

**Fixed**: `server.js`'s sweep now checks, only for `user_clips`, whether any row in `analyses.result_json` still references that directory (`LIKE '%/user-clips/<dir>/%'`) before deleting it, regardless of age — a clip stays as long as a History row points at it, consistent with History's own tier-based (not time-based) retention. `comparison_clips` (Versus mode) is untouched and still swept purely on age, since `VersusResultsScreen` only ever reads that URL once, immediately after the compare request, with no DB row keeping it alive later — genuinely ephemeral, unlike `user_clips`.

**Not recoverable**: the already-deleted video files for Jack's existing 105 History rows are gone — only the video is lost, the score/tips/overlay data is intact, but the "Watch & compare" video panes for anything analyzed before this fix will keep 404ing until re-analyzed. Going forward, newly saved analyses will keep their videos playable indefinitely. Verified the fix logic directly against the DB (a stored `user-clips` path from an existing row correctly matches the new reference-check query) — restarted the backend to pick it up; couldn't verify the sweep's actual deletion behavior over a real 24h wait in this session.

### 28. Find Games: seeded every OSM-tagged tennis court in England, capped render radius to 20km (2026-08-13, same-day follow-up)

Jack asked to have all of England's tennis courts available, but only shown within a fixed radius of the device's current location (settled on 20km after considering 10km).

Previously, `courts` only had data for areas someone had already opened Find Games in — `GET /courts` lazily calls Overpass and upserts on first empty query for a given area (`routes/courts.js`), which works but means a genuinely new area always starts empty until visited once. `overpassCourts.js` gained a second path alongside the existing per-area `seedCourtsNear(lat, lng, radiusKm)`: `seedCourtsInArea(areaName)`, a single Overpass named-area query (`area["name"="England"]["boundary"="administrative"]`) instead of tiling many bounding boxes — resolves to OSM's real England boundary polygon (won't miss coastal/border courts the way a bounding-box approximation could), one request instead of dozens, with a longer 180s timeout since a whole-country result set is large. New one-time script `backend/scripts/seedEngland.js` runs it.

**Run live against the real backend**: `node scripts/seedEngland.js` — upserted **32,153 courts** into the database (a few minutes, one Overpass call). Render radius dropped from 25km to 20km in three places kept in sync: `routes/courts.js`'s `DEFAULT_RADIUS_KM`, `frontend/api/courts.js`'s `getCourts()` fallback, and `FindGamesScreen.js`'s actual call site. Verified live: `GET /courts` near London returns 3,275 courts, all with `distance_km <= 20` (max observed exactly 20.0); near Manchester, 919 courts; a rural Scottish coordinate (outside the England-only bulk seed) still returned real courts via the existing lazy self-heal path, confirming that fallback still works for areas outside England. The lazy self-heal in `GET /courts` is left in place unchanged — still useful for Scotland/Wales/NI or if Jack travels abroad, this bulk seed just means England itself no longer depends on it.

### 29. Batch-analyzed Jack's two full match recordings into 85 real History rows (2026-08-14)

Jack's History was empty after item 26/27's cleanup and video-loss. He had the original raw match footage (`IMG_5755.MOV`, 33min/2.18GB; `IMG_5756.MOV`, 12.7min/839MB) sitting in Downloads, and asked to run the full existing rally-detection + shot-classification + comparison pipeline against them to repopulate History — this pipeline already existed (`rally_detector.py` → `analyze_rallies_parallel.py`, built in an earlier session, backed by `highlight_jobs`/`rally_clips` tables) but had never been run against full-length local files this large.

**New `backend/scripts/runLocalHighlightJob.js`**: mirrors `routes/highlights.js`'s `runJob()` (insert `highlight_jobs` row, run `rally_detector.py`, insert `rally_clips` rows) but triggered from a local file path instead of an HTTP upload — `POST /highlights/upload`'s 2GB multer limit couldn't take `IMG_5755.MOV` anyway, and uploading an already-local 2GB+ file over HTTP would've been a pointless slow copy.

**Real blockers hit and resolved, in order**:
1. **Anthropic API credits exhausted** — every Claude teacher-student call (shot-contact verification, shot classification) started failing with a 400 `credit balance too low`. Jack chose to proceed on the local rule-based heuristics only rather than wait on billing. Added `RALLYMAX_SKIP_CONTACT_VERIFIER`/`RALLYMAX_SKIP_CLASSIFIER_VERIFIER` env flags (both default off, unchanged behavior for normal runs) to `detect_rallies.py` and `analyze_rallies_parallel.py`.
2. **A real, independent bug the credit failure exposed**: `detect_rallies.py`'s local-classifier fallback passed pose data shaped by `02_pose_extraction/extract_poses.py` (landmarks as a list) into `classify_shot.py`'s `classify()`, which expects the dict-keyed-by-joint-name shape `compare_swing.py`'s `extract_user_poses()` produces — crashed with `'list' object has no attribute 'values'` on the very first local-fallback call. Fixed with a cheap reshape (`_as_classify_frames()`, confirmed both extractors use identical per-landmark fields/order) — **not** by letting `classify()` re-extract poses itself, which was tried first and caused a 7-hour hang (re-running full-video pose extraction once per swing candidate, ~111 times, before being killed).
3. Re-ran both videos successfully: job 7 (IMG_5756) → 15 rallies, job 8 (IMG_5755) → 32 rallies, 47 total, 111+290 raw swing candidates → 85 verified real non-serve+serve swings combined.
4. `analyze_rallies_parallel.py 7 8` with both skip flags → **85 saved, 0 failed**. Verified live via `GET /api/history`: 85 new rows (54 forehand / 16 backhand / 15 serve), spot-checked `user_clip_url`/`pro_clip_url` both resolve 200.

**Caveat, told to Jack directly**: shot-type accuracy wasn't Claude-verified this run (by his choice) — expect some wrong labels, correctable via the existing flag/confirm/correct-shot-type buttons. Rally/shot-boundary detection also ran on the local heuristic only, so a few of the 85 may be false positives (camera fiddling, not a real shot) rather than misclassified real ones.

### 30. Investigated a "3D pose" upgrade (Jack's idea, inspired by golf apps) — found and fixed a real, unrelated live scoring bug instead; the 3D attempt itself is shelved (2026-08-14)

Jack asked about upgrading pose detection to be more "3D" like golf swing apps (e.g. Sportsbox AI's single-camera 3D lifting). Investigation found MediaPipe's Pose Landmarker already outputs a `z` (rough hip-relative depth) per landmark, every frame, for free — captured at extraction but silently dropped in `build_pro_database.py`'s `normalise_landmarks()` (x/y only), never reaching DTW comparison or body-rotation scoring. Better still, the raw per-frame pose data for the whole pro database is cached on disk (`data/02_pose_extraction/*_poses*.json`), so re-including `z` didn't need re-running MediaPipe (hours) — just a fast reprocessing pass (minutes).

**Attempt 1 (shipped briefly, then reverted)**: carried `z` through `normalise_landmarks()`, added it to DTW's `_frame_dist()` (down-weighted `Z_WEIGHT=0.5`) and to a new blended rotation signal in `phase_breakdown.py` (`Z_ROTATION_BLEND=0.3`). Rebuilt `pro_database.json` live, then validated against 4 real saved swings (re-running `compare_swing.compare()` with the old vs new DB) — scores dropped 45-75% on 3 of 4, purely from the z change. **Reverted immediately**: `pro_database.json` restored from `pro_database_backup_pre_z_depth.json`, both weights set to `0.0` (code stays, inert). Root cause: MediaPipe's raw `z` has a much wider, noisier, outlier-prone distribution than x/y (measured: abs-median ~1.83 with outliers to ±17, vs x's ~0.60) — the "same normalized units as x/y" assumption was wrong.

**Attempt 2 (also shelved, cleanly this time)**: `build_database()` gained an optional `out_path` parameter (defaults to the live path, so this is a no-op for every existing caller) specifically so a retry could rebuild to a **separate test file** and never touch the live database until validated. Tried to properly calibrate the rotation-blend scale (`Z_TO_DEG_SCALE`) using shoulder/hip `z`-separation measured against the *existing* angle-based rotation range across 200 real entries — and found the angle-based metric itself is majority-broken (see item 31), making it useless as a calibration reference. Test file deleted, live database never touched, `Z_ROTATION_BLEND` stays `0.0`. **The z-depth idea is not disproven** — it's blocked on (a) properly rescaling `z` by its own measured distribution instead of reusing x/y's scale, and (b) fixing item 31 first, so there's a trustworthy signal to calibrate against. Real next step if revisited, not attempted this session.

### 31. Fixed a live angle-wraparound bug in body-rotation scoring, found as a side effect of item 30 (2026-08-14)

While calibrating item 30's attempt 2, measured `phase_breakdown.py`'s `rotation_range()` (the "X-factor" shoulder/hip coil metric, feeding the live `score_body_rotation()` 0-25 sub-score) against 200 real pro-database entries: **136/200 (68%) produced a rotation range over 180°** — physically impossible for one swing, and wildly outside the metric's own calibration (`ROTATION_SCALE_DEG=30`).

**Root cause**: `_rotation_angle()` uses `math.atan2()`, which wraps at ±180°. When a player's shoulder line crosses that boundary during a real, often-small, continuous rotation (e.g. 178° → -179°, an actual ~3° turn), `rotation_range()`'s naive `max(values) - min(values)` reads it as a ~357° jump. Pre-existing bug, unrelated to this session's z-depth work, live and affecting real scores the whole time it's existed: `25 * exp(-abs(deviation)/30)` collapses to ~0 whenever this artifact hits, silently zeroing out the rotation score/tip for the majority of real swings.

**Fixed**: new `_unwrap_degrees()` in `phase_breakdown.py` — standard sequence-unwrap technique (walks the chronologically-ordered per-frame values, adds/subtracts 360° whenever consecutive values jump by more than 180°), applied in `rotation_range()` before taking the range. No change to stored data — this is real-time scoring math, not stored trajectories, so `pro_database.json` didn't need touching at all for this fix (lower-risk than item 30's attempts).

**Verified**: unit-tested `_unwrap_degrees()` on synthetic wraparound sequences (confirms a naive-357°-range sequence correctly unwraps to its real ~40° range, and a no-wrap sequence is left unchanged). Re-measured the same 200 real entries: >180° cases dropped from 136 (68%) to 55 (27.5%), median range dropped from 352.6° to 96.6° — matching `ROTATION_SCALE_DEG`'s existing calibration much better. Re-ran `compare()` end-to-end on 3 real saved swings post-fix, confirmed no errors and sensible `body_rotation` scores/tips. **Honest residual finding**: the remaining 27.5% over-180° cases traced to genuinely noisy per-frame pose data (a single bad/occluded frame producing an implausible one-frame jump), not wraparound — a separate, smaller data-quality issue (something like outlier-frame rejection or a percentile-based range instead of pure min/max) that unwrapping correctly doesn't and shouldn't try to fix. Not addressed this session, flagged for later.

### 32. z-depth retry #2 — succeeded, now live (2026-08-14, same-day follow-up)

With item 31's angle-wraparound fix in place, retried item 30's shelved z-blend with real measurements instead of guesses. Two things attempt 1 got wrong, both corrected:

1. **Measured the wrong quantity the first time.** Attempt 1 judged z "too noisy" from pooled raw per-landmark z *values* (abs-median ~1.83, outliers to ±17). What `rotation_range()` actually uses is the per-trajectory **range** of shoulder/hip z-*separation* — a different, much better-behaved quantity: measured directly against 914 real entries, median 2.02, p99 5.9, no ±17-style outliers at all.
2. **`Z_TO_DEG_SCALE` was guessed (90), not measured.** Paired each entry's z-range against its (now-correctly-unwrapped) angle-range, filtered to the 697/914 entries where the angle side itself is trustworthy (<150°, avoiding item 31's residual noisy-frame cases): **measured median ratio is 28.6°/z-unit — 3x lower than the guess** — with a real, moderate positive correlation (0.35) confirming z carries genuine signal, just noisier than the angle metric.

Updated `phase_breakdown.py`: `Z_TO_DEG_SCALE = 90.0 → 28.6` (measured), `Z_ROTATION_BLEND = 0.0 → 0.2` (re-enabled, kept a clear minority weight given the moderate-not-strong correlation). Left `trajectory_compare.py`'s DTW-level `Z_WEIGHT` at `0.0` — deliberately not retried this round; extremity landmarks (wrists) have 2-4x the z variance of shoulders/hips, and that's the part of attempt 1 with the least evidence behind a safe fix.

Also added a small, permanent, low-risk improvement while doing this safely: `build_pro_database.py`'s `build_database()` now takes an optional `out_path` parameter (defaults to the live path — a no-op for every existing caller) so a database rebuild can be validated against a throwaway file before ever touching the live one. Used it for both this retry and the measurement work that grounded it.

**Verified before promoting to live**: same before/after methodology as the failed attempt — 4 real saved swings (forehand/backhand/serve mix) run through `compare()` against both the old and new database. This time, no wild swings: similarity moved +1.6 to +16 (never down), `body_rotation` sub-score moved -3.5 to +12.2 (bounded, both directions, on a 25-point scale) — consistent with a real, moderate signal contributing, not a metric-dominating regression. Backed up the pre-blend database (`pro_database_backup_pre_z_rotation_blend.json`, alongside the still-present `pro_database_backup_pre_z_depth.json` from attempt 1 — two rollback points) and promoted the validated file to live `pro_database.json` (914 entries, confirmed `z` present). Throwaway test files deleted after use.

**Live now, no backend restart needed** (Python is spawned fresh per request). Same honest caveat as always: whether the resulting rotation scores/tips *feel* more accurate to a real player is Jack's call from looking at real results, not something confirmable from the command line.

### 33. Legal review prep + fixed a real, live-broken account-deletion bug + basic message block/report (2026-08-15)

Jack has a lawyer visiting to review Terms/Privacy/policies, with only 30 minutes available. Produced 4 documents at the repo root (not tracked in this file's numbering since they're legal, not engineering, artifacts): `LEGAL_REVIEW_PREP.md` (factual data/third-party inventory, grounded directly in the code, not legal advice), and first-pass drafts — `TERMS_OF_SERVICE_DRAFT.md`, `PRIVACY_POLICY_DRAFT.md`, `ACCEPTABLE_USE_POLICY_DRAFT.md` — each clearly marked unreviewed, with every business-fact-only-Jack-knows or real-legal-judgment-call flagged in `[BRACKETS]` rather than guessed at. Explicitly did not draft anything as if it were legally sound; the point was to save the lawyer's limited time by giving her something to correct instead of a blank page.

**Found and fixed a real, live bug while researching for the prep doc**: `DELETE /auth/me` (account deletion) already existed but only handled a handful of tables — any user who had ever messaged someone, made a friend, watched/confirmed a court, or received a shared analysis would hit a foreign-key constraint error mid-transaction and simply be unable to delete their account, directly undermining any Privacy Policy promise of a working "right to erasure." Audited every table in `db.js` referencing `users(id)`/`analyses(id)` and rewrote the transaction with a clear split: content the user solely owns (their videos/analyses, push tokens, court watches, friend codes, etc.) is fully deleted; content shared with another user (messages, a shared analysis they received, an annotation drawn on someone else's swing, a coaching note they wrote, a friend match record) keeps its row — so the other person's thread/history isn't destroyed — but the deleted user's `users` row is anonymized in place (email → `deleted_<id>@rallymax.invalid`, name → "Deleted user", password hash replaced with a real bcrypt hash of random bytes so login fails cleanly) rather than deleted, since those relational rows still reference it via a `NOT NULL` foreign key.

**Verified thoroughly, not just syntax-checked**: created two real throwaway test accounts with a realistic cross-linked web of data (message thread, friend link, an analysis of their own shared with the other + annotated by the other, the reverse direction too, a court submission + watch + confirmation + cost update, a coach link + coach note, a friend match record), called the real endpoint, and checked every single table's before/after state directly — confirmed solely-owned content was gone, shared content survived and correctly resolved to "Deleted user," login with the old credentials now fails, and no FK errors anywhere. All test data cleaned up afterward.

**Also added, since it was flagged as a gap in the Acceptable Use Policy draft**: basic message blocking and reporting. New `user_blocks` and `message_reports` tables. `POST/DELETE /api/users/:id/block`, `GET /api/users/blocked`, `POST /api/messages/report/:messageId`. Blocking is checked in both directions at send-time (either party blocking stops new messages either way) but a user's own thread list only hides people *they* blocked (someone who blocked you doesn't vanish from your own history). `MessageThreadScreen.js` gained a "Block" header link and long-press-to-report on any message bubble. Verified live with two more real throwaway test accounts: block correctly stops sending in both directions, hides the thread for the blocker only, unblock restores it, report logs correctly — all cleaned up after. Both `TERMS_OF_SERVICE_DRAFT.md`/`PRIVACY_POLICY_DRAFT.md`/`ACCEPTABLE_USE_POLICY_DRAFT.md` and `LEGAL_REVIEW_PREP.md` updated to reflect both fixes instead of describing them as gaps.

### 34. RevenueCat payments went live + backend hosted on a real server (2026-08-19)

Both done directly by Jack, not step-by-step from this side, but confirmed working: a monthly RevenueCat/Stripe plan is live (annual/other tiers not set up — one price point only). The backend is hosted on a Hetzner CX33 VPS (4 vCPU/8GB, `rallymax-vps`, `167.233.107.31`) at `https://rallymax.167-233-107-31.sslip.io` (via `sslip.io`'s wildcard-DNS-to-IP trick, no real domain purchased), reverse-proxied through Caddy (`Caddyfile` at repo root, auto-HTTPS) into the Node container per `docker-compose.yml`/`Dockerfile`. `data/` is deliberately not baked into the image — see `DEPLOY.md` and item #41 below for the deploy mechanics, which had real gaps found and fixed this session.

### 35. Shot-classifier ML model trained + two new Dev Page review tools (2026-08-19)

Trained a logistic-regression shot-type classifier on pose-derived features from 116 real-shot-labeled amateur clips: **63.8% cross-validation accuracy vs. the rule-based classifier's 50%** (backhand recall 1/10 → 6/10, though backhand precision is still weak at 0.30). Wired in as a separate candidate student (`classify_shot.classify_ml()`) behind its own trust gate, same teacher-student shape as every other loop in this app — Claude stays the teacher until it proves out. Also fixed a real, previously-silent bug: `list_swing_candidates.py` was passing pose data to `classify()` in the wrong shape, so `student_shot_type` had been `None` on every Swing Review candidate ever served.

Two new free, manual-review Dev Page tools, mirroring Swing Review's pattern: **Tip Review** (`DevTipReviewScreen.js` — your swing next to the matched pro, which tip got surfaced and why, agree/disagree, extends `tip_training_log.py`'s loop) and the data-quality-focused **Pro Clip Review** (`DevProClipReviewScreen.js` — watch each pro-database clip, tag ok/mismatched/slow_motion/wrong_boundary, logs to `data/06_pro_database/clip_review_log.jsonl` via `scripts/06_database_build/clip_review_log.py`, for a later filter-and-rebuild pass once enough are reviewed).

### 36. Camera-angle sideline fallback, skeleton-overlay real fix, tip severity shown to users (2026-08-19/20)

**Camera-angle fallback**: `infer_angle.py` previously returned nothing when net detection failed entirely (e.g. filming from directly behind the baseline, where the record-time UI's "front" position picker already knows the net will be right at/behind the camera). New `detect_court_sidelines()` + `angle_from_sideline_symmetry()` Hough-detect the two court sidelines and estimate angle from their convergence asymmetry, confidence capped below `check_camera_setup.py`'s threshold so it always reads "uncertain," never a false "ok." Verified on synthetic test images; the existing net-based path is unchanged on real pro clips. **Not yet validated against real "recorded from the net" footage** — no known-good reference clips existed as of this writing.

**Skeleton-overlay fix, round 2**: the first attempted fix (a Catmull-Rom interpolation curve, presumably from an earlier session) didn't actually fix the real bug, per direct user feedback that it still looked laggy. Real root cause, found by pulling actual pro-database trajectory data: `right_wrist` goes `null` in the immediately-adjacent sample far more often than expected (motion blur near contact), and the old code drew nothing whenever either bracketing sample was null. Real fix: `SkeletonOverlay.js` now searches outward past null gaps for the nearest valid sample per joint before interpolating.

**Tip severity**: was computed (`SEVERITY_BANDS` in `tip_selector.py`) but never shown to users. `compare_swing.py` now carries `severity` through on each tip; `TipsSection.js` renders a mild/moderate/severe pill, shared by both `ResultsScreen.js` and `VersusResultsScreen.js`.

### 37. Ball detector project: audit + fine-tuning data pipeline (Phase 1/2 of a larger effort) (2026-08-20)

The ball detector has always been unfine-tuned generic COCO YOLO — audited this session and confirmed it's genuinely weak exactly where it matters: **50% detection rate / 0.41 avg confidence on 60 real user swings at the contact frame**, vs. the pro database's own 69%/0.664 (`scripts/07_ball_racket_tracking/audit_ball_confidence_at_contact.py`).

Scoped a full fine-tuning project (same shape as the racket/net keypoint models in `07_ball_racket_tracking/`/`10_net_detection/`) and built Phase 1 (data sourcing — 360 candidate frames: 180 near-contact + 120 mid-flight from real saved analyses, 60 negatives reused from real Claude-verified "not a real shot" timestamps) and Phase 2 (labeling). **Phase 2 had a real methodology failure worth knowing about**: asking Claude to freeform-locate the ball's pixel bbox across the full scene failed 3 times running — it kept confidently drawing a box on a bright gap in background tree foliage instead of the real ball (visible in the player's hand), verified by drawing the predicted boxes back onto the source images. Replaced with a classical-detector-then-confirm pipeline instead: `find_ball_candidates.py` proposes candidates via HSV color-threshold + contour/circularity filtering (no ML), then `ball_presence_verifier.py` asks Claude a much easier binary "is this a ball" question on a tight crop around the top candidate — validated 9/9 correct on the exact frames that broke the freeform approach.

Full batch run (`label_ball_frames.py`) result: **124 confirmed, 230 flagged `needs_manual_review` (no confident classical candidate, or Claude rejected every one), 6 transient errors**, total cost **$0.38**. New **Ball Label** Dev Page tool (`DevBallLabelScreen.js`) — the app's first draw-a-box-yourself interaction (`PanResponder`-based `DrawableImage`) — serves exactly those 230 frames for Jack's own manual labeling. Training the actual detector model comes after enough of those are done.

### 38. Premium folded into Home + Lessons, responsive bottom tab bar (2026-08-20)

Direct feedback from a friend testing via tunnel: the bottom tab bar read as compressed on a small phone, and Premium shouldn't be a standalone page — its features should live on Home with a lock icon, tapping straight through to payment. Removed the `Premium` tab (6 tabs → 5: Home/History/Friends/FindGames/Profile); `Premium` remains a real navigable screen (trimmed down to just the `PremiumCheckout` widget), reached via new locked feature cards on Home (`PremiumFeaturesSection.js`) and the existing Lessons lock badge. New shared `frontend/utils/premiumGate.js`'s `useGatedNavigate()` hook: non-premium web users now go **straight to checkout on tap, no confirm-alert step first** (a deliberate behavior change, confirmed with Jack — "press on them and premium payment appears," literally). `FloatingTabBar.js` also gained a real responsive pass below a ~375px breakpoint (smaller margins/icons/label font via the existing `useWindowWidth()` hook), not just relying on the one-fewer-tab fix alone.

### 39. App-wide fix: `Alert.alert()` is a silent no-op on web (2026-08-20)

Found while investigating a real user report ("the forgot password button doesn't work"): `react-native-web`'s `Alert.alert()` is a literal empty stub (`static alert() {}`), so **every** `Alert.alert()` call in the app — login-required prompts, delete confirmations, error messages, 20 files total — silently did nothing on the web build, which is how most of this app has actually been tested/used this session. Built a drop-in replacement, `frontend/utils/alert.js`, matching the real `Alert.alert(title, message, buttons)` signature: forwards to the real `Alert` on native, falls back to `window.confirm`/`window.alert` on web. Swapped all 20 call sites (`FindGamesScreen.native.js` correctly excluded — it has a `.web.js` sibling and never runs on web).

### 40. Self-serve password reset via email (2026-08-20)

Replaced the old "email support@rallymax.app" dead-end with a real flow. New `password_resets` table (only the sha256 hash of the reset token is ever stored, 1-hour expiry); `POST /auth/forgot-password` (always 204, never leaks whether an email exists — same reasoning as `/auth/login`'s timing-safe dummy-hash comparison) and `POST /auth/reset-password`. Email delivery goes through **Resend** (`backend/src/utils/email.js`, same bare-`fetch` pattern `billing.js` already uses for RevenueCat) — chosen over SendGrid/AWS SES for setup simplicity; **not actually configured yet, needs Jack's own `RESEND_API_KEY`**, and a real open question whether `rallymax.app` is an owned/verifiable domain (needed for Resend's shared sandbox sender to work for anyone other than the account owner). The reset link lands on a standalone page the **backend itself serves** (`backend/public/reset-password.html`, plain HTML/JS, no framework) rather than trying to deep-link into the Expo app, since only the backend is permanently hosted. Verified end-to-end against the dev DB with a manually-seeded token: request → reset → login with the new password → reused-token correctly rejected.

### 41. Hetzner redeploy fixes: stale deployment, SSH access, no `.git` on the server (2026-08-21)

Discovered the Dev Page's Ball Label/Pro Clip Review/Tip Review tools were all 404ing on the **hosted** server — not a code bug, the server was running code that predated all of items #35-40 above and had never been redeployed. Digging in surfaced two deeper, previously-unknown problems:
- **`/opt/tennis_app` on the server was never a git repo** — it was set up via a one-time file copy, not `git clone`, so `git pull` could never have worked there. Fixed in place (`git init` + `git remote add origin` + `git fetch` + `git reset origin/master` + `git checkout -- .` — none of which touch already-untracked paths like `data/`/`.env`, so nothing was at risk). One harmless untracked leftover found: `backend/src/routes/db.js` (not a real part of the app, nothing requires it, safe to delete whenever).
- **SSH root login via password was being silently denied** even after resetting the root password from Hetzner's dashboard — Ubuntu's cloud image default is `PermitRootLogin prohibit-password` (keys only). Fixed via Hetzner's browser Console, editing `/etc/ssh/sshd_config` directly. **There's already a working keypair for this exact purpose** on the dev machine: `~/.ssh/rallymax_key`/`rallymax_key.pub`, already authorized on the server — use `ssh -i ~/.ssh/rallymax_key root@167.233.107.31` (or `scp`) for any future server work instead of fighting password auth again.
- Also missing on the server and copied over via `tar`+`scp` (no `rsync` in this dev environment): `data/10b_ball_detection/` (151MB, item #37's ball-label data) and the net-detection model weight `data/10_net_detection/yolo_pose_run_v4/weights/best.pt` (5.4MB — its absence was also crash-looping the `calibration_server` subprocess on every boot, now fixed).

**Real, standing gap this surfaced**: there is no CI/CD. Every push to GitHub needs a manual `ssh` in, `git pull`, `docker compose up --build app` on the server (plus a manual data copy if `data/` changed) to actually go live — confirmed this is not automatic. See `TODO_MANUAL.md` for the exact commands.

### 42. Database verification framework, two audit rounds, a security review, and the first real native-device testing this app has had (2026-08-22)

Several distinct threads, landing together:

- **Database verification** (new): `backend/src/domain/invariants.js` is now the single source of truth for what every stored value is *supposed to be* (a similarity is 0–100, a latitude is ±90, `outcome_tag` is exactly the four values `HighlightReviewScreen.js`'s buttons produce, etc.) — derived from reading the actual producing code, not guessed. Enforced at every write route via `backend/src/validation/validateBody.js`, and separately re-verified against data *at rest* via `backend/src/domain/integrityChecks.js` (48 checks) and a new CLI, `npm run verify:db` (`backend/scripts/verifyIntegrity.js`). Found and fixed one real live bug this surfaced: `profile.js`'s Player Type feature filtered rally clips on `outcome_tag IN ('winner','ace','error')` — tags the app has never once written — so it silently never used real rally data for any user, ever. ~500 new tests across the backend suite (currently 418 passing) closing this out plus follow-up coverage gaps (see below).
- **Two rounds of bug/optimization audits** (background-agent-driven, every finding verified against actual code before acting): fixed a real N+1 query in `GET /friends` (one `friend_matches` query per friend → one batched query), deduplicated `generateCode()` between `coach.js`/`friends.js` into `utils/inviteCodes.js`, added a missing size cap on `swing_annotations` stroke arrays, and fixed real frontend bugs — `FriendsScreen.js`'s Messages-tab jump silently stopped working on a second tap (a `useEffect` keyed on a param value that never changed between calls; switched to `useFocusEffect`), `HighlightReviewScreen.js` was eagerly mounting a video player for every pending rally at once (same bug already fixed once on the dev-only boundary-review screen, missed on the real user-facing path), and `CoachScreen.js`'s student-history list was an unbounded `ScrollView.map()` over the same `analyses` table that caused History's real ~2.9MB stall earlier this session.
- **A full `/security-review`**: clean. No findings cleared the confidence bar — authorization ordering preserved everywhere, SQL stays parameterized, new predicates fail closed.
- **First real native-device testing, via `expo start --tunnel` to a physical phone** — every prior verification this session (and the frontend work before it) was web-only (`npm run web` / `expo export --platform web`), which turns out to have been masking real bugs:
  - `HomeScreen.js`'s `ScrollView` had no `style={{flex:1}}` (only `contentContainerStyle`) — collapses to content height instead of filling the screen on native Yoga layout; invisible on `react-native-web`'s block layout, which doesn't need it.
  - `FloatingTabBar.js`'s labels overflowed their flex slots and bled into neighboring tabs on a real 5-tab phone width — `width:'100%'` and `alignSelf:'stretch'` on the `Text` BOTH failed to fix it (confirmed each fix's code actually reached the device via the live Metro bundle; neither took effect at runtime). Root cause, found the hard way with temporary colored-border diagnostics: **`PressableScale`** (`frontend/components/PressableScale.js`) passed a *style function* — `style={({pressed}) => [...]}` — to `Animated.createAnimatedComponent(Pressable)`, which doesn't reliably resolve backgroundColor/borderRadius+overflow clipping or percentage/cross-axis child sizing on a real device. This one root cause explained three separate-looking symptoms at once (the tab label overflow, a square avatar that should've been circular, and a missing green background on the Home CTA card). Fixed by rewriting `PressableScale` to track `pressed` via local state instead of Pressable's callback-style API, so `style` goes back to being a plain array — the pattern `Animated.createAnimatedComponent` is actually built for. The tab bar's icon/label also needed explicit computed-pixel widths (`itemWidth`, already computed in that file) rather than percentage/stretch, for the same underlying reason.
  - **A live, production-breaking SQL bug in Find Games**, found by testing the actual endpoint with a real auth token rather than guessing: `courts.js`'s court-search query joins `courts` with `clubs` (both tables have their own `latitude`/`longitude` columns) and filtered on an unqualified `WHERE latitude BETWEEN...` — `SqliteError: ambiguous column name: latitude`, a genuine 500 that the frontend's generic error handler was showing as a misleading "check your connection." Pre-existing (traced via `git log -p` to an earlier session, not this one) but never caught until real-device testing actually exercised it. Fixed and **deployed directly** (an isolated one-line patch applied straight to the currently-deployed file on the host, not the rest of this session's uncommitted work, which isn't ready to ship) — confirmed live afterward: 3275 real courts returned, 200 OK.
  - **"Video unavailable" turned out to be almost entirely a non-issue** — an initial claim that video *data* was missing from the host was wrong (corrected after the user pushed back) — pro clips are all present and serve fine (confirmed 200). The real, narrower finding: 85 of 86 saved analyses all date to 2026-08-14 (item #29's batch-analysis run, done locally, never through the live server), so their `user_clip_url`s point at files that were never copied to the host. A brand-new upload made through the live app works fine. Documented as a scoped, low-priority gap in `TODO_MANUAL.md`, not fixed (no explicit decision to spend effort recovering old local test data).
  - Closed a consistency gap the review pass surfaced: `dev.js`, `drills.js`, `annotations.js`, and `auth.js` had all gotten input validation added earlier this session with **zero** test coverage for it, unlike every other route touched — added 4 new focused test files. Writing those tests caught one more real bug: `annotationStrokesJson`'s cap was set to 200KB per field, but two such fields share `express.json()`'s single 100KB body limit, making the cap structurally unreachable (the body parser's 413 always fires first) — lowered to 40KB.
- **Added the Playwright MCP server** (`claude mcp add playwright -- npx -y @playwright/mcp@latest`) for future screenshot-based web-build verification — connected, but note it only verifies `react-native-web` rendering, not native iOS/Android; the bugs above are exactly the kind that requires real-device testing regardless.

**Real, standing takeaway**: every frontend verification claim made in earlier sessions (including in this same session, before today) that was based on `npm run web` / `expo export --platform web` should be treated as unverified for native-only layout behavior until actually checked on a real device. This is not a one-time fix — it's a testing-methodology gap.

### 43. Reviewed/merged 3 more scheduled-routine PR batches, built a shared ball tracker, fixed pose-overlay jitter, and found a real gap in the ball-label data (2026-08-24/25)

**PR batches** (2026-08-24 and 2026-08-25, 8 branches total across bug-sweep/logic-review/security-review/future-ideas) — same rigor as the 2026-08-23 batch: every diff hand-traced against the pre-fix code (not just commit messages trusted), merged into an isolated worktree first, full backend suite + `npm run verify:db` run before touching real `master`. One real thing my own review caught that the PR author's sandbox couldn't: the 2026-08-24 bug-sweep's `compare_swing.py` minimum-trajectory-length fix was untestable in their environment (no Python venv); I imported the patched file under this machine's real venv and confirmed the guard fires exactly as claimed. One flaky test found and fixed along the way (a real-Python-subprocess test missing an extended Jest timeout). Final state: 26/26 backend suites, 474/474 tests, 51/51 DB invariants, all pushed to `master`, all merged branches deleted from GitHub. See the "Scheduled-routine PR round-up" sections below for the routines' own self-reported summaries.

**Pose-overlay jitter, fixed**: `SkeletonOverlay.js` already had solid gap-bridging (Catmull-Rom spline, per-joint nearest-valid-sample search) but still looked jittery — root cause was upstream, not in this file: `compare_swing.py` samples a pose every 3rd frame (~10/sec) and keeps every landmark regardless of MediaPipe's own per-sample noise, so the spline was curving *through* real noise, worst right at contact. Added a One Euro Filter (`makeOneEuroFilter`/`smoothTrajectory` in `SkeletonOverlay.js`) that smooths each joint's raw x/y once per clip (memoized on the trajectory reference) before interpolation — frontend-only, doesn't touch the pipeline or pro database. Deferred: increasing pose sample density / confidence-filtering in `compare_swing.py` itself, only worth it if this alone isn't enough (no automated frontend test infra exists in this repo — verification is manual playback).

**A real gap found in the manual ball-label data**: Jack's own labeling practice (Dev Page → Ball Label, 354 labels, all against the **hosted server** — local dev's own copy of the log is empty) was, for a frame where the real in-play ball wasn't visible, to sometimes box a *static* decoy ball instead rather than leave the frame unlabeled — logged identically to a real label (`ball_visible: true` + a box), no way to tell the two apart. Fixed going forward: `DevBallLabelScreen.js` gained an explicit "Not the ball in play" toggle, logged as `is_live_ball` by `log_manual_ball_label.py`. For the *existing* 354 labels: new `scripts/07_ball_racket_tracking/audit_ball_label_motion.py` applies Jack's own disambiguating rule ("if it isn't moving, it's not the ball being played") as a real check — groups labels by source clip, flags any clip whose *entire* labeled sequence shows near-zero motion throughout. Result: **5 clips / 16 labels flagged** (`analysis534`, `analysis501`, `analysis532`, `analysis519`, `analysis522`) — still needs Jack's own keep/exclude call per clip before Phase 3 fine-tuning starts (see `TODO_MANUAL.md`).

**Ball detector reliability re-measured, unchanged**: reran `audit_ball_confidence_at_contact.py` against real (now more numerous) saved analyses — **53.1% detection / 0.40 avg confidence at contact** (81 real clips checked), essentially identical to the 2026-08-20 baseline (50%/0.41 on 60 clips). Confirms nothing has organically improved; Phase 3 fine-tuning is still the real fix, still blocked on Jack finishing the 5 flagged-clip review above.

**New shared ball tracker**: `scripts/07_ball_racket_tracking/ball_tracker.py` — a constant-velocity Kalman filter (state `[x, y, vx, vy]`) replacing plain linear gap-interpolation. Predicts through a gap on faith for up to `max_gap_frames` consecutive misses (same cap `_interpolated_ball_track` already used), and rejects a measurement that doesn't fit the ball's established motion instead of blindly trusting every detection — the continuous version of the same "not moving = not the ball" rule used for the label audit above. `_interpolated_ball_track()` now delegates to it with the exact same signature/return shape, so `ball_departure_confirmed` (its only current caller) needed zero changes. 6 new synthetic tests (`test_ball_tracker_pytest.py`) — 2 initially failed and caught a real design question (streaming gap-bridging vs. the old all-or-nothing gate), fixed by correcting both the implementation's docstring and the tests to match the real, intended behavior rather than papering over the mismatch. Full existing Python suite stayed green (61/61), smoke-tested clean against 3 real saved clips. Deliberately NOT gravity/parabola-aware yet — a physics-informed post-contact flight model is scoped as a real future refinement, not built this session.

**Ball-speed feature: scoped, not built.** Recommended approach (discussed at length with Jack): use the already-trained, already-integrated net-keypoint model (`scripts/05_angle_detection/infer_angle.py`'s `run_net_keypoint_model()`) for a *local* pixel-to-meter scale at the net's depth in frame — confirmed by direct code search that **no pixel-to-real-world scale/homography exists anywhere in this codebase today**. Explicit limitation surfaced and agreed: a net-only scale is least accurate exactly where contact usually happens (far from the net), so v1's honest metric is ball speed *at the net crossing*, not off the racket at contact — a full ground-plane homography (new court-line detection, not built) would fix that later. Sequencing: hold this behind Phase 3 fine-tuning landing first. Nothing implemented yet — this is a scoped plan only.

**Hosted server was stale, redeployed**: discovered while diagnosing "most Dev Page tools don't load" — the server was running `cf76490` (the 2026-08-23 merge), **2 days and ~25 commits behind** `master`. Not a code bug in the tools themselves; the Dev Page's ML Reliability and Drills & Lessons editor happened to still work because their route code hadn't changed since that stale commit, everything else had. `git pull` on the server succeeded via SSH as usual, but the actual `docker compose up --build -d app` rebuild step got blocked by this environment's own permission classifier even after Jack approved it verbally — **worth knowing for next time**: remote `docker compose` commands over SSH may need an explicit Bash permission rule added, a one-time confirmation isn't enough. Jack ran the rebuild himself this time; server confirmed back on `f73af3d` (now further ahead, see below) afterward.

**Local dev housekeeping**: reset the local-only password for `jack.p14370@gmail.com` directly in `backend/data/app.db` (bcryptjs, 10 rounds, matching `auth.js`'s own convention) — legitimate since `RESEND_API_KEY` isn't configured locally so the real "Forgot password?" flow can't send anything there. Confirmed port 8081 vs 8090 confusion was unrelated to RallyMax (a different local project, "Pitchwise", was occupying 8081) — nothing was actually broken.

---

### 44. CI/CD for the hosted backend (2026-08-25)

Closes out the long-standing "no CI/CD" gap (items #41/#43 above, and the backend-architecture-backlog item 3 in `TODO_MANUAL.md`). New `.github/workflows/deploy.yml`: on every push to `master` that touches `backend/**`, `scripts/**`, `Dockerfile`, `docker-compose.yml`, or `Caddyfile` (deliberately excluding docs, so the scheduled docs-round-up routine's direct pushes to master don't trigger a pointless rebuild), it SSHes into the server and runs the same `git pull && docker compose up --build -d app` that was previously always done by hand, then polls `/health` and fails loudly if the app doesn't come back up. Also triggerable manually via `workflow_dispatch`.

Deliberately uses a **new, dedicated, forced-command-restricted** SSH key rather than the personal `rallymax_key` — a CI secret is a bigger exposure surface than a key that only ever lives on Jack's own machine, so it's scoped server-side (`command="/opt/tennis_app/deploy.sh"` in `authorized_keys`) to do nothing but run the deploy script, even if the GitHub secret ever leaked. Full setup — keygen, the `authorized_keys` line, and the 3 GitHub repo secrets (`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, plus `DEPLOY_HEALTH_URL` for the health-check step) — needed Jack's own hands (prod SSH access and GitHub secrets aren't something this session touches); see `DEPLOY.md`'s new "Continuous deployment" section for what's automatic now vs. still manual (`data/` transfers, `.env` changes).

Also resolved this session, both confirmed directly by Jack: the 5 ball-label clips flagged by `audit_ball_label_motion.py` in item #43 (`analysis534`, `analysis501`, `analysis532`, `analysis519`, `analysis522`) were all confirmed decoys and excluded from Phase 3 ball-detector fine-tuning data; and Rally Boundary Review's lazy-video-loading behavior (from the 2026-08-18 session) was click-tested live and confirmed working. See `TODO_MANUAL.md` for both, now struck through.

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
├── Dockerfile                             # backend deploy image (Node 22 + Python 3.13 + venv) — see DEPLOY.md
├── docker-compose.yml                     # app service (backend) + unused postgres/redis, for deployment — build verified locally 2026-08-10
├── DEPLOY.md                              # backend deploy runbook — Oracle Cloud Ampere A1 target + capacity-workaround section
├── HANDOVER.md                            # this file
│
├── backend/
│   ├── .env                               # JWT_SECRET (real), ANTHROPIC_API_KEY (rotated 2026-08-10), real RevenueCat creds, Stripe/AWS/Postgres/Redis placeholders
│   ├── .gitignore                         # node_modules/, uploads/*, .env, data/*.db*
│   ├── data/
│   │   └── app.db (+ -shm/-wal)           # SQLite — the only database in use, incl. reel_jobs (2026-08-11, job+polling for highlight-reel stitching)
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
│   ├── App.js                             # Tab nav (Home/History/Drills/Premium/Profile) + stack screens, wrapped in AuthProvider
│   ├── app.json                           # name: RallyMax, bundle com.jackp.tennisai
│   ├── package.json
│   ├── assets/
│   │   └── tipPhotos/                     # real tip photos, dropped in by filename (see README.md there); optional per-tip
│   ├── components/
│   │   ├── PlatformVideo.web.js           # real DOM <video>, explicit pixel sizing
│   │   ├── PlatformVideo.native.js        # expo-av Video wrapper, same interface
│   │   ├── TrendChart.js                  # hand-rolled react-native-svg progression chart, used by HistoryScreen
│   │   ├── TipDiagram.js                  # per-tip visual: real photo (tipPhotos.js) if present, else SVG (tipDiagrams/)
│   │   ├── tipDiagrams/                   # tipVisuals.js (id→SVG mapping), tipPhotos.js (id→photo mapping), landmarks.js, PlayerSilhouette.js
│   │   ├── AnnotationCanvas.js            # freehand pen/line/arrow/circle drawing layer, used per-pane in SyncCompareScreen -- persisted since 2026-08-13 (swing_annotations table)
│   │   ├── ScoreRing.js                   # gained an `animate` prop (2026-08-10) — sweeps fill + counts up, used by the share-preview popup
│   │   └── ResultShareCard.js             # forwards `animate` to ScoreRing; the offscreen instance used for the actual PNG capture stays static
│   ├── config/
│   │   └── api.js                         # API_BASE (hardcoded LAN IP)
│   ├── context/
│   │   └── AuthContext.js                 # token persistence, signup/login/logout, isPremium
│   └── screens/
│       ├── HomeScreen.js                  # real dashboard, pulls from GET /api/history
│       ├── HistoryScreen.js               # real history list + progression chart (overall + per-shot-type)
│       ├── DrillsScreen.js                # new (2026-08-10) — structural stub, no real drill content yet
│       ├── PremiumScreen.js               # entry point, not gated by tier
│       ├── ProfileScreen.js               # real auth state
│       ├── LoginScreen.js / SignupScreen.js   # real auth
│       ├── ContactMarkingScreen.js        # reused by both single-video and versus flows
│       ├── ResultsScreen.js               # real /api/analyse call — the working end-to-end path
│       ├── SyncCompareScreen.js           # synced dual-video comparison w/ zoom slider + real pinch/pan gesture (2026-08-12), skeleton toggle, annotation toolbar — reachable from Results and History
│       ├── VersusPickScreen.js / VersusResultsScreen.js       # 1v1 comparison, real /api/compare-videos call, same themed layout as ResultsScreen (2026-08-12)
│       └── HighlightUploadScreen.js / HighlightReviewScreen.js / HighlightArchiveScreen.js   # highlight archive + real rally detection pipeline
│
├── docs/
│   └── plans/
│       └── parallelize_batch_pipeline.md  # parked design doc for parallelizing the batch swing-analysis pipeline (not yet run against real data)
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
│   ├── 07_ball_racket_tracking/           # racket keypoint ML — used live (body_rotation phase scoring + shot-contact verifier)
│   ├── 08_comparison_engine/              # compare_swing.py (live) + compare_videos.py (live, wired 2026-08-12, now with phase breakdown too)
│   ├── 09_coaching_ai/                    # teacher-student tip selector — built and live in compare_swing.py
│   ├── 10_net_detection/                  # net-end keypoint ML — trained, unintegrated
│   ├── 11_highlight_clipping/             # detect_rallies.py — rally boundary detection, now gated on verified real shots (see Planned Features item 5)
│   ├── 12_video_crop/                     # crop_to_subject.py — pose-driven subject crop, used by Watch & compare + the shot verifier's cropped detection
│   ├── 13_overlay_trajectories/           # precomputed pro-side skeleton overlay trajectories (see Planned Features item 3)
│   ├── 14_shot_classifier/                # rule-based + Claude-vision-verifier shot classifier — 57% accuracy so far, verifier kept active until trusted (see Planned Features)
│   ├── 15_batch_analysis/                 # analyze_rallies_parallel.py — parallel batch pipeline; run for real 2026-08-10 to rebuild Jack's history through the new verified-shot gate (see item 7)
│   ├── 16_shot_verification/              # Claude teacher-student "is this a real shot" loop, mirrors 14_shot_classifier/ (see Planned Features item 7)
│   └── 17_amateur_eval/                   # evaluate_amateur_dataset.py + tune_shot_scorers.py -- real-footage eval harness for the classifier/verifier, zero API cost (see Planned Features items 10-11)
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
    ├── backups/                            # DB row backups taken before any bulk mutation (e.g. before the 2026-08-10 history rebuild)
    └── runtime/                             # this tree has grown a lot across sessions -- last_comparison.json is the only entry the doc previously tracked; notable others as of 2026-08-10:
        ├── last_comparison.json           # most recent live inference output
        ├── highlight_clips/13/{3,4}/      # real rally clips for Jack's two uploaded match videos (job 3 = 64 rallies, job 4 = 25)
        ├── user_clips/<analysis_id>/      # original.mp4 + cropped.mp4 per saved analysis, served via /user-clips
        ├── batch_swings/{3,4}/            # per-swing clips from the original (pre-verification) overnight batch run
        └── shot_verification_batch/       # batch_verify_all.py's checkpoint (verified_swings.jsonl) + cached poses
```

---

## Scheduled-routine PR round-up (2026-08-23)

Five scheduled routines run against this repo (docs, logic review, bug
sweep, security review, brainstorm/future-plans); this section is the
docs routine's daily summary of what the other four opened in the last
24h. None of these routines merge their own PRs — anything listed as
open is sitting there waiting on Jack.

**Checked:** GitHub PR search for `created:>=2026-08-22`, a full open-PR
listing, and a branch listing (only two branches exist on the remote:
`master` and one PR branch — no `logic-review/`, `security-review/`, or
`future-ideas/` branches from today).

**Result: only one PR from today.**

- **PR #1 — "Bug sweep: crash/race/edge-case fixes across backend routes
  and ML entry points"** (branch `bug-sweep/2026-08-23`, opened
  2026-08-23T09:34 UTC, still open). A systematic pass across
  `backend/src/routes/`, middleware, utils, and both live Python
  comparison entry points. Headline find: `GET /courts` was crashing
  unconditionally on every call (ambiguous `latitude`/`longitude` column
  reference after the `clubs` LEFT JOIN) — the court-search feature was
  completely broken in current code, now fixed with a regression test.
  Also fixes: a negative-`radiusKm` court-search bug that silently
  zeroed results and re-triggered an Overpass reseed every request;
  malformed-JSON bodies 500ing app-wide instead of 400ing; several
  non-string-input crashes in `auth.js`; a free-tier daily-analysis slot
  being permanently burned on an invalid `contactTime` with no refund;
  a missing `'error'` listener on a detached background spawn that could
  crash the whole server process; an `Infinity`/`-Infinity` bypass of
  `contactTime` validation; a paywall-bypass letting a free user record
  practice attempts against a locked premium lesson step by guessing its
  id; a `history.js` PATCH accepting a self-contradictory
  flagged/confirmed combination; unvalidated SQL binds in
  `highlights.js`/`friends.js`; and two Python `ZeroDivisionError`/
  `IndexError` crashes on malformed video uploads. Backend test suite
  went from 33→49 passing tests across 4 new + 3 extended test files.
  A few findings were deliberately left unfixed — see the new
  "Product-call items from PR #1" entry in `TODO_MANUAL.md`, added today
  — since they either need Jack's call or are too low-probability/risky
  to patch blind without dedicated test infra.
- **No CRITICAL security-review PR exists today** — the security-review
  routine hasn't produced a branch/PR yet as of this writing.
- **Logic review, security review, brainstorm/future-plans routines**:
  no PRs and no branches from any of them in the last 24h. Either they
  haven't fired yet on today's schedule or found nothing worth opening a
  PR for — nothing to report either way.

This routine (docs) does not touch application code — this is a docs-only
commit straight to `master`, no PR, per its own standing instructions.

---

## Scheduled-routine PR round-up (2026-08-24)

Checked via GitHub PR search/listing (no `gh` CLI in this environment,
used the GitHub MCP tools instead). Unlike yesterday, all four other
routines opened a PR overnight — **PRs #5–#8, all still open**, none
merged (these routines never merge their own work). **No `🚨 CRITICAL:`
PR today.**

- **PR #5 — "Logic review 2026-08-24: consolidate two drifted vocabulary
  duplicates"** (branch `logic-review/2026-08-24`, opened 03:07 UTC).
  Found two closed vocabularies defined once in `domain/invariants.js`
  but re-listed inline elsewhere — `profile.js`'s `computePlayerType()`
  hardcoded the rally-outcome tags instead of deriving them from
  `OUTCOME_TAGS`, and `drills.js`'s `GET /drills` `kind` filter used a
  literal `['drill', 'lesson']` instead of the shared `DRILL_KINDS`.
  Neither changes behavior today — both fixes just remove a future
  silent-drift risk if the canonical lists ever change. 441 tests still
  passing. Also re-flagged (not touched, already tracked): the
  `billing.js`/`webhooks.js` RevenueCat entitlement-id matching loose
  end, the empty-`rallyIds` product-intent question, and a couple of
  stale comments (`compare_swing.py` docstring, `rateLimit.js` header).
- **PR #6 — "Bug sweep 2026-08-24: 9 bugs across routes, domain layer,
  and the 1v1 comparison engine"** (branch `bug-sweep/2026-08-24`, opened
  03:29 UTC). Headline find: a real data-loss bug in the drill editor —
  a malformed routine-step `id` (e.g. a stringified `"undefined"`) made
  `Number.parseInt` return `NaN`, which is falsy, so the id-reconciliation
  save path treated an existing step as brand-new **and** hard-deleted
  the real step (plus all `drill_practice_attempts` history pointing at
  it) it was supposed to match — silently, inside the save transaction.
  Also fixed: orphaned upload files on every rejected drill-video
  submission; a highlights-ingest DB failure being mislabeled as "invalid
  detector output" with the real error never logged; two uncaught 500s
  that should've been 400s (a non-string leaderboard `note`, a
  non-string RevenueCat webhook `event.type`); an unenforced
  phase-vs-timestamp mutual-exclusivity rule on coach notes; an unlogged
  live-calibration failure; three write/at-rest integrity-check parity
  gaps; and a dead `angle_mismatch_warning` field in the 1v1 comparison
  engine (its threshold matched the hard-reject gate, so it could never
  actually fire). 465 passing tests (was 443, +22 regression tests).
  Left unfixed: the same previously-documented deliberate items (invite-code
  TOCTOU, non-transactional Overpass upsert, `runPythonJson` SIGKILL,
  RevenueCat field-name loose end) — no new product-call item this pass.
- **PR #7 — "Security review 2026-08-24: restrict video-upload extensions
  to a video allowlist"** (branch `security-review/2026-08-24`, opened
  03:40 UTC). Re-verified everything from the 2026-08-19/2026-08-23 passes
  (parameterized SQL, argv-array `spawn` calls, auth/JWT/rate-limiting, no
  secret ever committed) with nothing new there. New finding: every
  upload route (`analyse.js`, `compareVideos.js`, `highlights.js`,
  `calibration.js`, `dev.js`'s drill-video editor) built the stored
  filename's extension straight from the client-supplied original
  filename with no allowlist — a crafted upload that made it far enough
  through the pipeline to save as an analysis could get served back from
  `/user-clips` with an attacker-chosen extension (e.g. `.html`), a
  stored-HTML/XSS vector; the admin-only drill-video uploader had no
  processing gate at all. Judged a real gap, not a critical one (getting
  actual malicious bytes through MediaPipe/OpenCV as a "successful
  analysis" is unlikely in practice) — fixed anyway with a shared
  `videoFileFilter`/`safeVideoExt` allowlist (`.mp4`/`.mov`/`.m4v`/`.avi`/
  `.webm`/`.mkv`/`.3gp`) wired into all five upload sites. 443 passing
  tests (was 441, +2 new).
- **PR #8 — "Add future-ideas brainstorm doc (2026-08-24)"** (branch
  `future-ideas/2026-08-24`, opened 03:48 UTC). New dated section in
  `docs/future-ideas.md` — docs only, no application-code changes.

This routine (docs) does not touch application code — this is a docs-only
commit straight to `master`, no PR, per its own standing instructions.

---

## Scheduled-routine PR round-up (2026-08-25)

Checked via GitHub PR search/listing (no `gh` CLI in this environment,
used the GitHub MCP tools instead). All four other routines opened a PR
again overnight — **PRs #9–#12, all still open**, none merged (these
routines never merge their own work). **No `🚨 CRITICAL:` PR today.**
Also still open from yesterday and not yet merged: **PR #8**
(`future-ideas/2026-08-24`) — carried forward, not part of today's batch.

- **PR #9 — "Logic review 2026-08-25: video-timestamp validation,
  flagged-swing leakage, courts radius rounding, target_reps type gap"**
  (branch `logic-review/2026-08-25`, opened 03:11 UTC). Four
  correctness-vs-intent fixes: `/analyse` and `/compare-videos` now
  validate `contactTime`/`contactTimeA`/`contactTimeB` with the shared
  `isTimestampSec` invariant instead of a hand-rolled finite-number check
  (a negative or absurd-but-finite contact time used to pass straight
  through to the Python subprocess, burning a free-tier slot on a
  corrupted result instead of a clean 400); `profile.js`'s rank/player-type
  aggregates now exclude `flagged_not_shot` rows the same way
  `leaderboard.js` already does; `courts.js`'s radius filter/sort now uses
  the exact haversine distance instead of the already-rounded display
  value (fixing a boundary case where e.g. a true 20.03km court rounded to
  20.0 and wrongly passed a 20km radius filter); and `dev.js`'s
  `target_reps` step validation now type-checks like its sibling fields
  instead of coercing (`true`/`[5]` used to slip through as "a positive
  whole number" and 500 inside the save transaction). 469/469 tests
  passing. Noticed-but-not-touched: a stale `compare_swing.py` docstring
  ("every 2nd frame" vs. the real every-3rd-frame rate — no actual
  mismatch, just a wrong comment) and an unvalidated `drills.js` read-side
  `shot_type` filter (fails safe to zero rows, not a correctness bug).
- **PR #10 — "Bug sweep: fix 5 real bugs across the ML engine and backend
  routes"** (branch `bug-sweep/2026-08-25`, opened 03:28 UTC). Headline
  find: `compare_swing.py`'s `build_user_trajectory()` had no minimum-length
  guard (unlike the pro-database side's `MIN_TRAJECTORY_POINTS = 5`), so a
  swing with only 1-4 usable pose frames near contact (plausible from
  backlighting/occlusion/motion blur) produced a fake, meaningless
  similarity score instead of a clean error — now guarded with the same
  constant, routed through the existing empty-trajectory `RuntimeError`
  path. **This specific fix could not be executed in the routine's
  sandbox (no `cv2`/`mediapipe`/venv available)** — verified by inspection
  against the identical, already-tested pattern it mirrors; worth a real
  `pytest`/spot-check before merging. Also fixed: a highlights
  `boundary_note` that could never actually be cleared once set (omitted
  vs. explicit-empty key conflation between `highlights.js` and
  `DevRallyBoundaryReviewScreen.js`); untyped `pro_id`/`angle_label`/
  `tip_text` in `history.js` that could 500 instead of 400 on a malformed
  match payload; silently-swallowed file-cleanup failures on account
  deletion (`auth.js`, now logged); and a missing `Number.isInteger` guard
  on the block-user unblock route (`messages.js`, fails safe today, fixed
  for consistency). 472/472 tests passing (2 new regression tests).
- **PR #11 — "Security review 2026-08-25: pin JWT verification to
  HS256"** (branch `security-review/2026-08-25`, opened 03:39 UTC).
  Re-verified everything from the 2026-08-19/08-23/08-24 passes (parameterized
  SQL, argv-array `spawn` calls, auth/JWT/rate-limiting, video-upload
  extension allowlist, no secret ever committed) — still clean. **No
  critical finding.** New hardening (not an active exploit): `jwt.verify()`
  in `requireAuth.js`/`optionalAuth.js` didn't pin an `algorithms` option,
  so verification would accept whatever algorithm a token's own header
  claimed rather than only the HS256 this app actually signs with — not
  exploitable today (this app only ever holds one opaque HMAC secret, no
  dual-purpose public key to leak, and `jsonwebtoken` already refuses
  `alg: "none"`), but pinned anyway per OWASP's standard JWT-hardening
  recommendation, as a structural guarantee rather than one resting on
  library defaults. 467/467 tests passing, no regressions.
- **PR #12 — "Add future-ideas brainstorm doc (2026-08-25)"** (branch
  `future-ideas/2026-08-25`, opened 03:49 UTC). New dated section in
  `docs/future-ideas.md`, building on today's three review PRs — docs only,
  no application-code changes.

This routine (docs) does not touch application code — this is a docs-only
commit straight to `master`, no PR, per its own standing instructions.

---

## Scheduled-routine PR round-up (2026-08-26)

Checked via GitHub PR search/listing (no `gh` CLI in this environment,
used the GitHub MCP tools instead). All four other routines opened a PR
again overnight — **PRs #13–#16, all still open**, none merged (these
routines never merge their own work). **No `🚨 CRITICAL:` PR today.**
Yesterday's PRs (#9–#12 and the older #8) are all now merged — nothing
carried forward from prior rounds.

- **PR #13 — "Logic review 2026-08-26: shoulder-visibility trajectory bug
  + shot_type vocabulary drift"** (branch `logic-review/2026-08-26`,
  opened 03:10 UTC). Two fixes: `celebrity_scores`' schema-level `shot_type`
  `CHECK` constraint in `db.js` was a 6th hardcoded copy of `SHOT_TYPES`
  (a landmark import comment already flags 5 other files for this same
  drift) — now derived from `SHOT_TYPES` directly, plus a missing
  `VALUE_DOMAIN_CHECKS` entry added so `verify:db` actually covers it as a
  prior test already claimed. Bigger one: `get_shoulder_ref()` in
  `build_pro_database.py` computed the shoulder-midpoint origin every other
  landmark gets normalized against with **no visibility gate** — unlike
  every other landmark, which is dropped below 0.3 visibility. A commonly-
  occluded near shoulder at contact (the exact phase weighted most heavily)
  could silently shift the whole frame's coordinates. This function is
  shared with `compare_swing.py`, so it affects every live `/api/analyse`
  DTW comparison, not just the offline pro-database build. Fixed to reject
  (return `None`) a shoulder reference below the same 0.3 threshold, same
  as a genuinely missing shoulder. **Could not run the real `scripts/`
  pytest suite in the routine's sandbox (no venv)** — verified instead by
  stubbing `cv2`/`mediapipe` and exercising the function directly (existing
  regression test still passes, low-visibility correctly rejected, the 0.3
  boundary itself still accepted). Worth a real `cd scripts && pytest` pass
  before merging, same caveat PR #10 flagged for a similar live-path change
  on 2026-08-25. 474/474 backend tests passing. Noticed-but-not-touched:
  the already-known `rallyIds: []` product-intent question (still open,
  unreachable from the shipped frontend today) and Python-side
  `shot_type` vocabulary duplication across 4 argparse scripts (real, but
  cross-language and operationally harder to silently drift than the DB
  constraint fixed here).
- **PR #14 — "Bug sweep 2026-08-26: webhook crash, drill-video disk leak,
  Overpass hammering"** (branch `bug-sweep/2026-08-26`, opened 03:24 UTC).
  Three fixes: `webhooks.js` only guarded `event.entitlement_ids` against a
  *falsy* value, so a truthy non-array (e.g. `{}`) from RevenueCat threw
  inside a non-async handler — surfaced as a bare 500, and since the
  `payment_events` row is inserted before that line, RevenueCat's
  redelivery-on-non-2xx meant the same malformed event retried forever
  without ever applying the tier change. Now array-checked like the
  existing `event.type` guard. The Dev Page drill/lesson video editor
  never deleted the old file on a successful re-upload (only on a
  *rejected* one) — an unbounded slow disk leak on every re-edit, now
  cleaned up post-commit. `courts.js` re-hit the public Overpass API on
  *every* request for a genuinely court-less area (empty result looks
  identical to "never queried" with no record of the miss) — real risk of
  Overpass rate-limiting/banning the whole app's IP; fixed with a 1-hour
  in-process negative cache keyed on a coarse lat/lng bucket. 478/478 tests
  passing (regression tests added for all three). Noticed-but-not-fixed:
  RevenueCat's at-least-once, not-guaranteed-in-order webhook delivery
  means a stale `EXPIRATION` redelivered after a newer `RENEWAL` could
  downgrade a paying user until the next `/billing/sync` — a real design
  decision (tracking latest-applied-event timestamp per user), not a
  drive-by fix.
- **PR #15 — "Security review 2026-08-26: path traversal in Dev Page
  swing-review tool"** (branch `security-review/2026-08-26`, opened 03:41
  UTC). One real finding: `GET /api/dev/swing-candidates/:jobId` and
  `POST /api/dev/swing-candidates/label` forwarded `jobId`/`job_id`/
  `rally_id` straight into `os.path.join()` calls in two Python scripts
  with zero validation, so a crafted id (e.g. `..%2F..%2F...`) could walk
  `job_dir` outside `HIGHLIGHT_CLIPS_DIR` — an authenticated
  directory-listing-and-pose-extraction oracle over arbitrary filesystem
  paths. Not filed as `🚨 CRITICAL:`: both routes already sit behind
  `requireAuth` + `requireAdmin`, so exploitation needs a compromised admin
  session, not just any authenticated user. Fixed with the same
  `isPositiveIntegerId()` helper already used elsewhere in `dev.js`, since
  job ids are always real autoincrement integers. Everything else checked
  (JWT/auth, all multer upload sites, SQL parameterization across all 20
  route files, every `child_process.spawn` argv-array call, secret
  handling, webhook signature timing-safety, IDOR spot checks) came back
  clean — the 5th consecutive day this routine found the codebase already
  well-hardened going in. 474/474 tests passing.
- **PR #16 — "Add future-ideas brainstorm doc (2026-08-26)"** (branch
  `future-ideas/2026-08-26`, opened 03:53 UTC). New dated section in
  `docs/future-ideas.md` — product ideas (Coach Collaboration Mode
  end-to-end verification, graduating `player-type` to a trained model,
  friend head-to-head on Home), ML pipeline ideas (ball-speed v1 now that
  both named blockers are cleared, gravity-aware flight model, per-class
  shot-classifier trust bucketing), data-quality ideas (motion-audit rule
  applied to the pro database itself, rechecking ship-time-guessed
  thresholds), and tech debt (no test gate on the CD pipeline, narrowed
  untested-route list, an interim DB backup piggybacking on CD's SSH
  access, a stale `tip_verifier.py` comment, `TODO_MANUAL.md`'s stale
  banner). Docs only, no application-code changes.

This routine (docs) does not touch application code — this is a docs-only
commit straight to `master`, no PR, per its own standing instructions.
