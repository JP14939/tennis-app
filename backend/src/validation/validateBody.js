// Turns the domain rules in ../domain/invariants.js into a 400 response.
//
// Deliberately tiny -- no schema DSL, no dependency. Every route file in this
// backend already hand-writes `if (bad) return res.status(400).json({ error })`
// chains; the only thing wrong with them was that each one invented its own
// rules. This keeps the shape those routes (and the frontend) already expect
// and just moves the rules themselves to one place.

// Each rule is [field, value, predicate, message].
//   - `field` names the offending input, for the `field` key on the response.
//   - `message` completes the sentence "<field> ...", e.g.
//     ['shotType', v, isShotType, 'must be one of forehand, backhand, serve']
//     -> { error: 'shotType must be one of forehand, backhand, serve',
//          field: 'shotType' }
//
// Returns null when everything passes, otherwise the response body for the
// FIRST failure. First-failure-only is intentional: these are programming or
// tampering errors from a client that already knows the contract, not a form
// a human is filling in, so there's nothing to be gained from collecting them.
function validate(rules) {
  for (const [field, value, predicate, message] of rules) {
    if (!predicate(value)) {
      return { error: `${field} ${message}`, field };
    }
  }
  return null;
}

// Sugar for the very common "this field is optional, but if present it must
// satisfy P" shape -- without it every optional field needs its own
// `(v) => v === undefined || P(v)` wrapper written inline at the call site.
function optional(predicate) {
  return (value) => value === undefined || value === null || predicate(value);
}

// `must be one of a, b, c` -- the message every vocabulary rule wants, built
// from the vocabulary itself so it can't drift out of sync with the check.
function oneOfMessage(vocabulary) {
  return `must be one of ${vocabulary.join(', ')}`;
}

module.exports = { validate, optional, oneOfMessage };
