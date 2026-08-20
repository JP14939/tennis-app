# Manual to-do — things only you can do

Everything here needs a human clicking through a dashboard, creating an
account, or physically testing with a device — none of it is something I
can do myself. Grouped by priority: **tomorrow** (finish payments, which is
mid-build) vs. **later** (deferred on purpose, don't lose track of them).

---

## ~~Tomorrow: finish wiring up payments~~ — resolved 2026-08-19

RevenueCat is connected and a monthly payment plan is live (done directly
by Jack, not verified step-by-step from this side). Annual/other plan
tiers weren't mentioned as done — add one later if you want a second
price point. Left the original checklist below for reference in case
anything needs revisiting (e.g. the `active_entitlements` vs `items`
field-name loose end in step 11, if Premium ever seems to unlock late
instead of instantly).

Context: the code side of RevenueCat/Stripe payments is built and the
backend logic is tested (webhook grant/revoke, audit logging) — but nothing
can go live until you do the account setup below. See the payments plan
this was built from for the full picture; this is just the "your turn" list.

1. **Create a RevenueCat account** (revenuecat.com) and a new project.
2. **Connect a Stripe account in test mode** to it (RevenueCat's dashboard
   walks you through this under Project Settings → Payment Gateways →
   Stripe/Web Billing).
3. **Create an entitlement** named exactly `premium` (this matches
   `REVENUECAT_ENTITLEMENT_ID=premium` already set in `backend/.env` — if
   you name it something else, update that env var to match instead).
4. **Create a product + package + offering** for the subscription (e.g.
   "RallyMax Premium", monthly, whatever price you want to test with) and
   attach it to the `premium` entitlement.
5. **Grab your keys** from RevenueCat's dashboard:
   - The **public Web Billing API key** → put in `frontend/.env` (copy from
     `frontend/.env.example` if `frontend/.env` doesn't exist yet) as
     `EXPO_PUBLIC_REVENUECAT_WEB_API_KEY`.
   - Your **Project ID** → `backend/.env` as `REVENUECAT_PROJECT_ID`.
   - A **v2 secret API key** with `customer_information:customers:read`
     permission (Dashboard → API Keys → create a new v2 key with that scope)
     → `backend/.env` as `REVENUECAT_SECRET_API_KEY`.
6. **Set a webhook shared secret**: pick any random string yourself, put it
   in `backend/.env` as `REVENUECAT_WEBHOOK_SECRET`.
7. **Start a tunnel** so RevenueCat can reach your laptop (it isn't hosted
   yet, on purpose — see "Later" below):
   ```
   ngrok http 5000
   ```
   Copy the `https://....ngrok-free.app` URL it gives you.
8. **Configure the webhook in RevenueCat**: Dashboard → Project Settings →
   Integrations → Webhooks → add
   `https://<your-ngrok-url>/api/webhooks/revenuecat`, and set the
   Authorization header value to the exact same string you put in
   `REVENUECAT_WEBHOOK_SECRET` in step 6.
9. **Restart the backend** (`npm run dev` in `backend/`) so it picks up the
   new `.env` values, and start the frontend web build (`npx expo start`,
   press `w`).
10. **Do one real test purchase**: log in as a test user in the app, go to
    the Premium tab, use a
    [Stripe test card](https://docs.stripe.com/testing) (e.g.
    `4242 4242 4242 4242`, any future expiry/CVC) to buy the subscription.
11. **Check it actually worked**:
    - The Premium screen should unlock immediately (no logout/login needed).
    - In `backend/data/app.db`, `SELECT tier FROM users WHERE email = '...'`
      should say `premium`.
    - `SELECT * FROM payment_events ORDER BY id DESC LIMIT 5` should show the
      `INITIAL_PURCHASE` event.
    - **Known loose end to verify here**: `backend/src/routes/billing.js`
      has a comment flagging that the exact JSON key RevenueCat's REST API
      wraps entitlements in (`active_entitlements` vs `items`) wasn't
      confirmed against a real response. If step 10 didn't unlock Premium
      instantly (only via the webhook, a few seconds later), that's
      probably why — check the backend console log for
      `[billing/sync] failed:` and tell me what it says; I'll fix the field
      name.
12. Send a manual `EXPIRATION` test event from RevenueCat's dashboard
    (Customer view → simulate event, or via their test tools) and confirm
    `tier` flips back to `free` and Premium re-locks.

---

## Also on the list: data quality & manual testing

**Review the high-camera-angle pro database entries.** Flagged as a known
gap since before this session — `infer_angle.py`'s Hough/keypoint detection
can't fully distinguish a genuine side-on camera from one positioned behind
the baseline (they look geometrically similar: a narrow net either way).
Checked the actual numbers tonight: **20 of 631 pro database entries** have
`camera_angle > 65°` — 14 forehand, 6 backhand, 0 serve. These are real
swings currently being matched against and scored for real users, so a
wrongly-labeled one could quietly produce a bad match/DTW comparison.
- List: run
  `python -c "import json; db=json.load(open('data/06_pro_database/pro_database.json')); [print(e['id'], e['camera_angle'], e['clip_path']) for e in db['entries'] if e.get('camera_angle') and e['camera_angle']>65]"`
  from `scripts/` (venv activated) to get the full 20 with their clip paths.
- For each: watch the clip (`clip_path`), decide if the framing is genuinely
  side-on (keep) or actually behind-the-baseline (the entry's angle is
  wrong — either fix `camera_angle` manually in `pro_database.json` or
  remove the entry entirely if the swing itself is otherwise unusable).
- **You don't have to do this eyeballing alone** — this is the same kind of
  visual review I did this session for labeling amateur swing footage
  (contact sheets, batches of frames). If you want, I can generate contact
  sheets for these 20 clips and do a first-pass read on which look
  genuinely side-on vs. mislabeled, then you make the final call on the
  handful that are ambiguous. Just say so next time.

**Test "Record now" (live camera calibration) on a real phone — genuinely
needs a real check, higher priority than it might look.** This is a live
feedback loop (repeated snapshots → `calibration_server.py` → positioning
badge updates in your hand as you move the phone), not a one-shot
request/response — the kind of thing that can look fine in a curl test
against a single frame but feel laggy, jittery, or just wrong once it's
actually running continuously while someone's trying to adjust their
camera. I confirmed the backend/calibration-server side end-to-end via
curl, but never watched the live loop itself. Run `npx expo start`, scan
into Expo Go, try "Record now" from the upload screen, and check: does the
badge update feel responsive (not laggy/stale), does it flicker between
states unhelpfully, and does the messaging (net not found / height
warnings / "looks good") actually make sense as you physically move the
phone around.

**Keep `frontend/config/api.js`'s LAN-IP fallback current.** If Expo Go
suddenly can't reach the backend and nothing else changed, this is almost
always why — check `ipconfig` and update the fallback IP in that file (or
just set `EXPO_PUBLIC_API_BASE` in `frontend/.env` instead, which now
overrides it).

---

## Later — deferred on purpose, don't forget these exist

~~**Rotate the leaked Anthropic API key.**~~ — resolved 2026-08-19, Jack
rotated `ANTHROPIC_API_KEY`.

~~**Hosting.**~~ — resolved 2026-08-19, Jack has this hosted now.
**Double-check, since these weren't explicitly confirmed done:**
`EXPO_PUBLIC_API_BASE` in `frontend/.env` actually points at the real
server (not still the LAN IP fallback), and the RevenueCat webhook URL in
RevenueCat's dashboard points at the real server rather than the old ngrok
tunnel (an expired/closed ngrok URL there would silently break tier
upgrades via webhook, though `/api/billing/sync` would still work as a
fallback since it hits RevenueCat directly).

**Apple App Store prep**, closer to submission time:
- Apple Developer Program enrollment ($99/yr).
- Set up an EAS development build (`eas build`) — plain Expo Go can't do
  real in-app purchases or Google Sign-In, both already hit this limit
  earlier in the project.
- Add native iOS purchases via RevenueCat's native SDK once the EAS build
  exists — this is a client-side slot-in, the backend webhook/entitlement
  logic already built today doesn't change for it.
- Privacy policy URL, app icons/screenshots, permission usage strings
  (photo library / camera / microphone access).
- Get the backend hosted (see above) *before* submitting — Apple's
  reviewers need a working backend during review, and won't be on your
  home Wi-Fi.

~~**Not yet committed to git**~~ — resolved 2026-08-18, everything through
that session's Drills & Lessons/theme/DB-audit work is now committed.

---

## New from the 2026-08-18 session

**Click through today's UI changes for real** — all verified via API calls
and the Metro bundler (compiles cleanly, real curl/database checks), but
none of it was actually clicked through as a live user this session:
- Swing Review's new rough-pick contact-marking step (History... actually
  Dev Page → Swing Review → pick a job → mark a real shot → confirm the
  rough scrub feels right before the fine ±50 slider takes over).
- Rally Boundary Review's lazy video loading (Dev Page → Rally Boundary
  Review on a job with several pending clips — confirm videos only start
  loading once tapped, not all at once).
