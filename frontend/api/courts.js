import { API_BASE } from '../config/api';

async function handle(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(data.error || 'Something went wrong');
    err.code = data.code;
    throw err;
  }
  return data;
}

export function getCourts(token, { lat, lng, radiusKm }) {
  const params = new URLSearchParams({ lat, lng, radiusKm: radiusKm ?? 20 });
  return fetch(`${API_BASE}/api/courts?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function addCourt(token, { name, latitude, longitude }) {
  return fetch(`${API_BASE}/api/courts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, latitude, longitude }),
  }).then(handle);
}

export function confirmCourt(token, courtId) {
  return fetch(`${API_BASE}/api/courts/${courtId}/confirm`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function setCourtCost(token, courtId, costInfo) {
  return fetch(`${API_BASE}/api/courts/${courtId}/cost`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ cost_info: costInfo }),
  }).then(handle);
}

export function getWatchedCourts(token) {
  return fetch(`${API_BASE}/api/courts/watched`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function watchCourt(token, courtId) {
  return fetch(`${API_BASE}/api/courts/${courtId}/watch`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function unwatchCourt(token, courtId) {
  return fetch(`${API_BASE}/api/courts/${courtId}/watch`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

// Club watch is resolved server-side from a court id -- the frontend only
// ever deals in court ids, same shape as watchCourt/unwatchCourt above.
export function watchClub(token, courtId) {
  return fetch(`${API_BASE}/api/courts/${courtId}/club/watch`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function unwatchClub(token, courtId) {
  return fetch(`${API_BASE}/api/courts/${courtId}/club/watch`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

// Crowd-sourced club naming -- POST proposes/overwrites the name (resets
// verification, same as routes/courts.js's own comment on
// club_name_confirmations); the confirm endpoint is a separate call, same
// two-step shape as confirmCourt() above.
export function suggestClubName(token, clubId, name) {
  return fetch(`${API_BASE}/api/clubs/${clubId}/name`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name }),
  }).then(handle);
}

export function confirmClubName(token, clubId) {
  return fetch(`${API_BASE}/api/clubs/${clubId}/name/confirm`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

// Direct-by-club-id unwatch, for the My Watches screen (it only ever has the
// watched clubs list itself -- no associated court id -- to work from,
// unlike CourtSheet's per-court "Watching" pill, which resolves the club
// from a court id it already has). No matching create function -- watching
// a club is still only initiated from a specific court's sheet.
export function unwatchClubById(token, clubId) {
  return fetch(`${API_BASE}/api/courts/club-watch/${clubId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

// Area watch is a standalone resource (a dropped pin + radius), unlike
// court/club watch which toggle a watch flag on an existing entity -- so
// this creates/deletes the watch row directly instead of resolving it from
// a court id.
export function createAreaWatch(token, { name, latitude, longitude, radiusKm }) {
  return fetch(`${API_BASE}/api/courts/area-watch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, latitude, longitude, radius_km: radiusKm }),
  }).then(handle);
}

export function deleteAreaWatch(token, areaWatchId) {
  return fetch(`${API_BASE}/api/courts/area-watch/${areaWatchId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function getAvailability(token, courtId) {
  return fetch(`${API_BASE}/api/courts/${courtId}/availability`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function postAvailability(token, courtId, { startTime, endTime, note }) {
  return fetch(`${API_BASE}/api/courts/${courtId}/availability`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ start_time: startTime, end_time: endTime, note }),
  }).then(handle);
}

export function cancelAvailability(token, postId) {
  return fetch(`${API_BASE}/api/availability/${postId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}
