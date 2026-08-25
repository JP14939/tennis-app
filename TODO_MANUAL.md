# Manual to-do — things only you can do

Everything here needs a human clicking through a dashboard, creating an
account, or physically testing with a device — none of it is something I
can do myself. Grouped chronologically by session below; skim for `~~struck
through~~` (resolved) vs. plain (still open) headings if you're catching up.

**Quick status as of 2026-08-22, for a fresh chat starting cold:**
**a large amount of local work is uncommitted** — a database-verification
framework, two audit-round fixes, and native-device bug fixes (see
`HANDOVER.md` item #42 for the full picture) are all sitting in the working
tree, tested and green (418 backend tests, `npm run verify:db` clean, web
bundle builds), but never committed or pushed. One exception: a one-line
SQL fix to `courts.js` was deployed directly to the hosted server today
(isolated from the rest of this uncommitted work) and is live. Real open
items, cheapest first:
- **Commit and push today's work** — nothing lost, just never asked for.
  See the new section below for what's in scope.
- **Resend account** needed for password reset emails to actually send
  (`RESEND_API_KEY` unset) — see "self-serve password reset" section below.
- **IMG_5823.MOV**: dry-run only (6 candidates), never Claude-verified.
- **230 ball-label frames** waiting on manual review in the Dev Page's
  Ball Label tool.
- **IMG_5755.MOV**: ~$2.70 Claude verification spend, waiting on a go-ahead.
- **20 high-camera-angle pro clips**: offered to generate contact sheets
  for a first-pass review, never followed up.
- RevenueCat's `active_entitlements`/`items` field-name loose end
  (only matters if Premium ever unlocks late instead of instantly).

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
3. **No CI/CD.** Every deploy is a manual SSH + `git pull` +
   `docker compose up --build app` — see item #41 in `HANDOVER.md` for
   how this let the hosted server run stale code across multiple
   sessions without anyone noticing. Needs your call (GitHub Actions
   vs. something simpler, and whether the Hetzner box should accept
   inbound deploy hooks at all).
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

1. **Review the 5 flagged ball-label clips** (Dev Page → Ball Label data,
   `manual_ball_label_log.jsonl` on the hosted server) — `analysis534`,
   `analysis501`, `analysis532`, `analysis519`, `analysis522` all show zero
   motion across their entire labeled sequence, flagged by
   `scripts/07_ball_racket_tracking/audit_ball_label_motion.py` as likely
   static-decoy contamination. For each, confirm keep (a real slow/soft
   shot) or exclude (was a decoy) before Phase 3 fine-tuning starts. See
   `HANDOVER.md` item #43 for the full story.
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
