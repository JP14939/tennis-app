# RallyMax — Status

**What this file is:** a short, hand-curated snapshot, overwritten each time
someone updates it — not a log. Read this first if you just want to know
where things stand in under 2 minutes. For the full detailed history, see
`HANDOVER.md` (dated build log) and `TODO_MANUAL.md` (full backlog, also
chronological) — this file is a filter on top of those, not a replacement.

## Local-only artifacts pending server transfer

A running manifest, not a log entry — keep this current as items are built
or transferred, rather than letting the fact scatter across `HANDOVER.md`
session entries. CD auto-deploys code but never `data/` (gitignored), so
everything below is live locally and on the pre-transfer, older version on
the hosted server:

- [ ] Rebuilt `pro_database.json` (v4, stride-1, metric z, serve re-anchored)
      + `overlay_trajectories.json` — server still on the pre-2026-09-02 DB
- [ ] Fine-tuned ball detector `best.pt` (2026-09-08 retrain, KEPT)
- [ ] `onset_classifier.pkl` (audio-onset contact detection)
- [ ] Net-detection keypoint weights (`10_net_detection`) — needed for the
      behind-baseline view gate (`net_not_found` fires without it)
- [ ] `clusterCourts.js` output (`clubs`/`club_courts` rows) — hosted DB has
      zero clubs

None of these crash when absent — each degrades to a fallback (pose-peak
contact, generic COCO ball detection, advisory-only view gate) — which is
exactly why they're easy to forget. See `JACK_TODO.md` Phase 3b.

