# RallyMax — Status

**What this file is:** a short, hand-curated snapshot, overwritten each time
someone updates it — not a log. Read this first if you just want to know
where things stand in under 2 minutes. For the full detailed history, see
`HANDOVER.md` (dated build log) and `TODO_MANUAL.md` (full backlog, also
chronological) — this file is a filter on top of those, not a replacement.

**Last updated:** 2026-09-03 — audio-review-all + practice-footage ingestion (in progress)

---

## What RallyMax is, right now

An AI tennis swing analysis app (Expo — iOS/Android/web). Core loop: upload a
swing video, mark the contact frame, get pose extraction + a Dynamic Time
Warping comparison against 631 pro swing clips, back a closest-pro match, a
0–100 similarity score, and coaching tips. **Built and hosted, pre-launch** —
the backend is live and payments are wired, but no one outside Jack has used
the live product yet.

## Right now — the things that actually matter today

Curated, not exhaustive — the full backlog lives in `TODO_MANUAL.md`.

1. **Contact-frame detection rebuilt (2026-09-02) — 9 frames → <1 frame — now
   committed and applied.** A new **audio-onset classifier** (the ball-strike
   "pock", `data/07_ball_racket_tracking/onset_classifier.pkl`) picks contact at
   **median 0.75f / 89% within ±3f** vs. the old pose pipeline's ~9f/25%. Wired
   into the live `compare_swing.py` auto-detect path (no manual mark,
   confident-only, guarded). **All session work is now committed** (16 local
   commits, not yet pushed — Jack's step). **Phase B.2 done:** the pro DB's
   placeholder contact times were audio-filled and the DB rebuilt
   (796 → 415 entries, 108 audio fills, 111 flagged for a human pass, all 415
   re-tagged with `view_direction`). Still open: verify the live path on a real
   phone upload; the audio-teacher → visual-only student for audioless uploads
   (Phase C, ~half done). Detail: `HANDOVER.md` "Session 2026-09-02 (later still)".
2. **`detect_rallies.py`: accurate contact frame now wired in (2026-09-02).**
   The verifier was fed the swing-detector wrist-peak (~13f late), which made
   groundstrokes read as serves — most of the "everything is a serve" problem
   behind `rallies_detected: 0`. `refine_contact_times()` now uses the audio
   onset detector (the match video has audio) as the contact frame for shot
   verification and serve-gate boundaries, guarded/fallback to the wrist peak.
   **Still to do:** run it on a real match clip to confirm the serve share drops
   and rallies appear; `apply_serve_gate()`'s detection-gap-vs-point-boundary
   conflation is a separate open bug; `analyze_rallies_parallel.py` needs the
   same fix (it runs on audio-less clips).
3. **Shot-type classifier retrain — investigated 2026-09-02, not shipped.**
   Body-normalised the pose features (framing-invariant now;
   `FEATURE_VERSION` guarded). Jack's ~400 Pro Clip Review shot labels (151
   backhand) **still don't help the live/amateur model** — negative transfer
   from broadcast footage, confirmed again. They *do* make a good separate
   model for the rally-detection pipeline. **Real bottleneck: only 10 amateur
   backhand training examples** — needs more phone-style backhand footage.
   No model retrained/saved. Decisions in `TODO_MANUAL.md` 2026-09-02 item 4.
4. **Pro DB rebuilt (2026-09-02) + all contact times audio-anchored (2026-09-03).**
   `pro_database.json` **796 → 415 entries** (forehand 234, backhand 154,
   serve 27), excluded dropped, `view_direction` re-added. 2026-09-03:
   `--apply-all-audio` put an audio-derived contact time on **every** one of the
   219 non-hand-marked entries (0 placeholders left); ~300 entries are queued in
   the Dev Pro Clip Review tool for Jack to eyeball the contact frame + quality.
   **The rebuilt `pro_database.json` / `overlay_trajectories.json` are gitignored
   — Jack must copy them to the server.**
5. **Growing the DB from footage (2026-09-03, in progress).** yt-dlp fixed
   (was 403ing; now merges DASH via the bundled ffmpeg). New
   `ingest_practice_footage.py` pulls per-swing pro entries from court-level
   practice/points footage. **Probe result: this footage yields poorly** —
   Claude's real-shot filter works (~27% cut) but shot types come out ~all
   "forehand" (audio contact detection fails on broadcast audio → contact frame
   13f late) and the player is small / off-centre / 2-in-frame. A `--use-claude`
   run over all 4 videos is going; Jack accepted the manual relabel+recontact
   load. If it's as rough as the probe, single-shot slow-mo compilations are the
   better path.
