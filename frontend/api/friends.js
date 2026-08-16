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

export function getFriendCode(token) {
  return fetch(`${API_BASE}/api/friends/code`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function linkFriend(token, code) {
  return fetch(`${API_BASE}/api/friends/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  }).then(handle);
}

export function getFriends(token) {
  return fetch(`${API_BASE}/api/friends`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function unfriend(token, userId) {
  return fetch(`${API_BASE}/api/friends/${userId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function getMatches(token, userId) {
  return fetch(`${API_BASE}/api/friends/${userId}/matches`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function logMatch(token, userId, { playedAt, setsWon, setsLost, scoreDetail }) {
  return fetch(`${API_BASE}/api/friends/${userId}/matches`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ playedAt, setsWon, setsLost, scoreDetail }),
  }).then(handle);
}

export function deleteMatch(token, matchId) {
  return fetch(`${API_BASE}/api/friends/matches/${matchId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function shareSwing(token, friendId, analysisId) {
  return fetch(`${API_BASE}/api/friends/${friendId}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ analysisId }),
  }).then(handle);
}

export function getSharedSwings(token, friendId) {
  return fetch(`${API_BASE}/api/friends/${friendId}/shared`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function getSharedAnalysis(token, analysisId) {
  return fetch(`${API_BASE}/api/friends/shared/${analysisId}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}
