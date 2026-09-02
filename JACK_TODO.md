# Jack's To-Do List

A flat, actionable checklist of everything that needs a human (you) —
account creation, dashboard clicks, real-device testing, or a judgment call
only you can make. Pulled together from `TODO_MANUAL.md` (the full narrative
log, still the source of truth on *why*) plus everything that came up in the
2026-08-23 PR-merge/browser-testing session. Check items off as you go;
`TODO_MANUAL.md` stays the append-only history, this is just the flat list.

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
- [x] ~~Work through the 230 ball-label frames~~ — done, 354 labels logged
      total. **New follow-up** — [ ] **review 5 flagged clips for
      static-decoy contamination**: a real gap in the labeling tool meant a
      static (not in-play) ball sometimes got boxed and logged identically
      to a real label. An audit script
      (`scripts/07_ball_racket_tracking/audit_ball_label_motion.py`) flagged
      `analysis534`, `analysis501`, `analysis532`, `analysis519`,
      `analysis522` as showing zero motion across their whole labeled
      sequence — for each, confirm keep (real slow/soft shot) or exclude
      (was a decoy) before Phase 3 fine-tuning starts.
- [ ] **Decide on `IMG_5755.MOV` Claude verification spend** (~$2.70,
      290 raw candidates found in the free dry-run) — give the go-ahead or
      skip it.
- [ ] **`IMG_5823.MOV`** — dry-run found 6 candidates, never Claude-verified;
      decide if it's worth the (small) spend.
- [ ] **85 old History rows have no watchable video on the hosted server**
      (from the 2026-08-14 local batch-analysis run) — decide if it's worth
      a one-time `scp`/`tar` copy of `data/runtime/user_clips/8_*` to the
      host to make them watchable, or leave as-is.

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

## ML pipeline — fix the base before the top (bottom-up sprint plan, 2026-08-27)

Rally detection sits on top of a dependency chain: **shot contact detection →
shot type classification → serve gate → rally grouping**. Job 10 (real Claude
verification, `IMG_5755.MOV`) surfaced a break at the *second* level, which
silently wrecks everything above it — decided 2026-08-27 to stop patching
top-down and instead harden each level before trusting the one built on it.

- [ ] **Sprint 1 — shot-type classifier is over-predicting "serve"**: job 10
      found Claude itself classified 46 of 60 real, contact-verified shots as
      `serve` (14 forehand, 0 backhand) on `IMG_5755.MOV` — footage job 8
      (before the serve-gate existed) found 32 real rally clips in. A rally
      session doesn't become 77% serves once verification turns on, so this
      is very likely a real classifier miscalibration, not reality. Needs:
      pull the 46 "serve" clips job 10 logged and eyeball a sample — are they
      actually serves? If not, this is where to focus (prompt/logic in
      `scripts/14_shot_classifier/classify_shot_verified.py`) before touching
      rally logic again.
- [ ] **Sprint 2 — re-check the serve gate's assumption** (`apply_serve_gate()`
      in `scripts/11_highlight_clipping/detect_rallies.py`) once Sprint 1 is
      solid — right now it requires a `serve` to open every point, which is a
      reasonable model of real match play but may be too strict for practice
      footage where points don't always start with a formal serve.
- [ ] **Sprint 3 — only then re-run rally detection** (job 10 was `IMG_5755.MOV`,
      Claude-verified, ended at 0 rallies — don't re-spend Claude credits
      re-running this until Sprints 1–2 are done, or the same collapse just
      repeats).
- [ ] Revisit the separate, still-open **shot classifier accuracy gap**: docs
      claim 63.8% cross-validation accuracy but live agreement logs showed
      ~51% — may be the same root cause as Sprint 1, may be separate; check
      once Sprint 1's sample review is done.

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
- [ ] **Ball-speed feature**: scoped but not started. Recommended v1
      approach uses the net-keypoint model for a local scale calibration,
      measuring speed *at the net crossing* rather than off the racket at
      contact (a real, disclosed limitation — a full court-plane homography
      for contact-accurate speed anywhere in frame is a bigger, separate
      project). Also recommended holding this behind Phase 3 ball-detector
      fine-tuning landing first. Say the word whenever you want to
      greenlight actual implementation.

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
