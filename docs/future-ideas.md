# Future Ideas

A running, append-only brainstorm log for RallyMax. Each dated section below
is a snapshot from one ideation pass — grounded in the codebase and
`HANDOVER.md`/`TODO_MANUAL.md` as they stood that day, not a committed
roadmap. Older sections are kept for history; add new ones at the top.

Sizing is rough: **S** = a session or two, **M** = several sessions /
one focused effort, **L** = a real project, likely needs Jack's call on
scope or timing before starting.

---

### 2026-09-01

Context for this pass: a competitor-analysis pass, not a routine brainstorm —
driven by a full walkthrough video of **SevenSix** (`SevenSix AS`, Norway),
an iOS-only tennis swing-analysis app with the same pose-extraction +
compare-to-a-pro core loop as RallyMax (`C:\Users\jackp\Downloads\HQZE8437.MP4`,
a 3:15 iPhone screen recording Jack made going through their app). Read
`CLAUDE.md`, `STATUS.md`, `TODO_MANUAL.md`, `HANDOVER.md`, and the four prior
dated sections below. SevenSix specifics observed: on-device "stickman
overlay" pose estimation; scores Swing Curve / Timing / Impact Point → one
overall /100; shots = FH, BH (single + double), serve, slice; a server-side
analysis step with a visible "Aw Snap, our AI failed to analyse your video /
Report Issue" failure path; UK pricing £149.99/yr (£12.50/mo) or £14.99/mo
with a 14-day trial (US store price-tests $22.99/mo, $229/yr, plus
pay-per-swing $2.99 / $5.99 / $7.99); ~$550K raised total over grant/angel
rounds; ~4.0–4.34 App Store rating on ~62–80 lifetime ratings with reviews
citing failed analyses. Ideas below build on that read and deliberately do
**not** re-propose the standing ball-speed v1 and gravity-aware flight-model
items already scoped in the 2026-08-26 section, or true tactical
player-type classification.

#### Product features (building on the DTW pro-comparison core loop)

- **Promote "record a session, we find the swings" to the primary capture
  flow.** SevenSix's core loop is Record → "Session Highlights: browse your
  swings and select one to analyse" → Analyse, and it's the first thing the
  app pushes you toward. RallyMax has the pieces (`HighlightUploadScreen.js`,
  `scripts/11_highlight_clipping/`) but the feature is premium-gated *and*
  broken upstream — `detect_rallies.py`'s `apply_serve_gate()` discards
  ~100% of confirmed real rally forehands (TODO_MANUAL 2026-08-26 item 5).
  Fix the gate, then surface a session-upload → swing-picker step in the
  main analyse path instead of hiding it behind Premium. **M** (**L** if the
  picker becomes its own screen). Unblocks: the highlight/rally feature
  being usable at all.
