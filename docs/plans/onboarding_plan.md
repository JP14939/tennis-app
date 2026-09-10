# Onboarding plan (RallyMax)

Planning doc for **PRE_RELEASE_CHECK.md item C1** — "onboarding is underrated"
(from the Pete McPherson "sold my vibe-coded app" video: his churn was high
purely because users didn't know how to use the app). Nothing here is built
yet; this is the design + a phased build order.

Status: **Phase 1 built, 2026-09-09** (trimmed per Jack — no coach-marks, no
contact-intro card, no permission pre-prompts, no rotating loader copy).
Uncommitted. Owner: Jack.

### What shipped (Phase 1, trimmed)

**Backend — "gate at the reveal" (Option B):**
- `routes/analyse.js`: `requireAuth` → `optionalAuth`. Guests can run an
  analysis; `isGuest` skips the free-tier reservation, handedness lookup, and
  the contact-frame training logger.
- Guest cap: **2 / 24h per IP**, consumed *inside the handler* (via
  `tryConsume` from `rateLimit.js`) only once a request has cleared every
  validation gate and is about to spawn Python — a bad file pick costs
  nothing. 429 carries `code: 'GUEST_LIMIT'`. This does not fully close the
  "capped free user drops the token for 2 more runs per IP" gap — documented,
  judged not worth engineering against on a single box.
- `analyse.guestPath.test.js` — guest request is accepted past auth (400 on bad
  input, not 401); the cap core is unit-tested via `tryConsume` in
  `rateLimit.test.js`. Full suite 631 green, `verify:db` 99/99.

**Frontend:**
- `utils/onboarding.js` — `isOnboardingComplete()` / `markOnboardingComplete()`
  / `resetOnboarding()`, over `storage` key `onboarding_complete`.
- `screens/OnboardingScreen.js` — one screen (not a deck): payoff line + the
  three steps + "Analyse my first swing" / "Skip for now". Marks complete on
  either button.
- `App.js` — `RootNavigator` resolves the stored session + the onboarding flag
  before first render; initial route is `Onboarding` only when
  `!onboardingComplete && !isAuthenticated`.
- `ResultsScreen.js` — (1) `runAnalysis()` now sends the `Authorization` header
  when a token exists (it never did — latent bug); (2) a guest who completes an
  analysis sees a **reveal gate** ("Your score's ready — create a free
  account") instead of the result body; (3) an effect saves the held result to
  history once `isAuthenticated` flips (guest → signup → pop back).
- `SignupScreen.js` / `LoginScreen.js` — accept a `returnTo` param so signup
  mid-onboarding pops back to the result instead of going to Home; Signup
  sub-copy adapts ("One step to see your score").

**Not built (deferred / cut):** the 3-step result coach-mark overlay, the
contact-frame lead-in card, `PermissionPrePrompt`, rotating "analysing…" copy,
the welcome-email drip, funnel instrumentation. See §9 phasing — these are
Phase 2.

---

## Original plan follows


---

## 1. What exists today

The app has **no first-run experience**. A fresh install lands straight on
`HomeScreen` (via `MainTabs`, initial route `Home`) as a guest. The only
onboarding-shaped pieces that exist:

| Piece | Where | What it does |
|---|---|---|
| `FirstSwingCard` | Home, shown when `analyses.length === 0` | Static "Here's what comes back" card (3 bullet points). Good, but passive. |
| Fence-mount tutorial | `ContactMarkingScreen`, `phase === 'tutorial'`, gated by `storage` key `tennisai_seen_fence_tutorial` | Rubber-band phone-mounting guide (`FenceTutorialContent`), shown once before the first video pick. |
| Filming-position picker | `ContactMarkingScreen`, `phase === 'filming-position'` | "Where's your camera?" — net / behind-baseline / side. |
| Signup perks list | `SignupScreen` | 3 bullets: "2 free analyses/day", "scored against pro technique", "personalised tips". |
| `saveStatus === 'guest'` banner | `ResultsScreen` | "Log in to save this result →" — **but see §2, this path is effectively dead.** |

There is **no** welcome screen, no explanation of the core loop before you're
dropped into it, no guided first swing, no email sequence, and no analytics on
any of it.

---

## 2. Problems to fix (found while surveying)

### 2a. The guest wall is in the wrong place and is broken

`POST /api/analyse` is `requireAuth` (correctly — it's the expensive ML
endpoint, and free-tier caps depend on a user id). But:

- `HomeScreen`'s "Start analysis" CTA navigates to `Upload` with **no auth
  check**. `ContactMarkingScreen` has no auth guard either.
- `ResultsScreen.runAnalysis()` calls `/api/analyse` with **no `Authorization`
  header at all** (`frontend/screens/ResultsScreen.js` ~line 254).

So a logged-out user can: tap Start analysis → sit through the fence tutorial →
pick a video → mark the contact frame → land on Results → and **get a generic
"Analysis failed"** (a 401 they can't act on). They invested 60+ seconds of
effort and hit an opaque wall. This is the single worst thing in the current
first-run flow.

The `saveStatus === 'guest'` "Log in to save this result" banner implies the
opposite (that a guest *can* get a result and just can't save it) — it's a
leftover from an earlier design and is unreachable on the main path.

**Decision needed (see §5):** where does the account gate go?

### 2b. Nothing teaches the core loop before the user is in it

The value proposition ("your swing, scored 0–100 against tour pros, with ranked
fixes") is only stated on `SignupScreen` and in `FirstSwingCard` — both of
which a user might skip past. The three-step mechanic (film → mark contact →
read score) is never explained as a whole; the user discovers each step by
being dropped into it.

### 2c. "Mark the contact frame" is the scariest step and has no lead-in

Scrubbing a video to a single frame is unusual and fiddly. First-timers don't
know what "contact" means precisely (racket-ball contact), how precise it needs
to be, or that audio auto-detect exists for clips with sound. `ContactMarkingScreen`
drops them into a full-screen scrubber cold.

### 2d. Reading the result is not guided

`ResultsScreen` shows a score ring, a matched-pro line, phase breakdown, and
tips. A first-timer doesn't know which number matters, what "72" means (good?
bad?), or that the tips are the actionable part. Sebastian's app celebrates the
first completion; ours plays a sound and shows a dense screen.

### 2e. Camera + photo-library permissions are requested with no context

`expo-camera` / `expo-image-picker` prompt at the moment of use with only the
OS-level `app.json` permission strings. A pre-prompt ("we need your camera to
record your swing — nothing is uploaded until you choose") lifts grant rates.

---

## 3. Goals & principles

1. **Show the payoff before asking for anything.** The user should understand
   "I point my camera at myself hitting, and get a pro-compared score + fixes"
   within the first 15 seconds, before any form or permission dialog.
2. **One happy path, ruthlessly.** First run = one forehand, filmed or
   uploaded, scored. Everything else (highlights, versus, friends, drills)
   stays out of the way until swing #1 is done.
3. **Account at the moment of value, not before it.** Ask to create the account
   when the user has something to save/lose — ideally right as the score is
   revealed (§5).
4. **Every screen the first-timer sees is a screen they understand.** No dense
   result screen, no cold scrubber, without a one-line "here's what this is".
5. **Make it skippable.** A returning user, or someone who just wants to poke
   around, taps "Skip" and lands on Home. Gate on a `storage` key like the
   fence tutorial already does.
6. **Instrument it** (§8) so we can see the drop-off funnel and actually
   iterate, per the video's "don't let it coast" point.

---

## 4. Proposed first-run flow

```
App launch (no onboarding_complete key, not authenticated)
        │
        ▼
┌─────────────────────────────────────────────┐
│ 1. WELCOME  (new: OnboardingScreen, 3 slides)│   ← swipeable, "Skip" top-right
│    • What it is: "Film a swing. Get it       │
│      scored 0–100 against tour pros."        │
│    • The 3 steps, illustrated (film → mark   │
│      contact → read score + fixes)           │
│    • "Best results: phone on the fence,      │
│      court-level" (teaser for the mount tip) │
│    [ Analyse my first swing ]  [ I'll explore ]
└─────────────────────────────────────────────┘
        │  "Analyse my first swing"
        ▼
┌─────────────────────────────────────────────┐
│ 2. PICK SHOT + SOURCE                        │
│    Shot type defaults to Forehand (most      │
│    common, best-covered in the pro DB).      │
│    Two buttons: "Record now" / "Upload a     │
│    video I already have".                    │
│    Camera path: contextual pre-prompt →      │
│    OS permission → LiveCalibrationCamera     │
│      (positioning badge already exists)      │
│    Upload path: contextual pre-prompt →      │
│      library picker                          │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 3. MOUNT TIP (first time only)               │
│    Existing FenceTutorialContent, but only   │
│    shown on the RECORD path (an uploader     │
│    already has a video). Keep the existing   │
│    tennisai_seen_fence_tutorial key.         │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 4. MARK CONTACT  (add a lead-in)             │
│    New: a one-card explainer before the      │
│    scrubber — "Scrub to the frame where your │
│    racket meets the ball. Close is fine.     │
│    Got sound? We'll try to find it for you." │
│    Then the existing rough/fine scrubber.    │
│    If audio auto-detect fires, show it       │
│    worked ("Found it from the ball strike —  │
│    nudge if it's off").                      │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 5. ANALYSING  (existing loading state)       │
│    Fine as-is. Maybe add a rotating line of  │
│    "what we're doing" copy for the ~20–40s   │
│    wait (pose extraction, trajectory, DTW).  │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 6a. ACCOUNT GATE  (if still a guest —  §5)   │
│     "Your score's ready. Create a free       │
│     account to see it and keep your history." │
│     [ Create free account ]  · [ Log in ]    │
│     Backend has already run the analysis;    │
│     the result is held until they sign up.   │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│ 6b. RESULT  (guided first time)              │
│     Existing ResultsScreen + a lightweight   │
│     3-step coach-mark / spotlight overlay on │
│     first view:  ① the score ring ("your     │
│     technique match — higher is closer to    │
│     tour form")  ② the matched pro line      │
│     ③ the tips ("start here — ranked by      │
│     what's costing you most")                │
│     Then: "Analyse another" / "See how it    │
│     works" (highlights, versus…)             │
└─────────────────────────────────────────────┘
        │
        ▼
   onboarding_complete = "1"  →  Home (now with real data)
```

### Notes on each step

- **Slides (1)**: keep to 3, static illustrations (reuse the `MountDiagram`
  SVG style — palette-matched schematics, not stock photos, consistent with
  `FenceTutorialContent`'s existing approach). No video assets needed for v1.
- **Contact lead-in (4)**: this is a small card, not a new screen — render it
  as `phase === 'contact-intro'` in `ContactMarkingScreen` before `'rough'`,
  gated by its own `storage` key so it only shows once.
- **Result coach-marks (6b)**: a `<FirstResultSpotlight>` overlay component
  driven by a `storage` key. Three taps to dismiss. Never shown again.

---

## 5. The account-gate decision (needs Jack)

Three options. **Recommendation: Option B.**

### Option A — gate up front (before the flow)
Require signup on "Analyse my first swing". Simplest to build (just guard the
nav + the analyse call). But asks for commitment before the user has seen
anything work — worst for conversion, and the whole point of the onboarding
redesign is "show value first".

### Option B — gate at the reveal  ✅ recommended
Let the guest walk the whole flow. `ResultsScreen.runAnalysis()` calls a
guest-capable analyse path; the backend runs the real analysis and returns the
result, but the **client holds it behind the account gate (6a)** and only
renders the score once they've signed up. Maximum investment before the ask,
and the ask is perfectly timed ("your score is ready").

Backend work required:
- A guest analyse path. Cleanest: `optionalAuth` on `/analyse` + a **much
  stricter IP-keyed limit for the no-user case** (e.g. 2–3 lifetime-ish per IP
  per long window) so it can't be abused for free CPU. The `analyseIpLimiter`
  added on 2026-09-09 is the right shape; add a tighter guest tier.
- Guest results are **not** saved server-side (no user row). The client keeps
  the result in memory and POSTs it to `/history` immediately after signup
  (the `saveToHistory` path already exists; just call it once `isAuthenticated`
  flips).
- Abuse consideration: a guest analysis still spawns MediaPipe. The stricter
  per-IP cap + the existing 200 MB / timeout limits contain it. Revisit if
  it's a problem.

### Option C — gate at "save"
Let guests see the full result, only require an account to save it. Highest
funnel completion but weakest conversion (they got the value and left). Also
the current half-built `saveStatus === 'guest'` behaviour, which we know
doesn't actually work.

---

## 6. Build inventory

### New frontend files
| File | Purpose |
|---|---|
| `screens/OnboardingScreen.js` | The 3-slide welcome (step 1). Registered in `App.js` stack. |
| `components/OnboardingSlides.js` | Slide content + `MountDiagram`-style SVGs. |
| `components/FirstResultSpotlight.js` | 3-step coach-mark overlay for `ResultsScreen` (step 6b). |
| `components/ContactIntroCard.js` | The "mark the contact frame" lead-in (step 4). |
| `components/PermissionPrePrompt.js` | Reusable contextual permission explainer (camera + library). |
| `utils/onboarding.js` | `storage`-key helpers: `isOnboardingComplete()`, `markOnboardingComplete()`, plus per-step "seen" flags. Mirror `reviewPrompt.js` structure. |
| `screens/AccountGateScreen.js` *(if Option B)* | The "score's ready, create an account" interstitial. Could also be a modal on `ResultsScreen`. |

### Frontend changes
- `App.js` — decide initial route: if `!onboardingComplete`, start on
  `Onboarding` instead of `MainTabs`. Keep `Onboarding` in the stack so
  Settings can offer "replay the intro".
- `HomeScreen.js` — `FirstSwingCard` becomes a button that re-enters the
  guided flow, not just a static card.
- `ContactMarkingScreen.js` — add `contact-intro` phase; only show the mount
  tutorial on the record path.
- `ResultsScreen.js` — mount `FirstResultSpotlight` on first view; wire the
  Option-B guest→account→save handoff; delete/replace the dead
  `saveStatus === 'guest'` banner.
- `SignupScreen.js` — accept a `reason` param ("to see your score" /
  "to save your history") so the header copy matches the moment.

### Backend changes (Option B only)
- `routes/analyse.js` — `requireAuth` → `optionalAuth`; add a guest branch with
  a strict IP-keyed rate limit; guest requests skip `reserveDailyUsageSlot`
  and the history save. Add to `routeAuthExceptions.js` reasoning or keep
  `optionalAuth` (which the auth-convention test accepts).
- New test: guest can analyse within the guest cap, is blocked past it, and a
  guest result carries no `analysisId`.

### Content (Jack)
- 3 slide illustrations (or approve SVG schematics).
- Welcome-email sequence copy (§7).
- The rotating "analysing…" copy lines.

---

## 7. Welcome email sequence (backend, lower priority)

The video pairs onboarding with a welcome email sequence. We have Resend wired
(`utils/email.js`, used for password reset). Proposed 3-email drip, triggered on
signup:

1. **Immediately** — "You're in. Here's how to get your most accurate score"
   (the fence-mount tip + the 3 steps, 20 seconds to read).
2. **Day 2, if 0 analyses** — "Haven't tried a swing yet? Here's a 15-second
   demo" (link to a short clip / the app).
3. **Day 5, if ≥1 analysis** — "You've got your baseline — here's how to use
   the tips + what Premium unlocks" (drills, versus, unlimited).

Needs: a tiny scheduled job (the app already has `setInterval` sweeps in
`server.js`; a daily pass over `users` + `analysis_usage` is enough — no queue).
Gate on `notifications_enabled` / an email-opt-out. **Defer to post-launch** unless
it's cheap to land alongside the drip infra.

---

## 8. Instrumentation (do this with the flow, not after)

We can't iterate on a funnel we can't see. Minimum: a `POST /events` endpoint
that logs `{ user_id_or_null, anon_id, event, meta, ts }` to a new `events`
table, and a thin `utils/track.js` on the client. Fire on:

`onboarding_started`, `onboarding_slide_viewed` (n), `onboarding_skipped`,
`first_flow_source_chosen` (record/upload), `permission_prompt_shown` /
`_granted` / `_denied` (camera, library), `contact_marked`,
`analysis_started`, `analysis_succeeded` / `_failed` (code),
`account_gate_shown`, `account_created_from_gate`, `first_result_viewed`,
`first_spotlight_dismissed`, `second_analysis_started`.

That funnel tells us exactly where first-timers fall out. Keep it first-party
(our table) — no third-party SDK, consistent with the "no unused deps" ethos.

---

## 9. Phasing

**Phase 1 — MVP (do before launch):**
- Fix 2a: the guest wall. Either Option A (fast) or Option B (better) — Jack's
  call. At minimum, a guest must never see a bare "Analysis failed".
- `OnboardingScreen` (3 slides) + `onboarding_complete` gate in `App.js`.
- `ContactIntroCard` lead-in.
- `PermissionPrePrompt` for camera + library.
- Email #1 (immediate) only.

**Phase 2 — polish (fast follow):**
- `FirstResultSpotlight` coach-marks.
- Rotating "analysing…" copy.
- Emails #2 and #3 + the daily trigger job.
- `events` instrumentation + a first look at the funnel.

**Phase 3 — iterate:**
- A/B the slide count / the gate position, using the funnel data.
- Consider a real 15-second demo video (ties into the B2 screenshot / marketing
  asset work).

---

## 10. Open questions for Jack

1. **Account gate position** — Option A, B, or C? (Recommend B; it's more
   backend work but it's the whole point.)
2. Is a guest allowed to run ML at all (Option B), given each run spawns
   MediaPipe on the single box? Comfortable with a strict per-IP guest cap?
3. Slide illustrations — approve SVG schematics (cheap, on-brand, matches
   `FenceTutorialContent`), or do you want real photography/video?
4. Welcome emails — in scope for launch, or Phase 2?
5. Default first-swing shot type — Forehand assumed here. Agree?
6. Do we want the onboarding replayable from Settings?

---

## Related

- `PRE_RELEASE_CHECK.md` — item C1 (this), plus B3 (review prompt, already
  scaffolded — the "happy moment" it fires on is the same first-result moment
  this flow builds toward).
- `frontend/utils/reviewPrompt.js` — mirror its structure for `utils/onboarding.js`.
- `frontend/components/FenceTutorialContent.js` — existing mount tutorial, reused as step 3.
- `frontend/screens/ContactMarkingScreen.js` — the `phase` state machine this plan extends.
