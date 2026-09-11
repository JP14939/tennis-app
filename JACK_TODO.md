# Jack's To-Do List

A flat, actionable checklist of everything that needs a human (you) —
account creation, dashboard clicks, real-device testing, or a judgment call
only you can make. Pulled together from `TODO_MANUAL.md` (the full narrative
log, still the source of truth on *why*) plus everything that came up in the
2026-08-23 PR-merge/browser-testing session. Check items off as you go;
`TODO_MANUAL.md` stays the append-only history, this is just the flat list.

---

## ML-reliability roadmap (added 2026-09-08 — SUPERSEDES the 2-week push below)

**Date slipped.** Jack decided 2026-09-08: no fixed launch date — every premium
feature must be reliable at launch, so the ML work below is now in scope for v1
(the 2026-09-07 "defer the ML tail" call is reversed). Full plan + designs:
`C:\Users\jackp\.claude\plans\okay-so-i-finished-lovely-adleman.md`; narrative:
`HANDOVER.md` "Session 2026-09-08". Owner key: **[J]** you only, **[C]** Claude,
**[J+C]** both.

**Phase 0 — kick off (now / overnight)**
- [x] ~~**0a** [J+C] `sample_every` 3→1: back up pro DB, change the 4 coupled
      sites, re-extract pro poses + rebuild trajectories/overlays, re-run
      `evaluate_amateur_dataset.py`.~~ **Done 2026-09-09/10.** Re-extract was
      ~4.75 h (13/13 files, pose files ~6× bigger with world landmarks). Went
      further than planned — pro-side yaw wiring + a **v4** re-slice (metric z
      decoupled from x/y on all 648 entries, `traj_version 4`, `verify:db`
      99/99). DTW separation +7% → +11%. `phase_breakdown.Z_ROTATION_BLEND = 0.0`
      is the one live change (reversible). The current code/documentation batch
      was consolidated and pushed as `2f750e6`; the rebuilt data artifacts still
      need the separate manual server transfer below. HANDOVER
      "Session 2026-09-09/10".
- [x] ~~**0b** [C] Ball detector: let training finish → run the 3 gates in
      `README_ball_retrain.md` → keep or restore.~~ Done 2026-09-08 — resumed
      after an overnight stall, 150/150, gates run, new `best.pt` **KEPT**
      (Jack's call). Needs manual server transfer (see the backend/data item
      below). Details: HANDOVER.md "Session 2026-09-08 (later)".
- [ ] **0c** [J] Record 3-5 whole-match videos from the fence (behind baseline)
      + 2-3 deliberately wrong-angle short takes + several of your own competent
      single swings + a few deliberately sloppy ones. One session feeds items
      1a-val, 1b, and 2a.
- [ ] **0d** [J] Rotate the leaked `ANTHROPIC_API_KEY` in `backend/.env`.
      Unblocks the coaching-tip verifier loop (2e).

**Phase 1 — core-loop reliability** (all [C] unless noted)
- [x] **1a** Behind-baseline camera gate — **ENFORCED for launch 2026-09-09.**
      `infer_angle.evaluate_view_usable(view_direction, angle, conf, net_debug=)`
      blocks an upload unless it's a clean behind-baseline shot with the whole net
      in frame: `front_view` / `side_on` ≥78° / `net_not_found` (keypoint model
      missed the net) / `net_truncated` (`posts_inframe_frac` <0.5, a post off the
      edge) → `severity:'block'`; `angle_unreliable` (conf <0.45) stays a warning.
      `compare_swing.compare()` raises `ViewGateError`/`VIEW_NOT_USABLE` by default
      (`RALLYMAX_ENFORCE_VIEW_GATE=0` = advisory, for batch eval only).
      `check_camera_setup*` returns `view_severity`; `ContactMarkingScreen`
      hard-stops; `ResultsScreen` → "Check your camera setup". **Decision:** don't
      *normalize* camera angle — both attempts (pose-yaw, net-width) failed on real
      footage; restrict the input domain instead. See
      `~/.claude/plans/purrfect-jingling-rose.md`.
- [ ] **1a-val** [J+C] Optional refinement: hand-label ~60 pro + ~40 amateur +
      the 6 calib clips → check the gate's false-reject rate on real behind-view
      footage and retune `VIEW_GATE_*` / `NET_POST_EDGE_MARGIN` if needed. Not a
      launch blocker now the gate is on.
