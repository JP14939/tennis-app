// What the data in this database MEANS -- written from the real-world
// concept each column represents, not reverse-engineered from whatever the
// routes happened to accept. Every rule here should still read as true if
// the routes were rewritten from scratch tomorrow.
//
// Two consumers, deliberately sharing one definition:
//   - src/validation/validateBody.js, at every write boundary (reject bad
//     input at the door).
//   - src/domain/integrityChecks.js, against data already at rest (prove
//     what's stored still satisfies the same rules).
//
// Deliberately dependency-free and Express-unaware so both can use it, and
// so each predicate is unit-testable on its own.

const { SHOT_TYPES } = require('../config/shotTypes');

// ── Vocabularies ────────────────────────────────────────────────────────────
// Closed sets. Each one is cited to the code path that actually produces the
// value, because a vocabulary invented here rather than observed there is how
// profile.js ended up filtering on an 'outcome_tag' the app never writes.

// Drill/lesson library items cover one more category than the ML pipeline
// does: 'footwork' drills have no swing to analyse, so they're valid on a
// drill_item but never on an analyses row. See DevDrillsEditorScreen.js.
const DRILL_SHOT_TYPES = [...SHOT_TYPES, 'footwork'];

const DRILL_KINDS = ['drill', 'lesson'];

// The four buttons in HighlightReviewScreen.js's TAG_OPTIONS -- the complete
// set of answers a user can give to "who won this point?". 'skip' means "this
// isn't a rally at all", which is why it's a tag rather than an absence.
const OUTCOME_TAGS = ['ace', 'winner_this_side', 'winner_other_side', 'skip'];

// The subset that represents the USER ending the point aggressively. An
// opponent's winner ('winner_other_side') is a real, correctly-tagged rally
// but it is not the user's aggression, and 'skip' isn't a rally at all.
const AGGRESSIVE_OUTCOME_TAGS = ['ace', 'winner_this_side'];

// rally_clips.boundary_note is ML training data for tune_rally_gap.py, stored
// as a COMMA-JOINED LIST rather than a single token -- a clip can be wrong at
// both ends at once. See DevRallyBoundaryReviewScreen.js's toggleBoundary().
const BOUNDARY_NOTES = ['ok', 'started_too_late', 'cut_off_early', 'should_split'];

// 'started_too_late' and 'cut_off_early' describe independent problems and
// may co-occur. 'ok' and 'should_split' are whole-clip verdicts that can't be
// combined with anything, including each other.
const INDEPENDENT_BOUNDARY_NOTES = ['started_too_late', 'cut_off_early'];

// The four phases ResultsScreen renders a card for -- a coach note can be
// pinned to one of them, to a raw timestamp, or to neither (a general note).
const PHASE_KEYS = ['backswing', 'contact', 'follow_through', 'body_rotation'];

// Mirrors of the CHECK constraints db.js already declares. Duplicated here so
// the validation layer can reject a bad value with a clean 400 instead of
// letting SQLite raise SQLITE_CONSTRAINT_CHECK and falling through to a 500.
// (SHOT_TYPES, above, is also mirrored by a db.js CHECK constraint --
// celebrity_scores.shot_type -- but that one is generated FROM SHOT_TYPES
// rather than redeclared, so it can't drift the way these can.)
const TIERS = ['free', 'premium'];
const JOB_STATUSES = ['pending', 'processing', 'done', 'failed'];
const COURT_SOURCES = ['osm', 'user'];
const AVAILABILITY_STATUSES = ['open', 'cancelled'];

