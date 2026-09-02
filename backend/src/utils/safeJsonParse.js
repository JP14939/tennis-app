// A single malformed JSON column (partial write from a prior crash, manual
// DB edit, etc.) used to throw straight out of an unguarded JSON.parse and
// crash the *entire* list response for every row-mapping route that hit it,
// not just the one bad row. Centralized here so every call site degrades
// the same way instead of re-deriving its own try/catch.
function safeJsonParse(raw, context) {
  try {
    return JSON.parse(raw);
  } catch (err) {
    console.error(`[safeJsonParse] Failed to parse JSON for ${context}: ${err.message}`);
    return null;
  }
}

module.exports = { safeJsonParse };
