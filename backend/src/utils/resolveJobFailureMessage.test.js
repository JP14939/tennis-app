const { resolveJobFailureMessage } = require('./resolveJobFailureMessage');

const MESSAGES = {
  timeout: 'timed out',
  invalid_json: 'invalid json',
  spawn_failed: 'spawn failed',
  nonzero_exit: 'generic failure',
};

describe('resolveJobFailureMessage', () => {
  test('timeout, invalid_json, spawn_failed each use their own table entry', () => {
    expect(resolveJobFailureMessage({ kind: 'timeout' }, MESSAGES)).toBe('timed out');
    expect(resolveJobFailureMessage({ kind: 'invalid_json' }, MESSAGES)).toBe('invalid json');
    expect(resolveJobFailureMessage({ kind: 'spawn_failed' }, MESSAGES)).toBe('spawn failed');
  });

  test('nonzero_exit prefers the script\'s own reported error over the generic fallback', () => {
    const err = { kind: 'nonzero_exit', stdout: JSON.stringify({ error: 'no rallies detected' }) };
    expect(resolveJobFailureMessage(err, MESSAGES)).toBe('no rallies detected');
  });

  test('nonzero_exit falls back to the generic message when stdout is not JSON', () => {
    const err = { kind: 'nonzero_exit', stdout: 'Traceback (most recent call last): ...' };
    expect(resolveJobFailureMessage(err, MESSAGES)).toBe('generic failure');
  });

  test('nonzero_exit falls back to the generic message when stdout JSON has no error field', () => {
    const err = { kind: 'nonzero_exit', stdout: JSON.stringify({ ok: false }) };
    expect(resolveJobFailureMessage(err, MESSAGES)).toBe('generic failure');
  });

  test('nonzero_exit falls back to the generic message when stdout is empty', () => {
    const err = { kind: 'nonzero_exit', stdout: '' };
    expect(resolveJobFailureMessage(err, MESSAGES)).toBe('generic failure');
  });

  test('an unrecognized kind defensively falls back to the nonzero_exit message', () => {
    expect(resolveJobFailureMessage({ kind: 'something_new' }, MESSAGES)).toBe('generic failure');
  });
});
