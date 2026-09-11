# PRE_RELEASE_CHECK.md

Pre-launch checklist for RallyMax, distilled from four external videos (Sept 2026)
plus a first-pass audit of the current backend against them.

Legend: `[x]` done / verified in code · `[~]` partially done, gap noted · `[ ]` not started · `[infra]` needs a dashboard/console change, not code

Source videos:
1. *My App Makes $50K/Month: This Is My ASO Playbook* — Starter Story Build (w/ Sebastian, HabitKit) — `youtu.be/I2GG0lyb_RI`
2. *Vibe Coding Has A Security Problem (And How To Fix It)* — Chris Raroque — `youtu.be/tK4NQtzfZbM`
3. *Just SOLD my 2nd Vibe-Coded app (Full Breakdown)* — Code Playbook (Pete McPherson) — `youtu.be/Ppb5B20OqU8`
4. *16 Ways to Vibe Code Securely* — Matt Palmer (Replit) — `youtu.be/0D9FMFyNBWo`

---

## A. Security (videos 2 & 4)

Our stack is Express + SQLite + `child_process.spawn(python)`, not Supabase/Firebase,
but the threat models map almost 1:1. **The `/analyse` and `/compare-videos` routes spawn a
CPU-heavy Python/MediaPipe process — that is our "expensive endpoint".**

### A1. Rate limiting on expensive endpoints  `[x]`
- `[x]` `/analyse` — `analyseLimiter` (30 / 10 min), keyed by **user id** so account-rotation behind one IP doesn't help. `backend/src/routes/analyse.js:32`
- `[x]` `/compare-videos` — `compareLimiter` (15 / 10 min), keyed by user id. `backend/src/routes/compareVideos.js:20`
- `[x]` Auth endpoints (`/auth/login`, `/auth/signup`, `/auth/forgot-password`) rate-limited — `backend/src/middleware/rateLimit.js` header comment; unrestricted signup was itself a path to unlimited fresh free-tier quotas.
- `[x]` Sliding-window (not tumbling) counter, so the window-boundary 2x-burst is closed. `rateLimit.js:36-64`
- `[x]` **IP-based layer on the analysis endpoints** (done 2026-09-09): `analyseIpLimiter` (80 / 10 min per IP) + `compareIpLimiter` (40 / 10 min per IP), chained before the per-user limiters. Bounds one origin cycling through many accounts. Regression test in `analyse.rateLimit.test.js`.

