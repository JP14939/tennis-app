# Manual to-do — things only you can do

Everything here needs a human clicking through a dashboard, creating an
account, or physically testing with a device — none of it is something I
can do myself. Grouped chronologically by session below; skim for `~~struck
through~~` (resolved) vs. plain (still open) headings if you're catching up.
Resolved entries are kept short (breadcrumb only) — this file was compressed
2026-08-26 to cut ~45% of dead weight (finished checklists, superseded
runbooks); nothing open was trimmed.

**For a quick "what actually matters right now," read `STATUS.md`** (repo
root) instead of this block — it's a short, hand-curated, actively-overwritten
snapshot, not another log entry that goes stale the moment something below
gets resolved.

---

## New from the 2026-09-02 session (contact detection + shot classifier)

Full technical detail: `HANDOVER.md` "Session 2026-09-02 (later)". Working
plan: `C:\Users\jackp\.claude\plans\okay-where-do-things-woolly-pond.md`.
**None of this session's code is committed.**

1. **Source more footage — this is now the single highest-leverage manual
   task.**
   - **Amateur backhand footage** is the real bottleneck for the shot
     classifier — there are only **10** backhand training examples (vs ~50
     forehand / ~57 serve). Everything else about the classifier is blocked on
     this. Phone-style / instructional / rally footage, not broadcast.
     Labels go via `data/08_coaching_ai/amateur_swing_labels.json`.
   - **Pro footage for the database** — the Pro Clip Review left only **21
     serve** clips (77 % excluded), plus forehand 215 / backhand 123. Jack
     wants the DB bigger. New source compilations go through the
     `scripts/01`–`06` offline pipeline.

2. **Test the live audio contact detection on a real phone.** Record a swing
   with the in-app camera (`recordAsync` keeps an audio track), **do not mark
   the contact frame**, upload. In the backend logs for that analysis, look for
   `Contact auto-detected via AUDIO onset at X.XXXs (confidence ...)`. Confirm
   the similarity score / pro match look sane. This is the one bit of Phase B.1
   that couldn't be verified locally (no phone-recorded clip with audio on
   disk).

3. **Decision — run the pro-DB contact-time fill (Phase B.2)?** The review is
   done, so this is unblocked. It would: run the audio detector over all 359
   kept clips, auto-fill `clip_contact_time_sec` for the confident majority,
   flag the rest for a quick human pass, then
   `rebuild_pro_database_from_verdicts.py` re-anchors every trajectory. Right
   now `pro_database.json` is still half-hand-corrected (196 real contact
   times, the rest placeholder). ~1 h of compute + a short human pass. Say the
   word.

4. **Decision — the shot classifier.** Retraining is coded and ready but the
   results need Jack's call:
   - Ship the v2 body-normalised **amateur-only** model? (Marginal — backhand
     F1 0.30→0.40 on a 10-example test set, i.e. within noise. The body-norm +
     version-safety infra is worth keeping regardless.)
   - Build a **separate pipeline model** (`shot_classifier_pipeline_model.pkl`,
     amateur + pro) for `detect_rallies.py` / `analyze_rallies_parallel.py`?
     Pro data gives backhand F1 0.63 there (n = 161, real) but hurts the live
     phone model.
   - Neither is urgent, and **the serve over-prediction that's actually
     blocking rally detection is probably a contact-frame problem, not a
     classifier one** (see HANDOVER §7 / item below).

5. **Note for whoever picks up Sprint 2 (`detect_rallies` serve-gate):** before
   touching `apply_serve_gate()`, wire the accurate contact detection into
   `detect_rallies` — it currently feeds the Claude shot verifier a frame ~13
   frames off (the swing-detector wrist-peak), which makes groundstrokes look
   like serves. That may be most of the "everything is a serve" problem.

6. **Front-view pro clips** — clips around **swing_id ~2015** (forehand source
   job 2) are filmed from the front (camera at the net), so pose landmarks are
   mirrored vs. the rest. Handle when rebuilding the pro DB (view-direction
   correction or exclusion).

## New from the 2026-09-01 session

1. **Competitive analysis of SevenSix** (`SevenSix AS`, Norway) from a full
   walkthrough video Jack recorded of their app
   (`C:\Users\jackp\Downloads\HQZE8437.MP4`). Same pose-extraction +
   compare-to-a-pro core loop as RallyMax, iOS-only. Read: not a capital or
   tech threat (~$550K raised total, ~4.0–4.34 rating on ~62–80 ratings,
   visible reliability problems, shipped-then-killed features); the real
   risk is their tennis-federation distribution bet. Pricing observed: UK
   £149.99/yr or £14.99/mo + 14-day trial; US $22.99/mo, $229/yr, plus
   pay-per-swing tiers. Full teardown summarised in `STATUS.md`'s new
   "Competitive" block and the `docs/future-ideas.md` `### 2026-09-01`
   context paragraph.