**Last updated:** 2026-09-11 (later⁵) — **Root-cause pass on recurring
cross-session problems — process guardrails added, no ML/behavior changes.**
Jack asked for a read-through of `HANDOVER.md`/`TODO_MANUAL.md`/`JACK_TODO.md`
to find what kept tripping up different sessions. Five cross-cutting patterns
found: (1) the same broadcast/bench-to-real-footage generalization gap was
independently re-discovered 4+ times (camera-angle normalization × 3 attempts,
shot classifier, contact-frame detection); (2) eval-harness bugs repeatedly
produced a false read on whether a fix worked (stale results cache, an
overfit same-set-measured rubric gap, a frozen-checkpoint "regression" that
wasn't real); (3) uncommitted work has piled up and tangled across sessions
(the 2026-09-10 three-way split); (4) `data/` never syncs to the server
automatically and the gap degrades silently instead of erroring; (5) score
calibration (roadmap 1b) has been re-flagged as the top pre-launch risk in
4-5 separate session summaries without ever shipping past bench-only.
Shipped: `CLAUDE.md` gained a **"Known Dead Ends"** register (7 documented
failed approaches + why, so a future session checks before re-attempting),
an **"Eval hygiene"** rule (explicit cache invalidation, CV-not-same-set
numbers), and a **"Commit discipline"** convention (session-scoped branches
for multi-session bench work instead of a shared dirty tree); `HANDOVER.md`'s
"Read This First" now points to these; this file gained the "Local-only
artifacts pending server transfer" manifest above; a small shared helper
`scripts/00_utils/eval_stamp.py` (git-SHA + model-fingerprint stamping,
mixed-version detection) extracts the pattern `evaluate_amateur_dataset.py`
hand-rolled after the 64.5%→54.4% false-regression incident, covered by
`test_eval_stamp_pytest.py` (8/8 green); `JACK_TODO.md` got an explicit
**1b-decision** recommendation (stop axis-hunting, ship B2 as PROVISIONAL
once all three shot types clear a minimal CV bar, refine against real usage
instead of more bench iteration). This documentation and utility batch was
reviewed, tested, committed, and pushed as `2f750e6`; it made no ML-data
deployment changes.

**Prior — 2026-09-11 (later³):** **Shot classifier: amateur relabel
review done (backhand 10→26 examples), which exposed a real eval-cache bug
and a much worse honest amateur-accuracy number, then a cheap fix recovered
a chunk of it.** The amateur backhand-relabel pass finished (248/248
reviewed). Re-running the eval showed no change at first — traced to
`evaluate_shot_classifiers.py` silently skipping any clip id already scored
in its cached results file, so the relabel's effect was invisible until the
stale amateur rows were cleared by hand. Honest number with the full
26-backhand set: **ensemble accuracy 56.3%** (was a stale, inflated 68.1%
measured on only 10 easy backhand clips), backhand recall a real **31%**
(not 80%). The `ml_phone` model's backhand recall specifically crashed
100%→19% on the new clips — confirms its amateur self-reported numbers were
memorization (train==test leakage), not real generalization, exactly as an
existing code comment warned. Separately, pulled raw per-clip debug output
for misclassified serves and found the sustained-overhead serve signal was
genuinely present but arriving too late in the analysis window to cross the
detection threshold — widened `SERVE_WINDOW_POST_SEC` 0.5s→0.8s
(`extract_training_features.py`), which **recovered serve recall 60%→78%
and geom accuracy 58.0%→66.7% on amateur** (pro also improved: geom
67.1%→73.8%, serve recall 80%→84%), with no precision cost. One-line
constant change, **committed and pushed in `2f750e6`**. Forehand/backhand confusion itself barely
moved — likely a contact-frame-timing issue on specific clips, not a window
problem; queued as the next experiment (correlate remaining errors against
contact-frame source: audio vs pose-peak vs manual) rather than retuning
geometry thresholds blind. Full detail: `HANDOVER.md` "Session 2026-09-11
(later³)".

**Prior — 2026-09-11 (later²):** **Metric 3D depth: built + kept, but
depth as a SCORING signal is dead (negative result), confirmed on real
footage.** Jack asked to "make more of the database 3D" (every trajectory, not
just the ~48% that got fully yaw-rotated). Built it: `extract_trajectory_from_index`
decouples the z source from x/y — x/y unchanged, z always taken from MediaPipe
`world_landmarks` (soft-yaw-rotated, or unrotated-but-metric), a new `soft_yaw`
(= `usable_yaw` minus the deadband check). Schema `traj_version` 4; pro DB
re-sliced, all 648 entries v4, DB-wide z abs-median now 0.45 (was ~1.5 on the
unrotated half) — matches x's 0.51. `phase_breakdown.Z_ROTATION_BLEND → 0`
(the one live-scoring change; reverts `body_rotation` to its months-stable
angle-only form, since its `Z_TO_DEG_SCALE` constant was fit to the old noisy
image-z). Commits `be1e1c4`/`4d19e2b`, local, **not pushed**. **But**: the
depth rubric axes this was meant to unlock (`contact_depth_ahead` etc., bench
separation up to +30) were then tested against Jack's own 6 known-angle fence
clips and **failed** — the same axis ranged [-0.19, +4.27] for the identical
self-fed forehand at the identical 0° camera position. Pose noise, not
technique. Same broadcast-vs-phone gap as the shot classifier (86%/68%).
**Decision: 3D depth as a live-score signal is done — a negative result, not
a shipped feature.** Written to memory
(`project_metric_z_v4`/`project_viewpoint_normalization_dead`) so it isn't
re-attempted; roadmap 1b's real foundation stays the 2D axes (`tempo_peak_frac`
+62, `racket_body_range` +51, `backswing_depth` +37…). One thread stayed open:
Jack's "calibrate once per session" reframe (camera→net angle is a session
constant — read it from one deliberate square-and-still hold instead of a
per-clip lead-in). Built the gate (`calibration_hold_test.py`,
`12cab96`/`13771e7`) and ran it against the existing (self-fed, NOT
deliberately-square) calibration footage as a lenient proxy: **RED** —
within-hold facing estimate still bounces ±30° even while standing still
(depth noise, not squareness), head-on clip reads −57° median. Genuinely
untested on a *clean* deliberate hold though (the self-fed footage confounds
"not square" with "noisy even when square") — **needs Jack to film ~6 clips**
per the script's docstring before the calibrate-once idea can be closed out
either way. Full detail: `HANDOVER.md` "Session 2026-09-09/10/11 — 3D depth";
plan `~/.claude/plans/dreamy-exploring-eich.md`.

