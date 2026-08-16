# Legal Review Prep — RallyMax / TennisAI

**Purpose of this document:** a factual inventory of what the app actually does, what data it collects, and who it shares data with — prepared for your lawyer meeting. This is *not* legal advice or draft legal language; everything below is grounded directly in the current codebase so your lawyer has accurate source material to work from, not guesses.

**I am not a lawyer and have not drafted any Terms of Service, Privacy Policy, or other legal document here** — that's exactly what tomorrow's meeting is for. This is the briefing packet, not the deliverable.

**Update:** since her time is limited to 30 minutes, I've also drafted first-pass versions of the three documents she'd otherwise draft from scratch — [TERMS_OF_SERVICE_DRAFT.md](TERMS_OF_SERVICE_DRAFT.md), [PRIVACY_POLICY_DRAFT.md](PRIVACY_POLICY_DRAFT.md), [ACCEPTABLE_USE_POLICY_DRAFT.md](ACCEPTABLE_USE_POLICY_DRAFT.md). Each is clearly marked as an unreviewed draft, and every place that needs either a business fact only you know, or a real legal judgment call only she can make, is flagged in `[BRACKETS]`. Point is to turn her 30 minutes from "draft this from nothing" into "correct/confirm this" — much faster.

## Before she arrives — two things only you can do

1. **Fill in the plain business facts** in the three drafts wherever you see `[LEGAL ENTITY NAME]`, `[ADDRESS]`, `[SUPPORT EMAIL]`, `[DATE]`. These aren't legal questions — just find/replace with your real details so she's not spending billable time waiting on you to look them up.
2. **Read the §5 list below and decide your own gut position** on each (age gating yes/no, EU/international users yes/no, etc.) before she arrives, even if she ends up overriding you — going in with an opinion is faster than her asking you cold.

## Suggested use of the 30 minutes

Don't read the drafts together line by line — there isn't time. Instead: walk through the open questions in §5 verbally (this is the part that genuinely needs her judgment), let her take the three drafts away to redline on her own time, and use any remaining minutes on whichever single item feels highest-risk to you (my read: the biometric-data question in §2, since it changes what the Privacy Policy has to say).

---

## 1. What the app does (one paragraph, for context)

A mobile app (iOS/Android via Expo) where users upload video of their own tennis swings, get AI-generated pose analysis comparing their form to a database of professional players' swings, and receive a similarity score + coaching tips. Beyond that core feature, it has grown social/community features: friends, direct messaging, a coach-student linking system, a crowd-sourced court-finder map, leaderboards, and a premium subscription tier.

---

## 2. Data currently collected, by category

### Account data
- Email, password (hashed), display name, optional username
- No date of birth / age field anywhere in the schema — **there is currently no age gating or age verification of any kind.**