### A2. Subscription status must not live where the user can write it  `[x]`
- `[x]` `tier` is a `users` column written **only** by the RevenueCat webhook (`routes/webhooks.js`) and `POST /billing/sync` (server-to-server call to RevenueCat's REST API with a secret key). No client-settable path.
- `[x]` `currentTier()` always re-reads from the DB — never trusts a `tier` claim in the 30-day JWT. `backend/src/utils/tier.js`
- `[x]` Webhook auth = constant-time shared-secret compare; `app_user_id` must be all-digits or it maps to "no user" (prevents UUID→int collision flipping a real user). `webhooks.js:30-63`
- `[x]` `/billing/sync` is upgrade-only (never downgrades) and gated on `token_version` so a post-deletion race can't resurrect `premium`.
- `[x]` Free-tier daily cap (`FREE_DAILY_LIMIT = 2`) reserved via one synchronous transaction (`reserveDailyUsageSlot`) — the check-then-insert race is closed; counters are in `analysis_usage`, a table with no client write path.
- `[x]` `users.tier IN ('free','premium')` at-rest check already existed (`integrityChecks.js` `users.tier`).
- `[x]` **`analysis_usage.daily_cap` check added** (done 2026-09-09): no account has more than `FREE_TIER_DAILY_ANALYSIS_LIMIT` analyses recorded for a single day. Constant moved from two route files into `domain/invariants.js` (single source of truth for `analyse.js`, `highlights.js`, and the check). `verify:db` now 99 invariants, all hold against prod.

### A3. Budget caps + billing alerts on every paid API  `[infra]`
- `[ ]` `[infra]` KIE (`KIE_API_KEY` in `tennis_app/.env.local`, video-gen) — set hard spend cap + alert.
- `[ ]` `[infra]` Anthropic (`ANTHROPIC_API_KEY`) — budget cap + alert. Not on the live request path today (`09_coaching_ai` unused) but the key exists.
- `[ ]` `[infra]` AWS (`AWS_ACCESS_KEY_ID` / S3) — budget cap; scope the IAM key to S3-only (Chris/Matt both had 5-figure bills from over-permissioned leaked AWS keys used for SageMaker training).
- `[ ]` `[infra]` Resend, RevenueCat — usage alerts.
- `[ ]` `[infra]` Hetzner box — no autoscaling, so the real DoS ceiling is the single box. Confirm the ML timeouts (`ANALYSIS_TIMEOUT_MS = 2 min`, `COMPARE_TIMEOUT_MS = 3 min`) + rate limits are tuned to what one box survives under concurrent load.

### A4. No secrets / sensitive calls from the frontend  `[x]`
- `[x]` Only `EXPO_PUBLIC_*` vars in the frontend, all publishable RevenueCat keys (safe client-side by design). `frontend/.env.example`
- `[x]` All ML / paid-API calls go through the backend; the client only talks to our Express API.
- `[x]` **Source-level secret sweep** (done 2026-09-09): no hardcoded keys/tokens in `frontend/**`, no `process.env.*` refs outside `EXPO_PUBLIC_*` / `NODE_ENV`, `.env` + `.env.local` are gitignored, `app.json` / `eas.json` carry nothing sensitive.
- `[ ]` `[infra]` Grep the actual built bundle once before release (needs an EAS build) as a final belt-and-braces check.

### A5. Input validation & upload hardening  `[x]`
- `[x]` `videoFileFilter` rejects non-video extensions before disk write; `safeVideoExt` prevents an attacker-controlled extension (`.html`, `.svg`) naming a file later served from a static mount (stored-XSS vector). `backend/src/utils/videoUpload.js`
- `[x]` 200 MB file-size cap in multer.
- `[x]` `contactTime` / `contactTimeA/B` validated with `isTimestampSec` (rejects negative / absurdly large before reaching Python).
- `[x]` Shared `invariants.js` + `validateBody.js` (write-time 400s) + `integrityChecks.js` (`verify:db` at-rest re-check).
- `[ ]` Confirm magic-byte / ffprobe sniffing isn't needed — extension check is currently the only gate on file *content*. Low priority (the bytes only ever go to MediaPipe, never re-served as HTML thanks to `safeVideoExt`).

### A6. Error handling — don't leak internals  `[x]`
- `[x]` `analyse.js` / `compareVideos.js` log Python stderr **server-side only**; the client gets generic messages (`Analysis failed`, `timed out`, …).
- `[x]` `pro_matcher.py` and `video_matcher.py` both redact the upload path down to its basename before an exception message can flow back through `runPythonJson`'s `nonzero_exit` branch to the caller.
- `[x]` Post-response fire-and-forget spawns (`CONTACT_FRAME_LOGGER`) have `.on('error')` handlers so a spawn failure can't crash the process after headers are sent.

### A7. Route auth convention  `[x]`
- `[x]` `routeAuthConvention.test.js` fails CI if any route lacks `requireAuth`/`optionalAuth` and isn't a reasoned exception in `routeAuthExceptions.js`. This exists because of a real 2026-08-22 free-tier-cap bypass.

### A8. Use the LLM as a pen-tester  `[ ]`
Both videos: don't ask "check my security" — ask specific adversarial questions. Standing prompts to run against the repo before release:
- Can a user bypass their subscription status / grant themselves `premium`?
- Can a user reset or inflate their own rate-limit / daily-usage counters?
- Can one user read another user's history / highlights / clips / drills? (IDOR on every `:id` route.)
- Can `/analyse`, `/compare-videos`, or any `/dev/*` route be hit unauthenticated?
- Prompt-injection / path-traversal via any string that reaches a Python argv or a filesystem path.
- Can a static mount (`/user-clips`, `/comparison-clips`, `/highlight-clips`, `/drill-clips`) serve a non-video or another user's file?
- `[x]` **IDOR / broken-authz sweep** (done 2026-09-09): audited every `:id` resource route — `history/:id`, `analyses/:analysisId/annotations` (GET+PUT), `highlights/jobs/:id`, `highlights/reel-jobs/:id`, `highlights/rallies/:id` (PATCH), `highlights/rallies/:id/shots/...`, `friends/shared/:analysisId`, `friends/:userId/matches`, `coach/students/:studentId/history`, `drills/:stepId/practice`. **All enforce ownership** — `WHERE ... AND user_id = ?`, a shared `canAccessAnalysis` / `isLinked` / `isLocked` helper, or an explicit owner-or-recipient check. Combined with `routeAuthConvention.test.js` this axis is solid; no change needed.
- `[ ]` Chris's free markdown audit file (linked in video 2 description) — grab it, run it through Claude Code against the repo. (Manual — needs the video's description link.)
- `[~]` **`npm audit` run 2026-09-09:**
  - `[x]` **backend: `multer` 2.2.0 → 2.3.0** — 4 high-severity DoS advisories (crafted multipart field names, fd leak on aborted uploads, fileFilter race, oversized array index), all directly on our `/analyse` + `/compare-videos` upload path. Bumped; 626 tests green.
  - `[ ]` backend: `js-yaml` 3.15.1 (CPU-DoS on YAML merge keys) — **dev-only**, transitive via `jest → babel-plugin-istanbul → @istanbuljs/load-nyc-config`, only ever parses our own `.nycrc`. Not shipped. Leave until the jest tree moves it.
  - `[ ]` frontend: 35 advisories (`xmldom`, `metro`, `image-size`, `fast-uri`, `@expo/prebuild-config`, …) — **almost all Expo/Metro build toolchain**, not in the shipped bundle. **Do NOT `npm audit fix --force`** — it would drift the pinned Expo SDK 54 tree (see `frontend/AGENTS.md`). Resolve via Expo SDK patch bumps / the tracked SDK 55 upgrade. One shipped item: `decode-uri-component` (ReDoS) via `query-string` via `@react-navigation` deep-link parsing — moderate, no upstream fix yet, low exposure (we don't parse hostile deep links).
- `[x]` **Dropped unused deps** (done 2026-09-09): removed `pg`, `redis` (the CLAUDE.md scaffolding note; `bull` was already gone) and `axios` (billing.js uses native `fetch`) from `backend/package.json`. `require()`'d nowhere in `backend/**`. `package-lock.json` shed ~328 lines; suite 626 green, `verify:db` 99/99. Backend runtime deps now: `bcryptjs, better-sqlite3, compression, cors, dotenv, express, jsonwebtoken, multer`.

### A9. HTTPS / headers / DoS  `[~]`
- `[x]` TLS terminated by Caddy (`Caddyfile`), `trust proxy` set so `req.ip` is the real client.
- `[x]` **Security headers added** (done 2026-09-09): `middleware/securityHeaders.js` — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` (protects the reset-token URL), `Cross-Origin-Resource-Policy: cross-origin` (keeps the clip mounts loadable by the Expo app), `X-Permitted-Cross-Domain-Policies: none`, plus a strict CSP on the served `reset-password.html` only. Hand-rolled, no `helmet` dep — matches `rateLimit.js` ethos. Test: `securityHeaders.test.js`.
- `[ ]` `[infra]` Scan the live host with securityheaders.com after next deploy.
- `[x]` Secure-cookie flags aren't relevant (JWT in header, not cookie); no session cookie is set anywhere.
- `[ ]` `cors()` is wide-open (all origins). Fine today — JWT-in-header, no cookies — but consider an allowlist (Expo web origin + `PUBLIC_BASE_URL`) if a cookie/credential flow is ever added.

---

## B. App Store Optimization (video 1)

Sebastian: 98% of HabitKit's users come from App Store / Play search, zero paid marketing.
ASO is a 6-month-to-3-year game — do the foundations right now.

### B1. Name + subtitle (single biggest ranking factor)  `[ ]`
- `[ ]` Keyword research first: LLM brainstorm → validate volume/difficulty in an ASO tool. Candidates: "tennis coach", "swing analysis", "serve analyzer", "tennis technique", "AI tennis", "tennis training".
- `[ ]` Put the primary keyword **in the app name**, e.g. `Tennis Swing Analysis – RallyMax` or `AI Tennis Coach – RallyMax` (HabitKit ships as `Habit Tracker – HabitKit`).
- `[ ]` Subtitle (30 chars) = secondary keywords, **no words repeated** from the name (Apple indexes name+subtitle as one string).
- `[ ]` Fill all 100 chars of the App Store Connect keyword field: comma-separated, no spaces, no plurals-if-singular-used, no competitor names, no repeats of name/subtitle.

### B2. Screenshots (drive conversion — 3-5 sec to convince)  `[ ]`
- `[ ]` First screenshot = most visually distinctive feature. For us: the **pro side-by-side overlay + 0-100 score**, NOT the upload / onboarding screen.
- `[ ]` Show real UI, not lifestyle photos or abstract graphics.
- `[ ]` A/B test via Apple Product Page Optimization. Sebastian's polished designer screenshots *lost* to his scrappy originals — always test, never assume "fancier = better".

### B3. Ratings & reviews (feed ranking + conversion, compounding moat)  `[~]`
- `[x]` **Review prompt at a happy moment — scaffolded** (done 2026-09-09): `frontend/utils/reviewPrompt.js` + wired into `ResultsScreen.js`. `recordHappyEvent()` fires immediately on a **saved fresh analysis** (so leaving the screen fast doesn't lose the count); `considerReviewPrompt()` 2.2s later shows the native `expo-store-review` sheet only if gated: authenticated, score ≥ 50, 2nd+ happy event, ≥ 60 days apart, ≤ 3 lifetime, OS has final say. Dev Page has a "Test 'rate the app' prompt" button. `expo-store-review@~9.0.9` installed (no config plugin).
- `[ ]` Add `ios.appStoreUrl` / `android.playStoreUrl` to `app.json` once listings exist (for the older-Android fallback). Tracked in `TODO_MANUAL.md`.
- `[x]` Respect dismissal — the OS native sheet gives no callback, so we track *attempts* and back off (60-day gap, 3 lifetime) rather than re-asking.
- `[ ]` Reply to every review (good: thank; bad: help + fix). People flip 1★→5★ after a fix.
- `[ ]` Support-email signature: "If you're enjoying the app, I'd be grateful for a review."
- `[ ]` Treat repeated review requests as a feature-priority signal (20 people = strong signal).

---

## C. Growth / product / sale-readiness (video 3)

Pete's post-mortem on a vibe-coded app that sold for 5 figures (would have been 6 if he hadn't let it coast).

### C1. Onboarding is underrated  `[~]`
- `[x]` **Plan** → `docs/plans/onboarding_plan.md`.
- `[x]` **Phase 1 built** 2026-09-09 (trimmed per Jack): backend "gate at the reveal" (Option B) — `/analyse` is `optionalAuth` + a **2/24h per-IP** guest cap consumed *inside* the handler after validation (`tryConsume`), 429 carries `code: 'GUEST_LIMIT'`; guests skip the free-tier/handedness/logger paths. Frontend — `OnboardingScreen` (one screen), `utils/onboarding.js`, `App.js` initial-route gate, `ResultsScreen` guest reveal-gate + the latent "runAnalysis sent no auth header" bug fixed + a `GUEST_LIMIT` error-branch signup CTA, `Signup`/`Login` `returnTo` handoff via shared `utils/navigateAfterAuth.js`. `analyse.guestPath.test.js` added; suite **631 green**; web bundle builds clean.
- `[ ]` **Phase 2** (deferred): result coach-marks, contact-frame lead-in card, permission pre-prompts, welcome-email drip, funnel instrumentation.
- `[ ]` **Needs Jack**: test the flow on a device; decide Phase 2 priority; open questions 3–6 in the plan (illustrations, emails, default shot type, replay-from-Settings).

### C2. Don't let it coast  `[ ]`
- `[ ]` A launched app decays without continued feature pushes + marketing beats. Plan the post-launch cadence *now* (tweak → relaunch → feature push → relaunch).

### C3. Build-to-sell hygiene (also just good ops)  `[ ]`
- `[ ]` SOPs / runbook (we have `HANDOVER.md` / `STATUS.md` / `DEPLOY.md` — keep current).
- `[ ]` Clean financials + a testimonials doc (Google Doc, collect from day one).
- `[ ]` Separate accounts per service (own Gmail + branded domain) so a future handoff is "here's the login" not a migration.
- `[ ]` Emotionally detach — a healthy business is separable from the founder.

### C4. Technical  `[~]`
- `[x]` Stick with the known stack (Expo + Express + SQLite + Python) — don't chase new frameworks pre-launch.
- `[ ]` **Vibe-testing**: point Claude Code at the codebase specifically to hunt bugs/edge cases before users do, not just to write features.
- `[x]` Structured outputs from AI APIs — relevant when `09_coaching_ai` goes live; use JSON-schema-constrained responses, not free-text parsing.
- `[ ]` "Can't ChatGPT just do this?" — our moat is the pro-DB + DTW + pose pipeline + the packaged UX, not raw LLM output. Keep the differentiation sharp in store copy.

---

## Item 1 — Security audit pass (done 2026-09-09)

Audited `analyse.js`, `compareVideos.js`, `rateLimit.js`, `tier.js`, `requirePremium.js`,
`usageLimit.js`, `webhooks.js`, `billing.js`, `videoUpload.js`, and the two Python wrappers.

**Finding: the backend is already heavily hardened** — most of what videos 2 & 4 warn about
is done (see A1, A2, A5, A6, A7 above). Remaining, in priority order:

1. `[x]` **IP-based rate-limit layer on `/analyse` + `/compare-videos`** (A1 gap) — done 2026-09-09, `analyse.js` / `compareVideos.js` + `analyse.rateLimit.test.js`; full suite (622) green.
2. `[x]` **`verify:db` / `invariants.js` checks** for `tier` vocabulary + `analysis_usage` cap (A2) — done 2026-09-09, `analysis_usage.daily_cap` check + `FREE_TIER_DAILY_ANALYSIS_LIMIT` moved to `invariants.js`; suite 624 green, `verify:db` 99/99.
3. `[ ]` `[infra]` **Budget caps** on KIE / Anthropic / AWS / Resend / RevenueCat (A3), + scope the AWS IAM key to S3-only. **Needs you — dashboard work, I can't do it.**
4. `[x]` **Security headers** in `server.js` (A9) — done 2026-09-09, `middleware/securityHeaders.js` + test; suite 626 green.
5. `[x]` `npm audit` + dep cleanup — done 2026-09-09: backend `multer` 2.2.0→2.3.0 (4 high DoS advisories on the upload path); removed unused `pg`/`redis`/`axios`; `js-yaml` (dev-only) + frontend toolchain advisories documented & deferred (no `audit fix --force` on Expo SDK 54).
6. `[~]` A8 adversarial pass — IDOR / broken-authz sweep of every `:id` route done 2026-09-09 (all enforce ownership; no change). Chris's external audit-markdown still to run manually.
7. `[~]` Section B (ASO) / Section C (onboarding):
   - `[x]` **B3 review prompt** — built (`utils/reviewPrompt.js` + `ResultsScreen`, `expo-store-review` installed, Dev Page test button).
   - `[x]` **C1 onboarding Phase 1** — built ("gate at the reveal", `OnboardingScreen`, guest `/analyse`, `ResultsScreen` reveal-gate; `docs/plans/onboarding_plan.md`).
   - `[ ]` B1 store name + keyword research, B2 screenshot reorder, C1 Phase 2, device tests — **need you**.
8. `[x]` `/code-review` (Standards + Spec) + correctness pass over the working diff → 8 fixes applied (2026-09-09, see progress log). Backend suite 631 green; the later review/audit batch was pushed as `2f750e6`.

The reviewed release work is committed and pushed as `2f750e6`. Remaining items below are operational or human/device checks, not an uncommitted code tangle.

---

## Progress log

- **2026-09-09 (later)** — ran `/code-review` (Standards + Spec) + a correctness pass over the uncommitted session diff, then applied 8 fixes:
  1. guest analysis cap now consumed *inside* the handler after all validation (via new `tryConsume` in `rateLimit.js`), so a fat-fingered file pick no longer burns a slot; cap 3→2
  2. reworded the overstated "posing as a guest is strictly worse" comment (it's 2 free + 2 guest/IP — a small residual gap, documented not closed)
  3. `GUEST_LIMIT` response code → `ResultsScreen` error branch shows "Create a free account" instead of a bare "Analysis failed"
  4. fixed stale comments in the guest reveal-gate (claimed Signup passes `savedResult`; it doesn't)
  5. removed the dead `saveStatus === 'guest'` banner
  6. extracted `ipRateLimit(prefix, max, opts)` — collapses 3 hand-repeated IP-limiter blocks
  7. extracted `navigateAfterAuth(navigation, returnTo)` — Login + Signup shared 4 copy-pasted sites
  8. split `recordHappyEvent()` (immediate) from `considerReviewPrompt()` (delayed) so the happy-event count isn't lost when a user leaves the result screen fast
  Backend suite **631 green**, `verify:db` 99/99, web bundle builds clean.

- **2026-09-09** — created from the 4 videos. Backend security audit (A1–A9): found already heavily hardened.
  Shipped and pushed in the subsequent release batch, backend suite 626 green, `verify:db` 99/99:
  - IP-keyed rate-limit backstop on `/analyse` + `/compare-videos` (`analyseIpLimiter`/`compareIpLimiter`)
  - `analysis_usage.daily_cap` integrity check; `FREE_TIER_DAILY_ANALYSIS_LIMIT` centralised into `invariants.js`
  - `middleware/securityHeaders.js` (nosniff / frame-deny / no-referrer / CORP / CSP-on-HTML) wired into `server.js`
  - `multer` 2.2.0 → 2.3.0 (4 high-severity upload-path DoS advisories)
  - IDOR sweep of all `:id` routes — clean
  - removed unused backend deps `pg` / `redis` / `axios`
  - **B3 review prompt scaffolded** — `frontend/utils/reviewPrompt.js`, wired into `ResultsScreen`, `expo-store-review@~9.0.9` installed, Dev Page test button, `DevDashboardScreen` updated
  - source-level secret sweep (A4) — clean
  - **onboarding — plan + Phase 1 built** — `docs/plans/onboarding_plan.md`; `OnboardingScreen`, guest "gate at the reveal" (`/analyse` optionalAuth + 3/24h guest IP cap), `ResultsScreen` reveal-gate, `Signup/Login` returnTo, latent no-auth-header bug fixed. `analyse.guestPath.test.js`; suite 628; web bundle builds clean.
  Remaining: infra budget caps (A3), securityheaders.com scan post-deploy, B1/B2 (product), onboarding Phase 2 + device test.
