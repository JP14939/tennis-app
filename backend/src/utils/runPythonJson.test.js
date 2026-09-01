// Regression tests for runPythonJson.js's timeout handling. A plain
// proc.kill() only sends SIGTERM -- a child stuck in a blocking native call
// (or, in these tests, one that explicitly traps and ignores SIGTERM) used
// to never actually exit, so 'close' never fired and this promise never
// settled: the awaiting request hung forever and the orphaned process
// leaked (see HANDOVER.md's tracked "runPythonJson's subprocess timeout not
// escalating to SIGKILL" item). Uses `bash` rather than the real python
// interpreter -- runPythonJson takes an arbitrary executable, and these
// tests are about the timeout/kill mechanics, not anything python-specific.
const { runPythonJson } = require('./runPythonJson');

describe('runPythonJson', () => {
  test('resolves with parsed JSON on a clean, fast exit', async () => {
    const result = await runPythonJson('bash', ['-c', 'echo \'{"ok": true}\''], { timeoutMs: 2000, label: 'test' });
    expect(result).toEqual({ ok: true });
  });

  test('rejects a nonzero exit with kind nonzero_exit', async () => {
    await expect(
      runPythonJson('bash', ['-c', 'exit 1'], { timeoutMs: 2000, label: 'test' })
    ).rejects.toMatchObject({ kind: 'nonzero_exit' });
  });

  test('escalates to SIGKILL and settles when the child ignores SIGTERM', async () => {
    const start = Date.now();
    await expect(
      runPythonJson('bash', ['-c', 'trap "" TERM; sleep 30'], { timeoutMs: 200, label: 'stubborn process' })
    ).rejects.toMatchObject({ kind: 'timeout' });
    // Should settle at roughly timeoutMs (200ms) plus the SIGKILL grace
    // period (5s, hardcoded in runPythonJson.js) -- not hang indefinitely,
    // and nowhere near the child's full 30s sleep.
    expect(Date.now() - start).toBeLessThan(8000);
  }, 10000);
});
