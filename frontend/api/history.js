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

export function fetchHistory(token) {
  return fetch(`${API_BASE}/api/history`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function saveHistory(token, result, shotType) {
  return fetch(`${API_BASE}/api/history`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ ...result, shotType }),
  }).then(handle);
}

export function deleteHistory(token, id) {
  return fetch(`${API_BASE}/api/history/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  }).then((res) => {
    if (!res.ok && res.status !== 204) {
      return handle(res);
    }
  });
}
