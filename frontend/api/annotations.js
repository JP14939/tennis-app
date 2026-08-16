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

export function getAnnotations(token, analysisId) {
  return fetch(`${API_BASE}/api/analyses/${analysisId}/annotations`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(handle);
}

export function saveAnnotations(token, analysisId, { paneAStrokes, paneBStrokes }) {
  return fetch(`${API_BASE}/api/analyses/${analysisId}/annotations`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ paneAStrokes, paneBStrokes }),
  }).then(handle);
}