**Prior — 2026-09-11 (later):** **No-audio visual contact-frame: real
baseline measured for the first time, two fixes shipped (24%→38%≤3f on pro
broadcast), first-ever REAL amateur-footage numbers (25%≤3f — the honest
target, not pro's flattering 38%).** Jack: "verify the audio sync, plan ways
to improve it, even redesign or hand-label." Scope: the NO-AUDIO visual
fallback only (audio onset already works well, ~1f/89%≤3f). Committed the
long-stuck Roadmap 1c (`2791e7e`/`f28f3b5`, was blocked on a measured-neutral
serve gate — dropped as a blocker) plus a stride-1 eval-harness rewrite
(the old harness was silently running at the pre-rebuild stride-3, quantising
every error number). **First full-scale (370-clip) baseline: 12.9f median,
24%≤3f** — `ball_occlusion_gap` (any ≥2f ball-gap = contact) fires on 57% of
clips but is only 18%≤3f, with several ±100f+ blowups; a perfect-anchor
ceiling run showed it's a genuinely unreliable *method* (31%≤3f even with a
perfect anchor), not just an anchor problem — while `ball_racket_proximity`
IS excellent at ceiling (77%≤3f). Shipped both fixes gap-method first:
`_find_gap_contact` now requires the ball's tracked motion to actually be
consistent with a real strike (not just any 2-frame detection gap), and the
groundstroke anchor now recentres toward peak wrist *deceleration* (hand
brakes at contact) instead of peak speed (the follow-through). **Result:
12.9f/24%≤3f → 7.7f/38%≤3f** — the two fixes compound (gap method usage
dropped 57%→25% as it correctly stopped trusting spurious gaps; the freed
clips landed on the now-more-accurate proximity method). Full repo `pytest`
376/376 green. Then built real amateur validation with **zero manual
marking**: Jack's own YouTube amateur-match footage has audio even though the
cut clips don't (same `cv2.VideoWriter`-drops-audio issue as everywhere
else) — ran the SAME trained onset classifier against it (caught + fixed a
real bug: a whole-match audio window breaks the onset detector's
loudest-moment normalisation) for **85 confident, trustworthy labels**. Real
result: **9.65f/25%≤3f on amateur footage** vs pro's 7.7f/38% on the same
pipeline — the "no evidence at all" bucket nearly triples (10%→27%) on real
footage. **25%, not 38%, is the honest number the next piece (a supervised
per-frame contact classifier, the same reframe that made audio-onset work) needs
to beat.** The 2a/2b code and amateur-labelling scripts were reviewed, tested,
committed, and pushed in `2f750e6`. Full detail:
`HANDOVER.md` "Session 2026-09-10/11"; plan file
`~/.claude/plans/swirling-popping-flame.md`.

**Prior — 2026-09-11:** **Roadmap 1b: rubric de-overfit + two new Dev
Page review tools, still bench-only.** Added `redesign_similarity.py curate
--folds 5` (real 5-fold CV) and found the old +20.0 combined rubric gap was
overfit — honest numbers: forehand +1.9 (no real signal), backhand +28.7
(n=5, not trustworthy), serve +26.1 (real). Hunted new forehand axes at
Jack's request: `hip_shoulder_lead_contact` (shoulder-vs-hip angle AT contact,
sep +45, the session's strongest single axis) got **forehand to +12.2 CV**,
crossing target — found and fixed a real angle-wrap bug in it along the way.
Built **Amateur Clip Review** (Dev Page tool, re-review the 248-clip amateur
eval set + a second 81-clip never-reviewed batch) — Jack finished the whole
329-clip queue, **backhand 5 → 26+6**, unblocking the CV re-run. Hit a real
"why didn't my progress save" gap (nothing was lost, the tool just had no
memory of what it had shown you) — fixed with server-side reviewed-filtering,
an audit-log JSONL, a "✓ Done" button + **D** keyboard shortcut. Jack then
hand-picked 4 clips he judged clearly bad; they scored 40-52 (near/above the
amateur median) — pulled actual video frames and confirmed by eye: all 4 have
a rushed/minimal backswing our contact-*snapshot* axes can't see. Added
`swing_amplitude` (whole-window motion, not a snapshot) — helps, not yet
CV-stable. Jack's follow-up idea (tighten the pro reference pool itself) led
to **Pro Quality Review** (2nd new Dev Page tool, ⭐Gold/OK/✕Exclude tagging,
G/O/X shortcuts) — built with its own isolated log after testing showed
folding it into the existing verdict log would have let a later quality tag
silently corrupt ~5 other scripts' "is this entry excluded" reads. **0/648
pro clips tagged yet.** Backend 631/631, pytest 700/700, all green throughout.
Still **entirely uncommitted, entirely bench-only** — B2 (the actual
production scorer) hasn't started. Full detail: `HANDOVER.md` "Session
2026-09-11"; plan file `~/.claude/plans/reactive-enchanting-metcalfe.md`.