// ── Length caps ─────────────────────────────────────────────────────────────
// Defence in depth: express.json()'s 100KB default already bounds any single
// request body, so these exist to stop one field eating the whole budget and
// to keep values renderable in the UI that displays them.
//
// analyses.result_json is deliberately absent -- a real payload is ~28KB of
// legitimate trajectory data, and capping it here would reject valid saves.
const MAX_LENGTHS = {
  name: 80,
  messageBody: 2000,
  noteText: 2000,
  courtName: 120,
  costInfo: 500,
  scoreDetail: 100,
  availabilityNote: 300,
  reportReason: 500,
  pushToken: 200,
  celebrityName: 80,
  celebrityNote: 500,
  drillTitle: 200,
  drillExplanation: 5000,
  drillStepLabel: 200,
  // POST /history trusts req.body as a whole (see history.js's comment on
  // that route) -- these three flow straight into a SQLite bind param, and
  // better-sqlite3 throws a TypeError (surfacing as an unhandled 500, not a
  // clean 400) if the bound value is anything but a string/number/null, e.g.
  // an object or array. Capped generously above real observed values (pro
  // ids look like "forehand_0042"; angle labels like "Semi-front"; tip text
  // is a full coaching sentence) -- these exist to enforce TYPE, not length.
  proId: 50,
  angleLabel: 40,
  tipText: 1000,
  // A pen stroke's `points` array grows with every pixel of drag, and a
  // save can carry many strokes across both panes -- unlike every other cap
  // above (a length on the string itself), this bounds the SERIALIZED size
  // of the whole array, since the shape itself (array of {tool,color,points})
  // is arbitrary depth. A save carries TWO of these fields (paneAStrokes +
  // paneBStrokes) sharing express.json()'s single 100KB body limit -- a
  // first pass at this cap set it to 200KB per field, which made it
  // unreachable in practice (the body parser's 413 always fires first).
  // 40KB each leaves both fields room to hit the cap simultaneously
  // (80KB) with headroom under 100KB for the rest of the request body.
  annotationStrokesJson: 40_000,
};

// ── Value domains ───────────────────────────────────────────────────────────

function isOneOf(vocabulary) {
  return (value) => typeof value === 'string' && vocabulary.includes(value);
}

const isShotType = isOneOf(SHOT_TYPES);
const isDrillShotType = isOneOf(DRILL_SHOT_TYPES);
const isDrillKind = isOneOf(DRILL_KINDS);
const isOutcomeTag = isOneOf(OUTCOME_TAGS);
const isPhaseKey = isOneOf(PHASE_KEYS);
const isTier = isOneOf(TIERS);
const isJobStatus = isOneOf(JOB_STATUSES);
const isCourtSource = isOneOf(COURT_SOURCES);
const isAvailabilityStatus = isOneOf(AVAILABILITY_STATUSES);

// A similarity/score is a PERCENTAGE -- 0 means nothing matched, 100 means a
// perfect match, and there is no such thing as 101. Rejecting non-numbers
// matters more than it looks: SQLite's type affinity stores a string in the
// REAL `similarity` column as text, and `ORDER BY similarity DESC` sorts text
// ABOVE every number -- so a single bad row permanently tops both the friends
// and worldwide leaderboards and inflates profile.js's rank count.
function isScore(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100;
}

// Real geographic coordinates. Out-of-range values don't just look wrong:
// courts is a SHARED table (~33k rows), so one bad pin is visible to every
// user, and haversineKm() returns garbage distances for it.
function isLatitude(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= -90 && value <= 90;
}

function isLongitude(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= -180 && value <= 180;
}

// Sets won or lost in one match. A tennis match is best-of-3 or best-of-5, so
// 5 is the real ceiling; 7 leaves headroom for an unusual format without
// admitting values that are obviously data-entry errors. Negative sets would
// silently corrupt the win/loss record computeRecord() shows to both friends.
const MAX_SETS_IN_A_MATCH = 7;

function isSetCount(value) {
  return Number.isInteger(value) && value >= 0 && value <= MAX_SETS_IN_A_MATCH;
}

// An offset into a video, in seconds. Non-negative by definition, and capped
// at 4 hours -- longer than any real uploaded match, so anything above it is
// a unit mix-up (milliseconds) or garbage rather than a genuine timestamp.
const MAX_VIDEO_SECONDS = 4 * 60 * 60;

function isTimestampSec(value) {
  return typeof value === 'number' && Number.isFinite(value)
    && value >= 0 && value <= MAX_VIDEO_SECONDS;
}