2. **Ideas logged** to `docs/future-ideas.md` (`### 2026-09-01`, house
   format) and `AI's_ideas.md` refreshed to that pass (it was 3 passes
   behind). `STATUS.md` and `HANDOVER.md` stale facts corrected in the same
   pass (ball detector Phase 3 shipped, IMG_5755 verification done, backend
   auto-deploys now, serve-gate bug surfaced, `HANDOVER.md` got the
   "Quick status" line `CLAUDE.md` points at).
3. **New human-only / product-decision items from the teardown:**
   - Test the **pre-record framing / pose-lock gate** idea on a real phone —
     folds into the existing "Test Record now" item below, same session.
   - **Product call**: adopt a collapsed one-glance "hero result" as the
     default `ResultsScreen.js` state (score ring + one worst-phase line,
     everything else a tap away), the way SevenSix does?
   - **Product call**: build named, points-scored challenges (SevenSix has
     "Compare to the AO23" / "Weekly Biomech" on its Training tab)?
   - **Competitor watch**: check SevenSix's App Store release notes +
     regional pricing ~monthly — they price-test and churn features, so the
     read goes stale.
4. **Still open, now also blocking a product idea**: the `detect_rallies.py`
   `apply_serve_gate()` bug (2026-08-26 item 5) and the shot-classifier
   retrain (2026-08-26 item 4). The serve-gate fix is the prerequisite for
   promoting session-upload swing auto-split to the primary capture flow.

---

## New from the 2026-08-26 session

1. **Merged PRs #13–#16** (logic review, bug sweep, security review,
   future-ideas) from today's scheduled routines — reviewed diffs directly,
   ran the full test suite (478 backend + 61 Python) in an isolated git
   worktree before merging, pushed to master. Note for future sessions:
   the sandbox's permission classifier blocks a direct `git push` to
   `master` outright — Jack has to run that command himself even after
   everything's reviewed/merged/tested locally.
2. **Ball detector Phase 3 shipped.** Fine-tuned YOLO model
   (`data/10b_ball_detection/yolo_ball_run_v1/`) wired into production
   (`racket_tracker.py`, `verify_shot_contact.py`) — confirmed live via
   the original unmodified audit script: **95% detection / 0.548 avg
   confidence** at contact, up from the generic model's ~50%/0.41.
3. **Contact-verification rules+ML model shipped.** Trained on ~1,000
   logged Claude verdicts, wired into `verify_shot_contact_verified.py`
   with its own trust gate (`shot_contact_ml_training_log.py`), mirroring
   the existing shot-classifier ML pattern — skips Claude once it proves
   out, same as every other teacher-student loop in this app.
4. **Shot-type classifier: real bug found and fixed, training not yet
   re-run.** `extract_training_features_from_log.py` was pose-extracting
   *entire* raw source videos (found stuck 10+ hours on a 2.2GB file)
   instead of the ~1.5s window it actually needs around each contact
   frame, plus a path-separator dedup bug that would've double-processed
   the same video. Both fixed — re-running now correctly produces 102 real
   training rows in under a minute (was 5, wrongly, before the fix). Next
   step: run `train_shot_classifier_model.py` on the combined dataset and
   report CV metrics — not done yet.
5. **⚠️ Real pipeline bug found, NOT YET FIXED — needs your call.**
   Investigating why those 102 rows skew serve-heavy, you correctly
   pushed back that `IMG_5755.MOV` is real rally play, not serve practice.
   Confirmed a genuine bug in `scripts/11_highlight_clipping/
   detect_rallies.py`'s `apply_serve_gate()`: it treats a >6s gap since
   the last *detected* swing as "the point ended," but the swing detector
   itself misses most real rally shots (only 54 of 290 candidates in
   IMG_5755 confirmed real), so that gap is usually a detection gap, not
   a real point boundary. Result: **100% of confirmed real forehands
   (12/12) in IMG_5755 were discarded** by this gate — the actual reason
   `rallies_detected: 0` despite genuine rallies happening. Affects the
   rally-grouping/highlight-clip feature specifically. Tell me when you
   want this fixed (decouple the point-boundary gap from detection
   reliability) — not started.