- **Pre-record live framing / pose-lock gate.** SevenSix keeps its Record
  button disabled until a pose is locked ("Ready to record" vs "Player not
  detected"), so you don't waste a take. RallyMax's "Record now" live
  calibration is built but has never been tested on a real phone (STATUS
  item 8, TODO_MANUAL "Test Record now"). Add a hard pose-lock gate plus a
  framing badge before recording is allowed, and pair it with the failure-
  path hardening item below. **S–M**.
- **A collapsed "hero result" as the default `ResultsScreen.js` state.**
  SevenSix's result screen is one score ring plus one plain-language line
  ("Not bad! Our AI coach says your biggest improvement is ball hit"),
  everything else a tap away. `ResultsScreen.js` leads with the score but
  immediately stacks the compare button, angle rows, phase x/25, tips, and
  other matches. Add a collapsed default — ring + single worst-phase
  sentence + "see full breakdown" — reusing `phase_breakdown` data already
  in the response. **S**.
- **Named, points-scored challenges.** SevenSix's Training tab has "Compare
  to the AO23" and "Weekly Biomech" challenges with point targets. RallyMax
  has leaderboards and pro matching but no time-boxed challenge construct —
  a cheap engagement loop layered on the existing compare-to-a-pro
  machinery. **M**.
- **Surface the raw biomechanics numbers RallyMax already computes.**
  SevenSix's whole pitch is hip / shoulder / wrist velocity and
  kinetic-chain timing. `compute_phase_breakdown()`
  (`scripts/08_comparison_engine/phase_breakdown.py`) already derives
  hip/shoulder rotation range and racket-to-hip distance, then collapses
  them into the single `body_rotation` 0–25 score. Expose them as labelled
  readouts ("hip rotation range: X° vs pro Y°", "wrist-speed peak",
  "timing gap: Z ms"). **S–M** to surface the signals that already exist;
  **M–L** for real kinetic-chain sequence scoring.

#### ML pipeline improvements (numbered `scripts/` stages)

- **Decouple the point-boundary gap from detector reliability in
  `detect_rallies.py`.** Stated as the pipeline fix behind the session-upload
  product item above: `apply_serve_gate()` treats >6s since the last
  *detected* swing as the point ending, but the swing detector misses most
  real rally shots, so that gap is usually a detection gap, not a point
  boundary — 12/12 confirmed real forehands in IMG_5755 were discarded.
  Options: gate on a motion / ball-track signal instead, widen the gap, or
  skip the gate entirely for non-serve shot types. **S–M**. Unblocks: rally
  grouping, the session-upload flow, and unskews the shot-classifier
  training data (the 102 rows currently skew serve-heavy for exactly this
  reason — TODO_MANUAL 2026-08-26 item 4/5).

#### Data quality opportunities

- **A lightweight recurring competitor watch.** SevenSix price-tests by
  region and has shipped-then-killed features (an "AI Coach" added then
  removed in v4.0.1, Aug 2024), so the competitive picture moves. A monthly
  manual note — or a small scheduled-routine-style check — tracking their
  App Store release notes and regional pricing would keep the read current
  without another full walkthrough. **S**.

#### Technical debt worth paying down

- **Harden the analysis failure path — it's a direct wedge against
  SevenSix's weakest axis.** The walkthrough's most visible SevenSix
  failures were reliability: "Aw Snap, our AI failed to analyse your video"
  and "Player not detected", echoed by App Store reviews on failed analyses.
  `backend/src/routes/analyse.js` has a 2-minute spawn timeout and surfaces
  errors, but there's no retry, no partial-result fallback, and no "here is
  exactly which signal was missing" UX. Pre-flight checks (pose visible,
  enough trajectory points, shot in frame) plus graceful degradation when
  ball/net signals are absent — some of which the pipeline already reports
  as `null` rather than faking — would make "it just works" true, on top of
  RallyMax already being Android + web where SevenSix is neither. **S–M**.

---

### 2026-08-26

Context for this pass: read `CLAUDE.md`, all of `HANDOVER.md` (all 44 dated
items, the pipeline/backend/frontend backlogs, and the three PR round-up
sections), `TODO_MANUAL.md` in full, and all three prior dated sections
below. A lot closed out since the 2026-08-25 pass specifically: CI/CD now
exists (`.github/workflows/deploy.yml`, item #44), the 5 flagged ball-label
clips were resolved, JWT is pinned to HS256, and `webhooks.js` picked up a
validation test file. Ideas below try to build on that fresh ground and
deliberately skip repeating anything already sitting in the 2026-08-23/24/25
sections — including every item in those sections' own "already tried and
declined" lists (`Z_WEIGHT` at the DTW level, freeform Claude ball-bbox
labeling, synthetic-data training for the coaching-tip verifier,
`static_hold`'s speed-based rejection rule, the direct-regression racket
model) plus, this pass, the friends system's **single-sided, no-dedup match
logging** — confirmed in `HANDOVER.md` item 16 as "a deliberate scope call
... rather than building a confirm/dispute flow," not an oversight, so it's
left alone here too.

#### Product features (building on the DTW pro-comparison core loop)

- **Actually verify Coach Collaboration Mode end-to-end, not just that the
  files exist.** `HANDOVER.md` item 14 flagged this explicitly back on
  2026-08-11 — "only confirmed via a quick file-existence check... treat
  'how complete this is' as still an open question" — and nothing since has
  closed that question. `coach.js`/`coach_links`/`coach_notes` are real, but
  whether the full invite → link → student-history → per-analysis-note loop
  actually works end-to-end for two real accounts has never been the subject
  of its own verification pass the way Friends and Find Games got. **S–M**
  to verify; if it holds up, the natural next increment is a coach-facing
  aggregate view across all of a coach's students (weakest-phase trends,
  who hasn't logged a swing recently) instead of only per-analysis notes —
  **M**, and only worth scoping once the audit confirms the base loop is
  solid.
