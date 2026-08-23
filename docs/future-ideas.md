# Future Ideas

A running, append-only brainstorm log for RallyMax. Each dated section below
is a snapshot from one ideation pass — grounded in the codebase and
`HANDOVER.md`/`TODO_MANUAL.md` as they stood that day, not a committed
roadmap. Older sections are kept for history; add new ones at the top.

Sizing is rough: **S** = a session or two, **M** = several sessions /
one focused effort, **L** = a real project, likely needs Jack's call on
scope or timing before starting.

---

### 2026-08-23

Context for this pass: read `CLAUDE.md`, all of `HANDOVER.md` (items 1–41
plus the pipeline/backend backlogs), and `TODO_MANUAL.md`. Ideas below try
to build on what's already shipped or already explicitly scoped, and
deliberately avoid re-proposing things the docs show were tried and
declined — e.g. DTW-level `Z_WEIGHT` was deliberately left at `0.0` after
two real attempts (extremity landmarks are 2–4x noisier than shoulders/hips
— see HANDOVER item 32), the direct-regression racket keypoint model was
abandoned in favor of the YOLO-pose approach, freeform Claude ball-bbox
labeling failed 3x before the classical HSV-candidate pipeline replaced it,
and the coaching-tip verifier is deliberately not being trained on
synthetic pro-vs-pro data since that was judged unable to teach it anything
about real deviations.

#### Product features (building on the DTW pro-comparison core loop)

- **Weakest-phase drill recommendations.** Every analysis already returns a
  four-phase breakdown (backswing/contact/follow-through/body-rotation).
  Auto-surface the 1–2 drills tied to a user's most consistently weak phase
  right on `ResultsScreen`, using the `drill_items`/issue-id linkage the
  Drills feature already has room for. Turns a static score into a concrete
  next action, and the drill content already exists for forehand/backhand/
  serve. **M** — mostly plumbing (map phase → issue_id → drill), a little
  UI. Unblocks: makes the 30 seeded drills discoverable instead of only
  reachable by manually browsing the History → Drills tab.
- **Session/rally summary dashboard.** The rally-detection + shot-verification
  pipeline (item 7, item 29) already produces real per-rally data
  (`rally_clips.outcome_tag`, `swing_count`, `duration_sec`) for a full
  match upload — currently only consumed by the player-type estimator. A
  dedicated "session recap" screen (shots per rally, longest rally,
  consistency trend across the session, winner/error rate if tagged) would
  make a full-match upload feel like it produced something beyond 80-some
  individual History rows. **M** — no new ML, it's aggregation + a screen
  over data that's already being written.
- **"Which pro do you swing like" share card.** Lightweight, fun extension
  of the existing top-match result — a shareable card naming the matched
  pro across a user's last N analyses (e.g. "you swing most like Federer
  73% of the time this month"). Reuses `ResultShareCard.js`'s existing
  capture/share flow. **S** — good low-effort virality lever, no backend
  changes beyond one aggregation query.
- **Coach-note PDF/image export.** Coaches can already leave per-analysis
  notes tied to a phase/timestamp (`coach_notes`); a student currently has
  to be in the app to see them. A one-tap export (image or simple PDF) of
  a result + its coach notes would let a coach's feedback travel outside
  the app (text a parent, email a player). **S–M**.
- **Practice-streak nudges.** Push infra already exists and is used for
  highlights/messages/Find Games. A simple "you haven't logged a swing in
  N days" or "3-day streak — keep it going" notification, tied into the
  rank-tier system that's already count-based, would give the gamification
  work a retention hook it doesn't currently have. **S**.
- **Seasonal/weekly leaderboard resets.** The leaderboard feature (item 18)
  is currently a single all-time ranking. A weekly or monthly reset (kept
  alongside the all-time board, not replacing it) would keep it relevant
  for a user who isn't going to out-rank an early adopter with 600 great
  swings logged. **S–M** — mostly a `created_at`-windowed query variant and
  a UI toggle; no new tables needed if the existing rank data is just
  filtered by date range.
- **Serve type/speed auto-tag.** Full fault/in-or-out detection is
  correctly scoped as a bigger, separate project (already flagged in the
  pipeline backlog as out of reach without real ball-landing tracking).
  A much smaller, already-reachable slice: auto-tag serve analyses as
  flat/kick/slice using existing pose + racket-keypoint signals at contact,
  surfaced as a stat on the player card. **M** — new lightweight classifier
  in the same teacher/student pattern already used elsewhere, scoped to
  serves only.

#### ML pipeline improvements (numbered `scripts/` stages)

- **Ball detector Phase 3: train + integrate.** Phases 1–2 are done (124
  confirmed + 230 pending manual review, `$0.38` spent). Once the manual
  review backlog clears, actually fine-tuning a detector on the combined
  labeled set and wiring it in — as a candidate replacement/supplement to
  the generic pretrained YOLO racket/ball detector currently used in
  `07_ball_racket_tracking/` — is the next concrete step the Phase 1/2 work
  was scoped for. **M**, contingent on the manual-review data quality-item
  below actually finishing.
