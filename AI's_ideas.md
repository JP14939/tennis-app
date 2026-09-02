# AI's Ideas

Copied out of `docs/future-ideas.md` for quick reference. That file is the
authoritative, append-only running log — new dated sections get added there
by the weekly "Future-ideas brainstorm" scheduled routine, and by the
occasional manual pass. This is just a standalone copy of the most recent
pass for convenience (last refreshed: 2026-09-01 manual competitor-analysis
pass).

---

### 2026-09-01

Context for this pass: a competitor-analysis pass, not a routine brainstorm —
driven by a full walkthrough video of **SevenSix** (`SevenSix AS`, Norway),
an iOS-only tennis swing-analysis app with the same pose-extraction +
compare-to-a-pro core loop as RallyMax (`C:\Users\jackp\Downloads\HQZE8437.MP4`,
a 3:15 iPhone screen recording Jack made going through their app). Read
`CLAUDE.md`, `STATUS.md`, `TODO_MANUAL.md`, `HANDOVER.md`, and the four prior
dated sections in `docs/future-ideas.md`. SevenSix specifics observed:
on-device "stickman overlay" pose estimation; scores Swing Curve / Timing /
Impact Point → one overall /100; shots = FH, BH (single + double), serve,
slice; a server-side analysis step with a visible "Aw Snap, our AI failed to
analyse your video / Report Issue" failure path; UK pricing £149.99/yr
(£12.50/mo) or £14.99/mo with a 14-day trial (US store price-tests $22.99/mo,
$229/yr, plus pay-per-swing $2.99 / $5.99 / $7.99); ~$550K raised total over
grant/angel rounds; ~4.0–4.34 App Store rating on ~62–80 lifetime ratings
with reviews citing failed analyses. Ideas below build on that read and
deliberately do **not** re-propose the standing ball-speed v1 and
gravity-aware flight-model items already scoped in the 2026-08-26 section, or
true tactical player-type classification.

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
