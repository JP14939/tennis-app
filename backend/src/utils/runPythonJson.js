const { spawn } = require('child_process');

// A failed spawn (e.g. ENOENT because scripts/venv doesn't exist on this
// box) fires BOTH 'error' and 'close' on the child process -- 'error' first,
// then 'close' with a negative code -- verified empirically on Node 22.
// Every route in this app used to attach a `res.status().json()` call to
// each event independently, so a spawn failure sent two responses: the
// second call threw ERR_HTTP_HEADERS_SENT from inside an EventEmitter
// callback, outside Express's request lifecycle, which is an
// uncaughtException that takes the whole server down. Routing every call
// through a single Promise here means only one of resolve/reject can ever
// take effect, so only one response is ever sent.
class PythonProcessError extends Error {
  constructor(message, { kind, stdout = '', stderr = '', code = null } = {}) {
    super(message);
    this.name = 'PythonProcessError';
    this.kind = kind; // 'spawn_failed' | 'nonzero_exit' | 'invalid_json'
    this.stdout = stdout;
    this.stderr = stderr;
    this.code = code;
  }
}

// Spawns `pythonBin args`, collects stdout/stderr, and resolves with the
// parsed JSON stdout on a clean (code 0) exit. Rejects with a
// PythonProcessError otherwise. `stdinBody`, if given, is written to the
// child's stdin (JSON-stringified unless already a string) and the stream
// is closed immediately after.
function runPythonJson(pythonBin, args, { timeoutMs, stdinBody, label = 'python process' } = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonBin, args);
    let stdout = '';
    let stderr = '';
    let settled = false;
    let timedOut = false;

    // A plain proc.kill() sends SIGTERM, which a child stuck in a blocking
    // native call (MediaPipe/OpenCV doing work that doesn't return control
    // to the Python interpreter to handle the signal) can outlive
    // indefinitely -- 'close' then never fires, so this promise never
    // settles: the awaiting Express handler hangs on that request forever
    // and the orphaned process leaks. Escalate to SIGKILL after a grace
    // period if the process hasn't actually exited by then.
    const SIGKILL_GRACE_MS = 5000;
    let killTimeout = null;
    const timeout = timeoutMs ? setTimeout(() => {
      timedOut = true;
      proc.kill();
      killTimeout = setTimeout(() => proc.kill('SIGKILL'), SIGKILL_GRACE_MS);
    }, timeoutMs) : null;

    const finish = (fn, value) => {
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      if (killTimeout) clearTimeout(killTimeout);
      fn(value);
    };

    proc.stdout.on('data', (chunk) => { stdout += chunk; });
    proc.stderr.on('data', (chunk) => { stderr += chunk; });

    // Writing to stdin after a failed spawn raises EPIPE on a stream with
    // no listener, which is its own uncaught crash -- same failure shape
    // this whole file exists to prevent, just via a different event.
    proc.stdin.on('error', () => {});

    proc.on('close', (code) => {
      if (timedOut) {
        finish(reject, new PythonProcessError(`${label} timed out after ${timeoutMs}ms`, { kind: 'timeout', stdout, stderr, code }));
        return;
      }
      if (code !== 0) {
        finish(reject, new PythonProcessError(`${label} exited with code ${code}`, { kind: 'nonzero_exit', stdout, stderr, code }));
        return;
      }
      try {
        finish(resolve, JSON.parse(stdout));
      } catch {
        finish(reject, new PythonProcessError(`${label} produced invalid JSON output`, { kind: 'invalid_json', stdout, stderr, code }));
      }
    });

    proc.on('error', (err) => {
      finish(reject, new PythonProcessError(`Failed to start ${label}: ${err.message}`, { kind: 'spawn_failed', stdout, stderr }));
    });

    if (stdinBody !== undefined) {
      proc.stdin.write(typeof stdinBody === 'string' ? stdinBody : JSON.stringify(stdinBody));
      proc.stdin.end();
    }
  });
}

module.exports = { runPythonJson, PythonProcessError };
