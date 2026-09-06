// Shared by highlights.js's background job runners (runJob/runReelJob) --
// maps a runPythonJson.js PythonProcessError to a user-facing failure
// message, given a per-job-type `messages` table keyed by err.kind
// ('timeout' | 'nonzero_exit' | 'invalid_json' | 'spawn_failed'). A
// nonzero_exit's own reported error (JSON the Python script wrote to stdout
// even on failure) takes priority over the generic fallback text -- a
// timeout/spawn-failure/invalid-json's stdout is either empty or not the
// script's own error shape, so only nonzero_exit gets this override.
function resolveJobFailureMessage(err, messages) {
  let message = messages[err.kind] || messages.nonzero_exit;
  if (err.kind === 'nonzero_exit') {
    try { message = JSON.parse(err.stdout).error || message; } catch { /* stdout wasn't JSON */ }
  }
  return message;
}

module.exports = { resolveJobFailureMessage };