6. **Routine schedule changed — applied by you via the routines UI**, not
   something I have tool access to edit directly (I can only see/manage
   the per-PR check-in sessions each routine spawns, not the routines'
   own recurring schedule). New schedule, replacing the table below:

   | Routine | Cadence | Cron (UTC) | Fires at |
   | --- | --- | --- | --- |
   | Logic review | every 3 days | `0 3 */3 * *` | 03:00 |
   | Bug sweep | every 3 days | `15 3 */3 * *` | 03:15 |
   | Security review | every 3 days | `30 3 */3 * *` | 03:30 |
   | Future-ideas brainstorm | **weekly, Mondays** | `45 3 * * 1` | 03:45 |
   | Docs round-up | every 3 days | `0 4 */3 * *` | 04:00 |
   | **Training-data drift watch (new)** | every 3 days | `15 4 */3 * *` | 04:15 |

   The new drift-watch routine checks the ML training logs
   (`shot_classifier_training_log.jsonl`, `shot_contact_training_log.jsonl`,
   and their `_ml_` counterparts) for detection-bias/class-skew anomalies —
   exactly the class of bug found in item 5 above. Reports findings; opens
   a normal PR (branch `training-drift-watch/YYYY-MM-DD`) only if it finds
   a real pipeline bug, same rules as bug sweep. Doesn't retrain models —
   that stays manual, same as every other model in this app.
   `*/3` on day-of-month resets each month boundary (occasional 1-2 day
   gap at month start) — the pragmatic standard-cron way to say "every 3
   days," not a perfectly rolling interval.
