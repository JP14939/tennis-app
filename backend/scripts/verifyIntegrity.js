#!/usr/bin/env node
// Verifies the database against the domain invariants in
// src/domain/invariants.js. Read-only -- it reports what's wrong and never
// repairs anything, so it's safe to point at production.
//
//   npm run verify:db                    # backend/data/app.db
//   node scripts/verifyIntegrity.js <path-to.db>
//
// Exits 0 when every invariant holds, 1 when any is violated (so it can gate
// a deploy or run from a scheduled job), and 2 if the database can't be read.

const path = require('path');
const Database = require('better-sqlite3');
const { runIntegrityChecks, ALL_CHECKS } = require('../src/domain/integrityChecks');

const DEFAULT_DB_PATH = path.join(__dirname, '..', 'data', 'app.db');
const dbPath = process.argv[2] || process.env.DB_PATH || DEFAULT_DB_PATH;

let db;
try {
  // fileMustExist so a typo'd path reports itself instead of silently
  // creating an empty database and cheerfully passing every check.
  db = new Database(dbPath, { readonly: true, fileMustExist: true });
} catch (err) {
  console.error(`Could not open database at ${dbPath}\n  ${err.message}`);
  process.exit(2);
}

console.log(`Verifying ${dbPath}`);
console.log(`${ALL_CHECKS.length} invariants\n`);

let violations;
try {
  violations = runIntegrityChecks(db);
} finally {
  db.close();
}

if (violations.length === 0) {
  console.log(`✓ All ${ALL_CHECKS.length} invariants hold.`);
  process.exit(0);
}

const totalRows = violations.reduce((sum, v) => sum + v.count, 0);
console.log(`✗ ${violations.length} of ${ALL_CHECKS.length} invariants violated (${totalRows} bad rows)\n`);

for (const violation of violations) {
  console.log(`  [${violation.category}] ${violation.name} — ${violation.count} row(s)`);
  console.log(`      expected: ${violation.description}`);
  for (const row of violation.sample) {
    console.log(`      offending: ${JSON.stringify(row)}`);
  }
  if (violation.count > violation.sample.length) {
    console.log(`      ...and ${violation.count - violation.sample.length} more`);
  }
  console.log('');
}

process.exit(1);