**Prior — 2026-09-10 (later):** **ideal-swing reference clips DONE +
pre-release roadmap consolidated.** The display-only FH/BH/serve compare clips
are produced (Luma Dream Machine "Modify Video" — real swing footage re-rendered
with a new character, keeping the motion; Jack ran Luma, Claude removed Luma's
watermarks + finalised, Jack cropped/retimed in CapCut) and wired into
`frontend/assets/reference/` + `referenceClips.js` (web export verified).
**Uncommitted.** Jack to refine `CONTACT_SEC` (eyeball estimates in now) +
device-test. Full narrative: `HANDOVER.md` "Session 2026-09-10 (later)".
**Pre-release picture** (Jack asked "what's left / can we test?"):
consolidated read in `~/.claude/plans/snazzy-jumping-rain.md`. Critical path:
**(1)** `master` is **22 commits ahead, unpushed** and must stay so until
**JACK_TODO 3b** — the server `data/` transfer (rebuilt `pro_database.json` +
overlays + `onset_classifier.pkl` + ball `best.pt`, then `clusterCourts.js` on
the box); pushing first ships stride-1 user trajectories against a stride-3
server pro DB → score drift. Until 3b, **app testing against live tests stale
ML.** **(2)** The working tree is now **committed** (2026-09-10, later²) —
~34 commits ahead of `origin/master`, still **unpushed** by design (same 3b
gate). The tangle was split across three sessions: ea took roadmap 1c contact
detection (`2791e7e`/`f28f3b5`), 1b (`redesign_similarity.py` etc.) stays
uncommitted with session 0f, and this session committed the rest — net
detection, pro racket enrichment, serve-reanchor yaw parity, the pre-release
backend (security + guest `/analyse`), and the frontend pre-release stack
(score de-naming, reference clips, review prompt, onboarding Phase 1).
`stash@{1}` `jack-wip` is dead (125 commits stale, contents already merged) —
safe to `git stash drop`. **(3)** Roadmap **1b + 1c are both blocked on a Jack
decision, not Claude work**: 1c's serve eval already ran neutral (no
regression/no improvement; ship-as-safe vs tune `APEX_PLATEAU_TOL`) and its
claimed `compare()` wiring was lost in the churn; 1b's rubric is +20 gap but
PROVISIONAL (forehand still weak, depth axes still weighted, bench-only not
production). Store plumbing (Apple enrollment — long pole, EAS build, RevenueCat
native SDK, privacy policy/assets, Resend domain, DB backups, repo→private) and
`[infra]` budget caps on KIE/Anthropic/AWS/Resend/RevenueCat are all still open
and all Jack-only. Prior:

