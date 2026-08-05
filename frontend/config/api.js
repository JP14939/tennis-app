// EXPO_PUBLIC_API_BASE (set via frontend/.env, see .env.example) overrides
// this for pointing a build at a deployed server. With no .env present,
// falls back to the dev machine's LAN IP so both the phone (Expo Go) and the
// browser on this machine can reach a locally-running backend unchanged —
// update this fallback if your laptop's IP changes (check with `ipconfig` /
// `ifconfig`), Wi-Fi networks often reassign it.
export const API_BASE = process.env.EXPO_PUBLIC_API_BASE || 'http://192.168.1.162:5000';
