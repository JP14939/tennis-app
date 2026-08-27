// Defaults to the hosted backend so the app works from any network without
// requiring .env to be present/correct on every device — mobile especially,
// since Expo Go on a phone on a different network than the dev machine
// can't reach a LAN IP at all. For local dev against a locally-running
// backend, set EXPO_PUBLIC_API_BASE in frontend/.env to your dev machine's
// LAN IP (see .env.example) — Expo inlines it into the build, overriding
// this fallback.
export const API_BASE = process.env.EXPO_PUBLIC_API_BASE || 'https://rallymax.167-233-107-31.sslip.io';
