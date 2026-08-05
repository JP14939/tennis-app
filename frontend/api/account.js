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

export function updateProfile(token, patch) {
  return fetch(`${API_BASE}/api/auth/me`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(patch),
  }).then(handle);
}

export function changePassword(token, { currentPassword, newPassword }) {
  return fetch(`${API_BASE}/api/auth/password`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ currentPassword, newPassword }),
  }).then((res) => (res.ok ? undefined : handle(res)));
}

export function deleteAccount(token, password) {
  return fetch(`${API_BASE}/api/auth/me`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ password }),
  }).then((res) => (res.ok ? undefined : handle(res)));
}
