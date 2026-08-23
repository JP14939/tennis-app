const db = require('../db');
const crypto = require('crypto');

// Same alphabet/shape coach.js's and friends.js's invite/friend codes both
// need: 8 uppercase base32-ish characters, excluding ambiguous 0/O/1/I so a
// code is easy to read aloud or type from memory. Was defined identically in
// both route files (each one noting in a comment that the other had the same
// code); extracted alongside redeemInviteCode() below, which already
// consolidates the other half of this exact duplication.
function generateInviteCode() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let code = '';
  for (let i = 0; i < 8; i++) {
    code += alphabet[crypto.randomInt(alphabet.length)];
  }
  return code;
}

// Shared shape behind /coach/link and /friends/link: look up a still-valid
// invite code, reject self-redemption, insert the resulting link, and mark
// the code used -- all inside one synchronous transaction so two concurrent
// redemptions of the same code can't both pass the `used_at IS NULL` check
// before either UPDATE lands (a "single-use" code would otherwise link
// twice). Both call sites were written independently and ended up
// line-for-line identical in this shape, differing only in table/column
// names and the link-insert itself, which `insertLink` captures.
//
// `inviteTable` is always a fixed string literal from a call site, never
// user input -- safe to interpolate since better-sqlite3 can't bind
// identifiers (table/column names) as query parameters.
function redeemInviteCode({ inviteTable, ownerIdColumn, code, requesterId, insertLink }) {
  const CODE_NOT_FOUND = Symbol('CODE_NOT_FOUND');
  const SELF_LINK = Symbol('SELF_LINK');

  const redeem = db.transaction(() => {
    const invite = db.prepare(`SELECT * FROM ${inviteTable} WHERE code = ? AND used_at IS NULL`)
      .get(String(code).toUpperCase());
    if (!invite) return CODE_NOT_FOUND;
    if (invite[ownerIdColumn] === requesterId) return SELF_LINK;

    insertLink(invite);
    db.prepare(`UPDATE ${inviteTable} SET used_at = datetime('now') WHERE id = ?`).run(invite.id);
    return invite[ownerIdColumn];
  });

  return { outcome: redeem(), CODE_NOT_FOUND, SELF_LINK };
}

module.exports = { redeemInviteCode, generateInviteCode };
