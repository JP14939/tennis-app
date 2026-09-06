import { API_BASE } from '../config/api';

async function handle(res) {
  let data;
  let parseFailed = false;
  try {
    data = await res.json();
  } catch {
    data = {};
    parseFailed = true;
  }
  if (!res.ok) {
    const err = new Error(data.error || 'Something went wrong');
    err.code = data.code;
    throw err;
  }
  if (parseFailed) {
    // A 2xx whose body isn't JSON means something between us and the backend
    // answered instead of the backend (e.g. an ngrok/proxy interstitial page).
    // Fail loudly rather than returning {} and blanking the screen.
    throw new Error(`Unexpected non-JSON response from ${res.url}`);
  }
  return data;
}

export function fetchHistory(token) {
  return fetch(`${API_BASE}/api/history`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function fetchHistoryItem(token, id) {
  return fetch(`${API_BASE}/api/history/${id}`, {
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

export function flagNotShot(token, id, flagged = true) {
  return fetch(`${API_BASE}/api/history/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ flagged_not_shot: flagged }),
  }).then(handle);
}

export function confirmRealShot(token, id, confirmed = true) {
  return fetch(`${API_BASE}/api/history/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ confirmed_real_shot: confirmed }),
  }).then(handle);
}

export function correctShotType(token, id, shotType) {
  return fetch(`${API_BASE}/api/history/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ shot_type: shotType }),
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
