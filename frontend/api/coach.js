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

function authed(token) {
  return { Authorization: `Bearer ${token}` };
}

export function getInviteCode(token) {
  return fetch(`${API_BASE}/api/coach/invite-code`, {
    method: 'POST',
    headers: authed(token),
  }).then(handle);
}

export function linkCoach(token, code) {
  return fetch(`${API_BASE}/api/coach/link`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authed(token) },
    body: JSON.stringify({ code }),
  }).then(handle);
}

export function listStudents(token) {
  return fetch(`${API_BASE}/api/coach/students`, {
    headers: authed(token),
  }).then(handle);
}

export function getStudentHistory(token, studentId) {
  return fetch(`${API_BASE}/api/coach/students/${studentId}/history`, {
    headers: authed(token),
  }).then(handle);
}

export function addNote(token, { analysisId, noteText, phaseKey, timestampSec }) {
  return fetch(`${API_BASE}/api/coach/notes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authed(token) },
    body: JSON.stringify({ analysisId, noteText, phaseKey, timestampSec }),
  }).then(handle);
}

export function getNotes(token, analysisId) {
  return fetch(`${API_BASE}/api/coach/notes?analysisId=${analysisId}`, {
    headers: authed(token),
  }).then(handle);
}
