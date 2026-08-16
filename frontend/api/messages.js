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

export function getThreads(token) {
  return fetch(`${API_BASE}/api/messages/threads`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function getThread(token, otherUserId) {
  return fetch(`${API_BASE}/api/messages/thread/${otherUserId}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function sendMessage(token, otherUserId, body) {
  return fetch(`${API_BASE}/api/messages/thread/${otherUserId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ body }),
  }).then(handle);
}

export function reportMessage(token, messageId, reason) {
  return fetch(`${API_BASE}/api/messages/report/${messageId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ reason }),
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function blockUser(token, userId) {
  return fetch(`${API_BASE}/api/users/${userId}/block`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function unblockUser(token, userId) {
  return fetch(`${API_BASE}/api/users/${userId}/block`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => (res.ok ? undefined : handle(res)));
}