// friend_matches.played_at and availability_posts.start_time are both ORDER BY
// keys AND get rendered as dates by the app. An unparseable string sorts
// unpredictably and displays as "Invalid Date"; a year-3000 value sorts to the
// top of every list forever. Bound both ends to a plausible window.
const MIN_PLAUSIBLE_YEAR = 2000;
const MAX_PLAUSIBLE_YEAR = 2100;

function isIsoDateTime(value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;
  const year = parsed.getUTCFullYear();
  return year >= MIN_PLAUSIBLE_YEAR && year <= MAX_PLAUSIBLE_YEAR;
}

// Row ids as they arrive from a URL param or a JSON body. AUTOINCREMENT ids
// start at 1, so 0 and negatives are never real. Accepts a numeric string
// (`req.params.id` is always a string) as well as a number.
function isPositiveIntegerId(value) {
  if (typeof value === 'number') return Number.isInteger(value) && value > 0;
  if (typeof value !== 'string' || !/^\d+$/.test(value)) return false;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0;
}

// Required free text: a real string with real content, within its cap.
// Length is measured before trimming so a caller can't smuggle megabytes of
// whitespace past the check.
function isText(maxLength) {
  return (value) => typeof value === 'string' && value.trim().length > 0 && value.length <= maxLength;
}

// Same, but the field may legitimately be absent or explicitly cleared.
function isOptionalText(maxLength) {
  return (value) => value === undefined || value === null || (typeof value === 'string' && value.length <= maxLength);
}

// An array whose element SHAPE is open-ended (annotation strokes: arbitrary
// tool/color/points per entry) but whose serialized SIZE still needs a
// ceiling. Checks Array.isArray as the structural requirement, then caps
// JSON.stringify(value).length rather than array length, since one stroke
// with 10,000 points is exactly as much of a problem as 10,000 one-point
// strokes.
function isBoundedJsonArray(maxSerializedLength) {
  return (value) => Array.isArray(value) && JSON.stringify(value).length <= maxSerializedLength;
}

// rally_clips.boundary_note as it's actually stored: either absent, or a
// comma-joined list of BOUNDARY_NOTES with no duplicates, honouring the
// exclusivity toggleBoundary() enforces in the UI. Validating only membership
// would accept 'ok,should_split' -- two contradictory verdicts on one clip,
// which would quietly poison tune_rally_gap.py's training signal.
function isBoundaryNote(value) {
  if (value === undefined || value === null || value === '') return true;
  if (typeof value !== 'string') return false;

  const parts = value.split(',');
  if (parts.some((part) => !BOUNDARY_NOTES.includes(part))) return false;
  if (new Set(parts).size !== parts.length) return false;

  const exclusive = parts.filter((part) => !INDEPENDENT_BOUNDARY_NOTES.includes(part));
  // An exclusive verdict ('ok' / 'should_split') must stand alone.
  return exclusive.length === 0 || (exclusive.length === 1 && parts.length === 1);
}

module.exports = {
  SHOT_TYPES,
  DRILL_SHOT_TYPES,
  DRILL_KINDS,
  OUTCOME_TAGS,
  AGGRESSIVE_OUTCOME_TAGS,
  BOUNDARY_NOTES,
  INDEPENDENT_BOUNDARY_NOTES,
  PHASE_KEYS,
  TIERS,
  JOB_STATUSES,
  COURT_SOURCES,
  AVAILABILITY_STATUSES,
  MAX_LENGTHS,
  MAX_SETS_IN_A_MATCH,
  MAX_VIDEO_SECONDS,
  MIN_PLAUSIBLE_YEAR,
  MAX_PLAUSIBLE_YEAR,
  isOneOf,
  isShotType,
  isDrillShotType,
  isDrillKind,
  isOutcomeTag,
  isPhaseKey,
  isTier,
  isJobStatus,
  isCourtSource,
  isAvailabilityStatus,
  isScore,
  isLatitude,
  isLongitude,
  isSetCount,
  isTimestampSec,
  isIsoDateTime,
  isPositiveIntegerId,
  isText,
  isOptionalText,
  isBoundedJsonArray,
  isBoundaryNote,
};
