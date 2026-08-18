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

// token is optional -- guests can browse free drills/lessons (locked
// premium items still list, just without video/explanation, see
// backend/src/routes/drills.js's isLocked()).
export function listDrills(token, { kind, shotType } = {}) {
  const params = new URLSearchParams();
  if (kind) params.set('kind', kind);
  if (shotType) params.set('shot_type', shotType);
  const qs = params.toString();
  return fetch(`${API_BASE}/api/drills${qs ? `?${qs}` : ''}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }).then(handle);
}

export function getDrill(token, id) {
  return fetch(`${API_BASE}/api/drills/${id}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  }).then(handle);
}

export function logDrillPractice(token, stepId, analysisId) {
  return fetch(`${API_BASE}/api/drills/${stepId}/practice`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ analysisId }),
  }).then(handle);
}
