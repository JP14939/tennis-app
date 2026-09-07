# RallyMax — Status

**What this file is:** a short, hand-curated snapshot, overwritten each time
someone updates it — not a log. Read this first if you just want to know
where things stand in under 2 minutes. For the full detailed history, see
`HANDOVER.md` (dated build log) and `TODO_MANUAL.md` (full backlog, also
chronological) — this file is a filter on top of those, not a replacement.

**Last updated:** 2026-09-07 (later) — **`batch/2026-09-06-find-games-rally-shots` integrated into `master` and deployed** (PR #38, 171 files / ~22k lines: ~2 weeks of feature work that had never reached master — Find Games mesh clubs, ball speed, audio-onset contact, shot-classifier + contact-verification ML, practice ingest, serve anchor, overlays + interpolation, match-quality flag). CD run 34143861953 ✓, health check passed, live `/health` OK. Full suite green on the merge (backend 620, verify:db 98, pytest 289). Prior same day: match-quality flag, overlay interpolation, racket-detection measured (item 10).

---

## What RallyMax is, right now

An AI tennis swing analysis app (Expo — iOS/Android/web). Core loop: upload a
swing video, mark the contact frame, get pose extraction + a Dynamic Time
Warping comparison against the pro swing database, back a closest-pro match, a
0–100 similarity score, and coaching tips. **Built and hosted, pre-launch** —
the backend is live and payments are wired, but no one outside Jack has used
the live product yet.

## Right now — the things that actually matter today

Curated, not exhaustive — the full backlog lives in `TODO_MANUAL.md`.

1. **Find Games revamp (2026-09-05) — now deployed, still not clicked
   through on a real device.** Club clustering rewritten from a 250m running-centroid
   heuristic to a true 100m node-mesh graph (courts are nodes, an edge
   connects two courts ≤100m apart, a club is one connected component —
   confirmed directly with Jack, including that a long line of
   closely-spaced courts is deliberately one club). A third watch type
   (arbitrary map areas — pin + radius) joins the existing court/club
   watches, plus a new "My Watches" screen to manage all three (previously
   no way to see or remove a watch except re-opening the exact court/club).
   Also fixed a real bug: `GET /courts` never told the frontend which
   courts were already watched, so the map's watched-state always started
   empty on load. Live on the server since the 2026-09-07 merge — needs a
   real-device click-through, see `TODO_MANUAL.md`'s 2026-09-05 section.
2. **Postcodes + crowd-sourced club naming, same session.** Free postcode
   lookups (postcodes.io, no API key/cost — chosen explicitly over paid
   Google Geocoding) on courts/clubs/areas; a real backfill already ran
   against local data (16,711/33,222 courts resolved). Club naming now
   works like court verification already did: a user proposes a name, 2
   others confirm it, done — no paid automated lookup needed.
3. **The backend auth-convention gap is closed.** `TODO_MANUAL.md`'s
   backend-architecture backlog used to flag "no enforced convention for
   `requireAuth`/`optionalAuth` per route" as a known risk (root cause of a
   real free-tier-cap bypass, 2026-08-22). New
   `backend/src/routeAuthConvention.test.js` walks every router's actual
   Express middleware chain and fails on any route missing both, unless
   explicitly allowlisted with a reason — verified it actually catches the
   bug class (temporarily stripped auth from a route, test failed with a
   clear message). Two of the three items in that backlog remain open
   (SQLite FK enforcement, Postgres timing) — both still need Jack's call.
4. **`highlights.js`'s two background job runners were reimplementing (and
   partially re-breaking) a bug `runPythonJson.js` already fixed.** Found by
   a `/code-review` pass. Both now route through the same shared, tested
   subprocess module every other route already uses instead of hand-rolled
   spawn/timeout logic — closes a real double-notification/stuck-process
   risk. A small architecture review also logged 3 more deepening
   candidates (not started) — see `HANDOVER.md`'s "Architecture review"
   entry.
5. **Practice-footage review is the main live task — 201/333 done.** Jack is
   working through Pro Clip Review's practice queue (relabel shot type + fix
   contact time on court-level footage the 2026-09-03 Claude ingest added).
   The broadcast queue is essentially finished alongside it (354/359
   label-reviewed). Both training flywheels around this data are now wired
   (see item 6) — every clip reviewed compounds automatically, no separate
   step needed.
6. **Two shot-classifier training flywheels were broken since they shipped —
   both fixed 2026-09-04.** (a) A user's "Wrong shot type?" correction in
   History was logged with no `clip_path`/`contact_frame`, so it was
   silently dropped by the feature extractor every time, since the feature
   shipped — fixed, verified end-to-end with a real correction through the
   real endpoint. (b) Pro Clip Review verdicts on practice-footage entries
   were excluded outright from classifier training, even once reviewed —
   the exclusion was stricter than it needed to be (a verdict already implies
   review); deleting it was the whole fix. **119 reviewed rows already
   flowing into training** (43 forehand / 34 backhand / 42 serve) — the
   backhand count alone more than triples the old 10-example ceiling that's
   been the phone-classifier bottleneck. Re-run the extractor periodically
   to pick up more as Jack's review count climbs.
