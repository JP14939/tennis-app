# Manual to-do — things only you can do

Everything here needs a human clicking through a dashboard, creating an
account, or physically testing with a device — none of it is something I
can do myself. Grouped by priority: **tomorrow** (finish payments, which is
mid-build) vs. **later** (deferred on purpose, don't lose track of them).

---

## Tomorrow: finish wiring up payments

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

**Test "Record now" (live camera calibration) on a real phone.** This is
the one thing from tonight's live-camera work I couldn't verify myself —
I confirmed the backend/calibration-server side end-to-end via curl, but
never actually watched the live positioning badge update in your hand as
you move a phone around. Run `npx expo start`, scan into Expo Go, try
"Record now" from the upload screen, and confirm the badge feels
responsive and the messaging (net not found / height warnings) makes sense
in person.

**Keep `frontend/config/api.js`'s LAN-IP fallback current.** If Expo Go
suddenly can't reach the backend and nothing else changed, this is almost
always why — check `ipconfig` and update the fallback IP in that file (or
just set `EXPO_PUBLIC_API_BASE` in `frontend/.env` instead, which now
overrides it).

---

## Later — deferred on purpose, don't forget these exist

**Rotate the leaked Anthropic API key.** `ANTHROPIC_API_KEY` in
`backend/.env` has been exposed since early in this project. Fine to defer
while it's just you hitting it locally — **not fine once real users are
on this**. Get a fresh key from console.anthropic.com before real hosting
goes live.

**Hosting**, whenever you're ready (your own call, not urgent):
- Pick a host — recommended: a VPS with a dedicated vCPU (Hetzner cheapest,
  DigitalOcean if you want easier docs/UX) rather than Railway/Render/Fly
  (poor fit for the 12GB+ data volume and long-running Python process this
  app needs).
- `rsync`/`scp` the local `data/` folder to the server (gitignored, never
  comes via `git clone`).
- Create `backend/.env` on the server with real production secrets.
- `docker compose up --build app`.
- Full details already written up in `DEPLOY.md`.
- Once hosting is live: update `EXPO_PUBLIC_API_BASE` in `frontend/.env` to
  point at the real server instead of your LAN IP, and switch the
  RevenueCat webhook URL from the ngrok tunnel to the real server URL.

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

**Data-quality: `coaching_tips_database.json` has a mojibake encoding
bug.** Found while seeding Drills content from it — em-dashes and similar
punctuation in the tip/drill text render as mangled characters (e.g. "â€""
instead of "—"). This is in the source JSON file itself (pre-existing, not
introduced by the Drills seeding), and it was already affecting the
per-analysis tips shown on `ResultsScreen.js` — now also visible in the
new Drills library. Worth a cleanup pass re-encoding that file correctly
(likely a one-time UTF-8-read-as-Latin1-then-rewritten bug in whatever
originally generated it).
