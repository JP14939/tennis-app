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

export function getRank(token) {
  return fetch(`${API_BASE}/api/profile/rank`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function getPlayerType(token) {
  return fetch(`${API_BASE}/api/profile/player-type`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}