7. **Unreviewed practice entries were live match candidates — fixed.** Any
   of the 333 auto-labelled practice entries could have been served to a
   real user as their "closest pro match" before being reviewed. New
   `compare_swing.eligible_match_candidates()` requires a real Pro Clip
   Review verdict first. Verified against the live DB (forehand pool
   453→243, etc.), no pool-starvation risk.
8. **A real serve-classification bug fixed.** Strong serve evidence could be
   outvoted by a large lateral wrist offset at the (downswing) contact
   frame — the serve gate now hard-wins before the forehand/backhand test
   runs. Regression test added.
9. **Phase C (contact-frame correction model) retrained twice with real new
   data — failed its own accuracy gate both times, not shipped.** A real
   negative result: the "corrected" prediction is consistently *worse* than
   the plain geometric heuristic across every tolerance band, even with
   109 new hand-corrected practice examples. Diagnosed (not just observed):
   the broadcast `audio_teacher` labels are noisy on this footage (60%
   outliers), but training human-only was *also* worse — the regressor
   isn't finding real signal in these features. Not live-consequential
   either way (separate runtime trust gate needs 50+ real production
   examples, currently 0). Needs a redesign, not more data, if revisited.
10. **Serve contact detection was an ANCHOR problem (not racket detection) —
   measured, then fixed (Phase 1a, 2026-09-06).** Diagnosis: racket bbox
   detected in 60/60 serve windows; the wrist-velocity anchor was a median
   ~38f off (toss/follow-through beats contact in wrist speed) and outside
   the refinement window on most serves. **Fix:** new
   `scripts/00_utils/serve_anchor.py` — for serves, anchor on the overhead
   wrist apex (`(nose.y-wrist.y)/torso`) instead of wrist velocity, wired
   into `compare_swing.auto_contact_anchor_frame` + a serve-widened
   audio-onset band; `racket_tracker.find_contact_frame` got a narrow
   symmetric serve window. **Result (eval_pro_clip_contact.py, 60 serves):
   contact err median 44f → 17.7f, p90 110f → 80f, ≤3f 20% → 35%; forehand
   /backhand rows byte-identical (regression check).** ~half of serves still
   have a bad apex (bimodal tail) — improved, not solved. Live audioless
   fallback only; on real phone serve uploads audio-onset is the first line.
   **Phase 1b done (2026-09-07):** `scripts/06_database_build/reanchor_pro_serves.py`
   re-anchored 19 non-human-marked serve entries in `pro_database.json` to
   the apex (60 human-marked ones left alone), with backups; idempotent on
   re-run. Racket *keypoint* precision on serves (~2× worse) is still open —
   for the overlay + shot-contact verifier + the racket-tip coaching-tip
   gap, NOT the contact pipeline. Full writeup: HANDOVER.md 2026-09-06 (two
   entries) + 2026-09-07.

   *Two ball-tracking attempts, both NO-GO (2026-09-07).*
   (a) **Two-pass ROI re-detector** (`ball_roi_tracker.py` +
   `ball_tracker.track_ball_states` + `eval_ball_roi_tracker.py`): predicts
   the ball's position and re-runs the detector in a small crop there.
   Sparse fp gate fails; honest dense continuity (after a `_densify`
   inflation bug fix) helps 2/10 clips, regresses 1/10. Wired but
   `use_roi_tracker=False`.
   (b) **Near-side crop** (`near_court_ball_tracker.py` +
   `eval_near_court_ball_detection.py`): crop to player + net-ward cone,
   detect there. Eval on 354 human labels: **full-frame @320 is already the
   best config** (near 0.85 / far 0.87 detect); cropping loses
   (coverage 0.52, net undetected 79% of close phone frames). Not wired.
   **Takeaway: per-frame ball detection isn't the bottleneck it looked
   like** — the full-frame detector is ~85% on visible balls; only the
   contact frame (ball behind racket, gap-detection covers it) and the
   offline pro DB are weak.
   **Queued: a clean detector retrain** — `prepare_ball_yolo_dataset.py`
   had a real train/val leak (76 dupe images) + frame-level split, both
   fixed; `train_ball_detector.py` now imgsz 480 + multi_scale;
   `README_ball_retrain.md` has the recipe. Needs the server label log +
   wide-court labels reviewed, then ~1.8hr CPU. Plans:
   `okay-plan-it-floating-whistle.md` +
   `c-users-jackp-claude-plans-okay-plan-it-serene-map.md`.
11. **Local dev workflow had two real bugs, both fixed.** Web dev was
   pointed at an ngrok tunnel whose free-tier browser interstitial silently
   broke every API call (looked like a login/history bug, was zero backend
   involvement) — now points at localhost + a permanent fetch shim so a
   tunnelled session can't break the same way again. All 429 practice clips
   were saved in a browser-unplayable codec (`ingest_practice_footage.py`
   never re-encoded, unlike every other clip-writing path) — fixed at the
   source and backfilled.