**2026-09-10 — metric-3D v4 pro-DB rebuild + verifier
investigation. Roadmap 0a done; 3D-depth scoring = negative result.** The pro DB
was rebuilt end-to-end: `sample_every` 3→1 (pose re-extract at every frame +
MediaPipe world landmarks, ~4.75 h, 13/13 files), pro-side yaw wiring, then a
v3→v4 re-slice of all 648 entries (`traj_version 4`, z decoupled from x/y and
always metric-world-derived; `verify:db` 99/99). Committed `6cfee83`..`4d19e2b`,
**local, NOT pushed** (user-side stride-1 can't reach the server before the
rebuilt pro DB is transferred). One live change: `phase_breakdown.Z_ROTATION_BLEND
= 0.0` (v4 shifted every z scale; reverts `body_rotation` to angle-only,
reversible). **What it bought:** DTW pro-vs-amateur separation +7% → +11%. **What
it didn't:** the 3D **depth scoring axes are a negative result on real footage** —
bench (broadcast) `contact_depth_ahead` sep +30/+17/+18 and rubric gap +7.8→+20.0
(mechanically re-curated `CURATED_AXES`, `4d19e2b`, **flagged PROVISIONAL**), but
on Jack's 6 fence clips `contact_depth_ahead` swings [−0.19, +4.27] for the *same
forehand at the same 0° angle* — pose noise, no signal. **3D depth as a score is
done; pull the depth axes from `CURATED_AXES`; roadmap 1b's foundation is the
strong 2D axes** (`tempo_peak_frac` +62, `racket_body_range` +51, `backswing_depth`
+37, contact wrist pos, follow-through). Also: **"calibrate camera angle once per
session" tested RED** (`calibration_hold_test.py`, `12cab96`/`13771e7`) —
within-hold facing IQR 59°, a deliberate hold won't beat the depth noise; third
independent confirmation camera-angle normalization fails at fence distance.
**Verifier:** the amateur-eval "64.5% → 54.4%" was NOT a regression — the old
number was a stale multi-version append-only checkpoint; the verifier reads a
frozen-Aug pose cache, never touches the pro DB or stride-1, and **is not in the
live upload path** (`analyse.js` → `compare_swing.compare()` only). Real current:
54.4% verifier / 49.1% classifier, stamped baseline
`data/17_amateur_eval/results_baseline_2b27847.jsonl`. Eval hygiene shipped
(per-row `git_sha`+model-hash stamps, `--fresh` flag, `RALLYMAX_BALL_MODEL` env —
uncommitted). The real verifier issue is absolute: ~51% precision, `occlusion_gap`
keeps ~every clip as "real" → JACK_TODO **2b**, next session, not launch-blocking.
Prior: 2026-09-08 (later⁵ — **score presentation de-named.** Jack's
call: stop showing "matched to <pro>" (most pro-DB clips aren't identified). The
"Other close matches" #2/#3 list is **removed** from `ResultsScreen` — that kills
the visible contradiction where the hero score (`overall_score`/`PHASE_SCALE`) and
the runner-up numbers (`similarity`/`scale=0.4`) disagreed on screen. Hero score is
now the only 0–100 shown; caption → "How closely your <shot> matches pro
technique"; Sync Compare pane → "Pro swing"; History/Home/Coach/share/signup copy
all de-named; `analyse.js` → `--top 1`. `npm test` 620 green, frontend files
babel-parse clean. **`PHASE_SCALE` itself is still uncalibrated** — that's roadmap
1b, CPU-blocked. Prior: later⁴ — roadmap **1a** the behind-the-baseline view gate, now
**ENFORCED for launch** (2026-09-09). `infer_angle.evaluate_view_usable(...,
net_debug=)` blocks an upload when it isn't a clean behind-baseline shot with the
whole net in frame: reasons `front_view` / `side_on` (≥78°) / **`net_not_found`**
(trained keypoint model didn't locate the net) / **`net_truncated`** (a post runs
off the frame edge — `posts_inframe_frac < 0.5`). `angle_unreliable` (net found,
conf <0.45) stays a soft warning. `compare_swing.compare()` raises `ViewGateError`
(code `VIEW_NOT_USABLE`) on a `severity:'block'` reason by default —
`RALLYMAX_ENFORCE_VIEW_GATE=0` restores advisory mode for batch eval over legacy
footage. `check_camera_setup*` returns `view_severity`; `ContactMarkingScreen`
hard-stops on `block` (⛔ + "Record another swing"), `ResultsScreen` shows a
"Check your camera setup" screen. **Why enforce not normalize:** two attempts to
*correct* camera angle (pose-yaw, net-width un-foreshortening) both failed on real
footage — see `~/.claude/plans/purrfect-jingling-rose.md`. **Open:** on-device
live-calib click-through + confirm hosted `calibration_server` :5055 net weight
present. Prior: roadmap **1b** research: the swing score
can't be fixed by rescaling. `scripts/17_amateur_eval/calibrate_similarity.py`
proved **nearest-pro DTW distance can't tell a pro swing from a decent
amateur's** (amateur 0.48 vs held-out pro 0.45 — inside the noise; ~10 DTW
variants failed). Jack's call: **reframe the number + build a rule-based
"technique score"** grading a swing on biomechanical axes (contact height,
elbow extension, tempo, racket looseness…) vs the pro DB's own distribution
per shot type + camera view. Bench (`redesign_similarity.py axes`/`rubric`):
view-conditioning alone moved the pro-vs-amateur gap **+3 → +13**; backhand
**+32**, serve **+23**, forehand **+10** (weakest). Code prep done; **2 CPU
jobs queued** (blocked on net-model training) — pro racket-mechanics enrich
(~35 min, also revives a dead `phase_breakdown` racket feature) + grow the
held-out test set 18→58. Runbook + full state:
`scripts/17_amateur_eval/RESUME_swing_score_redesign.md`. Nothing production/
frontend/backend touched. This **supersedes** the "unify PHASE_SCALE vs
scale=0.4" framing below — unification is cosmetic, the metric is the problem.)
Prior: roadmap **1c** coded: visual no-audio
contact backstop wired into `compare()`, serve-apex plateau recentred,
`contact_source` field + onset model in `/dev/ml-status`. **Not committed** —
blocked on a serve accuracy-eval run that was paused for CPU; resume via
`scripts/07_ball_racket_tracking/RESUME_1c_contact_eval.md`. HANDOVER "Session
2026-09-08 (later²)".) Prior: ball-detector retrain finished + gated, new
`best.pt` KEPT (item 10), still needs manual server transfer —
**ML-reliability roadmap built; release date slipped.**
Jack reviewed ML reliability across the whole app and decided: **no fixed launch
date**; every premium feature must be reliable at launch, so the highlights/ML
work that 2026-09-07 said to defer is **now in scope for v1**; **behind-the-
baseline camera view only** for v1; **invest in a visual (no-audio) contact-frame
model**; serve classification ~80% is acceptable for v1; **build a real highlights
eval set** from Jack's own fence footage. Roadmap (Phase 0 kickoff → 1 core loop
→ 2 premium features → 3 pre-release gate) is in `JACK_TODO.md` ("ML-reliability
roadmap"); full plan + designs in
`C:\Users\jackp\.claude\plans\okay-so-i-finished-lovely-adleman.md`; narrative in
`HANDOVER.md` "Session 2026-09-08". **Nothing coded yet.** Facts the review
nailed down: no behind-view gate exists (unsupported views silently score against
the whole pool); the hero score (`PHASE_SCALE=1.8`) and the #2/#3 match scores
(`scale=0.4`) use **different, uncalibrated scales and must be unified**, and no
labelled match-quality set exists; the 86.6%/68.1% classifier numbers are
broadcast-TV / YouTube, not the real fence-footage domain; `find_contact_frame`
never reaches production; the serve-gate bug is already partly mitigated
(`advisory` mode); racket keypoints feed the live body-rotation score but not
DTW; the tip verifier is dead (leaked API key) and the 3 match tip-sets can
contradict. Prior below.

**Prior — 2026-09-07 (later still³):** **main loop verified across ALL THREE layers** (local Python engine, local full stack, live server), on top of the 2-week launch-readiness review. 6/6 engine cases (incl. no-mark auto-detect + left-handed mirror) exit 0 with valid JSON; `POST /api/analyse` on :5000 returns HTTP 200 + full overlay payload, `/api/history` round-trips, free-tier cap fires 403 after 2; the hosted server returns a **byte-identical score** to local (engine parity) and its candidate pool confirms it's still on the older pro DB. **The core loop works end to end, locally and in production.** New flaws found this pass: **the hero score and the runner-up match scores use different scales** (`overall_score`/`PHASE_SCALE=1.8` → ~62–70 for the top match vs raw `similarity`/`scale=0.4` → ~25–38 for #2/#3 of the *same* quality) — so `ResultsScreen` shows "62/100" then "other matches: 30, 25" right below; serve `similarity` scored 18/100 with all-practice-footage matches; camera-angle confidence measured 0.05–0.64 (mostly ~0.3) on real clips. Full trace: `HANDOVER.md` "Session 2026-09-07 (later still³)". Prior same day (later still²): ranked weak points — (1) **score presentation/calibration** — the number the user reads as *their score* is governed by `PHASE_SCALE`, not the `scale=0.4` that `JACK_TODO.md`'s calibration task names; both need a look, and they need to agree (most likely thing to make the product feel broken to a first user); (2) auto contact detection ≈9f off unless the audio model is deployed + the clip has audio (not confirmed on server); (3) server still on the pre-2026-09-02 pro DB (can't copy until practice review done); (4) camera-angle confidence usually low → silently compares against the whole shot-type pool; (5) `sample_every=3` timing cap; (6) no behavioral route test; (7) z-depth disabled; (8) serve is the weak shot everywhere. Full trace + blocker list: `HANDOVER.md` "Session 2026-09-07 (later still²)". The ML-reliability sprint tail is downstream of rally-detection/highlights (a secondary feature) — recommend deferring past launch. New pre-launch checklist in `JACK_TODO.md`. Prior same day: **local maintenance run: court clustering + shot-classifier retrain.** `clusterCourts.js` run against the local dev DB for the first time (100m node-mesh): 33,222 courts → 3,848 clubs / 14,696 courts-in-a-club, 2,180 clubs postcoded (rest non-UK OSM), `verify:db` 98/98, `clusterCourts.test.js` 10/10. `app.db` backed up first (`app.db.bak-20260907`); `club_watches` was empty so no watch migration/orphaning. Shot classifier: all 3 feature extractors re-run — Pro Clip Review verdict rows 524→632 (FH 323 / BH 229 / serve 80). `shot_classifier_model.pkl` retrained `--no-log` (CV acc 0.629, backhand F1 0.40 — unchanged; phone ML model is bottlenecked on *amateur* backhand footage, none added). `evaluate_shot_classifiers.py --set both`: production **ensemble** now **86.6%** on the 634 pro labels (FH 89 / BH 86 / serve 80), up from 83.6% on 2026-09-04 — the bigger reviewed pool helped the pipeline path; phone ensemble flat at 68.1%. All local-only, nothing committed/pushed/deployed. Prior same day: `batch/2026-09-06-find-games-rally-shots` integrated into `master` and deployed (PR #38, 171 files / ~22k lines: ~2 weeks of feature work that had never reached master — Find Games mesh clubs, ball speed, audio-onset contact, shot-classifier + contact-verification ML, practice ingest, serve anchor, overlays + interpolation, match-quality flag). CD run 34143861953 ✓, health check passed, live `/health` OK. Full suite green on the merge (backend 620, verify:db 98, pytest 289). Prior same day: match-quality flag, overlay interpolation, racket-detection measured (item 10).

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
   **`clusterCourts.js` now actually run against the local DB (2026-09-07):
   3,848 clubs from 33,222 courts.** The hosted DB still has no clubs — a
   `data/` transfer is still the open step there (`club_courts`/`clubs`
   rows aren't touched by CD).
2. **Postcodes + crowd-sourced club naming, same session.** Free postcode
   lookups (postcodes.io, no API key/cost — chosen explicitly over paid
   Google Geocoding) on courts/clubs/areas; a real backfill already ran
   against local data (16,711/33,222 courts resolved; club postcodes filled
   during the 2026-09-07 cluster run — 2,180/3,848). Club naming now
   works like court verification already did: a user proposes a name, 2
   others confirm it, done — no paid automated lookup needed. Many derived
   club names are the generic "Courts near Tennis Court" fallback (all
   constituent courts carry the default OSM tag) — crowd-sourced naming is
   the intended fix.
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
   to pick up more as Jack's review count climbs. **Re-run 2026-09-07:
   `training_features_from_pro.json` now 632 rows (FH 323 / BH 229 / serve
   80). Feeding the trajectory-kNN / ensemble path lifted the pipeline
   ensemble 83.6% → 86.6%. The phone `.pkl` (`--no-log`, amateur-only) is
   still flat — `--use-pro` collapses amateur backhand F1 (0.40→0.15), so
   pro rows stay out of that model; the real lever remains new *amateur*
   backhand footage.**
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
   **Clean detector retrain — DONE + KEPT (2026-09-08).**
   `prepare_ball_yolo_dataset.py` had a real train/val leak (76 dupe images)
   + frame-level split — both fixed; dataset rebuilt from the 354 server
   labels with **0 image / 0 clip overlap** (262 train / 76 val).
   `train_ball_detector.py` now imgsz 480 + multi_scale + scale 0.6. The run
   stalled overnight at epoch 107/150 (laptop slept), resumed 2026-09-08 →
   150/150. New `best.pt` (epoch 126): **clean-val mAP50 0.592** (leak-free
   split, not comparable to the old leaky 0.558). Gates run: at-contact
   **91.7%** / conf **0.64** (vs generic baseline 50% / 0.41; bar was 93.3%
   — ~1 clip under, confidence up); near-player FH/serve **~94-96%**,
   **backhand flat at 0.77**; full-frame far-ball **79%**. Jack's call:
   **KEEP** — no real regression, honest eval, good enough for v1. **Not on
   the server yet** (manual `data/` transfer, tracked in JACK_TODO /
   TODO_MANUAL alongside the pro-DB copy). Still-weak: backhand + far/wide
   balls — a future retrain, blocked on cleaning the ~8 sloppy wide-court
   labels + more amateur backhand footage. Not launch-blocking. Full writeup:
   HANDOVER.md "Session 2026-09-08 (later)".
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
   external users — biggest open strategic question. **Jack now wants to
   publish in ~2 weeks (target ~2026-09-21).** Core loop verified working
   across all three layers (engine / local full stack / live server) 2026-09-07
   (see the "Last updated" line + `HANDOVER.md` "Session 2026-09-07 (later
   still³)"). Launch is gated on plumbing, not the ML
   sprint tail: Apple Developer enrollment (long pole), EAS build, RevenueCat
   native SDK, privacy policy + store assets, Resend sender domain, copying
   the current `data/` + models + `clusterCourts.js` to the server, one real
   end-to-end live upload, off-box DB backups, device click-throughs, repo
   back to private. Full checklist: `JACK_TODO.md` "2-week launch push".
   **Product-quality risk to weigh first: score presentation.** The user's
   headline score is `overall_score` (`PHASE_SCALE=1.8`, ~62–70 for a decent
   swing); the 2nd/3rd match scores shown right below it are raw `similarity`
   (`scale=0.4`, ~25–38 for the same quality). They contradict on screen and
   neither is calibrated against a labelled match-quality set. Decide whether
   to recalibrate `PHASE_SCALE` and/or unify the two scales before real users
   see numbers — `JACK_TODO.md`'s calibration item names only `scale=0.4`,
   which is the wrong (or at least incomplete) knob.
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
    *Set aside during the merge:* `stash@{0}` on the batch branch held a
    parallel session's racket-detection imgsz-calibration + serve-anchor
    eval + wide-court ball labeling WIP. The wide-court labels have since
    been reviewed (see item 12); the rest still needs that session or Jack.
    `stash@{1}` (`jack-wip`) untouched.

    *Also not on the server:* the re-anchored `pro_database.json` /
    `overlay_trajectories.json` from serve-anchor Phase 1b (2026-09-07, item
    10) — same manual-transfer situation as the practice-ingest DB, with
    backups (`*_pre_serve_reanchor_20260907_124604.json`).
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
18. **Pre-release check thread (2026-09-09/10) — security + onboarding +
    rating prompt, all uncommitted.** Driven by 4 external videos; running
    checklist in **`PRE_RELEASE_CHECK.md`** (new). Done in code: IP
    rate-limit backstop on `/analyse` + `/compare-videos`, `securityHeaders.js`
    middleware, `multer` DoS bump + unused-dep removal, `analysis_usage.daily_cap`
    integrity check; a **guest onboarding flow** ("gate at the reveal" —
    `/analyse` is now `optionalAuth` + a 2/24h guest IP cap, new
    `OnboardingScreen`, `ResultsScreen` guest reveal-gate, and a **latent bug
    fixed** where `runAnalysis()` sent no auth header); an `expo-store-review`
    rating prompt. `/code-review` + a fix pass applied 8 follow-ups. Backend
    suite 631 green, `verify:db` 99/99, web bundle clean. **Biggest open
    item: `[infra]` budget caps + alerts on KIE / Anthropic / AWS / Resend /
    RevenueCat and scoping the AWS IAM key to S3-only** (both security videos
    featured 5-figure surprise bills). Also open: ASO store name / keywords /
    screenshots (B1/B2), onboarding Phase 2, device tests. Narrative:
    `HANDOVER.md` "Session 2026-09-09/10 — pre-release check". Working tree
    tangles this with Jack's own WIP on `analyse.js` / `ResultsScreen.js` /
    `SignupScreen.js` — commit strategy is Jack's call, not yet made.

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
  code kept with wiring OFF
- Fine-tuned ball detector `best.pt` — retrained + kept 2026-09-08 (item 10),
  **live locally, not yet transferred to the server**
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
