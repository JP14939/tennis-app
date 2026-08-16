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

export function getFriendsLeaderboard(token, shotType) {
  return fetch(`${API_BASE}/api/leaderboard/friends?shotType=${shotType}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function getWorldwideLeaderboard(token, shotType) {
  return fetch(`${API_BASE}/api/leaderboard/worldwide?shotType=${shotType}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function getCelebrities(token) {
  return fetch(`${API_BASE}/api/leaderboard/celebrities`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function addCelebrity(token, { name, shotType, score, note }) {
  return fetch(`${API_BASE}/api/leaderboard/celebrities`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ name, shotType, score, note }),
  }).then(handle);
}

export function deleteCelebrity(token, id) {
  return fetch(`${API_BASE}/api/leaderboard/celebrities/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}