- **Wire the trained net-keypoint model into angle inference as a third
  signal.** `10_net_detection/`'s keypoint model is trained (val MSE
  0.0067, visually validated) but currently unused in the live pipeline —
  `infer_angle.py` only has the Hough-line net-width method and the
  sideline-symmetry fallback (item 4 in the pipeline backlog). Adding the
  keypoint model as a third vote (or a tie-breaker when Hough-line
  confidence is low) could reduce the same behind-baseline-vs-side-on
  ambiguity that's driving the 20-clip manual audit below, without
  training anything new. **M**.
- **Two-stage shot classifier to fix backhand precision.** The trained
  ML shot classifier (63.8% CV accuracy, real jump from the 50% rule-based
  baseline) over-predicts backhand (0.30 precision) even though recall
  improved a lot. A cheap, well-understood fix for this specific failure
  mode: split into a serve-vs-groundstroke stage, then a separate
  forehand-vs-backhand stage on groundstrokes only — narrows what the
  weak stage has to distinguish. **M**, no new data collection required to
  start (re-uses the existing 116 labeled amateur clips), though more
  backhand-labeled examples (only 10 today) would help validate it.
- **Interpolate racket position across occlusion gaps.** The shot-contact
  verifier's `occlusion_gap` bucket is both the largest (N=126) and the
  weakest (55.6% agreement) of the three trust buckets — visually confirmed
  false positives include a player just standing still. A geometric
  improvement (bridge the gap using racket velocity/position just before
  and after the occlusion, rather than treating "occluded" as its own
  undifferentiated evidence type) could pull this bucket toward the 90%
  Wilson-bound trust threshold without more Claude calls. **M** — same
  geometric-signal territory as the shot-verification work already done,
  scoped to one bucket.
- **In-app "was this tip helpful?" micro-feedback.** The coaching-tip
  teacher/student loop is deliberately not being trained on synthetic data
  (correctly judged as teaching nothing about real deviations) and is
  waiting on real user footage + verifier calls to accumulate. A one-tap
  thumbs up/down on a shown tip — logged into the same training-log shape
  `tip_training_log.py` already expects — is a second, cheap real-signal
  source alongside the Claude verifier, and doesn't require rotating the
  gate on when verification starts; it can run in parallel and start
  building trust data immediately. **S**.
- **Pose sampling density (`sample_every` 3→1).** Already scoped in detail
  in the pipeline backlog (item 13) as a real accuracy lever, not just a
  smoothness fix — the closest sample to a fast moment like contact can
  currently be off by up to 1/3 of a frame interval, and that same sparse
  trajectory feeds DTW distance and tip-deviation features, not just the
  overlay. Re-stating it here since it's one of the highest-plausible-impact
  items sitting unstarted. **L** — full pro-database re-extraction (~60-90
  min job) + re-running the amateur eval set to confirm it actually helped
  before treating it as done.

#### Data quality opportunities

- **Finish the 230-frame ball-label manual review.** Flagged as squarely
  "on you" in `TODO_MANUAL.md` — the only unblocker for the ball-detector
  Phase 3 item above. Could lower the friction: a "quick mode" in the Dev
  Page tool that shows only the frames with a plausible-but-unconfirmed
  auto-candidate box pre-drawn (accept/adjust/reject) rather than drawing
  every box from scratch, if the review time turns out to be the real
  bottleneck. **S** for the tool tweak; the review itself is manual time
  either way.
- **Contact sheets for the 20 high-camera-angle pro entries.** Already
  offered once and never followed up per `TODO_MANUAL.md`. Cheap to
  generate (one script, no new labeling), and unblocks a real-but-currently-
  deferred data-quality risk: these 20 entries are live and being matched
  against for real users today. **S**.
- **Build the pro-database rebuild-excluding-flagged-clips script.** The
  Pro Clip Review Dev Page tool (item 14 in the pipeline backlog) already
  logs ok/mismatched/slow-motion/spans-two-swings verdicts to
  `clip_review_log.jsonl`, explicitly shaped to support a
  `filter_by_ball_visibility.py`-style rebuild — but that rebuild script
  itself was never written. Writing it is what actually turns review time
  spent in that tool into a cleaner live database. **M** (mirrors an
  existing script's shape, plus a rebuild + before/after validation pass
  like the DTW calibration and z-depth fixes both did).
- **Accelerometer/gyroscope tilt capture at record time.** Flagged in the
  pipeline backlog as the "much cheaper, more reliable fix" for camera
  elevation, which today is calibrated on only 2 known-elevated reference
  videos. Capturing real device tilt at record time sidesteps the
  vision-only inference problem outright rather than patching it further.
  **M** — frontend sensor capture (Expo has this built in) + a pipeline
  change to prefer the real reading over the vision heuristic when present.