### Video & biometric-adjacent data — likely the most important thing to flag
- Users upload video of themselves (and sometimes visible in-frame: other people on court, e.g. an opponent or bystander who did not separately consent).
- Every uploaded video is run through pose-estimation (MediaPipe) which extracts **body landmark coordinates per frame** (33 points: shoulders, hips, wrists, etc., including a depth estimate) — stored indefinitely as part of each saved analysis.
- **Open question for your lawyer**: does per-frame skeletal/body landmark data of a real, identifiable person count as biometric data under applicable law (UK GDPR Article 9 "special category data" treats biometric data used for identification purposes specially; there's genuine nuance on whether pose-for-coaching falls into that bucket — this needs an actual legal opinion, not my guess). If it does, that changes consent/processing requirements.
- Original + cropped video files are stored server-side (not currently on any cloud storage — plain disk on the app's own server) and served back to the user for playback.

### Location data
- Users grant device location (for the "Find Games" court finder). Precise lat/lng is sent to the backend on every map load.
- Community-submitted court pins (name + coordinates) are stored, attributed to the submitting user, and visible to all users.
- Court data itself is also bulk-sourced from OpenStreetMap (Overpass API) — that's public map data, not user data, but worth mentioning as a third-party data source.

### User-to-user content (real people communicating)
- Direct messages between users (stored, not end-to-end encrypted — plain text in the database).
- Shared swing analyses between friends, with freehand drawn annotations.
- Friend/coach linking via invite codes.
- Basic moderation exists for messages as of 2026-08-15: users can block each other (stops messaging both directions) and report an individual message (logged for manual review, no admin UI yet). Community court submissions still have no moderation beyond the crowd-confirmation mechanism (§2 below doesn't cover this — see item 6 in §5).

### Payment data
- Subscriptions are handled via **RevenueCat** (not directly via Stripe/Apple/Google — RevenueCat sits in front of the platform stores). The app's own backend never sees raw card data — RevenueCat manages the purchase, then sends a webhook to grant/revoke a `premium` entitlement.
- The backend stores subscription *events* (grant/revoke type, timestamps) but no payment method details.

### Push notification tokens
- Device push tokens stored per user (via Expo's push service) for notifications (court availability alerts, new messages, etc.).

---

## 3. Third-party services / data processors currently in use

| Service | What it's used for | What data reaches it |
|---|---|---|
| **Anthropic (Claude API)** | AI-assisted verification of shot detection/classification, used in the batch analysis pipeline | Video frames / cropped images sent for vision analysis |
| **RevenueCat** | Subscription/payment management | User ID (app-internal, not email), purchase events |
| **Expo push notification service** | Push notifications | Device push tokens |
| **OpenStreetMap / Overpass API** | Court location data | Outbound only — queries by lat/lng, no user data sent |
| **AWS** | Credentials are configured (`AWS_REGION`, access keys) in the environment but **not currently used anywhere in the backend code** — likely provisioned for a future feature (e.g. cloud video storage) and not yet wired up. Worth confirming with whoever set this up whether it's genuinely unused. |

No data-sharing/DPA agreements were found in the repo for any of these — if formal processor agreements are required (e.g. under UK GDPR, a Data Processing Agreement with each processor), that's likely not yet in place and worth asking your lawyer about.

---

## 4. Jurisdiction signals

- Court/location data this session was seeded specifically for **England** (OpenStreetMap query scoped to `area["name"="England"]`), suggesting the primary target market is UK users — relevant for UK GDPR / Data Protection Act 2018 applicability.
- Nothing in the app restricts sign-ups to the UK — it's a public app store listing, so realistically some users could be from anywhere, which raises the question of whether EU GDPR / US state privacy laws (CCPA etc.) also need consideration depending on your distribution plans.

---

## 5. Specific things worth raising directly with the lawyer

1. **Biometric/pose data classification** (see §2) — the single most important open question, since it affects what consent language and processing basis you need.
2. **No age gating at all.** If under-13s (or under-16s, depending on jurisdiction) could plausibly use the app, COPPA (US) / equivalent UK-GDPR children's provisions may require an age gate, parental consent flow, or explicit exclusion in the ToS.
3. **Video of third parties.** A user's uploaded swing video may capture other real, identifiable people (opponents, bystanders) who never consented to being recorded/processed/stored. Needs a ToS clause putting responsibility on the uploader, and possibly a "report a photo/video of me" removal process.
4. **Physical injury liability.** This is a sports-coaching app generating AI coaching advice ("your elbow is dropping," "your wrist is breaking down at contact," etc.) — a fairly standard fitness-app liability disclaimer is likely needed (advice is not professional coaching, use at your own risk, consult a professional, etc.).
5. **AI accuracy disclaimers.** The coaching tips and similarity scores are AI-generated and explicitly known (internally) to sometimes be wrong or based on imperfect detection — worth a clear "for informational purposes, not guaranteed accurate" disclaimer, both for the swing analysis and for user-submitted court information (which is unverified/crowd-sourced).
6. **Content moderation — basic tooling added 2026-08-15.** Direct messages can now be blocked (per-user, both directions of sending) and reported (press-and-hold a message) — reports land in a `message_reports` table for manual review, no automated moderation or admin review UI yet. Community court submissions still have no moderation of any kind (only the crowd-confirmation mechanism from item 20 above). Still worth a clear Acceptable Use Policy either way.
7. **Data retention & deletion — fixed 2026-08-15.** There IS a self-service "delete my account" flow (Settings → Delete Account), but it was found to be broken (would crash with a database error for any user who'd ever messaged someone, made a friend, or interacted with a court — i.e. most real users) and has been fixed and tested. Approach: fully deletes content the user solely owns (videos, analyses, court watches, etc.); anonymizes (rather than deletes) records shared with another user (messages, shared analyses, coaching notes, friend match history) so the other party's history isn't destroyed, replacing the deleted user's identity with "Deleted user." **Ask your lawyer to confirm this anonymize-for-shared-records approach actually satisfies "right to erasure" requirements** — that's a legal question, what's described here is only the engineering behavior.
8. **International users vs. UK-first design.** Worth deciding explicitly with your lawyer whether to geo-restrict at launch or write policies broad enough to cover wherever the app is actually downloaded.

---

## 6. Documents that likely need to be drafted (none currently exist in the repo)

- Terms of Service / Terms of Use
- Privacy Policy
- Acceptable Use Policy (covers messaging, court submissions, impersonation, etc.)
- A clear in-app consent flow/disclosure for video + pose data collection, and for location access
- A sport/fitness liability disclaimer
- (If applicable after the biometric-data question above) a specific biometric data notice/consent, some jurisdictions (e.g. Illinois BIPA in the US) have very specific statutory requirements here

---

*This document was generated by inspecting the actual application code and database schema on 2026-08-15 — it reflects what the app currently does, not what it's intended to do or what any policy should say. Treat it as a fact sheet to hand to your lawyer, not a substitute for their review.*