- **Graduate `player-type` from a rule-based heuristic to the same
  teacher-student pattern already proven for shot-type and shot-contact.**
  `GET /api/profile/player-type` ships today as an explicitly-labeled
  `confidence: 'estimated'` guess (outcome-tag rates or shot-type mix,
  hand-picked thresholds) because, per item 14, "the app has no
  court-position/rally-pattern data" for a real tactical classifier — that
  hasn't changed, but the verified-rally-outcome corpus behind it has grown
  a lot since 2026-08-13 (85+ real match rows, a shot-verification pipeline
  now gating what counts as a real shot). A lighter-weight win than true
  tactical classification: train on the *existing* feature set (outcome-tag
  rates, rally length, shot-type mix) instead of hand-picked thresholds, and
  validate it the same teacher-student way `classify_shot.classify_ml()`
  was — Claude labels a small verified sample, compare against the current
  rule-based labels. **M**.
- **Surface the existing head-to-head record on Home, not just inside a
  friend's detail view.** `friend_matches`/`GET /friends` already compute a
  live per-friend win/loss badge (e.g. "3–1"), but it's only visible one tap
  deep in the Friends tab. A small "your rivalries" card on `HomeScreen.js`
  (top 1-2 friends by recent match activity) would surface data that
  already exists today, no backend changes. **S**.

#### ML pipeline improvements (numbered `scripts/` stages)

- **Build ball-speed v1 — both things it was waiting on now exist.** Item
  #43 scoped this in detail and explicitly held it "behind Phase 3
  fine-tuning landing first," but the two concrete prerequisites named at
  the time — a real ball-motion model instead of raw detections, and an
  agreed-on scale/approach — are both now in place: `ball_tracker.py`'s
  Kalman filter (built 2026-08-25, 6 tests, smoke-tested) gives a stable
  track to measure velocity from, and the net-keypoint-based local-scale
  approach (speed *at the net crossing*, not at racket contact — an agreed,
  disclosed v1 limitation) was already worked out with Jack. Phase 3
  fine-tuning improving raw detection quality only makes this converge
  faster, it was never a hard blocker on starting. **M–L**.
- **Give `ball_tracker.py` a gravity-aware flight model, per its own
  "deliberately NOT... yet" scoping note.** The shipped constant-velocity
  Kalman filter is explicitly flagged in item #43 as "a real future
  refinement, not built this session." Now that the constant-velocity
  baseline is live, tested, and has a real caller (`ball_departure_confirmed`
  via `_interpolated_ball_track()`), swapping in (or blending toward) a
  parabolic/gravity motion model for the post-contact flight phase would
  improve exactly the segment where a ball decelerates and drops
  differently than a constant-velocity model assumes — directly relevant to
  the ball-speed feature above, whichever lands first. **M–L**.
- **Reuse the Wilson-score trust-bucketing pattern per predicted class, not
  just per evidence-type.** `shot_contact_training_log.py`'s bucketing (one
  trust score per evidence category) already solved "some signals are more
  reliable than others" for shot verification, and the 2026-08-25 section
  already proposed applying the same idea to camera-angle confidence. A
  third, distinct place it fits: the ML shot-type classifier's honestly-
  reported 0.30 backhand precision (vs. much healthier forehand/serve
  numbers) is being masked by one pooled 90%/50-example trust gate — bucket
  `should_trust_bucket()`-style by *predicted class* instead, so forehand/
  serve predictions could start being trusted standalone well before
  backhand clears the same bar. **M**.

#### Data quality opportunities

- **Apply the new "not moving = not the ball being played" audit to the pro
  database too, not just the 354 manual user labels.** `audit_ball_label_
  motion.py` (built 2026-08-25) exists purely because Jack's own labeling
  practice could box a static decoy ball — but the *pro* database's
  `ball_visibility_audit.json` (the filter that turns ~914 raw entries into
  631) was built earlier, by a different process, and has never been
  checked against this exact rule. If any of the 631 live entries have a
  similar decoy-vs-real-ball ambiguity, it's silently feeding every user's
  comparison today. Running the same motion-check logic (adapted from
  per-label to per-database-entry) against the pro database's own ball
  track data is a cheap, direct reuse of code that already exists and is
  already trusted. **S–M**.