- [~] **1b** Similarity-score calibration — reframe as a rule-based **technique
      score** on biomechanical axes vs the pro DB's per-shot/per-view distribution
      (the DTW metric can't separate a pro from a decent amateur; ~10 variants
      failed, 2026-09-08). **2026-09-11: full plan + de-overfit + two new Dev
      Page tools, still bench-only** — see `~/.claude/plans/reactive-enchanting-metcalfe.md`
      and `HANDOVER.md` "Session 2026-09-11" for the complete state. The old
      +20.0 combined gap was **overfit** (measured on the same clips axes were
      picked from) — real 5-fold CV (`redesign_similarity.py curate --folds 5`)
      gives **forehand +12.2** (after 2 rounds of new axes, incl. fixing a real
      angle-wrap bug), **serve +26.1** (ships as-is), **backhand pending a
      `curate` re-run** now that the amateur label pool is 5→26+6 (see 1b-data
      below). 3D depth axes (`contact_depth_ahead` etc.) remain excluded from
      `CURATED_AXES` after their negative real-footage result; they are not
      part of the production score. New candidate
      axis `swing_amplitude` (whole-window motion, catches a rushed/minimal
      backswing that contact-snapshot axes miss) found real but not yet
      CV-stable. **B2 (the actual production scorer/wiring) has not started
      — this is all still bench + data-quality work.**
- [ ] **1b-decision** [J+C] This has been re-flagged as the top pre-launch
      risk in 4-5 separate session summaries without shipping past
      bench-only. Recommendation: stop hunting further axes indefinitely.
      Once the just-finished amateur backhand relabel produces a backhand CV
      number from `redesign_similarity.py curate --folds 5`, make one
      go/no-go call — if all three shot types clear a minimal CV-separation
      bar, wire the rubric into `compare_swing.py` as B2 behind an explicit
      "PROVISIONAL" tag in the API response and ship it, refining against
      real usage once there's a beta instead of continuing to iterate on
      bench data alone.
- [ ] **1b-data** [J] Two new free Dev Page tools to work through, no rush,
      stop per shot type once "enough":
      - **Amateur Clip Review** — DONE, Jack finished the full 329-clip queue
        2026-09-11 (backhand 5→26 in the amateur eval set +6 more in a second
        raw-footage batch). Re-run `curate` with the bigger sample is next
        (Claude's step, not Jack's).
      - **Pro Quality Review** (new) — tag pro-database clips ⭐Gold/OK/✕Exclude
        on TECHNIQUE quality (not label accuracy) — builds a tightened
        reference pool for the same `exp(-|Δ|/IQR)` kernel every axis uses.
        **0/648 tagged as of 2026-09-11.** Target ≥15 gold per shot/view
        bucket to start being useful; more is better, no need to do all 648.
        G/O/X keyboard shortcuts on web.
