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

## New from the 2026-09-09/10 session (metric-3D v4 pro-DB rebuild + verifier)

Full story: `HANDOVER.md` "Session 2026-09-09/10". Jack-only items:

- **DO NOT `git push` yet.** Commits `6cfee83`..`4d19e2b` (+ `12cab96`/`13771e7`)
  are local only. Pushing auto-deploys the user-side `sample_every` 3→1 change,
  and stride-1 user trajectories against the server's stride-3 pro DB = score
  drift. Push only *after* the rebuilt `data/06_pro_database/pro_database.json`
  + `overlay_trajectories.json` are copied to the VPS (folded into the existing
  pro-DB transfer item under "Backend / data" in `JACK_TODO.md`).
- **Uncommitted, yours to review/land with the verifier batch:**
  `scripts/07_ball_racket_tracking/racket_tracker.py` (`RALLYMAX_BALL_MODEL`
  env knob), `scripts/17_amateur_eval/evaluate_amateur_dataset.py` (per-row
  provenance stamps + `--fresh`), `scripts/06_database_build/reanchor_pro_serves.py`
  + its test (`yaw_enabled=True`).
- **`CURATED_AXES` in `redesign_similarity.py` (`4d19e2b`) is PROVISIONAL** —
  the 3D depth axes in it are a negative result on real footage; pull them
  before the rubric drives any user-facing number.
- *(optional, RED expected)* Film ~6 deliberate square-and-still ~3 s holds
  (one per camera position) for `calibration_hold_test.py` to fully close the
  "calibrate camera angle once per session" question. See `JACK_TODO.md`.

## New from the 2026-09-09 session (pre-release check + review prompt)

- **`PRE_RELEASE_CHECK.md` (repo root) is the running list** — distilled from
  4 videos (ASO + vibe-code security). Security + onboarding-Phase-1 + rating
  prompt are code-complete (backend 631 tests green, `verify:db` 99/99, web
  bundle clean; `/code-review` run + 8 fixes applied). **All still uncommitted
  and tangled with your own WIP** on `analyse.js` / `ResultsScreen.js` /
  `SignupScreen.js` / `TODO_MANUAL.md` — decide: commit everything together,
  have Claude hunk-split just the pre-release work, or you drive. The open
  items there are mostly yours:
  - **Budget caps + billing alerts** on KIE / Anthropic / AWS / Resend /
    RevenueCat, and scope the AWS IAM key to S3-only. Both security videos
    had 5-figure surprise bills from this.
  - **securityheaders.com scan** of the live host after the next deploy
    (headers middleware was added this session).
  - **ASO foundations** (Section B): store name + subtitle keyword research,
    100-char keyword field, screenshot reorder (lead with pro-overlay +
    score), then confirm the new rating prompt reads well on-device.
- **`ios.appStoreUrl` / `android.playStoreUrl` in `app.json`** — not set yet.
  The in-app native rating sheet (`StoreReview.requestReview()`) works
  without them, but `StoreReview.storeUrl()` / `hasAction()`'s fallback for
  older Android needs them. Add once the real store listings exist.