- **Recheck the ship-time-guessed thresholds now that real usage data
  exists.** At least three real numbers went live as explicit placeholders,
  never revisited: the 8-tier rank ladder's thresholds (item 14: "a
  first-pass geometric spacing with no real usage data behind it yet"),
  `player-type`'s minimum-data gates (`≥5` tagged rallies / `≥10`
  analyses, also picked without usage data), and the `similarity >= 75`
  "great swing" cutoff duplicated across `theme.js`/`HomeScreen.js`/
  `HistoryScreen.js`/`profile.js`. There's now real distribution data
  (hundreds of real analyses, 85+ real match-derived rows) to check whether
  any of these guesses are badly off — e.g. everyone hitting "Legend" too
  fast, or `player-type` staying `null` for most real users. **S**, a data
  pull + threshold tuning pass, no new architecture; also a natural moment
  to collapse the duplicated `75` into one shared constant while touching
  those call sites.

#### Technical debt worth paying down

- **The new CD pipeline has no test gate before it deploys.**
  `.github/workflows/deploy.yml` (item #44) triggers straight from a push to
  `master` touching `backend/**`/`scripts/**` — it SSHes in and rebuilds
  immediately, with no `npm test` (or `pytest`) step in between and no
  separate CI workflow anywhere in `.github/workflows/` to catch a red suite
  first. Before CI/CD existed, a broken push just sat on GitHub until
  someone manually deployed; now the exact same broken push reaches
  production automatically, faster. Worth adding a `test` job the `deploy`
  job depends on (`needs:`) — the backend suite already runs fast enough
  locally to not meaningfully slow the pipeline down. **S–M**, and pairs
  directly with the next item: this is sharpest on exactly the routes with
  no test coverage to catch a regression before deploy.
- **Three route files still have zero test coverage: `billing.js`,
  `calibration.js`, `compareVideos.js`.** Down from the four named in the
  2026-08-24 pass — `webhooks.js` picked up `webhooks.validation.test.js`
  since then — but the remaining three are still real-money (`billing.js`
  is the client-triggered tier-sync path) and the second live comparison
  engine entry point. Combined with the CD test-gate gap above, these are
  currently the routes most exposed to "a bad change reaches production
  with nothing to catch it." **S** each, **M** for all three.
- **A zero-account-setup interim DB backup, using infrastructure that
  already exists.** `TODO_MANUAL.md`'s off-box-backup item has real,
  tested code (`backupDatabase.js`, `npm run backup:db`) sitting behind
  three human steps (a Backblaze B2 account, `rclone` on the VPS, a cron
  job) that haven't happened yet. The CD pipeline (item #44) already has a
  working, scoped SSH credential into the same server — a stopgap cron job
  that `scp`s a nightly `app.db` snapshot to wherever the CD workflow's own
  runner (or any already-authorized machine) can write it would give real
  off-box coverage today, without waiting on the Backblaze account to get
  created. Not a replacement for the real B2 setup once it happens, just a
  way to not have zero backups in the meantime. **S**.
- **`tip_verifier.py`'s safety-gate comment is now factually wrong.** Its
  module docstring still reads "do not call `verify_picks()` until the
  ANTHROPIC_API_KEY... has been rotated (the current one was exposed in
  chat and needs replacing first)" — but the key was rotated back on
  2026-08-10, 16 days before this pass. Harmless today since the whole
  coaching-tip verifier loop is independently disabled at both live call
  sites (per the 2026-08-23 logic-review PR), but a stale safety gate is
  exactly the kind of comment someone re-enabling this system later would
  reasonably trust at face value. Update it to describe the real current
  gate (disabled pending a kill-switch decision, not "key not rotated
  yet"). **S**.
- **`TODO_MANUAL.md`'s "Quick status" banner is now stale by 4 days of real
  work.** `CLAUDE.md` tells every fresh session to read this exact line
  first, but it's still dated 2026-08-22 and predates CI/CD, the ball
  tracker, the pose-overlay jitter fix, and three more PR rounds — someone
  reading it cold today would miss all of that. Worth either updating it as
  part of the next docs round-up or considering whether a banner that has
  to be manually kept current across many sessions is the right shape for
  this at all (vs., say, deriving "what's open" from the struck-through/
  plain headings that already exist further down the same file). **S** to
  just refresh it; **M** if it's worth restructuring instead.

---

### 2026-08-25

Context for this pass: read `CLAUDE.md`, all of `HANDOVER.md` (all 42
dated items plus the pipeline/backend backlogs), and `TODO_MANUAL.md`, plus
the existing 2026-08-23 section below and the still-open
`future-ideas/2026-08-24` PR content (not merged into master as of this
pass, but read to avoid repeating it) and today's three fresh
scheduled-routine PRs (`logic-review/2026-08-25`,
`bug-sweep/2026-08-25`, `security-review/2026-08-25` — all open, none
merged yet). Ideas below deliberately build on what those three PRs just
found rather than repeating the 2026-08-23/08-24 lists, and skip
re-proposing anything already tried and declined: `Z_WEIGHT`
re-enablement, the direct-regression racket keypoint model, freeform
Claude ball-bbox labeling, coaching-tip-verifier training on synthetic
pro-vs-pro data, and `verify_shot_contact.py`'s removed speed-based
`static_hold` rejection rule.

#### Product features (building on the DTW pro-comparison core loop)

- **Turn the new low-trajectory guard into user guidance, not just a
  clean error.** `bug-sweep/2026-08-25` fixed `compare_swing.py` silently
  returning a fake similarity score when MediaPipe only found a usable
  pose on 1-4 frames near contact (now raises, matching the pro-database
  build's own `MIN_TRAJECTORY_POINTS` guard) — correct, but "analysis
  failed" alone doesn't tell a user *why* or what to do differently. The
  app already computes a pose-detection-rate percentage elsewhere (the
  ball-detector audit used it); surfacing "we could barely see your body
  near contact — try better lighting or a less occluded angle" on this
  specific failure would turn a dead-end error into the same kind of
  actionable camera guidance `check_camera_setup.py` already gives
  pre-upload. **S** — the detection-rate number likely already exists in
  the pipeline output, mostly a frontend error-message + one backend field.
- **A "this match doesn't look right" flag on results, feeding the
  existing Pro Clip Review log.** The Pro Clip Review Dev Page tool (admin/
  Jack-only today, `clip_review_log.jsonl`) already has the exact shape
  needed to record a bad pro-database entry. Real users hitting a
  genuinely mismatched top-match clip is a much larger, ongoing sample
  than one person's manual review pass — a small flag button on
  `ResultsScreen` next to the existing "Yes, real shot"/"No, not a shot"
  pair, logging to the same `clip_review_log.jsonl` shape (tagged
  `source: 'user_flag'`, same pattern already used for shot-verification
  and shot-type corrections), would let real usage help find the pro
  database's data-quality problems faster than manual review alone. **S–M**.
- **Weekly recap email.** Password-reset email delivery (Resend) is built
  and just needs `RESEND_API_KEY`/domain setup per `TODO_MANUAL.md` — once
  that's live, the same `backend/src/utils/email.js` plumbing plus the
  already-real `GET /profile/rank` and history-aggregation queries could
  send a weekly "N swings analyzed, rank progress, where you land on the
  leaderboard" digest with near-zero new backend logic. **S–M**, gated on
  the Resend account setup already sitting in `TODO_MANUAL.md`.

#### ML pipeline improvements (numbered `scripts/` stages)

- **Apply the shot-verification trust-bucketing pattern to camera-angle
  confidence.** `shot_contact_training_log.py`'s per-evidence-type Wilson-
  score trust gating (bucket net-detection method → confidence, rather
  than one pooled number) already solved a real "some methods are more
  reliable than others" problem for shot verification. `infer_angle.py`
  today has two methods with genuinely different reliability (Hough net-
  line detection vs. the sideline-symmetry fallback, the latter
  deliberately capped low-confidence per the pipeline backlog) but no
  learned trust signal between them — just a fixed confidence constant per
  method. Reusing the same bucketing/Wilson-bound machinery (which already
  exists and is proven) against real angle-vs-ground-truth data as it
  accumulates could make that confidence number earned rather than
  assumed. **M**.
- **Audit for the same "filter on the rounded value" bug class
  elsewhere.** `logic-review/2026-08-25` found `courts.js` filtering
  the radius search on the *rounded* `distance_km` instead of the exact
  haversine value, silently admitting a court a few dozen meters outside
  the requested radius. The same shape of bug — round for display, then
  accidentally filter/sort on the rounded copy — is worth a quick grep
  across `compare_swing.py`'s angle-window filter (`abs(pro_angle -
  user_angle) <= angle_window`) and anywhere else a value gets both
  displayed and filtered, since this is exactly the kind of drift a
  logic-review pass catches one site at a time rather than as a class.
  **S** — a targeted grep-and-check, not a rewrite.
- **Validate `contactTime` against the video's real duration before
  spawning Python.** `logic-review/2026-08-25` tightened `contactTime`
  validation to reject negative/absurd-but-finite values via the shared
  `isTimestampSec` invariant — but that check has no upper bound tied to
  the actual uploaded video's length, so a syntactically-valid but
  video-exceeding timestamp (e.g. `contactTime=999` on a 3-second clip)
  still reaches the Python subprocess before failing there instead of
  failing fast in Node with a clearer message. Worth a follow-up: probe
  duration (already needed for camera-setup checks) and bound
  `contactTime` against it before spawning. **S**.

#### Data quality opportunities

- **Audit every `analyses` consumer for `flagged_not_shot` parity, not
  just the two `logic-review/2026-08-25` fixed.** That PR closed the gap
  in `profile.js`'s rank count and player-type fallback (leaderboard.js
  already excluded flagged rows) — worth checking `TrendChart.js`'s
  client-side progression-chart aggregation and `HomeScreen.js`'s stats
  strip too, since both compute similar "how good are this user's real
  swings" numbers straight from the fetched history list and could have
  the identical gap, just never audited. **S** — a targeted check of two
  more call sites, same shape of fix if either is affected.
- **A manual-review-backlog dashboard.** `TODO_MANUAL.md` currently
  tracks four separate open manual-review backlogs in prose (230 ball-
  label frames, 20 high-camera-angle pro entries, 120 unmatched
  shot-verification rows from the 2026-08-10 retrain, the un-verified
  `IMG_5823.MOV` dry-run) — easy for any one of them to quietly get lost
  across sessions since nothing surfaces "how many are still open" in one
  place. A small Dev Page summary tile or a `scripts/`-level status
  command that counts each backlog directly from its source of truth
  (`needs_manual_review` frames, `camera_angle > 65` entries, unmatched
  ids, etc.) would make "is this actually still open" a one-glance check
  instead of trusting doc prose to stay current. **S**.
- **Close the `drills.js` read-side validation gap `logic-review/2026-08-25`
  noticed but didn't touch.** `GET /drills`'s `shot_type` query param isn't
  checked against `DRILL_SHOT_TYPES` the way the write-side already is —
  today that's harmless (an invalid value just yields zero rows), but it's
  a one-line addition for consistency and removes a spot future review
  passes will keep re-flagging as "noticed, not fixed." **S**.

#### Technical debt worth paying down

- **Give the scheduled-routine sandbox real Python execution, not just
  code-reading confidence.** `bug-sweep/2026-08-25`'s ML-side fix (the
  near-empty-trajectory guard) explicitly could not be run — "no `cv2`/
  `mediapipe`/venv available in the sandbox this ran in" — and verified
  the fix only by pattern-matching against an already-tested sibling
  guard. That's a real, recurring gap: every scheduled review that
  touches `scripts/` is flying blind on actual execution, unlike the
  backend's `npm test`, which every PR runs for real. Worth checking
  whether the routine's environment can get a slim `scripts/venv` (even
  without the full model weights, just enough to import and unit-test
  pure-Python logic like trajectory guards) so ML-pipeline fixes get the
  same real-test confidence backend fixes already do. **M**, and
  needs Jack's call on whether that environment access is worth granting.
- **Lock in today's JWT algorithm pin with a regression test, not just
  the fix.** `security-review/2026-08-25` added `algorithms: ['HS256']`
  to both `jwt.verify()` call sites — correct, and confirmed
  not-currently-exploitable, but nothing stops a future change from
  adding a third verify call site (or a second signing path) without the
  same pin. A one-line static check (grep-in-CI, or a small test that
  greps `requireAuth.js`/`optionalAuth.js` for the `algorithms` option) is
  the same "catch the pattern automatically" idea already proposed for
  the `optionalAuth`-vs-`requireAuth` convention in the 2026-08-23 list,
  scoped to this specific hardening instead. **S**.
- **A doc/comment-drift audit pass across `scripts/`.** `logic-review/
  2026-08-25` noted (but correctly left alone, per its own "no unrelated
  cleanup" scope) that `compare_swing.py`'s `build_user_trajectory()`
  docstring still claims "every 2nd frame" when the actual sampling — and
  every path that depends on it — has been "every 3rd frame" since the
  DTW calibration fix. Harmless today since the code paths already agree
  with each other, but it's exactly the kind of stale claim that misleads
  the next person reading the docstring instead of the code, the same
  class of drift `CLAUDE.md` itself warns about for `HANDOVER.md`/
  `TODO_MANUAL.md`. Worth a one-off grep pass for comments describing
  sampling rates, thresholds, or constants that may have drifted from
  their real values, rather than waiting for review passes to catch them
  one docstring at a time. **S**.
### 2026-08-24

Context for this pass: read `CLAUDE.md`, all of `HANDOVER.md` (through item
42 and the 2026-08-23 PR-merge/round-up sections), and `TODO_MANUAL.md`.
The 2026-08-23 pass already covers a lot of good ground (weakest-phase
drills, session recap, ball detector Phase 3, net-keypoint wiring, test
coverage, `optionalAuth` convention, CI/CD, SQLite/Postgres, FK enforcement,
`expo-av` migration) — this pass tries not to repeat those and instead
builds on what changed since: the four 2026-08-23 PRs got merged, item 42's
real-device testing found a cluster of native-only bugs invisible to web
testing, and a handful of concrete "still your call" items are sitting in
`TODO_MANUAL.md`'s "Product-call items from PR #1" list without a proposed
direction. Also skipping anything already explicitly declined — e.g. still
not re-proposing `Z_WEIGHT` re-enablement or the direct-regression racket
model.

#### Product features (building on the DTW pro-comparison core loop)

- **Seed the worldwide leaderboard.** `celebrity_scores` has 0 rows right
  now (confirmed in the 2026-08-22 commit that shipped `FirstSwingCard` and
  hid the leaderboard when empty) — the "worldwide, admin-added pros/
  celebrities" leaderboard mode built in item 18 has no data to actually
  show yet, so it's effectively dead weight in the UI today. Populating it
  is pure content work: run a handful of well-known pro clips through the
  existing comparison engine (or hand-enter representative scores) and
  seed the table. **S** — no code changes, just data + maybe a small admin
  script if one doesn't already exist.
- **Haptic feedback on score reveal and achievements.** The 2026-08-22
  session added a real motion system (`theme.js` easing/duration/spring
  tokens, `PressableScale` spring feedback, an orchestrated `ScoreCard`
  reveal) but it's visual-only — `expo-haptics` isn't used anywhere. A
  light tap on the score-count-up landing and on an achievement/rank-tier
  unlock would be a small, cheap follow-on to that work, and fits the
  "make AI feedback feel tangible" goal the original GolfFix brief called
  out for the skeleton overlay. **S**.
- **Self-serve recovery for a missing History video.** The 85-row gap from
  the 2026-08-14 local batch run (item in `TODO_MANUAL.md`) is a one-off,
  but the underlying failure mode — a saved analysis whose `user_clip_url`
  points at a file that isn't actually on the server — isn't specific to
  that batch and could recur after any future local-run-then-deploy
  mismatch. Instead of (or in addition to) manually copying the old files,
  a "video unavailable — re-upload this swing to restore playback" prompt
  on `HistoryScreen`/`ResultsScreen` when the clip 404s would make the
  failure self-healing for users instead of needing a manual `scp` every
  time it happens. **S–M**.

#### ML pipeline improvements (numbered `scripts/` stages)

- **Spot-check the 120 "unmatched" analyses from the 2026-08-10 shot-
  verification retrain.** Called out in item 7 of `HANDOVER.md` and never
  followed up: when `apply_verification_to_history.py` was run against
  Jack's real history, 120 of 245 existing rows couldn't be matched to a
  swing-index in the fresh verification pass (numbering didn't line up
  between the original overnight run and the retrain), so they never got a
  real verified/flagged/re-cropped verdict either way — they're just
  sitting there unverified. The two-way "Yes, real shot"/"No, not a shot"
  buttons already on every History card are the exact tool needed to clear
  this backlog by hand; a small script to list just the 120 unmatched ids
  first would make it a bounded task instead of an open-ended scroll.
  **S**.

#### Data quality opportunities

- **Reconcile `annotationStrokesJson`'s per-field cap against the shared
  `express.json()` body limit, everywhere else this pattern exists.** Item
  42 found and fixed one real instance (a 200KB per-field cap that was
  structurally unreachable because two such fields share a 100KB total
  body limit, so the parser's 413 always fired first) — worth a quick
  audit of `invariants.js`/`validateBody.js` for any other per-field size
  cap that could have the same problem (drill/lesson content bodies,
  message text, coach notes) rather than assuming this was the only site.
  **S** — a grep-and-check pass, not new architecture.
- **`celebrity_scores` being empty** is also worth flagging here as a data
  gap in its own right, separate from the leaderboard feature idea above —
  whatever gets used to seed it (real pro footage run through
  `compare_swing.py`, or hand-entered reference scores) should get the
  same "verified against real code, not guessed" treatment the rest of
  this app's data has had. **S**, same effort as the feature item above —
  listed twice deliberately since it's both a UI gap and a DB gap.

#### Technical debt worth paying down

- **Four route files still have zero test coverage, and they're not the
  low-risk ones.** Route-level test coverage has moved a lot since
  yesterday's pass (`analyse.js` now has `analyse.test.js`, e.g.) — as of
  today, exactly `billing.js`, `webhooks.js`, `calibration.js`, and
  `compareVideos.js` have no test file at all. That's the entire real-money
  path (`billing.js`/`webhooks.js` are what keep `users.tier` correct) plus
  the second live comparison engine entry point. Worth calling out
  specifically rather than folding into the general "14 files untested"
  framing from yesterday, since the remaining gap is now small enough to
  name file-by-file. **S** each, **M** for all four.
- **`runPythonJson`'s missing `SIGKILL` escalation doesn't actually need
  Jack's call.** It's listed in `TODO_MANUAL.md` alongside three genuinely
  product-judgment items (the invite-code TOCTOU race, the non-transactional
  Overpass upsert, the empty-`rallyIds` semantics question), but unlike
  those three it's pure robustness with no behavioral ambiguity to resolve
  — a hung Python subprocess should die on timeout, full stop. Worth
  splitting out and just building: `SIGTERM` then a short grace window then
  `SIGKILL` if the process hasn't exited. **S**.
- **Give the coaching-tip Claude verifier a real kill switch before ever
  re-enabling it.** The logic-review PR found it silently live on every
  `/api/analyse`/`/api/compare-videos` call (up to 3 synchronous Anthropic
  calls per request) and disabled both call sites — but `CLAUDE.md` still
  describes `09_coaching_ai/` as "never run with real data, not wired in,"
  so the docs and the code have drifted apart on this before and could
  again. If/when this comes back, wiring it behind an explicit env flag
  plus the cost-budget tracking `tip_training_log.py` already has the
  shape for (rather than a bare import) would make "is this live" a
  one-line check instead of a full-file read. **M**, and still needs
  Jack's call on *whether* to re-enable, just not on *how* to gate it
  safely if he does.
- **Turn `npm run verify:db` into a scheduled check, not just a manual
  command.** The 2026-08-22 session built real infrastructure here (48
  integrity checks, safe to run read-only against production) but it only
  runs when someone remembers to type the command. A daily scheduled run
  against a read-only copy of the hosted `app.db` (or over SSH, output
  piped back) would catch the next `outcome_tag` -style silent-mismatch
  bug automatically instead of waiting for someone to notice a feature
  quietly not working, the same way the Player Type bug was found this
  time. **S–M** — the checking logic already exists, this is scheduling +
  a place to report failures (could ride on the same GitHub-connected
  routine infra the other five scheduled routines already use).

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