- [~] **1c** Visual contact-frame model for clips with no audio — **base
      committed 2026-09-11** (`2791e7e`/`f28f3b5` — serve apex plateau,
      `onset_classifier` in `/dev/ml-status`, stride-1 eval harness). **Two
      accuracy fixes on top, measured, NOT yet committed:** ball-motion-
      continuity gate on the "ball vanished = contact" heuristic +
      deceleration-recentred groundstroke anchor → pro-broadcast **24%→38%≤3f**.
      **First real amateur-footage numbers (85 audio-pseudo-labelled clips,
      zero manual marking): 25%≤3f** — the honest target, pro's 38% overstates
      it. Still short of the ≥55%≤3f goal — **next: the supervised per-frame
      classifier** (same candidates→features→score→argmax reframe that made
      audio-onset work; Phase C's old offset-regression framing stays dead).
      The 2a/2b helpers and new
      `label_amateur_contact_from_audio.py`/`amateur_contact_eval.py`/
      `mark_amateur_contact_time.py` were reviewed, tested, committed, and
      pushed as `2f750e6`. Details: HANDOVER "Session 2026-09-10/11";
      plan `~/.claude/plans/swirling-popping-flame.md`.
- [x] ~~**1d** z-depth re-enable attempt~~ — **done, negative, 2026-09-10.**
      Metric world-z is now on every trajectory (v4), and the scale is right
      (median 0.45), but it carries no technique signal at fence distance
      (`contact_depth_ahead` [−0.19, +4.27] for the same forehand). `Z_WEIGHT`
      stays 0.0 in DTW; `Z_ROTATION_BLEND` set to 0.0. Don't reopen without a
      better depth source.

**Phase 2 — premium-feature reliability** (all [C] unless noted)
- [ ] **2a** [J+C] Highlights eval on your 0c fence footage — label every swing,
      get a real accuracy number for the whole-match feature. Gates 2b/2c.
- [~] **2b** Shot-contact verifier `occlusion_gap` fix (require ball
      approach→gap→departure, not a bare gap). **Investigated 2026-09-09/10:**
      not in the live upload path; the "regression" was a stale eval checkpoint,
      not real. Real issue is absolute — ~51% precision, `_find_gap_contact`
      + `filter_verified_swings` keep any bare gap regardless of confidence.
      Stamped baseline `data/17_amateur_eval/results_baseline_2b27847.jsonl`
      (54.4% / 49.1%); eval hygiene is committed and pushed in `2f750e6`.
      Track 2 plan
      (anchor-proximity constraint + confidence gate + threshold sweep):
      `~/.claude/plans/rustling-meandering-petal.md`. Not launch-blocking.
- [ ] **2c** Swing-detector recall — stop missing soft shots; confirm the
      serve-gate fix end-to-end on a real match clip.
- [ ] **2d** [J+C] Racket-keypoint labeling push (serves + handle point) →
      retrain. Affects the body-rotation phase score + overlays.
- [ ] **2d-ball** [J+C] *(not launch-blocking)* Ball-detector v2 — the
      2026-09-08 retrain left **backhand ~0.77** and **far/wide balls** weak.
      Blocked on: [J] re-draw the ~8 sloppy `wide_court_ball_labels*.jsonl`
      positives in the Dev Page Ball Label tool + record more amateur backhand
      footage; then [C] rebuild the dataset (add the 43 wide-court negatives)
      and retrain per `README_ball_retrain.md`.
- [ ] **2e** Tip selector: kill cross-match contradictions now; after 0d, run
      the Claude verifier offline to build the trust set. [J] work the Tip
      Review queue.
- [ ] **2f** [J] Keep working Pro Clip Review — the 55 held-out practice serves
      flow into the classifier pool as you go. No dedicated serve work.

**Phase 3 — pre-release gate**
- [ ] **3a** [C] Full test + eval suite green.
- [ ] **3b** [J] Transfer rebuilt `pro_database.json` + overlays + model files +
      run `clusterCourts.js` on the server.
- [ ] **3c** [J] One real end-to-end swing upload through the live app + the
      5-case matrix below.
- [ ] **3d** [J] Store-submission plumbing (list below) — runs in parallel, not
      gated by the ML work.

---

## 2-week launch push (added 2026-09-07 — target ~2026-09-21) — DATE DROPPED 2026-09-08

*Kept for the plumbing checklist. The "defer the ML tail" framing here is
superseded by the roadmap above.*

Core analysis loop was verified working end-to-end locally 2026-09-07
(`HANDOVER.md` "Session 2026-09-07 (later still²)").

**Long pole — start day 1:**
- [ ] Apple Developer Program enrollment ($99/yr) — approval can take days.
- [ ] Set up an EAS build (`eas build`) — Expo Go can't do real IAP or Google
      Sign-In.
- [ ] Wire RevenueCat's native SDK into the EAS build (backend
      webhook/entitlement logic doesn't change).
- [ ] Privacy policy URL, app icons, screenshots, permission usage strings
      (camera / mic / photo library).

**Backend / data — before real users:**
- [ ] Finish the Pro Clip Review practice queue, **then** copy to the server:
      `data/06_pro_database/pro_database.json`, `overlay_trajectories.json`,
      `player_names.json`, and the model files (`onset_classifier.pkl`,
      fine-tuned ball `best.pt`). `data/` is gitignored; CD never touches it,
      so live matching is still on the pre-2026-09-02 pro DB until this is
      done. **The local `pro_database.json` is now the 2026-09-10 v4 rebuild**
      (`traj_version 4`, stride-1 + metric z; carries the earlier serve-anchor
      re-anchor). **The commits `6cfee83`..`4d19e2b` must not be `git push`ed
      until this transfer lands** — a push auto-deploys the user-side stride-1
      change, and stride-1 user trajectories vs the server's stride-3 pro DB =
      score drift. Also NOT for transfer: the `data/02_pose_extraction/*.json`
      stride-1 pose files (local build artefact, the server never reads them).
- [ ] *(optional, RED expected)* [J] Film ~6 **deliberate square-and-still ~3 s
      holds**, one per camera position, to 100 %-close the "calibrate camera
      angle once per session" question (`scripts/05_angle_detection/calibration_hold_test.py`
      docstring has the filming spec). The proxy run on self-fed footage is RED
      (within-hold facing IQR 59°); a real film would confirm, not overturn.