- **Test the new onboarding flow on a device** (Phase 1 built 2026-09-09,
  `docs/plans/onboarding_plan.md`). Fresh install → welcome screen → "Analyse
  my first swing" → full flow **as a guest** → after the analysis runs, a
  "Your score's ready — create a free account" gate → sign up → the result is
  revealed and saved to the new account's history. Check: the guest analysis
  actually runs against the hosted backend (needs the `optionalAuth` change
  deployed); the 2/24h guest per-IP cap behaves (429 with a "create an
  account" CTA, not a bare failure); "Skip for now" and
  already-have-an-account both work; a returning logged-in user never sees the
  welcome screen. `storage` key to clear for a re-test: `onboarding_complete`.
- **Decide onboarding Phase 2 scope** — result coach-marks, contact-frame
  lead-in card, permission pre-prompts, welcome-email drip (Resend is wired),
  funnel instrumentation. All deferred; none block launch.
- **Test the "rate the app" prompt on a device** — Dev Page → "Test 'rate
  the app' prompt" fires it immediately and clears the back-off state.
  Normal trigger: 2nd+ successful fresh analysis with score ≥ 50, max once
  per 60 days, 3 lifetime (`frontend/utils/reviewPrompt.js`). iOS suppresses
  the sheet unless the system feels like showing it — expect to see nothing
  most of the time; that's normal.

## ~~New from the 2026-09-08 session (ideal-swing reference clips)~~ — DONE 2026-09-10

- ~~**Produce 3 "ideal swing" reference clips**~~ — **DONE 2026-09-10.** Route
  that worked: **Luma Dream Machine "Modify Video"** (lumalabs.ai directly).
  Real behind-view swing clip + character start-frame → Luma re-renders the
  person, keeps the motion. Jack ran Luma (free trial credits); Claude
  transcoded the sources + removed Luma's two watermarks; Jack cropped around
  the player + retimed in CapCut; Claude finalised to 720p H.264.
  `frontend/assets/reference/{forehand,backhand,serve}-ideal.mp4` in place,
  `referenceClips.js` wired (3 requires uncommented, `CONTACT_SEC` set), web
  export verified. **Uncommitted.** WIP: `C:\Users\jackp\Documents\rallymax_reference_wip\`.
  Full narrative: `HANDOVER.md` "Session 2026-09-10 (later)".
  - **Left for Jack:** refine `CONTACT_SEC` in `referenceClips.js` (currently
    eyeball estimates `{forehand: 0.43, backhand: 1.0, serve: 0.3}`); device-test
    the compare screen ("Watch the ideal swing" button + per-tip "See this done
    right" links); commit alongside the rest of the uncommitted tree.
  - Prior AI route (Kie.ai, ~$3.38) and the Blender/composite routes are all
    closed — see `HANDOVER.md` if the history is needed.

## New from the 2026-09-08 session (ML-reliability roadmap, planning only)

Jack reviewed ML reliability across the whole app and built a release roadmap.
**No code changed.** Release date slipped (no fixed target); every premium
feature is now in scope for v1. The flat checklist is in `JACK_TODO.md`
("ML-reliability roadmap"); the full plan + two detailed designs (behind-baseline
camera gate, similarity-score calibration) are in
`C:\Users\jackp\.claude\plans\okay-so-i-finished-lovely-adleman.md`; the
narrative is `HANDOVER.md` "Session 2026-09-08".

**Your items from it (also in `JACK_TODO.md`):**
1. Record 3-5 whole-match videos from the fence + a few wrong-angle takes + some
   competent single swings + some deliberately sloppy ones (one session feeds the
   camera-gate validation set, the similarity-calibration anchors, and the
   highlights eval set).
2. Rotate the leaked `ANTHROPIC_API_KEY` in `backend/.env` (unblocks the
   coaching-tip verifier — still the same key flagged since 2026-08-10, partially
   rotated then, needs a clean rotation now).
3. Kick off the `sample_every` 3→1 pro-DB re-extract overnight (Claude will
   prep the code; you run the long job when CPU is free).
4. Keep working the Pro Clip Review practice queue — the held-out serves flow
   into the classifier pool as you go.

## New from the 2026-09-07 offline sessions (serve anchor Phase 1b, ball-tracking, retrain)

Full detail: `HANDOVER.md` "Session 2026-09-07" (three entries) + `STATUS.md`
items 10 & 12. All code is merged to master (PR #38). What's left for you:

1. **Serve-anchor Phase 1b — transfer the re-anchored pro DB to the server.**
   `scripts/06_database_build/reanchor_pro_serves.py` re-anchored 19
   non-human-marked serve entries in the local `pro_database.json` /
   `overlay_trajectories.json` to the overhead apex (backups:
   `*_pre_serve_reanchor_20260907_124604.json`). `data/` isn't deployed by
   CD — these need a manual `scp`, ideally bundled with the practice-ingest
   DB transfer once your Pro Clip Review pass is far enough along. Until
   then the live app serves the old server-side pro DB (serves anchored on
   the wrist-velocity peak).

2. ~~**Ball-detector retrain — check the gates, then decide.**~~ **DONE
   2026-09-08 — new `best.pt` KEPT (your call).** Retrain finished (resumed
   after an overnight stall, 150/150), 3 gates run: at-contact 91.7% / conf
   0.64 (baseline 50% / 0.41), near-player FH/serve ~94-96%, backhand flat
   ~0.77, far-ball 79%. No regression, honest non-leaky eval. **Left for
   you: the manual server transfer of `data/10b_ball_detection/yolo_ball_run_v1/weights/best.pt`**
   — bundle it with the pro-DB copy in item 1. (If you ever want to undo:
   `cp -r` the `_BACKUP_20260907_165355` dir back.) Writeup: HANDOVER.md
   "Session 2026-09-08 (later)".

3. **(Low priority) Wide-court ball labels need a hand pass — now the path to
   a ball-detector v2.** ~8 of the 22 `wide_court_ball_labels*.jsonl`
   positives are wrong or sloppy (box on background / the player's hip /
   offset) — see `data/10b_ball_detection/wide_court_review_notes.md`.
   Re-draw them in the Dev Page Ball Label tool + record more amateur
   backhand footage, then a Claude session rebuilds the dataset (adding the
   43 wide-court negatives) and retrains. This is the fix for the two weak
   spots the 2026-09-08 model still has (backhand, far/wide balls). Not
   urgent — the kept model is fine for v1; full-frame far-ball is ~79-87%.

Nothing to do for the two-pass ROI tracker or the near-court crop — both
evaluated NO-GO, code committed but unwired.

### Later same day (2026-09-07, later still) — clustering + classifier retrain run

Full detail: `HANDOVER.md` "Session 2026-09-07 (later still)". Both local-only,
nothing committed/pushed.

4. **`clusterCourts.js` has now been run locally (3,848 clubs from 33,222
   courts) — but the hosted DB still has zero clubs.** To get Find Games
   clubs live you need to either run `node backend/scripts/clusterCourts.js`
   on the server or transfer the `clubs` / `club_courts` rows — CD doesn't
   touch them. Bundle it with the pro-DB / practice-ingest data transfer
   (item 1 above, and the 2026-09-03/04 items below). Local `app.db` backed
   up as `backend/data/app.db.bak-20260907` — safe to delete once you're
   happy with the club list.
5. **Shot-classifier feature files re-extracted + `.pkl` retrained
   (`--no-log`) — no action needed, informational.** Pro Clip Review verdict
   rows are up to 632 (was 524); production ensemble on the pipeline domain
   rose 83.6% → 86.6%. The phone `.pkl` is unchanged and will stay flat
   until you source **amateur backhand footage** (still the one real lever —
   10 training examples). Old model backed up as
   `data/14_shot_classifier/shot_classifier_model.pkl.bak-20260907`.

### Later same day (2026-09-07, later still²) — core-loop verification + 2-week launch review

Jack wants to publish in ~2 weeks (target ~2026-09-21) and asked to verify the
core analysis loop works. No code changed — review only. Full trace + ranked
weak points: `HANDOVER.md` "Session 2026-09-07 (later still²)". Flat launch
checklist: `JACK_TODO.md` "2-week launch push".

6. **Core loop is verified working locally** — ran `compare_swing.py`
   end-to-end on a real saved upload, got a valid top-3 match + score + tips +
   phase breakdown, no crash. The engine is sound. The remaining launch work
   is plumbing (below), not the ML sprint.
7. **The ML-reliability sprint tail is downstream of rally-detection /
   highlights — a secondary feature.** Sprint 3, Phase C, the
   `analyze_rallies_parallel.py` contact wiring, and the classifier
   accuracy-gap revisit do **not** block launch. Recommend deferring the
   whole tail; do Sprint 3's $0 sanity run only if you want the number.
8. **Similarity scores land low and uncalibrated** — a legit forehand scored
   ≈50/100. `similarity_score`'s `scale=0.4` was never calibrated against a
   labelled match-quality set. This is the most likely thing to make the
   product feel broken to a first user. **Decision for you:** ask a Claude
   session to run a calibration pass on the amateur eval set and propose a
   `scale` (or a score-curve remap) before real users see numbers — or
   consciously ship as-is.
9. **Confirm the audio-onset contact model is actually deployed on the
   server.** If it isn't, every auto-detect upload (no manual contact mark)
   silently falls back to the ~9-frame wrist-peak heuristic, which shifts the
   whole DTW window. Check via a real no-mark upload: backend logs should show
   `Contact auto-detected via AUDIO onset`. Bundle the `.pkl` with the
   pro-DB / clustering data transfer (item 4 above).
10. **The 5-case live upload matrix + score-calibration decision are the real
    "is the core loop launch-ready?" gate** — see `JACK_TODO.md` "Pre-launch
    core-loop verification". Everything else there (Apple enrollment, EAS
    build, RevenueCat native SDK, Resend domain, privacy policy + assets,
    backups, repo-private) is standard store-submission plumbing.

### Later same day (2026-09-07, later still³) — main-loop verification (3 layers)

Full detail: `HANDOVER.md` "Session 2026-09-07 (later still³)". No code changed.
Verified the core loop at the local Python engine (6/6 cases incl. auto-detect
+ left-handed), local full stack (`POST /api/analyse` on :5000 → 200 + full
payload, `/api/history` round-trip, free-tier 403 after 2), and the live server
(HTTP 200, byte-identical score to local). **Works end to end, locally and in
production.** New flaws for you to weigh — none block the code, all are
product-quality calls:

11. **Score presentation — the inconsistency is FIXED (2026-09-08), calibration
    still open.** Was: `ResultsScreen` hero score = `overall_score`
    (`phase_breakdown.PHASE_SCALE=1.8`) → ~62–70, but the 2nd/3rd match scores
    right under it = raw `similarity` (`scale=0.4`) → ~25–38 for the *same*
    quality, so a user saw "62/100" then "other matches: 30, 25".
    **Jack's call: drop the pro-match framing entirely** — most
    `pro_database.json` clips were never identified (`player_names.json`
    partial), so "matched to Forehand Technique #142" read as broken. The
    "Other close matches" section is **removed** from `ResultsScreen` (kills the
    `scale=0.4` numbers on screen); the hero `overall_score` is the only 0–100
    shown; caption → "How closely your <shot> matches pro technique"; Sync
    Compare pane → "Pro swing"; History/Home/Coach/share/signup copy de-named;
    `analyse.js` → `--top 1`. Full writeup: `HANDOVER.md` "Session 2026-09-08
    (later⁵)". **Still open:** `PHASE_SCALE` is uncalibrated against a labelled
    match-quality set — that's roadmap **1b** (rubric redesign), CPU-blocked.
    `scale=0.4` now only governs the ≥75 "great swing" gate + the stored
    `similarity` fallback when phase breakdown fails.
12. **Serve looks bad to a first user.** A real marked-contact serve scored
    `similarity` 18/100 and matched only reclassified practice-footage clips
    (~82 pro serve entries total). Nothing new to fix here that isn't already
    tracked (serve anchor, more serve footage) — just confirming a serve upload
    is the worst first impression the app can make right now.
13. **Camera-angle confidence is ~0.3 on most real clips** (measured 0.05–0.64
    across 6). Below the 0.5 gate the ±20° filter still leaves a big pool, so
    DTW runs against loosely-framed clips silently. The phone accelerometer/gyro
    tilt-capture idea (deferred backlog, "camera elevation calibrated on only 2
    references") would also help here.

*Non-issues checked and cleared so nobody re-chases them:* `forehand_0039`-style
ids in a backhand pool (stale id string, `shot_type` field is right);
`practice_*` top matches (all Pro-Clip-Review-verdict'd, filter working);
mid-session mojibake in tip text (the verification harness's cp1252 file write,
not the app — real `/api/analyse` output is clean UTF-8).

---

## New from the 2026-09-05 session (Find Games revamp: mesh clubs, watches, postcodes, club naming)

Full detail: `HANDOVER.md` "Session 2026-09-05". Nothing here is blocked —
it's all built and tested, just needs your eyes on a real device.

1. **Click through the whole Find Games revamp on a real phone** —
   `npx expo start`, Find Games tab. Specifically: tap "Watch an area", drop
   a pin, drag the radius slider, save it, confirm it actually saved (open
   "My Watches" and check the Areas section shows it); open a court and
   confirm its "Notify me" pill already shows "Watching" if you'd
   previously watched it (this was broken before — always started
   unwatched on load, regardless of real state); open a court that's part
   of a club, suggest a name in the new "unverified name" banner, then
   confirm it from a second account; unwatch a court/club/area from the My
   Watches screen and confirm the row disappears.
2. ~~Decide whether to re-run `node scripts/clusterCourts.js`.~~ — **done
   2026-09-07**: run against the local DB (it had never actually been run —
   0 clubs), producing 3,848 clubs. See the 2026-09-07 section at the top,
   item 4. Original note kept below for context. Existing
   `club_watches` should carry over correctly (the new
   `deleteOrphanedClubs()` cleanup + `reconcile()`'s existing court-overlap
   matching both got test coverage for this), but worth eyeballing the
   before/after club list once, not blindly trusting it.
3. **The postcode backfill already ran** against your local dev DB
   (16,711/33,222 courts resolved) — nothing to do here, just noting it so
   a future session doesn't re-run it by accident thinking it's still
   pending. Re-running is safe/idempotent regardless (only touches rows
   where `postcode IS NULL`) if more courts get seeded later and you want
   to top it up.
4. Nothing pushed or deployed — same as every other item below.

---

## New from the 2026-09-04 session (dev-workflow fixes, flywheels, Phase C rejected)

Full detail: `HANDOVER.md` "Session 2026-09-04".

1. **Keep reviewing the practice-footage queue in Pro Clip Review** — 201/333
   done. No change to the workflow itself; two new things happen
   automatically as you go, no separate step: each reviewed entry becomes
   eligible for live matching (previously any unreviewed entry could be
   shown to a real user), and its corrected shot type flows into classifier
   training. Every ~50-100 more reviewed clips, worth asking me to re-run
   `extract_training_features_from_pro_verdicts.py` +
   `evaluate_shot_classifiers.py --set both` to see the phone-accuracy
   number move.
2. **Decide whether to pursue the Phase C contact-frame model further.**
   It failed its ship gate twice this session (see `STATUS.md` item 5) —
   the "predict a correction offset" framing doesn't seem to have signal in
   the current features. Options if you want to keep going: different
   features, a more conservative model, or predicting the frame directly
   instead of an offset. Not urgent — it's not live-consequential either way.
3. **Look at the ball/racket tracker audit images** and decide if
   fine-tuning the ball/racket YOLO detector (flagged since
   `audit_ball_confidence_at_contact.py`, never acted on) is worth doing now
   that there's visual evidence serves are the weak point:
   `data/07_ball_racket_tracking/contact_review/<clip_id>/*.jpg` — start
   with `practice_100126`, `practice_100109`, `practice_100005` (the worst
   misses, over 85 frames off).
4. **Copy `pro_database.json` + `overlay_trajectories.json` to the server**
   — still don't do this yet, see item 4 under the 2026-09-03 section below
   for why (practice review isn't far enough along).
5. Everything else from local dev this session (ngrok, video codec, review
   UI) needed no action from you and is already fixed — see `STATUS.md`
   item 7 if curious.
6. **Decide whether/when to prioritize the architecture-deepening backlog**
   an `/improve-codebase-architecture` review surfaced this session (report:
   `%TEMP%\architecture-review-20260904-233151.html`). Candidate A (the
   highlights.js job-runners) is already done. B (`compare_swing.py`'s
   `compare()` — the single most-modified file in the repo, no seams for its
   8 inline special cases), C (three duplicate contact/swing-peak-detection
   implementations with no shared interface), and D (two small duplications
   in the Pro Clip Review pipeline) are not started — see `HANDOVER.md`'s
   "Architecture review" entry for the full writeup. Not urgent; B is the
   highest-leverage of the three but needs its own design pass before
   touching it.

## New from the 2026-09-03 session (audio-review-all + practice footage)

Full detail: `HANDOVER.md` "Session 2026-09-03". **See "New from the
2026-09-04 session" below for current status — most of this is resolved or
superseded.**

1. ~~Work the Pro Clip Review queue.~~ — in progress, not blocked on
   anything: 354/359 broadcast entries label-reviewed, only 5 left (machine
   audio-fills to eyeball). Practice-footage queue below is the real
   remaining work.
2. ~~Decide on the practice-footage ingest.~~ — resolved 2026-09-03: the
   `--use-claude` run completed (333 entries, 225 forehand/70 serve/38
   backhand, ~$5). Jack chose to keep and manually review rather than
   revert. **201/333 reviewed as of 2026-09-04**, ongoing.
3. ~~yt-dlp~~ — resolved, now 2026.08.19, merges DASH via bundled ffmpeg.
4. **Copy `pro_database.json` + `overlay_trajectories.json` to the server**
   — still open, don't do yet. Wait until the practice review pass is
   further along (currently ~60%) or unreviewed/lower-quality practice
   entries would go live — the match-pool filter added 2026-09-04 protects
   *local* matching from this, but a straight file copy to the server
   bypasses that filter's whole point if done mid-review.
5. ~~Phase C — run the labelling pass + retrain, then copy the model.~~ —
   **done, and rejected.** Ran the full labelling pass (`--audio-only` +
   the new `--practice` sweep, see 2026-09-04 below) and retrained twice.
   **Failed its own ship gate both times** — the corrected model is worse
   than the raw heuristic on every tolerance band. **Do not copy
   `contact_frame_model.pkl` to the server** — it would make contact
   detection worse, not better, if the runtime trust gate ever turned it on
   (it currently can't — 0 of the required 50 real production examples).

## New from the 2026-09-02 evening session (commit + detect_rallies + Phase B.2)

Full detail: `HANDOVER.md` "Session 2026-09-02 (later still)".

1. **Push the 16 local commits.** `master` is 16 commits ahead of `origin`
   (`a694e37..343f4a1`) — the whole session, committed thematically. The
   sandbox blocks `git push` to `master`; Jack runs it. Touches `backend/**`
   and `scripts/**` → will trigger one auto-deploy.
2. **Copy the rebuilt pro-DB data files to the server** (gitignored, CD never
   touches `data/`): `data/06_pro_database/pro_database.json`,
   `overlay_trajectories.json`, and the new `pro_clip_contact_predictions.json`.
   The DB went 796 → 415 entries this session with audio-anchored contact times.
   Without the copy the live server keeps the old 796-entry DB.
3. **~111 flagged pro clips need a quick human contact-mark pass.** The audio
   detector wasn't confident on them (`pro_clip_contact_predictions.json`,
   `confident: false`). They keep their placeholder contact time until marked
   in the Dev tool's "Fix contact time".
4. **Run `detect_rallies.py` on a real match clip with audio** to confirm the
   fix: the serve share in `swings_verified` should drop and `rallies_detected`
   should go above 0 on footage that genuinely has rallies (IMG_5755 was the
   canonical failing case).
5. **Review the uncommitted camera-roll work.**
   `scripts/05_angle_detection/review_camera_roll.py` (new) + a
   `compare_swing.py` `--camera-roll` / `camera_roll_override` change appeared
   in the working tree mid-session (a routine or another Claude session), left
   uncommitted. Coherent follow-up to the committed camera-roll feature —
   review and commit or discard.
6. **Dev task, not manual:** `scripts/15_batch_analysis/analyze_rallies_parallel.py`
   still feeds the verifier the wrist peak — it runs on the audio-less cut
   clips so it can't use audio; needs its own contact fix (e.g. the visual
   student model, Phase C.4).

## New from the 2026-09-02 session (contact detection + shot classifier)

Full technical detail: `HANDOVER.md` "Session 2026-09-02 (later)". Working
plan: `C:\Users\jackp\.claude\plans\okay-where-do-things-woolly-pond.md`.
~~None of this session's code is committed.~~ **Committed 2026-09-02 evening**
(see the block above).

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
   the contact frame**, upload. The analysis response JSON should carry
   `contact_source: "audio_onset"` (added by 1c, 2026-09-08). Anything else
   (`wrist_peak`, `ball_occlusion_gap`, `ball_racket_proximity`, `serve_apex`,
   `audio_visual`) means the audio model didn't confidently fire — check
   `GET /dev/ml-status` → `onset_classifier.model_present` to tell "not
   deployed" from "deployed but not confident on this clip". (The old
   instruction to grep backend logs for `Contact auto-detected via AUDIO
   onset` never worked — stderr-only, discarded on success by
   `runPythonJson.js`.) Confirm the similarity score / pro match look sane.
   This is the one bit of Phase B.1 that couldn't be verified locally (no
   phone-recorded clip with audio on disk).

3. ~~**Decision — run the pro-DB contact-time fill (Phase B.2)?**~~ **DONE
   2026-09-02 evening.** Audio detector ran over the kept clips, 108 confident
   fills applied + re-anchored, 111 flagged for a human pass (see the evening
   block above), DB rebuilt 796 → 415. Validation vs the 196 hand marks:
   confident picks median 13 ms / 96% within 50 ms.

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
move the phone. **2026-09-09:** the behind-baseline view gate is now
ENFORCED — film from the side / from the net / with the net cut off and the
app should hard-stop at ContactMarkingScreen (⛔ "Record another swing") and,
if you get past that, at ResultsScreen ("Check your camera setup"). Verify a
normal behind-baseline swing still sails through. `RALLYMAX_ENFORCE_VIEW_GATE`
no longer needs setting on the server (on by default; `=0` = advisory, batch
eval only).

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
- ~~**Ball-speed feature scoped, not built.**~~ Built 2026-09-02 (v1,
  net-keypoint local scale + speed at the net crossing), then extended
  2026-09-11 (v2) to add a second, ball-size-derivative ("radial") signal
  covering the low camera-angle / dead-centre behind-the-baseline case v1
  silently returned `None` for — see `scripts/07_ball_racket_tracking/
  ball_speed.py`'s module docstring for the full reasoning.
  **Correction to the first sanity-check number below**: the initial
  real-footage pass used `data/01_source_videos/practice/*.mp4`, believed
  to be real practice footage. It isn't — pulled frames and confirmed it's
  downloaded broadcast TV footage (Alcaraz/Medvedev/Federer ATP broadcasts,
  scoreboard overlays and a "COURT LEVEL IS BACK" promo banner sitting over
  the net in one clip), a visual domain the net-keypoint model was never
  trained on (raw model output showed zero detection boxes, not a
  confidence-threshold issue). Re-checked against Jack's own real match
  footage instead (`C:\Users\jackp\Downloads\IMG_5755.MOV`, filmed behind
  the baseline): net detection succeeds on **29/40 (72.5%)** sampled
  frames — a healthy real-world rate. The "2/36 non-null" low-angle number
  below was measured on the mislabelled broadcast set and should be
  disregarded as a reliability signal (it's a domain-mismatch artifact, not
  a real-footage measurement) — a proper low-angle non-null rate on real
  footage hasn't been measured yet.
  **v2.1 (same session)**: added a per-device-model focal-length
  calibration table (`DEVICE_FOCAL_PX_PER_WIDTH`, keyed off
  `com.apple.quicktime.model`, confirmed present on real iPhone videos e.g.
  `IMG_5755.MOV` → "iPhone 13") as a better fallback than
  `ASSUMED_CAMERA_TO_NET_M` alone — still starts empty, still needs a real
  filmed reference per device model to populate (recipe: eye-level, aimed
  straight down the ball's flight path, either a tape-measured distance to a
  known-size object or a labelled ball-machine speed). Jack flagged this
  doesn't scale across many phone models, which is correct.
  **v3 (same session): true self-calibration, no assumption at all.** Added
  `scripts/05_angle_detection/infer_angle.py`'s `sideline_vanishing_point_y`
  and `detect_near_baseline`, combined with the already-detected net (row +
  width) in `ball_speed._solve_camera_geometry` to solve for focal length,
  camera height, pitch, and camera-to-baseline distance simultaneously from
  the court's fixed dimensions alone (`NET_WIDTH_M`, baseline-to-net=11.89m)
  — no per-device table, no assumed distance/height. Now the top-priority
  tier in `_focal_px_for_video`, falling through to the v2.1 device table
  then the v2 assumed-distance approximation when its inputs aren't
  available. Verified against 320 synthetic (focal length, height, pitch,
  distance) combinations — recovers all exactly
  (`test_court_geometry_calibration_pytest.py`).
  **Real-footage findings (`IMG_5755.MOV`, 59 sampled frames)**: the full
  solve succeeded on 18/59 (~30%), bottlenecked almost entirely by near-
  baseline detection recall (lighting/shadow-dependent — the earlier part of
  this match detected 0/33, the later part 18/26, suggesting the baseline
  detector is sensitive to specific lighting conditions worth improving
  later). Where it DID succeed, the recovered values were plausible and
  reasonably stable for a fixed tripod across many different swings: focal
  length 1176-1334px, pitch 1.9-2.5°, camera-to-baseline distance 1.9-2.6m
  (a believable "mounted a couple of metres back from the fence" setup).
  One flag: recovered camera height clustered at 0.63-0.81m — lower than a
  typical eye-level phone-holding height, more consistent with a fence mount
  partway down (plausible for this specific setup, but worth another look
  once a second real device/setup can be checked — no ground truth exists to
  confirm this number is actually correct, same caveat as everything else in
  this feature).
  **Still open across all three tiers: no ground-truth accuracy check.**
  Nothing in v1/v2/v2.1/v3 has been checked against a real known speed —
  the same radar-gun/ball-machine/known-distance reference clip ask from
  v1/v2 would validate all tiers at once, and is now the single most
  valuable next step for this feature.
- **Net-detection domain generalization is unverified beyond Jack's own
  footage.** The `yolo_pose_run_v10` net-keypoint model detects the net
  fine on `IMG_5755.MOV` (72.5%, see above) and fails completely on
  broadcast TV footage (different domain, expected, not user-facing). What's
  untested: real users on different court surfaces/colours (clay, indoor,
  non-standard net colour) and lighting the training set may not have
  covered. Don't assume this generalizes just because one user's footage
  worked. Recommended check: as real user uploads accumulate, periodically
  sample a few and measure net-detection rate the same way this session did
  for `IMG_5755.MOV`, rather than waiting for a support complaint. Candidate
  for the v10→v11 retrain already flagged in `infer_angle.py`'s comments if
  a real pattern of failures shows up on genuine user footage.
- **Ball-detector adequacy for the radial ball-speed signal, measured** (not
  guessed): new `scripts/07_ball_racket_tracking/
  eval_ball_speed_diameter_availability.py`, run against `IMG_5755.MOV` /
  `IMG_5756.MOV` (40 arbitrary in-play windows each, not swing-contacts
  specifically — a general-play proxy). Result: **the binding constraint is
  RECALL (window density), not box precision** — the opposite of this
  session's working assumption. Only 50-62% of `±DIAMETER_HALF_WINDOW`
  (±4 frame) windows had the >=2 confident detections a linear diameter fit
  needs (48-58% for the default quadratic fit); when a window DOES have
  enough confident detections, their frame-to-frame box-size jitter is
  small (median 1-2% of diameter), with a real but secondary tail of bad
  jumps (p90 ~9-11%, max up to ~50% — likely occlusion/motion-blur
  misdetections). Read: the ball detector's box-fit quality is fine when it
  fires; it doesn't fire densely enough near-simultaneously across a short
  window often enough. This points at recall/coverage (matches the known
  far-ball/occlusion weak spots) as the more valuable ball-detector
  improvement target for this feature specifically, not IoU/box-regression
  precision as originally guessed. Re-run this eval after any future ball-
  detector retrain to check whether it actually moved this number.
- **Local dev password reset**: `jack.p14370@gmail.com` on local
  (port 8090) was reset directly in `backend/data/app.db` to a password
  given in chat, not recorded here. `RESEND_API_KEY` still isn't
  configured locally, so the real email flow won't work on local dev
  until Resend is set up (account/API key/sender domain — same shape as
  the RevenueCat setup above, not detailed further here since it's a
  standard 3rd-party dashboard flow).

---

## New from the 2026-08-20 session

**Decide on IMG_5755.MOV Claude verification spend.** Free dry-run (no
API cost) found **290 raw swing candidates** across its 33 minutes. At
IMG_5822's real measured rate (~$0.0093/call on Haiku), fully verifying
it would run **~$2.70**. Not run yet — waiting on your go-ahead. Run it
with `detect_rallies.py` once you're ready (same command pattern as the
IMG_5822 run).

~~**39 more unprocessed clips sitting in Downloads.**~~ — fully run
2026-08-20 (both the free dry-run and real Claude verification).
`IMG_5757`–`5774` (17 files, `5768` doesn't exist), `IMG_5795`–`5815`
(21 files), `finesse shot.mov`, `game-winnder-stable.mov` — 39 files,
**149 raw swing candidates** over 11.9 minutes of footage. Ran full
verification (`detect_rallies.py`) on all of them — result: **0 real
swings confirmed, 0 rallies, across every single clip**, and **actual
spend was $0.00**, not the ~$1.39 estimated: every candidate's
contact-evidence type (`no_evidence` — no racket/ball detected near the
wrist-velocity peak) has earned enough trust from past real Claude
verdicts (96% historical agreement, 840 logged examples) that the
student model now handles that bucket alone, no Claude call needed. Two
of these clips (`finesse shot.mov`, `game-winnder-stable.mov`) also had
unusually poor pose-detection rates (25%/49% vs. 82-100% on the rest),
consistent with this being casual/poorly-framed footage rather than
deliberately-shot analysis video. Net result: **nothing usable came out
of this batch** — no swing clips, no new training data. Not worth
re-running as-is; if any of this footage matters to you, it'd need
better framing/distance to give the ball/racket detector something to
work with.

`IMG_5823.MOV` dry-run separately: **6 raw candidates** over 40.5s, not
yet Claude-verified (`IMG_5842`/`5843.MOV` confirmed not tennis footage,
skipped).

**GitHub repo created.** `https://github.com/JP14939/tennis-app` —
currently **public** (flipped from private at your request 2026-08-20,
for sharing purposes). `data/` and `.env` are correctly gitignored and
never went up. If this was meant to be temporary, flip it back to
private when you're done sharing it (`gh repo edit JP14939/tennis-app
--visibility private`).

---

## ~~Urgent: hosted backend needs a redeploy~~ — resolved 2026-08-21

Root cause of Ball Label / Pro Clip Review / Tip Review all showing
"couldn't load candidates": the Hetzner box (`rallymax-vps`,
`167.233.107.31`) had never been redeployed since these features were
built — **and it turned out `/opt/tennis_app` on the server wasn't
even a git repo** (it was set up via a one-time file copy, not
`git clone`), so `git pull` couldn't have worked there from day one.
Also hit real SSH trouble along the way, all fixed now — worth knowing
for next time:

- **SSH password login was denied even with a freshly-reset root
  password.** Cause: Hetzner's Ubuntu image ships with
  `PermitRootLogin prohibit-password` by default in `/etc/ssh/sshd_config`
  (only SSH keys allowed for root, not passwords) — fixed via Hetzner's
  browser Console (Server page → the `>_` icon), editing that file and
  `PasswordAuthentication` to `yes`, then `systemctl restart ssh`.
- **There's already a working keypair for this server**:
  `~/.ssh/rallymax_key` / `rallymax_key.pub` on this machine — it was
  already authorized on the server the whole time (`ssh -i
  ~/.ssh/rallymax_key root@167.233.107.31` just works, no password
  needed). Use this for any future SSH/scp to the box instead of
  fighting the password flow again.
- **Converted `/opt/tennis_app` into a real git repo** in place
  (`git init` + `git remote add origin ...` + `git fetch` + `git reset
  origin/master` + `git checkout -- .` — none of which touch
  already-untracked files like `data/`/`.env`, so nothing was at risk),
  then `docker compose up --build app` to rebuild and restart with
  current code. One harmless untracked leftover file was found and can
  be deleted whenever (`backend/src/routes/db.js` — not a real part of
  the app, nothing requires it).
- **Ball detector data (`data/10b_ball_detection/`, 151MB) and the
  net-detection model weight (`data/10_net_detection/yolo_pose_run_v4/
  weights/best.pt`, 5.4MB) were both missing on the server** — `rsync`
  isn't installed in this environment, so both were sent via `tar` +
  `scp` instead (using the `rallymax_key` above) and extracted directly
  into place, then `docker compose restart app`. Confirmed after: all
  three Dev Page tools return real data, `reset-password.html` serves,
  and `calibration_server` (the live camera-calibration subprocess,
  previously crash-looping on the missing model weight) now logs
  `models loaded, listening on 127.0.0.1:5055` cleanly.

**Going forward**: any time real backend/scripts changes get pushed,
they need a manual `git pull` + `docker compose up --build app` on the
server to actually go live — this isn't automatic yet (no CI/CD). If
`data/` gains new files too (like the ball detector project did), those
need a manual copy over as well, same as above.

---

## New: finish wiring up self-serve password reset (2026-08-20)

Built the whole flow (backend endpoints, DB table, a standalone
`reset-password.html` page the backend serves directly, and a new
"Forgot password?" screen in the app that replaces the old
email-support alert) — tested end-to-end against the dev DB with a
manually-seeded token (request → reset → login with new password →
reused token correctly rejected). **The only thing missing is a real
email-sending account**, same shape as the RevenueCat setup below:

1. **Create a Resend account** (resend.com, free tier: 3,000 emails/month).
2. **Grab an API key** from the dashboard → `backend/.env` as `RESEND_API_KEY`.
3. **Decide on the sender domain**: the shared sandbox sender
   (`onboarding@resend.dev`, already the default in `.env.example`) only
   lets you send to *your own* verified email — fine for your own
   testing, useless for real users. To send to anyone, you need to
   verify a real domain in Resend's dashboard (DNS records) and set
   `RESEND_FROM_EMAIL` to an address on it, e.g.
   `RallyMax <noreply@rallymax.app>`. **Open question I can't answer for
   you**: does `rallymax.app` actually exist/is it yours? The old
   "email support@rallymax.app" alert text assumed so, but that was
   never confirmed this session.
4. **Set `PUBLIC_BASE_URL`** in `backend/.env` to wherever the backend
   is actually reachable (already `https://rallymax.167-233-107-31.sslip.io`
   in `.env.example`) — this is what the reset link in the email points at.
5. **Restart the backend** so it picks up the new env values.
6. **Real test**: tap "Forgot password?" in the app, check the inbox
   for the linked email, click through to `reset-password.html`, set a
   new password, confirm you can log in with it.

**Also note**: while testing this, I reset the dev account
`direct@example.com`'s password to `brandnewpass123` to verify the full
flow end-to-end (login-with-new-password confirmed working) — change it
if that account matters to you.

---

## New from the 2026-08-20 evening session

**Premium folded into Home + Lessons, per your friend's feedback.**
Removed the standalone Premium tab (was 6 tabs on the bottom bar, now 5);
its 2 feature cards (1v1 Comparison, Highlight Archive) now render
directly on Home with a lock badge, and Lessons already had a lock badge
but used an old confirm-alert flow — both now go **straight to checkout**
on tap, no confirm step, matching "press on them and premium payment
appears" literally. `PremiumScreen` itself is trimmed to just the
checkout widget. Bottom tab bar is also now responsive below ~375px
width (smaller margins/icons/labels) so it doesn't read as compressed on
a small phone like an iPhone SE. Removed the "Premium" section heading
that sat above the Home feature cards per your last note. Not yet
click-tested on a real device from this side — worth a quick pass next
time you're on your phone.

**Ball detector Phase 1/2 complete** — see item 3 in the pipeline
backlog below for the full writeup. Short version: 124 frames
auto-labeled, 230 sitting in the new Ball Label Dev Page tool waiting on
your manual review time.

**Everything committed and pushed** — nothing outstanding in git as of
2026-08-21 (`https://github.com/JP14939/tennis-app`, `master` branch;
check `git log` for the latest hash rather than trusting a specific one
written here, since this file itself gets committed after code changes
and would otherwise always be one commit behind).

~~**Still open, not done this session**: the 5 mismatched pro clips,
the 39-clip dry-run.~~ — both done later the same session, see the
resolved entries above/below this one. Left struck rather than deleted
so it's clear this was chased down, not forgotten.

---

## Pipeline improvement backlog (from 2026-08-19 architecture review)

Context: walked through every stage of the ML pipeline end to end and
talked through what's weak/worth investing in. Nothing here is urgent —
captured so it doesn't get lost. Roughly ranked by impact; each note names
whether it's a normal follow-up build (I can just do it) or needs your
call first.

1. ~~**Shot classifier is rule-based only and doesn't learn from labeled
   data.**~~ — built 2026-08-19. Trained a logistic-regression model on
   rich pose-derived features (not just the 3 final scores) extracted from
   the 116 real-shot-labeled amateur clips. Real, honestly-reported
   cross-validation result: **63.8% accuracy vs. the rule-based
   classifier's 50%** — backhand recall jumped from 1/10 correct to 6/10
   (precision on backhand is still weak, 0.30, so it now over-predicts
   backhand somewhat). Wired in as a SEPARATE candidate student
   (`classify_shot.classify_ml()`) with its own trust gate
   (`shot_classifier_ml_training_log.py`, same 50-example/90%-agreement
   bar as the rule-based one) — it only starts being used standalone once
   it proves out against real Claude verdicts, exactly like every other
   teacher-student loop in this app. Claude stays the teacher for now (no
   Dev Page manual-review tool built yet); added real cost tracking so you
   can watch the actual $ spent building toward that threshold at
   `/api/dev/ml-status` → `shot_classifier_ml.verifier_cost` (note: this
   rides along on Claude calls already happening today, not new spend).
   Also extended both training logs to capture `clip_path`/`contact_frame`
   going forward, so future labels — automatic and manual — can be
   re-extracted into richer features later instead of staying stuck at 3
   numbers per example. 8 new tests for the feature extractor; full
   41-test suite across the affected directories passes.
2. ~~**Fix `list_swing_candidates.py`'s classify() bug.**~~ — resolved
   2026-08-19. It was passing pose data to `classify()` in the wrong shape
   (a list instead of the dict-keyed-by-joint-name shape `classify()`
   needs), so `student_shot_type` had been silently `None` on every Swing
   Review candidate ever served. Fixed with the same reshape helper
   (`_as_classify_frames`) `detect_rallies.py` already used for this;
   verified against real cached data (job 7: 0/26 candidates `None` now,
   was 26/26 before). Training data logged from today onward is trustworthy
   for item 1; anything logged before today's fix still has a real
   `None` student prediction paired against it.
3. **Ball detector is generic/unfine-tuned**, known-unreliable exactly at
   the contact frame (the moment that matters most) — audited this
   session: 50% detection rate / 0.41 avg confidence on 60 real user
   swings vs. the pro database's own 69%/0.664. **Re-audited 2026-08-25
   against 81 real clips (more now exist than at the original 60-clip
   run): 53.1%/0.40 — essentially unchanged, confirms nothing has
   organically improved and Phase 3 fine-tuning is still the real fix.**
   Scoped and Phase 1/2 built 2026-08-20:
   - **Phase 1 (data sourcing)** done —
     `scripts/07_ball_racket_tracking/sample_ball_frames.py` sourced 360
     candidate frames (180 near-contact, 120 mid-flight from real saved
     analyses, 60 negatives reused from real Claude-verified "not a real
     shot" timestamps).
   - **Phase 2 (labeling)** done, after a real methodology failure and
     pivot: asking Claude to freeform-locate the ball's pixel bbox failed
     3 times running (confidently wrong boxes landing in background
     foliage, verified by drawing the boxes back onto the images).
     Replaced with a classical HSV-color + contour pipeline
     (`find_ball_candidates.py`) that proposes candidates, then Claude
     just confirms/rejects a tight crop around the top one
     (`ball_presence_verifier.py`) — much easier binary question, 9/9
     correct on the frames that broke the freeform approach.
     `label_ball_frames.py` ran the full 360-frame batch: **124
     confirmed, 230 need manual review, 6 transient errors**, total cost
     **$0.38**. Frames with no confident candidate get flagged
     `needs_manual_review` rather than force-labeled.
   - **Manual-review fallback built**: new **Ball Label** Dev Page tool
     (Dev Page → Ball Label (free, manual)) — draw a box yourself on any
     of the 230 `needs_manual_review` frames (first draw-a-box UI in the
     app, `DevBallLabelScreen.js`). **This is now on you**: work through
     those 230 whenever you have time; no further action needed from me
     until you want to move on to actually training the model on the
     combined labeled set.
   - **Update (2026-08-25): you finished the manual-review backlog (354
     labels logged), but a real methodology gap surfaced along the way** —
     for a frame where the actual in-play ball wasn't visible, some labels
     boxed a static decoy ball instead of leaving the frame unlabeled,
     logged identically to a real label (no field existed to distinguish
     the two). Fixed going forward: `DevBallLabelScreen.js` now has a "Not
     the ball in play" toggle, logged as `is_live_ball` by
     `log_manual_ball_label.py`. For the labels already logged: new
     `scripts/07_ball_racket_tracking/audit_ball_label_motion.py` applies
     your own rule ("if it isn't moving, it's not the ball being played")
     as a real check across all 354 — **flagged 5 clips / 16 labels as
     fully static throughout their sequence**: `analysis534`, `analysis501`,
     `analysis532`, `analysis519`, `analysis522`. **This is now on you**:
     for each, confirm whether it was really a decoy (exclude those labels)
     or a legitimately slow/soft shot (keep it) before Phase 3 training
     starts — the audit script's own output is the review list, no
     separate tool needed.
   - **New (2026-08-25): a shared ball tracker was built independent of
     fine-tuning** — `scripts/07_ball_racket_tracking/ball_tracker.py`, a
     constant-velocity Kalman filter replacing plain linear gap-
     interpolation in `_interpolated_ball_track()`. Predicts through short
     gaps and rejects a detection that doesn't fit the ball's established
     motion, rather than trusting every raw YOLO detection. No action
     needed from you — this is complementary to fine-tuning, not a
     substitute; better raw detections later just make it converge faster.
4. ~~**Camera angle has no fallback when the net isn't visible at all.**~~ —
   built 2026-08-20. When the record-time filming-position picker says
   `'front'` (camera at the net — net detection is predictably useless
   there, it's right at/behind the camera) or net detection organically
   fails on every sampled frame, `infer_camera_angle()` now falls back to
   a new court-sideline detector (`detect_court_sidelines()` +
   `angle_from_sideline_symmetry()` in `infer_angle.py`) — Hough-detects
   the two court sidelines and estimates angle from how asymmetrically
   they converge, instead of returning nothing. Confidence is capped well
   below `check_camera_setup.py`'s `MIN_CONFIDENCE` (0.5) so it always
   reads as "uncertain," never a false "ok." Verified the geometry math
   itself on synthetic test images (symmetric lines → 0°, asymmetric →
   nonzero), and confirmed the existing net-based path is byte-for-byte
   unchanged on a sample of real pro clips. **Not yet validated against
   real "recorded from the net" footage** — same shape of gap as item 5's
   elevation calibration below (no known-good reference clips yet). Worth
   a real spot-check once such footage exists — the IMG_57xx batch sitting
   in Downloads, once processed, may include some.
5. **Camera elevation is calibrated on only 2 known-elevated reference
   videos.** Much cheaper, more reliable fix: capture the phone's
   accelerometer/gyroscope tilt at record time instead of inferring it
   from the video — near-free, solves elevation outright rather than
   patching the vision-only approach further.
6. ~~**Coaching tip selection has no manual QA tool.**~~ — built
   2026-08-19. **Tip Review** Dev Page tool (`DevTipReviewScreen.js`):
   your swing next to the matched pro, which tip got surfaced and why
   (full re-derived scored-issue list, not just the final pick),
   agree/disagree — extends `tip_training_log.py`'s loop the same free
   way Swing Review does for shot verification. Also fixed a real bug
   found while building it: the video wasn't wired to play at all (no
   ref/trigger on `PlatformVideo`).
7. ~~**Tip severity is computed but never shown to users.**~~ — shipped
   2026-08-20. `compare_swing.py` now carries `severity` through on each
   tip; `TipsSection.js` shows a mild/moderate/severe pill next to the fix
   text (same component both `ResultsScreen.js` and
   `VersusResultsScreen.js` already share, so both got it for free).
8. **z-depth is disabled in the DTW trajectory comparison**
   (`Z_WEIGHT = 0.0` in `trajectory_compare.py`) — a real signal sitting
   unused. A past attempt to enable it tanked similarity scores 45-75% on
   test clips because MediaPipe's z is on a much wider numeric scale than
   x/y and dominated the distance metric. Re-enabling needs z rescaled by
   its own measured spread (not reused off the x/y shoulder-width divisor)
   and re-validated against real saved swings — not just a smaller
   constant.
9. **True 3D pose extraction** — bigger, later idea, once there's budget
   for it (your framing, not mine). Worth knowing going in: MediaPipe's z
   is a rough monocular guess, not a measurement — a real upgrade means
   multi-camera triangulation or a depth-aware model, a bigger jump than
   swapping a library call.
10. **No fault/ball-landing/in-or-out detection anywhere** — caps how far
    serve-gating and any future point-by-point scoring can go. A bigger,
    separate project if real point tracking is ever wanted.
11. **Single-player tracking only** — no opponent/dual-player awareness
    anywhere in the pipeline. Relevant if "which side served" or doubles
    support is ever wanted (came up directly in this session's serve-gate
    work — deliberately scoped out of it).
12. **More coaching tip content** — expanding
    `data/08_coaching_ai/coaching_tips_database.json` per shot type/phase
    is pure content work, no architecture change, always helps coverage.
13. **Pose sampling is sparse (`sample_every=3`) on both the pro database
    and user uploads.** Found 2026-08-19 while chasing why the skeleton
    overlay visibly lags/cuts corners on fast swings. First fix attempt
    (a 4-point Catmull-Rom curve) didn't actually help — the real bug,
    found 2026-08-20 by checking a real trajectory directly, was that a
    joint (`right_wrist`, heavily concentrated right around/after contact
    — motion blur) was `null` in the immediately-adjacent sample far more
    often than expected, and the old code drew *nothing* for a joint
    whenever either bracketing sample was null, instead of bridging the
    gap. Real fix shipped: `SkeletonOverlay.js` now searches outward past
    null gaps for the nearest valid sample on each side (per joint) before
    interpolating, so a joint stays drawn continuously through a
    motion-blur gap instead of vanishing and snapping back — pure
    rendering fix, no pipeline change. The deeper issue: `extract_poses.py`
    and `compare_swing.py`'s `extract_user_poses()` only sample real pose
    landmarks every 3rd native frame, and that same sparse trajectory feeds
    DTW distance, contact-frame timing, and coaching-tip deviation features
    — not just the overlay. Increasing density (`sample_every` 3→1) would
    plausibly improve real comparison accuracy, not just smoothness, since
    the closest-available sample to a fast moment like contact can currently
    be off by up to ~1/3 of a frame interval. Not done yet because it's a
    real pipeline change, not a display tweak: needs re-extracting the pro
    database (~1281 clips, ~60-90 min background job), keeping
    `compare_swing.py`'s user-side rate matched to stay DTW-comparable, and
    re-running `scripts/17_amateur_eval/evaluate_amateur_dataset.py`'s eval
    set afterward to confirm match quality actually improved rather than
    just changed. Worth doing once there's a reason to prioritize it.
14. **Pro database needs a manual clip-quality review pass.** Direct
    report 2026-08-20: a real number of the ~914 pro-database clips have
    data-quality problems beyond the already-tracked high-camera-angle
    entries above — mismatched footage, some are slow-motion, and some
    span the tail end of one swing/player's motion butted against the
    start of a different one. Now has a Dev Page tool for it: **Pro Clip
    Review** (Dev Page → Pro Clip Review), same free one-at-a-time pattern
    as Swing Review/Tip Review — watch each clip, tag it ok / mismatched /
    slow-motion / spans two swings. Verdicts log to
    `data/06_pro_database/clip_review_log.jsonl`
    (`scripts/06_database_build/clip_review_log.py`); once enough clips
    are reviewed, a one-off script (same shape as
    `filter_by_ball_visibility.py`) can rebuild `pro_database.json`
    excluding the flagged entries — not built yet, just enabled by this
    log's shape. Longer-term idea, not scoped: once the shot-classifier/
    rally-detection pipeline built this session is trusted enough, it
    could reprocess the pro database's *source* footage the same way user
    footage gets auto-clipped, fixing bad swing boundaries at the root
    instead of one-by-one manual curation.

---

## Backend architecture backlog (from code review, 2026-08-22)

Context: a two-axis diff review plus a follow-up database/route audit
found a batch of real bugs, all fixed the same session (see git log
around this date — double-response server crashes on spawn failure,
an unauthenticated resource-exhaustion endpoint, a free-tier cap
bypass, four orphaned-row bugs, six missing indexes, and a few
authorization/validation holes). Fixing each site closed the specific
bugs, but a few of them are symptoms of a broader pattern worth a
deliberate pass rather than only patching every site the pattern was
found at. Ranked by impact; each note names whether it's a normal
follow-up build (I can just do it) or needs your call first.

1. **No enforced convention for `optionalAuth` vs `requireAuth` per
   route.** This is what caused the `/analyse` free-tier-cap bypass
   fixed this session — the route was optionally-authed for a reason
   that made sense once, and nobody revisited it as the product grew.
   Ranked highest because it's the one most likely to produce the next
   silent security bug rather than an obvious crash. I can just do
   it: either a lint rule or a small route-manifest module that
   asserts each route's intended auth level, checked at startup or in
   CI.
2. **SQLite foreign keys are never enforced** (`PRAGMA foreign_keys`
   is off in `db.js`) — every `REFERENCES` across the 31-table schema
   is decorative. This is the root cause behind three separate
   orphaned-row bugs fixed this session (deleted analyses, deleted
   accounts, deleted drill steps all left dangling child rows). Each
   known site is now fixed individually, but the pattern means the
   *next* new delete route will likely repeat it unless someone
   remembers to check. Turning the pragma on for real would need a
   real audit of every existing DELETE against every table it could
   orphan (some deletes are intentionally partial, e.g. account
   deletion anonymizes rather than deletes rows other users still
   reference) — needs your call before attempting, since getting it
   wrong could break account deletion or history deletion outright.
3. ~~**No CI/CD.**~~ — resolved 2026-08-25. `.github/workflows/deploy.yml`
   now auto-redeploys on push to `master` (code paths only, docs-only
   commits are excluded), via a dedicated forced-command-restricted SSH
   key rather than the personal `rallymax_key`. See `HANDOVER.md` item
   #44 and `DEPLOY.md`'s new "Continuous deployment" section for the
   full setup and what's still manual (`data/` transfers, `.env` edits).
4. **SQLite is still standing in for the Postgres `DATABASE_URL`
   already implies.** `pg` has been an installed-but-unused dependency
   for a while, and this migration has been scoped as "later" for
   several sessions without resurfacing. Not urgent — flagged here so
   it doesn't quietly become permanent by default. Needs your call on
   timing.
5. ~~**The Python-subprocess boundary had no shared abstraction.**~~ —
   fixed 2026-08-22. 12 routes had each hand-rolled their own
   `spawn` + stdout/stderr collection + timeout + JSON-parse block,
   which is why the double-response-on-spawn-failure crash bug existed
   in 12 places simultaneously instead of being one isolated mistake.
   Now centralized in `backend/src/utils/runPythonJson.js`, which every
   spawn site was migrated to use.

---

## Frontend: expo-av must be migrated before the SDK 55 upgrade (2026-08-22)

The frontend is pinned to **Expo SDK 54** (`expo@54.0.36`), and as of
2026-08-22 every Expo-managed dependency matches SDK 54's own version
map exactly. Don't let that drift.

The one live time-bomb: **`expo-av` is deprecated in SDK 54 and is
removed outright in SDK 55.** We deliberately kept it — it works fine on
54, and migrating is a real behavioural change to video playback with no
frontend tests to catch regressions. But the SDK 55 bump cannot happen
until this is done. Two call sites, and note they need *two different*
replacement packages:

- `frontend/components/PlatformVideo.native.js` — uses `Video` +
  `ResizeMode`, migrates to **`expo-video`**. Careful: this file exposes
  a hand-written ref interface (`playAsync`/`pauseAsync`/
  `setPositionAsync`/`setRateAsync`) that `PlatformVideo.web.js`
  deliberately mirrors, and `SyncCompareScreen` drives both through it.
  The migration must preserve that shared interface or update both
  platform files together.
- `frontend/utils/sounds.js` — uses `Audio`, migrates to
  **`expo-audio`**, which is **not currently installed** and will need
  adding.

`expo-video` *was* installed (unused, imported nowhere) and was removed
on 2026-08-22 along with its stale `app.json` plugin entry, so the
manifest reflects what the app actually uses. It'll need re-adding as
part of the real migration.

Native-build note: because the app uses `expo-dev-client`, dependency
changes like this only reach the native side on the next
`eas build`/prebuild — the existing dev client still contains the old
module set until then.

---

## ~~Connect GitHub to enable the 5 scheduled daily routines~~ (2026-08-22) — resolved 2026-08-23

GitHub got connected and all 5 routines ran for the first time overnight
2026-08-23, exactly as designed below: logic review, bug sweep, and
security review each opened a PR (`logic-review/2026-08-23`,
`bug-sweep/2026-08-23`, `security-review/2026-08-23`); brainstorm/future-plans
opened `future-ideas/2026-08-23` with `docs/future-ideas.md`; the docs
round-up pushed straight to master as designed. All three code PRs were
reviewed and manually merged into master the same day (see the new section
below) — the routines still don't merge their own work, a human did it.
Leaving the original design writeup below for reference on what each
routine does and when it fires.

Once connected, the five routines (all `claude-sonnet-5`, `environment_id:
env_01DBvdQgWmCeNBRoUWiCz3Jz`, repo `https://github.com/JP14939/tennis-app`)
are ready to create as-designed:

| # | Time (London / UTC, currently BST) | Routine | Output |
| --- | --- | --- | --- |
| 1 | 04:00 / 03:00 | Logic review (correctness vs. intent, boundary errors, invariant violations, drifted duplicate logic) | branch `logic-review/YYYY-MM-DD` + PR |
| 2 | 04:15 / 03:15 | Bug / critical-error / edge-case sweep | branch `bug-sweep/YYYY-MM-DD` + PR |
| 3 | 04:30 / 03:30 | Security review (`/security-review` skill if available in that environment, else a direct checklist) | branch `security-review/YYYY-MM-DD` + PR. **Critical findings (client-data loss, large financial loss) open a `🚨 CRITICAL:`-titled PR immediately on discovery, not batched at end-of-run**, so GitHub's own email notification is the fastest available signal — no WhatsApp/Slack channel is wired up yet (none currently connected; user said they'll connect WhatsApp themselves later) |
| 4 | 04:45 / 03:45 | Brainstorm / future-plans ideation, reading `HANDOVER.md`/`TODO_MANUAL.md` first | `docs/future-ideas.md` (new/dated section) + PR |
| 5 | 05:00 / 04:00 | Round up that day's PRs/branches (`gh pr list`, falling back to `git branch -r` filtered by today's date) and update `HANDOVER.md`/`TODO_MANUAL.md` | commits + **pushes straight to master** — docs only, never application code; the other four routines' PRs still wait for a human merge |

Explicitly decided against: the routines merging each other's PRs
automatically (kept human-in-the-loop on all application-code changes),
and the security routine autonomously shutting down the production
server on a critical finding (no SSH/infra credentials available to the
cloud sandbox anyway, and an AI's own severity judgment triggering an
unsupervised outage was judged worse than the risk it'd be guarding
against).

**Caveat:** the cron expressions above are fixed UTC, so the actual
London local time will drift by an hour whenever BST/GMT changes
(next: late October 2026) unless the cron expressions are updated then.

Also worth knowing before flipping this on: these are real
`claude-sonnet-5` cloud sessions billed against the same usage limits as
interactive Claude Code sessions — five real agentic runs every day,
three of which may also run tests and open PRs. Moving them to 4am only
avoids competing with daytime interactive usage; it doesn't reduce total
consumption. User confirmed proceeding with all 5 daily despite this.

---

## 85 old History rows have no watchable video on the hosted server (2026-08-22)

Not a bug to fix in code — a scoped data gap, found while investigating a
"video unavailable" report and confirmed directly via SSH.

Pro clips are fine: `data/04_clips` has all 1282 real files on the host and
serve correctly (verified: a real pro-clip URL returns 200). The problem is
narrower — 85 of this account's 86 saved analyses all date to
**2026-08-14**, matching the "batch-analyzed 2 full match videos into 85
History rows" work documented in `HANDOVER.md`. That batch was run
**locally** against the dev backend, not through the live server, so the
resulting `user_clip_url`s (e.g. `/user-clips/8_147_3/original.mp4`) point
at files that were never copied to the host — confirmed: that exact URL
404s, and `backend/data/runtime/user_clips` is empty on the host.

**A brand-new upload made through the live app today would work fine** —
it's created directly on the host, so its video exists where the app looks
for it. This only affects the 85 old rows from that specific local batch
run.

**If those old entries need to be watchable too**, the fix is a one-time
`scp`/`tar` copy of the relevant local `data/runtime/user_clips/8_*` dirs
to `/opt/tennis_app/data/runtime/user_clips/` on the host (same mechanism
as the "data/ needs manual copy" note in the deployment gotcha section) —
not done here since no explicit decision was made to spend that effort on
recovering old test data specifically.

---

## End-of-session handoff (2026-08-22) — see `HANDOVER.md` item #42 for the full story

- ~~**Uncommitted work needs a decision.**~~ — resolved 2026-08-23. Committed
  (418 backend tests, `verify:db` clean) and merged to master the same day
  as the scheduled-routine PR merges below.
- **The Playwright MCP server was added but needs a fresh session to
  actually use** — `claude mcp add playwright -- npx -y @playwright/mcp@latest`
  ran successfully and shows Connected, but MCP tools registered mid-session
  don't surface until reconnect. It verifies `react-native-web` (the web
  build) only, not native iOS/Android — the bugs found this session were
  all native-only and invisible on web, so it's a complement to real-device
  testing, not a replacement for it.
- **Confirm the three fixes on your actual phone if you haven't already**:
  avatar should be circular (was square), the Home CTA card should have
  its green background back, and Find Games should show real courts
  (a live SQL bug — deployed and confirmed working from this side, but
  worth your own eyes on it too).
- **85 old History rows' videos** — see the section directly above. No
  action needed unless you want those specific old entries watchable.

---

## Set up off-box database backups (2026-08-23)

Found while reviewing hosting status: `backend/data/app.db` — every user
account, analysis, friend link, message, everything — has **no backup at
all**. It's a single SQLite file on the Hetzner VPS with no redundancy; if
that disk/VM were lost, it's gone with no recovery path. (The backup
snapshots already documented elsewhere in this doc/`HANDOVER.md` are all for
the separate ML pro-database, `pro_database.json` — not this file.)

Chose the smallest fix over a full Postgres/Supabase/Neon migration for now:
keep SQLite, make it durable. `backend/scripts/backupDatabase.js` is written
and tested (uses SQLite's Online Backup API via `better-sqlite3`'s
`.backup()` — safe against the live WAL-mode DB, no need to stop the
server; run it directly with `npm run backup:db`). It snapshots to
`backend/data/backups/app-<timestamp>.db` and prunes anything beyond the
last 14. That alone only protects against *this file* getting corrupted —
it still lives on the same disk, so it doesn't protect against losing the
VPS itself. Getting a copy off that box needs three things only you can do:

1. **Create a free Backblaze B2 account** (backblaze.com/b2) and a bucket
   (e.g. `rallymax-db-backups` — 10GB free tier comfortably covers this,
   the DB is currently ~9MB and backups are incremental in size only in
   the sense that old ones get pruned, not that each one is small forever).
   Generate an application key (Account → App Keys → Add a New Application
   Key), scoped to just that bucket if you want to be tight about it.
2. **Install and configure `rclone` on the VPS**:
   ```
   ssh -i ~/.ssh/rallymax_key root@167.233.107.31
   curl https://rclone.org/install.sh | sudo bash
   rclone config    # create a remote named b2remote, type "b2", paste the
                     # key id / application key from step 1
   ```
3. **Add the cron job** (`crontab -e` on the VPS):
   ```
   0 3 * * * cd /opt/tennis_app && docker compose exec -T app node backend/scripts/backupDatabase.js && rclone copy backend/data/backups b2remote:rallymax-db-backups --min-age 1m
   ```
   (3am matches the same "avoid daytime usage" reasoning as the scheduled
   routines' cron times elsewhere in this doc.)

Once set up, the real verification is checking the B2 bucket the morning
after the first 3am run and confirming a new file landed. Considered and
rejected Supabase for the actual DB engine itself (not just backups) — its
free tier auto-pauses a project after 7 days of no traffic and has zero
backups on that tier; self-hosted Postgres on this same VPS or Neon were
the stronger picks if a full engine migration is ever revisited, but that's
a separate, bigger decision deliberately deferred here. **Still needs your
three manual steps (Backblaze account, `rclone` on the VPS, the cron job)
— not done as part of the 2026-08-23 PR-merge session below, which was
code-only.**

---

## ~~New from the 2026-08-23 docs round-up~~ — resolved 2026-08-23, same day

**~~Review and merge (or request changes on) PR #1, "Bug sweep."~~** All
three code PRs from that morning's scheduled routines — bug sweep, security
review, and logic review — were read through, reviewed, and manually merged
into master later the same day (plus the older 2026-08-22 uncommitted work
above, committed at the same time). See `HANDOVER.md`'s "Scheduled-routine
PR round-up" section for the full list of what each fixed, and the new
"Manual merge of 2026-08-23 PRs + prior uncommitted work" section below for
how the merge itself went (two real conflicts, resolved by hand, both
verified against the full test suite).

**Deliberately left unfixed by the bug-sweep PR — still your call, still
open:**
- An invite-code redemption TOCTOU race (very low probability — ~10¹²
  collision space) — decide if it's worth closing or fine to leave.
- A non-transactional bulk Overpass court-upsert — same "is this worth
  the risk of touching blind" call.
- `runPythonJson`'s subprocess timeout not escalating to `SIGKILL` — a
  hung Python process may currently outlive its timeout.
- **Product-intent question**: what should an empty `rallyIds: []` mean
  when building a highlight reel — is that a no-op, an error, or "use
  every rally"? The route currently has ambiguous behavior here and the
  PR didn't guess at an answer.

**New from the logic-review PR, worth knowing about**: the coaching-tip
Claude verifier (`scripts/09_coaching_ai/select_coaching_tips.py`) had been
silently live on every real `/api/analyse`/`/api/compare-videos` request
(up to 3 synchronous Anthropic calls per request, no kill switch) —
contradicting `CLAUDE.md`'s description of that module as unused. Now
disabled on both live call sites. Worth deciding on purpose whether this
should ever go live again (with a real kill switch/cost budget) or stay
offline-only as the docs currently describe it.

**`docs/future-ideas.md`** (from the brainstorm routine's
`future-ideas/2026-08-23` PR) has not been merged yet as of this note —
docs-only, no urgency, still open on GitHub. A convenience copy of that
pass's ideas also exists at the repo root, `AI's_ideas.md`.

---

## New from the 2026-08-24 docs round-up

**Review and merge (or request changes on) PRs #5–#8 from today's
scheduled routines** — logic review (`logic-review/2026-08-24`,
consolidates two drifted-vocabulary duplicates), bug sweep
(`bug-sweep/2026-08-24`, 9 fixes including a real drill-editor data-loss
bug), security review (`security-review/2026-08-24`, closes a
video-upload-extension gap that could let a crafted upload get served
back with an attacker-chosen extension), and brainstorm
(`future-ideas/2026-08-24`, docs only). None titled `🚨 CRITICAL:`. See
`HANDOVER.md`'s "Scheduled-routine PR round-up (2026-08-24)" for the full
per-PR summary — nothing here is new territory beyond what the
2026-08-23 round of PRs already needed (same review-then-merge shape).

---

## Manual merge of 2026-08-23 PRs + prior uncommitted work (2026-08-23)

Merged `security-review/2026-08-23` → `bug-sweep/2026-08-23` →
`logic-review/2026-08-23` into master one at a time (each pushed and
verified separately), then merged the 2026-08-22 uncommitted local work on
top. The first three merges were done in an isolated git worktree, never
touching the working tree's uncommitted changes, specifically to avoid
tangling them together before the local work was safely committed.

Two real conflicts, both hand-resolved and re-verified against the full
test suite afterward (not just trusted because git resolved the text):
- **`backend/src/routes/analyse.js`**: bug-sweep and logic-review both
  independently fixed the same free-tier usage-slot leak on invalid
  `contactTime`, differently. Combined the better parts of both — validate
  before reserving the slot (logic-review's structural fix, so the slot is
  never taken for a request that was going to 400 anyway) plus rejecting
  `Infinity`/`-Infinity`, not just `NaN` (bug-sweep's more complete check).
- **`backend/src/routes/drills.js`**: same paywall-bypass fix from both
  PRs, again differently. Took logic-review's version — it also 403s when
  the parent drill item is missing entirely (an orphaned step), which
  bug-sweep's version silently let through.

Merging the older 2026-08-22 uncommitted work against the now-updated
master produced 7 conflicts total (this doc, `HANDOVER.md`, and
`auth.js`/`courts.js`/`dev.js`/`friends.js`/`highlights.js`) — all from the
same root cause: that older work and the PRs both touched the same route
files independently. Each was resolved by reading both sides and combining
them (not by picking one side wholesale) and the full 418-test backend
suite was green after.

**Not yet done**: the actual redeploy to the hosted server (`ssh` + `git
pull` + `docker compose up --build app`) — everything above is merged to
master but not live yet. Explicitly deferred to a separate session per
your own call.

---

## ~~New from the 2026-08-25 docs round-up~~ — resolved 2026-08-25, same day

**Review and merge (or request changes on) PRs #9–#12 from today's
scheduled routines** — logic review (`logic-review/2026-08-25`, 4 fixes:
`contactTime` timestamp validation, flagged-swing leakage into profile
stats, courts radius using the exact vs. rounded distance, `target_reps`
type coercion), bug sweep (`bug-sweep/2026-08-25`, 5 fixes including a
near-empty pose trajectory producing a fake similarity score instead of
an error), security review (`security-review/2026-08-25`, pins JWT
verification to HS256 — hardening, not an active exploit), and brainstorm
(`future-ideas/2026-08-25`, docs only). None titled `🚨 CRITICAL:`. Also
still open and unmerged from yesterday: **PR #8**
(`future-ideas/2026-08-24`) — same as the last two round-ups, purely
docs, no urgency. See `HANDOVER.md`'s "Scheduled-routine PR round-up
(2026-08-25)" for the full per-PR summary.

**Worth checking before merging PR #10 specifically**: its headline fix
(a minimum pose-trajectory-length guard in `compare_swing.py`'s
`build_user_trajectory()`, mirroring the pro-database side's existing
`MIN_TRAJECTORY_POINTS` guard) could not be executed in the routine's
sandbox — no `cv2`/`mediapipe`/venv available there. The PR verified it
by inspection only, against an existing tested pattern it mirrors, but
this is the one live-inference code path in this batch — worth a real
`cd scripts && .\venv\Scripts\activate && pytest` pass (or at least a
manual `compare_swing.py` run against a real short/occluded clip) before
merging, since a mistake here would land directly on the core swing-match
flow.

**Resolved same day**: reran the exact venv/pytest check this section asked
for (verified by directly importing the patched `compare_swing.py` under
the real venv and confirming the guard fires as claimed) and merged all of
PRs #9–#12 plus #8 into `master`. See `HANDOVER.md` item #43 for the full
session summary.

---

## New from the 2026-08-25 session (manual work, not a scheduled routine)

1. ~~**Review the 5 flagged ball-label clips.**~~ — resolved 2026-08-25.
   `analysis534`, `analysis501`, `analysis532`, `analysis519`, `analysis522`
   all confirmed decoys by Jack, excluded from Phase 3 ball-detector
   fine-tuning data. See `HANDOVER.md` item #43 for the original flagging
   and item #44 for the resolution.
2. **Ball-speed feature is scoped but not built.** Recommended approach:
   net-keypoint-based local scale calibration, v1 metric is speed *at the
   net crossing* (not off the racket at contact — a real, disclosed
   limitation of a net-only reference). No action needed unless you want to
   greenlight actual implementation.
3. **Remote redeploys may need a permission rule added.** `docker compose
   up --build -d app` run over SSH got blocked by the environment's own
   permission classifier even after verbal approval — `git pull` alone
   worked fine. If this keeps happening, add a Bash permission rule for
   the SSH+docker pattern, or expect to run the rebuild command yourself
   each time (one line, ~1-2 min, see `HANDOVER.md`'s "Read This First" #5).
4. **Local dev password reset**: `jack.p14370@gmail.com` on the *local*
   instance (port 8090 → localhost:5000) was reset directly in
   `backend/data/app.db` to a password Jack provided in chat — not
   recorded here. `RESEND_API_KEY` still isn't configured locally, so the
   real "Forgot password?" email flow won't work on local dev until that's
   set up (see the still-open Resend section above).

---

## New from the 2026-08-26 docs round-up

**Review and merge (or request changes on) PRs #13–#16 from today's
scheduled routines** — logic review (`logic-review/2026-08-26`, a
`celebrity_scores.shot_type` vocabulary-drift fix plus a shoulder-
visibility gate added to the live DTW normalization path), bug sweep
(`bug-sweep/2026-08-26`, 3 fixes: a RevenueCat webhook crash/infinite-
redelivery loop, a drill-video disk leak, and unbounded Overpass API
hammering from court-less areas), security review
(`security-review/2026-08-26`, closes a path-traversal gap in the Dev
Page's swing-review tool — admin-only, not filed as critical), and
brainstorm (`future-ideas/2026-08-26`, docs only). None titled
`🚨 CRITICAL:`. See `HANDOVER.md`'s "Scheduled-routine PR round-up
(2026-08-26)" for the full per-PR summary.

**Worth checking before merging PR #13 specifically**: like PR #10 on
2026-08-25, its `build_pro_database.py` shoulder-visibility fix touches
the live DTW comparison path (`compare_swing.py` imports the same
`normalise_landmarks`/`get_shoulder_ref` functions) but could not be
run through the real `scripts/` pytest suite in the routine's sandbox (no
`cv2`/`mediapipe`/venv there) — only verified by stubbing those modules
out and exercising the function directly. Worth a real
`cd scripts && .\venv\Scripts\activate && pytest` pass before merging,
same as the resolved 2026-08-25 case.

**Deliberately left unfixed by the bug-sweep PR — still your call, still
open**: RevenueCat's webhook delivery is at-least-once and not
guaranteed in-order, so a stale `EXPIRATION` redelivered after a newer
`RENEWAL` could downgrade a currently-paying user to `free` until the
next `/billing/sync` call. Needs a real design decision (e.g. tracking
the latest-applied-event timestamp per user), not a targeted diff.

---

## New from the 2026-09-04 docs round-up

**Review and merge (or request changes on) PRs #28–#30 from today's
scheduled routines** — logic review (`logic-review/2026-09-04`, 8 fixes
including a highlights-job double-event/stuck-process guard and a
rate-limiter fixed-window bug that let auth-route callers burst up to 2x
the intended cap), bug sweep (`bug-sweep/2026-09-04`, 4 fixes including a
NaN-fps crash in the live swing comparator and 4 more foreign-key columns
missing from `verify:db`'s orphan checks), and security review
(`security-review/2026-09-04`, patches a moderate `qs` DoS advisory and a
`GET /courts` coordinate-validation gap). None titled `🚨 CRITICAL:`. All
ten PRs from the prior three rounds (#17–#27) are already merged, so these
3 are the only open PRs right now — a clean backlog, unlike the ten-deep
pile called out on 2026-09-01. See `HANDOVER.md`'s "Scheduled-routine PR
round-up (2026-09-04)" for the full per-PR summary.

**Worth checking before merging PR #28 and PR #29 specifically**: both
touch `scripts/08_comparison_engine/compare_swing.py` — the live
pro-database comparison path (#28's `sample_every` mismatch fix, #29's
NaN-fps guard) — and neither could be run through the real `scripts/venv`
pytest suite in the routine's sandbox (no `cv2`/`mediapipe` there), only
verified by inspection/stubbing. Same recommendation as every prior PR
touching this file (#10, #13, #24, #25): a real
`cd scripts && .\venv\Scripts\activate && pytest` pass before merging.

**Also noted, not a new action item**: no scheduled-routine PRs were
opened on 2026-09-02 or 2026-09-03. This lines up with the code-review
routines' every-3-days cadence (last batch before today was 2026-09-01)
and isn't itself a sign anything is broken — flagging only so a future
session doesn't mistake it for a missed run if the pattern looks odd in
the git history.

---

## Training-data drift watch cannot run: no access to the accumulated logs (2026-09-07)

This is the 6th scheduled routine's first actual attempt (added
2026-08-26 evening per `HANDOVER.md`, scheduled weekly Mondays starting
2026-08-31 — no PR ever appeared for 2026-08-31, which this run now
explains). Its job is to read `data/14_shot_classifier/shot_classifier_training_log.jsonl`,
`data/14_shot_classifier/shot_classifier_ml_training_log.jsonl`,
`data/16_shot_verification/shot_contact_training_log.jsonl`, and
`data/16_shot_verification/shot_contact_ml_training_log.jsonl` for
class-balance skew, candidate→confirmed ratio drops, and buckets falling
out of the trust range described in `shot_contact_training_log.py`/
`shot_classifier_training_log.py`'s own `__main__` self-reports.

**It can't — the cloud sandbox this routine runs in has no copy of any
of those files.** `/data/` is entirely gitignored (12GB+, "not suited for
git without LFS" per `.gitignore`'s own comment) and this routine, like
the other 5, only ever gets a fresh `git clone` of the repo with no
SSH/infra credentials to the machine(s) that actually hold the real
data — the same limitation already called out for the security routine's
"no SSH/infra credentials available to the cloud sandbox" back when the
5 original routines were designed. Those training logs are written by
live production traffic (`analyse.js`'s detached background hook, the
app's "Flag as not a real shot"/shot-type-correction actions, and the
overnight batch pipeline), so they only ever exist on whichever machine
actually serves that traffic — the Hetzner host per `DEPLOY.md`, and/or
Jack's own dev machine (`C:\Users\jackp\tennis_app\`) if run locally
there. Neither is reachable from here. Confirmed directly this run: a
fresh checkout has no `data/` directory at all, and no
`*training_log*.jsonl` file exists anywhere in the repo (fixtures
included) for the two `__main__` self-report scripts
(`scripts/14_shot_classifier/shot_classifier_training_log.py`,
`scripts/16_shot_verification/shot_contact_training_log.py`) to read.

**This isn't a one-off — every future Monday run will hit the exact same
wall** until one of these is done (your call, not something a routine
can decide for itself):
- Sync the 4 `.jsonl` files (small — line-delimited JSON records, not
  the 12GB of video/pose data the rest of `/data/` holds) from the
  Hetzner host into somewhere this routine's `git clone` can reach —
  e.g. a dedicated low-traffic branch/path carved out of `.gitignore`'s
  blanket `/data/` exclusion, synced by a cron job on the host itself.
- Or give this specific routine's environment SSH/read access to the
  Hetzner host's `data/14_shot_classifier/` and `data/16_shot_verification/`
  paths (a narrower ask than full infra credentials, if that's the
  concern from the original design decision).
- Or drop the routine and check drift manually/locally instead, since
  as designed it can structurally never produce a finding.

No code changes made this run (nothing to fix — the scripts and their
trust-gating logic read fine on inspection; there's simply no data
reachable to run them against), so no PR opened.

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
