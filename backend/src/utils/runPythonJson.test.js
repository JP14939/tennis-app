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
    // A Node child (not `bash -c sleep`) so no orphaned grandchild process
    // keeps a stdio pipe open after the parent is killed -- on Windows,
    // killing bash leaves its `sleep` running and 'close' never fires.
    // This child installs a no-op SIGTERM handler and stays alive on a
    // long timer, so on a real POSIX box the plain proc.kill() (SIGTERM)
    // is genuinely ignored and only the SIGKILL escalation ends it.
    await expect(
      runPythonJson(process.execPath, ['-e', "process.on('SIGTERM',()=>{}); setTimeout(()=>{}, 30000);"], { timeoutMs: 200, label: 'stubborn process' })
    ).rejects.toMatchObject({ kind: 'timeout' });
    // Should settle at roughly timeoutMs (200ms) plus the SIGKILL grace
    // period (5s, hardcoded in runPythonJson.js) -- not hang indefinitely,
    // and nowhere near the child's full 30s timer.
    expect(Date.now() - start).toBeLessThan(8000);
  }, 12000);
});