- [x] ~~**Ball-detector retrain — run the gates, then keep-or-revert.**~~ Done
      2026-09-08: retrain finished (resumed after an overnight stall, 150/150),
      3 gates run. New `best.pt` = at-contact 91.7% / conf 0.64 (baseline 50%
      / 0.41), near-player FH/serve ~94-96%, backhand flat ~0.77, far-ball
      (full frame) 79%. **Jack's call: KEEP** — no regression, honest non-leaky
      eval. Weights already live locally; **still needs the manual server
      transfer** (folded into the pro-DB copy item above). Backhand + far/wide
      balls stay weak → future retrain, see below. Full writeup: HANDOVER.md
      "Session 2026-09-08 (later)".
- [ ] Run `node backend/scripts/clusterCourts.js` on the server (or transfer
      the `clubs` / `club_courts` rows) — the hosted DB has zero clubs, so
      Find Games shows no clubs live.
- [ ] Resend sender domain: create account, `RESEND_API_KEY` →
      `backend/.env`, confirm `rallymax.app` is yours + verify DNS, set
      `RESEND_FROM_EMAIL` / `PUBLIC_BASE_URL`, restart, test the real reset
      email. (Currently password-reset emails redirect to Jack's inbox as a
      stopgap.)
- [ ] Off-box DB backups — `backend/scripts/backupDatabase.js` is written;
      just the 3 manual steps in "Deploy & infrastructure" below (Backblaze
      B2 bucket, `rclone config` on the VPS, one cron line).
- [ ] Flip the GitHub repo back to private
      (`gh repo edit JP14939/tennis-app --visibility private`).

**Pre-launch core-loop verification (real device / live backend):**
> Engine + backend + live server already verified via curl 2026-09-07 (all
> HTTP 200, valid payloads, `/api/history` round-trips, free-tier cap fires,
> live score == local score). What's left below is the **real-device / app-UI**
> pass — the parts a curl test can't cover (does `ResultsScreen` actually
> render it, does the audio model fire on a phone-recorded clip, etc.).
- [ ] One upload **with the contact frame marked** — score/match/tips render
      in `ResultsScreen`.
- [ ] One upload **without** marking — the analysis response JSON has
      `contact_source: "audio_onset"` (proves `onset_classifier.pkl` is
      deployed + firing; `wrist_peak` / `ball_occlusion_gap` / `serve_apex`
      means it fell back). Also visible: `GET /dev/ml-status` →
      `onset_classifier.model_present`. (The old check — "backend logs show
      `Contact auto-detected via AUDIO onset`" — never worked: that line is
      stderr-only and `runPythonJson.js` discards stderr on success. Fixed
      by 1c, 2026-09-08.)
- [ ] One left-handed upload (mirror path).
- [ ] One serve upload (worst-case shot — only 82 pro serve entries, weak
      anchor).
- [ ] "Record now" live camera calibration on a real phone (continuous
      feedback loop, higher risk than a curl test). **Now also gates on the
      1a view check (2026-09-08):** confirm the badge goes **red** with a
      "move behind the baseline" message when pointed from the net side and
      **green** from behind the baseline fence, within ~2 poll cycles.
- [ ] One deliberately wrong-angle upload (filmed from the net / hard side-on)
      → the amber view-gate warning banner shows on `ResultsScreen`, results
      still render below it (advisory mode — not a hard reject yet).
- [ ] Confirm the hosted `calibration_server` is up: `GET /dev/ml-status` (or
      curl :5055) + `data/10_net_detection/yolo_pose_run_v4/weights/best.pt`
      present on the server. If `/api/check-setup-live` returns 503, that
      weight needs the manual `data/` transfer (past crash-loop cause).