6. **Off-box database backups are set up but the end-to-end check is still
   open.** B2 bucket `rallymax-db-backups`, `rclone` remote `b2remote` on
   the VPS (auth verified live), cron in `root`'s crontab (3am daily). Open
   since 2026-08-25: just needs someone to eyeball the bucket once for a
   real file landing after a 3am run to close it.
7. **A real beta launch hasn't happened.** The product is feature-complete
   well past the original MVP scope but has never been tested by real
   external users — biggest open strategic question.
8. **Three backend-architecture decisions need Jack's call**, not urgent but
   flagged: SQLite foreign-key enforcement (currently off, root cause of
   several fixed orphaned-row bugs), the Postgres migration timing, and
   whether to add a route-level auth-convention check. See `TODO_MANUAL.md`'s
   "Backend architecture backlog" section.
9. **Resend sender domain still not set up, but a stopgap is live.**
   Password reset emails now redirect to Jack's own inbox (with the real
   requester's address + reset link in the body) instead of silently
   failing to send — see `backend/src/utils/email.js`. Real users still
   can't self-serve a reset without Jack manually forwarding the link;
   only fixed properly once a verified sending domain is set up.
10. **RevenueCat's live price point isn't confirmed anywhere in the docs.**
   The entitlement/payment mechanism is real and wired; the actual £ number
   hasn't been stated to me directly.
11. **"Record now" live camera calibration hasn't been tested on a real
    phone** — flagged as higher priority than it looks, since it's a live
    feedback loop that can feel fine in a single-request test but laggy in
    continuous real use.

## What's live

- Core analysis loop: MediaPipe pose extraction + DTW vs. the pro clip database
  (rebuilt 2026-09-02 to **415 reviewed entries** with audio-anchored contact
  times + view-direction tags), camera-angle inference, 216-tip coaching database
- **Audio-onset contact detection** wired into `compare_swing.py`'s auto-detect
  path (2026-09-02, uncommitted) — when the user doesn't mark a contact frame
  and the upload has audio, the ball-strike sound pins contact to <1 frame
- Ball detector Phase 3: fine-tuned YOLO model
  (`data/10b_ball_detection/yolo_ball_run_v1/`) wired into
  `racket_tracker.py` + `verify_shot_contact.py` — 95% detection /
  0.548 avg confidence at contact (up from ~50% / 0.41)
- Contact-verification rules + ML model
  (`verify_shot_contact_verified.py`, `shot_contact_ml_training_log.py`)
  with its own trust gate, mirroring the shot-classifier pattern
- RevenueCat payments, wired end-to-end (entitlement `premium`)
- Backend hosted (Hetzner + Docker) with **automated CD** (added
  2026-08-25 — push to `master` auto-redeploys, see `DEPLOY.md`;
  note: **no test gate runs before deploy** — a red suite still ships)
- Social/gamification: friends, leaderboards, Find Games court map,
  messaging, community-submitted courts
- History/progression tracking, 1-on-1 comparison, Drills (free tier)
- Self-serve password reset (Resend, sandbox sender)

## Competitive — SevenSix (assessed 2026-09-01)

Jack recorded a full walkthrough of **SevenSix** (`SevenSix AS`, Norway),
an iOS-only app with the same pose-extraction + compare-to-a-pro loop.

- **Not a capital or tech threat.** ~$550K raised total (grants + angel),
  iOS-only, ~4.0–4.34 App Store rating on ~62–80 ratings, visible
  reliability problems ("Aw Snap, our AI failed to analyse your video"),
  shipped-then-killed features. RallyMax is ahead on analysis depth
  (631-clip DTW, phase breakdown, synced side-by-side compare, ball speed).
- **The real risk is distribution** — their bet is tennis-federation
  partnerships, not the product.
- **Top 3 ideas from the teardown** (full detail: `docs/future-ideas.md`
  `### 2026-09-01`): (1) promote "record a session, we find the swings" to
  the primary flow — blocked by the serve-gate bug, item 1 above; (2)
  pre-record framing / pose-lock gate before recording is allowed; (3) a
  collapsed one-glance "hero result" as the default results screen.

## Where to look for more

- `HANDOVER.md` — the full dated build log, most detail
- `TODO_MANUAL.md` — the full backlog, chronological by session
- `DEPLOY.md` — how hosting + CD actually work
- `CLAUDE.md` — commands, architecture, where things live in the codebase
