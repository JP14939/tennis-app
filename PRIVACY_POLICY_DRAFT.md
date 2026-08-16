> **⚠️ UNREVIEWED DRAFT — FOR ATTORNEY REVIEW ONLY.**
> Not legal advice, not fit to publish as-is. The data inventory below (§2-4) is factually accurate as of 2026-08-15, verified directly against the app's code — the legal characterization and required disclosures around it are not, and need your lawyer's input, especially §3 (biometric data).

# Privacy Policy — RallyMax

**Last updated:** [DATE]

## 1. Who we are and scope

This policy explains what data RallyMax ("we," "us") collects, why, and what you can do about it. Contact: [SUPPORT EMAIL].

## 2. Data we collect

**Account data:** email address, password (stored hashed, never in plain text), display name, optional username.

**Video and pose data:** video you upload of your own tennis swings, and per-frame body landmark coordinates (approximately 33 points — shoulders, hips, wrists, etc., including an estimated depth value) extracted from that video via on-device/server pose-detection software. This data is stored to power the comparison/scoring feature and so you can review past analyses.

**Location data:** if you use the court-finder feature, your device's location (latitude/longitude) is sent to our servers to find nearby courts. If you submit a court location, that location and your account are stored together and visible to other users.

**Messages and shared content:** direct messages you send other users, and any swing analyses or annotations you choose to share.

**Payment data:** we do not directly receive or store your payment card details. Subscription purchases are handled by [Apple/Google via RevenueCat]; we receive only confirmation that a subscription is active, not payment details.

**Device data:** a push-notification token if you enable notifications.

## 3. Special note on biometric data [NEEDS LAWYER INPUT]

[OPEN LEGAL QUESTION, not resolved here: body pose/landmark data extracted from your videos may or may not constitute "biometric data" for identification purposes under applicable law (e.g. UK GDPR Article 9 special category data, or US state biometric privacy laws like Illinois BIPA). Depending on that determination, this section may need to describe a specific legal basis for processing, additional consent language, or a dedicated biometric data notice. **Do not publish this policy without resolving this question with counsel.**]

## 4. Who we share data with

- **Anthropic** (Claude API) — receives video frames/images for AI-assisted analysis during processing.
- **[Apple/Google] via RevenueCat** — receives your app-internal user ID and purchase events for subscription management.
- **Expo** (push notification infrastructure) — receives your device push token.
- **OpenStreetMap/Overpass** — we query this service for public court location data; no personal data is sent to it.

[CONFIRM: whether formal Data Processing Agreements exist or are needed with each of the above.]

We do not sell your personal data.

## 5. How long we keep data

We keep your data for as long as your account is active. **You can delete your account at any time from Settings**, which deletes your videos, swing analyses, and other content you solely own. Some records that involve another user (e.g. a message thread, a swing analysis you shared with a friend, a coaching note) are kept so the other person's history isn't broken, but your personal identifying information on those records is anonymized — they'll show as belonging to a "Deleted user," not you. [LAWYER TO CONFIRM this approach — anonymizing rather than fully deleting shared/relational records — satisfies applicable "right to erasure" requirements; this is an engineering description of what the product does, not a legal conclusion that it's sufficient.]

## 6. Your rights

Depending on your location, you may have rights to access, correct, delete, or export your data. [LAWYER TO CONFIRM which rights apply and draft the standard language — likely UK GDPR rights at minimum, given other users identified.] **Account deletion is available as a self-service feature in the app (Settings → Delete Account, requires password confirmation).** For any other request (e.g. data export/access), contact [SUPPORT EMAIL] — that part remains a manual process today.

## 7. Children's privacy

[OPEN QUESTION: the app has no age verification. If the app is not intended for children under 13 (or 16, jurisdiction-dependent), this section should say so explicitly and describe what happens if we learn a child has provided data. If children are a plausible/intended audience, a materially different compliance approach (e.g. COPPA-compliant consent flow) is likely required — this needs a decision, not just wording.]

## 8. International transfers

[LAWYER TO CONFIRM: where is data actually hosted/processed, and does that cross a border requiring specific safeguards (e.g. UK GDPR international transfer rules) given Anthropic/RevenueCat/Expo are US-based services?]

## 9. Security

We take reasonable measures to protect your data (e.g. hashed passwords, access controls). No system is perfectly secure. [STANDARD SECURITY DISCLAIMER LANGUAGE.]

## 10. Changes to this policy

[STANDARD NOTICE-OF-CHANGES LANGUAGE.]

## 11. Contact

[SUPPORT EMAIL / ADDRESS / DATA PROTECTION CONTACT IF REQUIRED]