7. **Noted, not yet acted on**: several hourly PR check-in loops for
   already-merged PRs (#9–#12) are still re-arming daily instead of
   stopping themselves, as their own instructions say they should once a
   PR is merged. Worth a cleanup pass — not investigated or killed yet.
8. **Job #9 (IMG_5755 manual Swing Review) is ready** — Dev Page → Swing
   Review, cache pre-warmed, all 7 rally clips present plus the full
   video hardlinked in as an 8th candidate (no extra disk usage).

---

## Still open — payments loose end

RevenueCat/Stripe setup fully resolved 2026-08-19 (monthly plan live).
One thing never confirmed: whether Premium unlocks *instantly* on
purchase or only via the webhook a few seconds later — if it's ever
noticeably delayed, check `backend/src/routes/billing.js`'s
`active_entitlements` vs `items` field-name comment, likely culprit.
Annual/other price tiers were never added — optional, add later if wanted.

---

## Also on the list: data quality & manual testing

**Review the high-camera-angle pro database entries.** **20 of 631** pro
database entries have `camera_angle > 65°` (14 forehand, 6 backhand, 0
serve) — real swings currently being matched/scored for real users, so a
wrongly-labeled one could quietly produce a bad match. List them: run
`python -c "import json; db=json.load(open('data/06_pro_database/pro_database.json')); [print(e['id'], e['camera_angle'], e['clip_path']) for e in db['entries'] if e.get('camera_angle') and e['camera_angle']>65]"`
from `scripts/` (venv activated). For each: watch the clip, decide if the
framing is genuinely side-on (keep) or actually behind-the-baseline (fix
`camera_angle` or remove the entry). Offer stands: I can generate contact
sheets and do a first-pass read for you if you want.

**Test "Record now" (live camera calibration) on a real phone.** Never
click-tested the *live* feedback loop itself (only curl'd the backend in
isolation) — run `npx expo start`, try "Record now," check the
positioning badge feels responsive and the messaging makes sense as you
move the phone.

**Keep `frontend/config/api.js`'s LAN-IP fallback current** if Expo Go
ever can't reach the backend and nothing else changed — check `ipconfig`,
or set `EXPO_PUBLIC_API_BASE` in `frontend/.env` instead (overrides it).

---

## Later — deferred on purpose, don't forget these exist

~~API key rotation~~ and ~~hosting~~ — both resolved 2026-08-19.

**Apple App Store prep**, closer to submission time:
- Apple Developer Program enrollment ($99/yr).
- Set up an EAS development build (`eas build`) — plain Expo Go can't do
  real in-app purchases or Google Sign-In.
- Add native iOS purchases via RevenueCat's native SDK once the EAS build
  exists (backend webhook/entitlement logic doesn't change for it).
- Privacy policy URL, app icons/screenshots, permission usage strings.
- Backend is already hosted (done) — needed before submission, done.

---

## Still open from earlier sessions

- **Click through Swing Review's rough-pick contact-marking step** as a
  live user (Dev Page → Swing Review → pick a job → mark a shot → confirm
  the rough scrub feels right) — verified via API only, never clicked
  through.
- **Android icon/splash needs a native build to actually see** — correct
  on disk, but Android only renders them at native-build time, invisible
  in Expo Go. Same build step as the App Store prep above.
- **GitHub repo is public** (flipped from private 2026-08-20 for sharing)
  — flip back to private when done sharing:
  `gh repo edit JP14939/tennis-app --visibility private`.
- ~~Mojibake encoding bug~~, ~~Rally Boundary Review lazy loading~~,
  ~~Drills & Lessons showing real content~~ — all resolved/verified, prior
  sessions.
- **85 old History rows (2026-08-14 batch) have no watchable video on the
  hosted server** — those videos were only ever created locally, never
  copied to the host. A brand-new upload works fine; this only affects
  that specific old local batch. Fix would be a one-time `scp`/`tar` copy
  of `data/runtime/user_clips/8_*` to the host — not done, no decision to
  spend the effort on recovering old test data.
- **z-depth is disabled in DTW comparison** (`Z_WEIGHT = 0.0` in
  `trajectory_compare.py`) — a past attempt tanked similarity scores
  45-75% because MediaPipe's z needs its own measured-spread rescaling,
  not a reused x/y divisor. Re-enabling needs that rescale + re-validation
  against real saved swings.
- **True 3D pose extraction** — bigger/later idea; MediaPipe's z is a
  monocular guess, a real upgrade needs multi-camera triangulation or a
  depth-aware model.
- **No fault/ball-landing/in-or-out detection anywhere** — caps how far
  serve-gating or point-by-point scoring can go. Bigger separate project.
- **Single-player tracking only** — no opponent/dual-player awareness;
  relevant if "which side served" or doubles support is ever wanted (came
  up directly in the serve-gate bug found this session, item 5 above).
- **More coaching tip content** — expanding
  `data/08_coaching_ai/coaching_tips_database.json` is pure content work,
  always helps coverage.
- **Pose sampling is sparse (`sample_every=3`)** on both the pro database
  and user uploads — plausibly caps real comparison accuracy (fast
  moments like contact can be off by up to ~1/3 frame interval), not just
  overlay smoothness (already fixed separately). Increasing density needs
  re-extracting the ~1281-clip pro database (~60-90 min job) and
  re-running the amateur eval set to confirm quality actually improves.
  Not done — real pipeline change, worth doing once prioritized.
- **Pro database needs a manual clip-quality review pass** — beyond the
  high-camera-angle entries above, some of the ~914 clips are mismatched,
  slow-motion, or span two different swings. **Pro Clip Review** Dev Page
  tool exists for this (watch/tag ok / mismatched / slow-motion / spans
  two swings / don't-use / cut-to-fix, verdicts logged). Once enough are
  reviewed, a rebuild script excluding flagged entries isn't built yet.
- **Camera elevation calibrated on only 2 known-elevated reference
  videos.** Cheaper fix than more vision-side patching: capture phone
  accelerometer/gyroscope tilt at record time instead of inferring it.
- **No enforced convention for `optionalAuth` vs `requireAuth` per
  route** — root cause of a free-tier-cap bypass fixed 2026-08-22; each
  known site is patched, but the *next* new route could repeat it. Needs
  a lint rule or route-manifest assertion — I can just build it, no
  decision needed from you.
- **SQLite foreign keys are never enforced** (`PRAGMA foreign_keys` off)
  — root cause of 3 orphaned-row bugs, each individually fixed. Turning
  it on needs a full audit of every DELETE (some are intentionally
  partial) — needs your call before attempting, risk of breaking account/
  history deletion if done wrong.
- **SQLite still stands in for the Postgres `DATABASE_URL` implies** —
  `pg` installed but unused. Not urgent, flagged so it doesn't silently
  become permanent by default. Needs your call on timing.
- **`expo-av` must be migrated before the SDK 55 upgrade.** Deprecated in
  SDK 54 (currently pinned), removed outright in 55. Two call sites need
  *different* replacement packages: `PlatformVideo.native.js` →
  `expo-video` (must preserve its hand-written ref interface, shared with
  the `.web.js` platform file), `utils/sounds.js` → `expo-audio` (not
  currently installed). `expo-video` was previously removed as
  dead-weight; re-add as part of the real migration.
- **Ball-speed feature scoped, not built.** Recommended approach:
  net-keypoint local scale calibration, v1 metric = speed at the net
  crossing (disclosed limitation, not off-racket-at-contact). No action
  unless you want to greenlight implementation.
- **Local dev password reset**: `jack.p14370@gmail.com` on local
  (port 8090) was reset directly in `backend/data/app.db` to a password
  given in chat, not recorded here. `RESEND_API_KEY` still isn't
  configured locally, so the real email flow won't work on local dev
  until Resend is set up (account/API key/sender domain — same shape as
  the RevenueCat setup above, not detailed further here since it's a
  standard 3rd-party dashboard flow).

---

## Resolved — history/breadcrumbs only

- ~~RevenueCat 12-step setup~~ — 2026-08-19, live (see "Still open —
  payments loose end" above for the one lingering question).
- ~~Not yet committed to git~~ — 2026-08-18.
- ~~39 unprocessed clips in Downloads~~ (`IMG_5757`-`5774`, `5795`-`5815`,
  2 misc) — run 2026-08-20, **0 real swings confirmed across all of it**,
  $0 spent (trusted-bucket auto-reject). Not worth re-running as-is.
- ~~GitHub repo created~~ — 2026-08-20 (see "still open" note above re:
  visibility).
- ~~Hosted backend redeploy~~ — 2026-08-21. Root cause: `/opt/tennis_app`
  on the VPS wasn't a real git repo (one-time file copy, not `git clone`)
  — converted in place. SSH key `~/.ssh/rallymax_key` works for the VPS
  (`root@167.233.107.31`), use it over fighting password auth. Superseded
  2026-08-25 by real CD (`.github/workflows/deploy.yml`) — manual
  `git pull`+`docker compose` is no longer needed for code, only for
  `data/` file transfers (still manual) and `.env` edits (still manual).
- ~~Password reset email flow~~ — built and tested 2026-08-20, needs a
  real Resend account to send real emails (see "still open" list above).
- ~~Premium folded into Home + Lessons~~ — 2026-08-20 evening, per user
  feedback (6 tabs → 5, straight-to-checkout on tap).
- ~~Ball detector Phase 1/2 (data sourcing + labeling)~~ — 2026-08-20,
  354 labels logged including manual-review backlog. 5 static-decoy clips
  flagged and confirmed excluded 2026-08-25. Constant-velocity Kalman
  ball tracker also shipped as a complementary (not substitute) fix.
  **Phase 3 (fine-tuning) shipped this session, item 2 above.**
- ~~Shot classifier trained on real labeled data (not rule-based only)~~
  — 2026-08-19, 63.8% CV accuracy vs. rule-based 50%. Own trust gate,
  Claude stays teacher until it earns trust. **Log-derived data extraction
  bug found/fixed this session, item 4 above.**
- ~~`list_swing_candidates.py` classify() bug~~ — 2026-08-19, was silently
  passing `None` for every `student_shot_type` ever served.
- ~~Camera angle fallback when net isn't visible~~ — 2026-08-20,
  court-sideline Hough detector, confidence capped low. Not yet validated
  against real net-position footage (no known-good reference clips yet).
- ~~Coaching tip manual QA tool~~ — 2026-08-19, **Tip Review** Dev Page.
- ~~Tip severity shown to users~~ — 2026-08-20, mild/moderate/severe pill.
- ~~No CI/CD~~ — 2026-08-25, `.github/workflows/deploy.yml` auto-redeploys
  on push to master (code paths only).
- ~~Python-subprocess spawn boundary duplicated 12x~~ — 2026-08-22,
  centralized in `backend/src/utils/runPythonJson.js`.
- ~~5 scheduled daily routines connected~~ — 2026-08-23, ran as designed.
  **Schedule changed this session, item 6 above — see that entry for the
  current cron table, this is now historical only.**
- ~~PRs #1-#4 (2026-08-23 round)~~, ~~#5-#8 (2026-08-24)~~,
  ~~#9-#12 (2026-08-25)~~, ~~#13-#16 (2026-08-26)~~ — all scheduled-routine
  PRs reviewed and merged same-day or next-day each round. Two real merge
  conflicts hand-resolved on the 2026-08-23 round (`analyse.js`,
  `drills.js` — both had independent duplicate fixes from two different
  routines, combined the better parts of each). Per-PR fix summaries live
  in `HANDOVER.md`'s "Scheduled-routine PR round-up" sections if the
  specific detail of an old fix ever matters again.
- ~~Off-box database backups~~ — 2026-08-25. B2 bucket
  `rallymax-db-backups`, `rclone` remote `b2remote` on the VPS, cron job
  in `root`'s crontab (3am UTC). Auth verified live; a real file landing
  in the bucket after an actual 3am run was the last unconfirmed step as
  of 2026-08-25 — check the bucket if this hasn't been eyeballed since.
- ~~5 flagged ball-label clips reviewed~~ — 2026-08-25, all confirmed
  decoys, excluded from Phase 3 training data.
- ~~Coaching-tip Claude verifier was silently live on every real
  request~~ — found and disabled 2026-08-23 (contradicted docs describing
  it as unused/offline-only). Open question, never decided: should it
  ever go live again with a real kill switch/budget, or stay offline.