- Drills & Lessons: History → Drills segment should now show 30 real
  drills instead of "coming soon"; try adding a test lesson via Dev Page →
  Drills & Lessons Editor and confirm the Lessons segment/Premium page
  entry behave as expected for a free vs. premium account.

**Seeing the new Android icon/splash for real needs a native build.** The
new mascot-based `android-icon-*.png`/`splash-icon.png` files are correct
on disk (verified by re-reading them), but Android icon/splash rendering
only happens at native-build time — you won't see them in Expo Go. Needs
an Expo prebuild or EAS build to actually check (same build step already
needed for App Store prep above — worth doing together).

~~**Data-quality: `coaching_tips_database.json` mojibake encoding bug.**~~
— checked 2026-08-20, couldn't reproduce: scanned the whole file
programmatically for the mangled-character pattern and for em/en dashes
generally, found zero of either. Looks like it was already fixed at some
point between when this was flagged and now (unclear exactly when/how).
Leaving this line struck rather than deleted in case it resurfaces —
if you spot mangled punctuation in a tip again, it's worth a fresh look.

---

## New from the 2026-08-20 session

**Decide on IMG_5755.MOV Claude verification spend.** Free dry-run (no
API cost) found **290 raw swing candidates** across its 33 minutes. At
IMG_5822's real measured rate (~$0.0093/call on Haiku), fully verifying
it would run **~$2.70**. Not run yet — waiting on your go-ahead. Run it
with `detect_rallies.py` once you're ready (same command pattern as the
IMG_5822 run).

**39 more unprocessed clips sitting in Downloads.** `IMG_5757`–`5774`,
`IMG_5795`–`5815` (39 files, mostly small — 3-110MB), plus `finesse
shot.mov` and `game-winnder-stable.mov`, have never been run through
even the free candidate-count dry-run. Say the word and I'll run the
free dry-run (`dry_run_candidate_count.py`, no Claude cost) across all of
them so you have real candidate counts/cost estimates for the whole
batch, not just the two big files.

**GitHub repo created.** `https://github.com/JP14939/tennis-app` —
currently **public** (flipped from private at your request 2026-08-20,
for sharing purposes). `data/` and `.env` are correctly gitignored and
never went up. If this was meant to be temporary, flip it back to
private when you're done sharing it (`gh repo edit JP14939/tennis-app
--visibility private`).

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
   the contact frame (the moment that matters most). Once/if item 1 lands,
   a small fine-tuned ball model — similar scope to how the racket
   keypoint model got built — is the natural next investment.
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