- [ ] **1a-val** [J+C] The upload gate is now ENFORCED by default (2026-09-09) —
      `RALLYMAX_ENFORCE_VIEW_GATE` no longer needs setting on the server (`=0`
      only reverts to advisory for batch eval). Remaining optional work: hand-label
      real behind-view footage and check the false-reject rate, retune
      `VIEW_GATE_*` / `NET_POST_EDGE_MARGIN` if it's too aggressive.
- [ ] Find Games revamp click-through + Drills/Lessons/Swing Review as a real
      user.

**Judgment calls:**
- [~] **Score presentation + calibration.** Problem (1) — the contradicting
      second number — is **fixed 2026-09-08**: Jack's call was to drop the pro
      identity entirely (most pro-DB clips aren't identified, "matched to
      Forehand Technique #142" read as broken). The "Other close matches"
      #2/#3 list (the `scale=0.4` numbers) is **removed** from `ResultsScreen`;
      the hero `overall_score` (`PHASE_SCALE`) is now the only 0–100 on screen.
      Score-card caption → "How closely your <shot> matches pro technique";
      Sync Compare pane → "Pro swing"; History/Home/Coach/share card/signup
      copy all de-named to match. `analyse.js` now asks `--top 1`. Problem (2)
      — **`PHASE_SCALE` is still uncalibrated** against a labelled match-quality
      set; that's roadmap **1b** (the rubric redesign), still CPU-blocked.
      `scale=0.4` now only governs the ≥75 "great swing" gate + the stored
      `similarity` fallback when phase breakdown fails.
- [ ] Decide: add an annual pricing tier (only monthly is live)?
- [ ] Decide: coaching-tip Claude verifier back on (with a cost budget) or
      stay offline?

---

## Deploy & infrastructure

- [x] ~~Redeploy the hosted server.~~ — done 2026-08-23. Server pulled
      `master` (`cf76490`) and rebuilt/restarted cleanly. Also found and
      resolved a leftover uncommitted hotfix on the server itself (an
      identical one-line `courts.js` fix applied directly there in a past
      session, never committed — discarded in favor of the incoming
      identical fix from `master`, no functional change). Verified live:
      signup and `GET /courts` both work on production with no crash.
- [ ] **Set up off-box database backups** (backend/scripts/backupDatabase.js
      is already written and tested — this is just the 3 manual steps):
  1. Create a free Backblaze B2 account + bucket (`rallymax-db-backups`),
     generate an application key.
  2. On the VPS: `curl https://rclone.org/install.sh | sudo bash`, then
     `rclone config` (remote name `b2remote`, type `b2`, paste the key).
  3. Add the cron job (`crontab -e` on the VPS):
     `0 3 * * * cd /opt/tennis_app && docker compose exec -T app node backend/scripts/backupDatabase.js && rclone copy backend/data/backups b2remote:rallymax-db-backups --min-age 1m`
- [x] ~~Decide what to do with the test account created on production.~~ —
      done 2026-08-23, deleted (`browsertest_1787503060@example.com`, via
      its own real `DELETE /api/auth/me` self-service call). A second
      throwaway account created while verifying the redeploy
      (`deploycheck_...@example.com`) was also cleaned up the same way.
- [x] ~~Merge the last open PR (`future-ideas/2026-08-23`).~~ — was already
      merged into `master` earlier the same session (confirmed via
      `git log`), nothing further needed.
- [x] ~~Delete the merged PR branches on GitHub.~~ — done 2026-08-23,
      2026-08-24, and 2026-08-25 (all merged batches' branches deleted
      each time). Only `master` remains.
- [x] ~~Redeploy the hosted server (again).~~ — done 2026-08-25. Found the
      server 2 days stale (still on the 2026-08-23 commit) while diagnosing
      "most Dev Page tools don't load" — that was the actual cause, not a
      code bug. `git pull` over SSH worked as usual; the
      `docker compose up --build -d app` rebuild step got blocked by this
      environment's own permission classifier even after you approved it,
      so you ran that one command yourself. Server confirmed back on
      `master` and healthy afterward. **Heads up for next time**: if a
      redeploy is needed again, the rebuild step specifically may need you
      to either add a permission rule or run it yourself again.
- [ ] **Flip the GitHub repo back to private** if you're done sharing it
      publicly (`gh repo edit JP14939/tennis-app --visibility private`).
      **Still needs you** — no `gh` CLI available in this environment and
      no other credentialed path to change repo-level settings, so this
      one couldn't be done for you.

## Self-serve password reset (Resend)

- [ ] Create a Resend account (resend.com, free tier).
- [ ] Grab an API key → `backend/.env` as `RESEND_API_KEY`.
- [ ] Decide on the sender domain — confirm whether `rallymax.app` is
      actually yours; if so verify it in Resend's dashboard (DNS records)
      and set `RESEND_FROM_EMAIL`. If not, the "email support@rallymax.app"
      text needs changing too.
- [ ] Set `PUBLIC_BASE_URL` in `backend/.env` to the real hosted URL.
- [ ] Restart the backend, then test: "Forgot password?" in the app → check
      inbox → reset → log in with the new password.

## RevenueCat / payments

- [ ] Verify the `active_entitlements`/`items` field-name loose end in
      `backend/src/routes/billing.js` — only matters if Premium ever seems
      to unlock late (via webhook, a few seconds after purchase) instead of
      instantly. Check backend logs for `[billing/sync] failed:` if so.
- [ ] Optional: add an annual/other pricing tier (only the monthly plan is
      live today).

## Data quality — pro database & footage review

- [ ] **Review the 20 high-camera-angle pro database entries**
      (`camera_angle > 65°`, 14 forehand + 6 backhand) — decide keep vs.
      fix vs. remove for each. Offer still stands: I can generate contact
      sheets for a first-pass read if that helps.
- [x] ~~Work through the 230 ball-label frames~~ — done, 354 labels logged.
- [x] ~~Review 5 flagged clips for static-decoy contamination~~ — done
      2026-08-25, all 5 (`analysis534/501/532/519/522`) confirmed decoys,
      auto-excluded by `find_fully_static_files()` in the dataset build.
- [ ] **Decide on `IMG_5755.MOV` Claude verification spend** (~$2.70,
      290 raw candidates found in the free dry-run) — give the go-ahead or
      skip it.
- [ ] **`IMG_5823.MOV`** — dry-run found 6 candidates, never Claude-verified;
      decide if it's worth the (small) spend.
- [ ] **85 old History rows have no watchable video on the hosted server**
      (from the 2026-08-14 local batch-analysis run) — decide if it's worth
      a one-time `scp`/`tar` copy of `data/runtime/user_clips/8_*` to the
      host to make them watchable, or leave as-is.
- [ ] **Keep working the practice-footage queue in Pro Clip Review** —
      201/333 done as of 2026-09-04. Reviewed entries now feed both the
      live match pool and classifier training automatically, no extra step.
- [ ] **Decide whether to keep pushing on the Phase C contact-frame model**
      — retrained twice 2026-09-04 with real new data, failed its own
      accuracy gate both times (worse than the plain heuristic). Not
      shipped, not live-consequential either way. Needs a different
      approach if you want to revisit it, not more data.
- [x] ~~Decide if fine-tuning the ball detector is worth doing~~ — answered
      2026-09-07. Two clever tracker ideas (two-pass predicted-ROI
      re-detection; near-court crop) were both built and evaluated **NO-GO**
      — the full-frame detector already gets ~85% near / ~87% far on visible
      balls; only the contact frame (ball behind racket, gap-detection
      covers it) and the offline pro DB are weak. A **clean retrain** IS
      worth it and is the live task — see the "Ball-detector retrain" item
      in the launch push above.
- [ ] **Don't copy `pro_database.json` to the server yet** — wait until the
      practice-review pass is further along, or unreviewed/lower-quality
      practice entries would go live on the hosted server (the local match-
      pool filter added 2026-09-04 doesn't protect a straight file copy).
      When you do, it carries the Phase 1b serve re-anchor too.

## Real-device / real-browser testing

- [ ] **Test "Record now" (live camera calibration) on a real phone** —
      flagged as higher priority than it looks: it's a continuous feedback
      loop, not a one-shot request, so it can look fine in a curl test but
      feel laggy/jittery in practice. Check the positioning badge updates
      smoothly as you move the phone.
- [ ] **Confirm on your actual phone**: avatar is circular (was square),
      Home CTA card has its green background, Find Games shows real courts.
      (Backend side of the courts fix is verified working via direct API
      test tonight — worth your own eyes on the native map UI too, since
      Find Games isn't testable on web.)
- [ ] **Click through Drills & Lessons / Swing Review / Rally Boundary
      Review** as a real user on your phone at some point — these were
      verified via API/bundler checks, not a live click-through.
- [ ] **Ideal-swing compare screen** (new 2026-09-10) — the FH/BH/serve
      reference clips are wired into `frontend/assets/reference/` +
      `referenceClips.js` (web export verified, uncommitted). On a device:
      run a swing analysis, confirm the "Watch the ideal swing ▸" button on
      `ResultsScreen` opens `SyncCompareScreen` with the reference on the
      left, and each coaching tip's "See this done right ▸" deep-links to the
      right phase. Then **refine `CONTACT_SEC`** in `referenceClips.js` — it's
      Claude's eyeball estimate right now (`{forehand: 0.43, backhand: 1.0,
      serve: 0.3}`); nudge if the contact-relative scrubber lands off.

## ML pipeline — fix the base before the top (bottom-up sprint plan, 2026-08-27)

Rally detection sits on top of a dependency chain: **shot contact detection →
shot type classification → serve gate → rally grouping**. Job 10 (real Claude
verification, `IMG_5755.MOV`) surfaced a break at the *second* level, which
silently wrecks everything above it — decided 2026-08-27 to stop patching
top-down and instead harden each level before trusting the one built on it.

- [x] ~~**Sprint 1 — shot-type classifier over-predicting "serve"**~~ —
      investigated 2026-09-02 (HANDOVER §7). Root cause is **not** the
      classifier: it's the contact frame `detect_rallies` feeds the verifier
      being ~13f off, so groundstrokes look like serves. Classifier features
      body-normalised + version-guarded; pro labels confirmed net-harmful to
      the live model; real bottleneck = only 10 amateur backhand examples
      (needs Jack to source phone footage). No remaining code task here.

- [ ] **Phase C — activate the visual contact-frame student** (code done +
      wired 2026-09-03, no-op until trained). From `scripts/` with the venv:
  1. `python 07_ball_racket_tracking/build_contact_student_dataset.py --audio-only`
     — ~500 audio-teacher training rows. YOLO-heavy (~1h+), resumable, touches
     no `pro_database.json`. Run it once the ingest + shot-verification jobs
     are done so it isn't fighting them for CPU.
  2. `python 07_ball_racket_tracking/build_contact_student_dataset.py --human-only --force-relog`
     — backfills wrist-kinematics features onto the 196 old hand-marked rows.
  3. `python 07_ball_racket_tracking/train_contact_frame_model.py` — only ship
     if the `corrected (human)` slice beats `raw (human)` and the ~9f wrist
     baseline.
  4. Copy `data/07_ball_racket_tracking/contact_frame_model.pkl` +
     `contact_frame_model_meta.json` to the server (gitignored). Live path
     stays a no-op until the model is present *and* has earned trust.

- [x] ~~**Sprint 2 — fix `apply_serve_gate()`**~~ — done 2026-09-03 (code).
      `detect_rallies.py`: split `POINT_BOUNDARY_GAP_SEC` (12s) from
      `RALLY_GAP_SEC` (6s) so a detection gap mid-rally no longer slams the
      serve gate shut; `apply_serve_gate` is now **advisory** by default (keeps
      every non-serve shot, tags `after_serve`) with `--serve-gate
      strict|off`; `group_into_rallies` + clip bounds now use the audio-refined
      contact time. Serve-gate tests rewritten (189 pytest green). Still open:
      **run Sprint 3** (below), and wire accurate contact into
      `analyze_rallies_parallel.py` (still uses the wrist peak; audio-less
      clips → needs the Phase C visual student).
- [x] ~~**Sprint 2b — is Claude's shot classifier right?**~~ — answered
      2026-09-03/04. Cross-check ($0.45, over budget — my error) found **every**
      method ~35% on the 68 hand-labelled pro clips; Claude was not a usable
      teacher. **Shot classifier rebuilt** (HANDOVER "Part 5"): new geometric +
      trajectory-kNN ensemble, **40% → 84% on the pipeline domain, backhand
      24% → 84%**. Wired into `get_verified_shot_type` as the first student
      (shadow-mode until it earns trust, or used directly under
      `SKIP_CLASSIFIER_VERIFIER`). **Not committed — Jack's step.**
      - Open (Phase 2): serve recall still 44% (needs motion-direction
        features); the phone-upload domain is only ~56% (trajectory-kNN doesn't
        transfer — needs the ~809 unlabelled amateur swings + a real ML retrain).
      - ~~The **v2 ML retrain**~~ — done. The on-disk model is v2-bodynorm
        (since 2026-09-04), re-run `--no-log` again 2026-09-07 with the
        larger pro-review pool: unchanged (CV 0.629, backhand F1 0.40).
        The phone ML model is bottlenecked on amateur backhand footage
        (10 examples), not on retrain frequency. The pipeline **ensemble**
        (geom + trajectory-kNN, the real production path) is at 86.6% on
        the 634 pro labels as of 2026-09-07.
- [ ] **Sprint 3 — re-run `detect_rallies` on IMG_5755, Claude-free.**
      `RALLYMAX_SKIP_CONTACT_VERIFIER=1 RALLYMAX_SKIP_CLASSIFIER_VERIFIER=1
      python 11_highlight_clipping/detect_rallies.py <IMG_5755> <out>
      --serve-gate advisory` — $0. Expect serve share well below 78% and
      `rallies_detected > 0`. If plausible, one paid confirmation run with
      contact verification on (~$2–3).
- [ ] **Sprint 3 — only then re-run rally detection** (job 10 was `IMG_5755.MOV`,
      Claude-verified, ended at 0 rallies — don't re-spend Claude credits
      re-running this until Sprints 1–2 are done, or the same collapse just
      repeats).
- [ ] Revisit the separate, still-open **shot classifier accuracy gap**: docs
      claim 63.8% cross-validation accuracy but live agreement logs showed
      ~51% — may be the same root cause as Sprint 1, may be separate; check
      once Sprint 1's sample review is done. (Partly addressed by the
      geom+trajectory ensemble now being the production FH/BH path — 86.6%
      on the pipeline domain as of 2026-09-07 — but the phone-upload
      domain and the old `.pkl`'s CV-vs-live gap are still open.)

## Decisions needed (no clear default — your call)

- [ ] **Bug-sweep's deliberately-unfixed items**: an invite-code TOCTOU
      race (very low probability), a non-transactional bulk Overpass court
      upsert, `runPythonJson`'s subprocess timeout not escalating to
      `SIGKILL`, and what an empty `rallyIds: []` should mean when building
      a highlight reel (no-op / error / "use every rally").
- [ ] **Coaching-tip Claude verifier**: logic-review found it was silently
      live on every real request (up to 3 Anthropic calls per analysis) and
      disabled it. Decide if it should go live again on purpose later, with
      a real kill switch/cost budget, or stay offline-only.
- [ ] **SQLite → Postgres**: `pg` has sat unused for a long time while
      `DATABASE_URL` implies a migration that isn't scheduled. Worth an
      explicit "not now" or a real timeline, so it doesn't drift forever.
- [ ] **SQLite foreign-key enforcement**: root cause of three past
      orphaned-row bugs (now individually patched). Turning the pragma on
      needs a full DELETE audit first — some deletes are intentionally
      partial (e.g. account anonymization).
- [ ] **CI/CD for the hosted backend**: every deploy is still manual SSH +
      `git pull` + rebuild. Your call on GitHub Actions vs. something
      simpler, and whether the VPS should accept inbound deploy hooks.
- [x] ~~**Ball-speed feature**: scoped but not started.~~ — **built + merged**
      (in PR #38). `ball_speed.estimate_net_crossing_ball_speed_kmh` — net
      crossing via the net-keypoint local scale, gated on camera angle ≥ 30°,
      returns `None` silently when it can't be trusted. Surfaces as
      `result.ball_speed_kmh`. The far-side landing-zone extension is a
      deferred follow-up (needs a gravity model + court reference).

## Apple App Store prep (when you're ready)

- [ ] Apple Developer Program enrollment ($99/yr).
- [ ] Set up an EAS development build (`eas build`) — needed for real IAP
      and Google Sign-In (Expo Go can't do either).
- [ ] Add native iOS purchases via RevenueCat's native SDK once the EAS
      build exists.
- [ ] Privacy policy URL, app icons/screenshots, permission usage strings.
- [ ] Confirm the backend is hosted and reachable before submitting —
      Apple's reviewers need a working backend, not your home Wi-Fi.

## Read when you have time (no action required)

- [ ] `docs/future-ideas.md` / `AI's_ideas.md` — this session's brainstorm
      pass (product features, ML pipeline improvements, data-quality
      opportunities, tech debt), sized S/M/L. Nothing here is committed to,
      just worth a read.
