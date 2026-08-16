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