12. **`detect_rallies.py` / shot classifier (2026-09-02/03, still the
   pipeline-domain baseline):** ensemble 40%→84% pipeline, backhand 24%→84%.
   Phone-upload domain was ~56% before this session's flywheel fixes above;
   not re-measured end-to-end yet with the new practice training data —
   worth a fresh `evaluate_shot_classifiers.py --set both` run once Jack's
   review count is higher.
13. **A real beta launch hasn't happened.** The product is feature-complete
   well past the original MVP scope but has never been tested by real
   external users — biggest open strategic question.
14. **The whole backlog IS merged + deployed now (2026-09-07).** `master`
    is at the PR #38 merge; CD deployed it (health check passed); local
    `master` = `origin/master`, working tree clean. **Still deliberately
    NOT copied to the server:** the rebuilt `pro_database.json` /
    `overlay_trajectories.json` / `clip_review_log.jsonl` — `data/` is
    gitignored, CD never touches it, and copying them now would ship
    unreviewed practice entries (review pass only ~60% done). **Also
    probably not on the server yet:** the model `.pkl`/`.pt` files the new
    ML paths use (`onset_classifier.pkl`, `contact_frame_model.pkl`,
    fine-tuned ball `best.pt`). Their absence *degrades, doesn't crash* —
    verified fallbacks: no audio model → pose-peak / manual mark; no ball
    model → generic COCO. **A real swing upload through the live app is the
    open verification step** — the merge is code-only, live matching is
    likely still on the older server-side pro DB.
    *Set aside during the merge:* `stash@{0}` on the batch branch holds a
    parallel session's racket-detection imgsz-calibration + serve-anchor
    eval + wide-court ball labeling WIP — not lost, needs that session (or
    Jack) to pop + finish it. `stash@{1}` (`jack-wip`) untouched.
15. **Two backend-architecture decisions still need Jack's call**, not
    urgent: SQLite foreign-key enforcement (off), Postgres migration timing.
    (The third item this used to list — a route-level auth-convention check
    — is done, see item 3 above.) See `TODO_MANUAL.md`'s "Backend
    architecture backlog".
16. **Resend sender domain still not set up** — password-reset emails
    redirect to Jack's inbox as a stopgap.
17. **"Record now" live camera calibration hasn't been tested on a real
    phone** — a continuous feedback loop, higher-risk than a one-shot
    request to only test via curl.

## What's live

- Core analysis loop: MediaPipe pose extraction + DTW vs. the pro clip
  database, camera-angle inference, 216-tip coaching database
- Audio-onset contact detection in `compare_swing.py`'s auto-detect path;
  serve-specific overhead-apex contact anchor (`serve_anchor.py`)
- Ball detector (fine-tuned YOLO) + contact-verification rules/ML, each with
  their own trust gate
- Sync Compare overlays: skeleton + racket + ball paths, with server-side
  short-gap interpolation (`interpolate_track.py`); a "this doesn't look
  like my swing" match-quality flag → `match_quality_flags.jsonl`
- Find Games: mesh-clustered clubs, court/club/area watches + My Watches
  screen, postcodes, crowd-sourced club naming
- RevenueCat payments, wired end-to-end (entitlement `premium`)
- Backend hosted (Hetzner + Docker) with automated CD (push to `master` →
  auto-redeploy; **no test gate runs before deploy**)
- Social/gamification: friends, leaderboards, Find Games court map,
  messaging, community-submitted courts
- History/progression tracking, 1-on-1 comparison, Drills (free tier)
- Self-serve password reset (Resend, sandbox sender)

## What's built but not shipped / not live

- Phase C contact-frame correction model — fails its own ship gate, see
  item 9 above
- Ball ROI re-detector + near-court crop — both evaluated NO-GO (item 10),
  code kept with wiring OFF; a clean ball-detector retrain is queued
  (`README_ball_retrain.md`)
- Coaching-tip Claude verifier half of `09_coaching_ai` — blocked on
  rotating a leaked API key, unrelated to this session
- Net-endpost keypoint model (`10_net_detection`) — trained, unused
- View-aware trajectory-kNN for the phone-classifier path — deferred,
  ~1-1.5 days estimated, would be the real fix for phone accuracy

## Competitive — SevenSix (assessed 2026-09-01, unchanged this session)

`SevenSix AS` (Norway), iOS-only, same pose+compare-to-pro loop. Not a
capital/tech threat (~$550K raised, visible reliability problems); their bet
is tennis-federation distribution, not the product. Full detail:
`docs/future-ideas.md` `### 2026-09-01`.

## Where to look for more

- `HANDOVER.md` — the full dated build log, most detail
- `TODO_MANUAL.md` — the full backlog, chronological by session
- `JACK_TODO.md` — flat actionable checklist pulled from the above
- `DEPLOY.md` — how hosting + CD actually work
- `CLAUDE.md` — commands, architecture, where things live in the codebase
