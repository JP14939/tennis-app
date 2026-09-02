# RallyMax — Status

**What this file is:** a short, hand-curated snapshot, overwritten each time
someone updates it — not a log. Read this first if you just want to know
where things stand in under 2 minutes. For the full detailed history, see
`HANDOVER.md` (dated build log) and `TODO_MANUAL.md` (full backlog, also
chronological) — this file is a filter on top of those, not a replacement.

**Last updated:** 2026-09-01

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

1. **The `detect_rallies.py` serve-gate bug — needs Jack's call.**
   `scripts/11_highlight_clipping/detect_rallies.py`'s `apply_serve_gate()`
   treats >6s since the last *detected* swing as a point boundary, but the
   swing detector misses most real rally shots, so **100% of confirmed real
   forehands (12/12) in IMG_5755 were discarded** — the actual reason
   `rallies_detected: 0` despite real rallies. Blocks the rally-grouping /
   highlight-clip feature and skews the shot-classifier training data
   serve-heavy. Found 2026-08-26, not started — decide how to fix (decouple
   the point-boundary gap from detection reliability). See `TODO_MANUAL.md`
   2026-08-26 item 5.
2. **Shot-type classifier retrain is pending.** The log-derived feature
   extraction bug was found and fixed 2026-08-26 (now 102 real training
   rows, was 5 wrongly); `train_shot_classifier_model.py` has **not yet been
   re-run** on the corrected dataset. See `TODO_MANUAL.md` 2026-08-26 item 4.
3. **Off-box database backups are set up but the end-to-end check is still
   open.** B2 bucket `rallymax-db-backups`, `rclone` remote `b2remote` on
   the VPS (auth verified live), cron in `root`'s crontab (3am daily). Open
   since 2026-08-25: just needs someone to eyeball the bucket once for a
   real file landing after a 3am run to close it.
5. **A real beta launch hasn't happened.** The product is feature-complete
   well past the original MVP scope but has never been tested by real
   external users — biggest open strategic question.
6. **Three backend-architecture decisions need Jack's call**, not urgent but
   flagged: SQLite foreign-key enforcement (currently off, root cause of
   several fixed orphaned-row bugs), the Postgres migration timing, and
   whether to add a route-level auth-convention check. See `TODO_MANUAL.md`'s
   "Backend architecture backlog" section.
7. **IMG_5755.MOV Claude verification is done.** Ran against 290 raw swing
   candidates — **54 confirmed real**. Job #9 is ready in Dev Page → Swing
   Review (cache pre-warmed, 7 rally clips + full video as an 8th
   candidate). Output in `data/runtime/highlight_clips/verify_5755/`,
   separate from the database.
8. **Resend sender domain still not set up, but a stopgap is live.**
   Password reset emails now redirect to Jack's own inbox (with the real
   requester's address + reset link in the body) instead of silently
   failing to send — see `backend/src/utils/email.js`. Real users still
   can't self-serve a reset without Jack manually forwarding the link;
   only fixed properly once a verified sending domain is set up.
9. **RevenueCat's live price point isn't confirmed anywhere in the docs.**
   The entitlement/payment mechanism is real and wired; the actual £ number
   hasn't been stated to me directly.
10. **"Record now" live camera calibration hasn't been tested on a real
    phone** — flagged as higher priority than it looks, since it's a live
    feedback loop that can feel fine in a single-request test but laggy in
    continuous real use.

## What's live

- Core analysis loop: MediaPipe pose extraction + DTW vs. 631 pro clips,
  camera-angle inference, 216-tip coaching database
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