- **Grow the backhand-labeled amateur eval set.** Only 10 labeled backhand
  examples exist in the 116-clip amateur eval dataset — too small to be
  confident in isolation, and directly relevant to the two-stage-classifier
  idea above. The existing "Wrong shot type?" correction UI already feeds
  real corrections into the training log; a small push (or just time) to
  accumulate more real backhand corrections would help validate any future
  classifier work here. **S**, mostly time/volume, not new engineering.
- **Expand `coaching_tips_database.json` content.** Already flagged as
  "always helps coverage" — pure content work, no architecture change. Best
  paired with the micro-feedback idea above once there's real signal on
  which existing tips are and aren't landing. **M**, content-authoring
  effort rather than engineering effort.

#### Technical debt worth paying down

- **Test coverage on the untested route files — start with the ones that
  move money or the core loop.** 14 of ~21 route files have zero tests.
  Notably, `analyse.js` — the single endpoint the live app actually
  depends on — has no test file, despite `drills.js`/`history.js`/
  `highlights.js` all having real coverage. A prioritized order: `auth.js`,
  `billing.js`, `webhooks.js` (anything payment/account-adjacent — highest
  blast radius if broken silently), then `analyse.js`/`compareVideos.js`
  (the core product loop), then `coach.js`/`friends.js`/`messages.js`/
  `courts.js`/`profile.js`/`leaderboard.js`/`calibration.js`/
  `annotations.js`/`dev.js`. **L** overall, but cleanly phaseable as
  individual **S**-sized PRs per file — doesn't need to be one effort.
- **Enforce an `optionalAuth`-vs-`requireAuth` convention per route.**
  Already the named root cause of this session's real free-tier-cap bypass
  bug (HANDOVER backend backlog item 1) — ranked highest there because it's
  the pattern most likely to produce the *next* silent security bug rather
  than an obvious crash. A small route-manifest module asserting each
  route's intended auth level, checked at startup or in CI, would catch
  drift automatically instead of relying on someone noticing in review.
  **M**, and doesn't need Jack's call first — it's additive tooling, not a
  behavior change.
- **CI/CD for the hosted backend.** The manual SSH + `git pull` +
  `docker compose up --build app` deploy flow is exactly what let the
  server run stale code across multiple sessions without anyone noticing
  (item #41). Needs Jack's call on approach (GitHub Actions vs. something
  simpler) and whether the Hetzner box should accept inbound deploy hooks
  at all, but even a minimal "build + test on push, SSH-deploy on manual
  approval" pipeline would close the exact gap that caused a real incident.
  **L**.
- **Decide the SQLite-vs-Postgres timeline, one way or the other.** `pg`
  has sat as an installed-but-unused dependency for many sessions now
  while `DATABASE_URL` in `.env` keeps implying a migration that isn't
  scheduled. Not urgent on its own, but worth an explicit decision (commit
  to a timeframe, or deliberately un-imply it — drop the unused `pg`/
  `redis`/`bull` deps and stop pointing `.env` at Postgres) so it doesn't
  keep quietly becoming permanent by default without anyone deciding that
  on purpose. **S** to decide either direction; **L** if the migration
  itself is chosen.
- **SQLite foreign-key enforcement audit.** Root cause behind three
  separate real orphaned-row bugs fixed this cycle (deleted analyses,
  deleted accounts, deleted drill steps). Each known site is patched
  individually, but the pattern means the next new DELETE route will
  likely repeat it. Explicitly flagged as needing Jack's call before
  attempting — some deletes (like account anonymization) are intentionally
  partial, so turning the pragma on for real needs a full audit of every
  existing DELETE first. **L**, and blocked on that call.
- **`expo-av` → `expo-video`/`expo-audio` migration.** The one confirmed
  blocker on ever moving off Expo SDK 54 — `expo-av` is removed outright in
  SDK 55. Two call sites, one of which (`PlatformVideo.native.js`) has a
  hand-written ref interface that `PlatformVideo.web.js` mirrors and
  `SyncCompareScreen` drives through — real behavioral risk with no
  frontend tests to catch a regression, which is presumably why it's been
  deliberately deferred so far. **L**, and worth pairing with adding at
  least smoke-test coverage for `SyncCompareScreen`'s playback controls
  before touching it, given the total lack of frontend tests today.
- **Small cleanups sitting on the shelf.** Two low-risk, low-effort items
  worth batching together whenever someone's next in the backend: delete
  the harmless leftover `backend/src/routes/db.js` on the server (not a
  real part of the app, already identified as safe to remove), and decide
  the fate of `expo-auth-session`/`expo-web-browser`/`expo-crypto`
  (installed, unused, kept from the deferred Google Sign-In investigation)
  — either remove them now or explicitly keep them earmarked for whenever
  the EAS dev-client build happens, since that's also the trigger for
  native RevenueCat checkout. **S**.
