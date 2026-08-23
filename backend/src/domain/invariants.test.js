// Unit tests for the domain rules themselves, with no database or HTTP in
// the way. Table-driven and boundary-focused: an off-by-one in isScore or a
// missed type check in isLatitude is exactly the kind of thing that passes a
// happy-path route test and then admits a bad row for years.

const {
  SHOT_TYPES,
  DRILL_SHOT_TYPES,
  OUTCOME_TAGS,
  AGGRESSIVE_OUTCOME_TAGS,
  BOUNDARY_NOTES,
  PHASE_KEYS,
  MAX_SETS_IN_A_MATCH,
  MAX_VIDEO_SECONDS,
  isShotType,
  isDrillShotType,
  isDrillKind,
  isOutcomeTag,
  isPhaseKey,
  isScore,
  isLatitude,
  isLongitude,
  isSetCount,
  isTimestampSec,
  isIsoDateTime,
  isPositiveIntegerId,
  isText,
  isOptionalText,
  isBoundaryNote,
} = require('./invariants');

// Values that are never valid for anything. Every predicate gets run against
// all of them, so a rule that forgets a typeof check can't slip through by
// only being tested with plausible-looking input.
const JUNK = [undefined, null, NaN, Infinity, -Infinity, {}, [], true, false, () => {}, Symbol('x')];

function expectRejectsJunk(predicate, { except = [] } = {}) {
  for (const value of JUNK) {
    if (except.includes(value)) continue;
    expect({ value: String(value), accepted: predicate(value) }).toEqual({ value: String(value), accepted: false });
  }
}

describe('vocabularies', () => {
  test.each([
    ['isShotType', isShotType, SHOT_TYPES, ['footwork', 'volley', 'Forehand', 'forehand ', '']],
    ['isDrillShotType', isDrillShotType, DRILL_SHOT_TYPES, ['volley', 'Footwork', '']],
    ['isDrillKind', isDrillKind, ['drill', 'lesson'], ['routine', 'Drill', '']],
    ['isOutcomeTag', isOutcomeTag, OUTCOME_TAGS, ['winner', 'error', 'Ace', '']],
    ['isPhaseKey', isPhaseKey, PHASE_KEYS, ['followthrough', 'Contact', '']],
  ])('%s accepts exactly its vocabulary', (_name, predicate, accepted, rejected) => {
    for (const value of accepted) expect(predicate(value)).toBe(true);
    for (const value of rejected) expect(predicate(value)).toBe(false);
    expectRejectsJunk(predicate);
  });

  // Regression guard for the bug this whole exercise surfaced: profile.js
  // filtered on tags ('winner', 'error') the app has never written.
  test('the outcome vocabulary matches what the review screen produces', () => {
    expect(OUTCOME_TAGS).toEqual(['ace', 'winner_this_side', 'winner_other_side', 'skip']);
    expect(OUTCOME_TAGS).not.toContain('winner');
    expect(OUTCOME_TAGS).not.toContain('error');
  });

  test('aggressive outcomes are a strict subset that excludes the opponent winning', () => {
    for (const tag of AGGRESSIVE_OUTCOME_TAGS) expect(OUTCOME_TAGS).toContain(tag);
    expect(AGGRESSIVE_OUTCOME_TAGS).not.toContain('winner_other_side');
    expect(AGGRESSIVE_OUTCOME_TAGS).not.toContain('skip');
  });
});

describe('isScore (a similarity is a percentage)', () => {
  test.each([0, 0.1, 50, 99.99, 100, -0])('accepts %p', (value) => {
    expect(isScore(value)).toBe(true);
  });

  test.each([
    [-0.0001, 'just below zero'],
    [100.0001, 'just above one hundred'],
    [101, 'above the range'],
    [999999, 'the leaderboard-topping value the old finite-only check allowed'],
    [-5, 'negative'],
  ])('rejects %p (%s)', (value) => {
    expect(isScore(value)).toBe(false);
  });

  // The reason this matters: SQLite stores a bound string in a REAL column as
  // text, and text sorts above every number in ORDER BY.
  test.each(['80', '0', '100', ''])('rejects the numeric-looking string %p', (value) => {
    expect(isScore(value)).toBe(false);
  });

  test('rejects junk', () => expectRejectsJunk(isScore));
});

describe('coordinates', () => {
  test.each([[-90], [0], [90], [51.5]])('isLatitude accepts %p', (v) => expect(isLatitude(v)).toBe(true));
  test.each([[-90.0001], [90.0001], [5000], ['51.5']])('isLatitude rejects %p', (v) => expect(isLatitude(v)).toBe(false));

  test.each([[-180], [0], [180], [-0.12]])('isLongitude accepts %p', (v) => expect(isLongitude(v)).toBe(true));
  test.each([[-180.0001], [180.0001], [360], ['0']])('isLongitude rejects %p', (v) => expect(isLongitude(v)).toBe(false));

  test('reject junk', () => {
    expectRejectsJunk(isLatitude);
    expectRejectsJunk(isLongitude);
  });
});

describe('isSetCount', () => {
  test.each([0, 1, 3, MAX_SETS_IN_A_MATCH])('accepts %p', (v) => expect(isSetCount(v)).toBe(true));
  test.each([
    -1, -5, MAX_SETS_IN_A_MATCH + 1, 1e9, 2.5, '3',
  ])('rejects %p', (v) => expect(isSetCount(v)).toBe(false));
  test('rejects junk', () => expectRejectsJunk(isSetCount));
});

describe('isTimestampSec', () => {
  test.each([0, 0.5, 12.75, MAX_VIDEO_SECONDS])('accepts %p', (v) => expect(isTimestampSec(v)).toBe(true));
  test.each([-0.1, -1, MAX_VIDEO_SECONDS + 1, '12'])('rejects %p', (v) => expect(isTimestampSec(v)).toBe(false));
  test('rejects junk', () => expectRejectsJunk(isTimestampSec));
});

describe('isIsoDateTime', () => {
  test.each([
    '2026-08-22',
    '2026-08-22T10:30:00Z',
    '2026-08-22T10:30:00.000Z',
    '2026-08-22 10:30:00',
  ])('accepts %p', (v) => expect(isIsoDateTime(v)).toBe(true));

  test.each([
    ['not a date', 'unparseable'],
    ['', 'empty'],
    ['   ', 'whitespace'],
    ['1899-01-01', 'implausibly early'],
    ['3000-01-01', 'implausibly late — would sort to the top of every list forever'],
  ])('rejects %p (%s)', (v) => expect(isIsoDateTime(v)).toBe(false));

  test('rejects junk', () => expectRejectsJunk(isIsoDateTime));
});

describe('isPositiveIntegerId', () => {
  test.each([1, 42, '1', '42', 9007199254740991])('accepts %p', (v) => expect(isPositiveIntegerId(v)).toBe(true));
  test.each([
    0, -1, '0', '-1', 1.5, '1.5', '1e3', 'abc', '', ' 1', '1 ', '+1', '01x',
  ])('rejects %p', (v) => expect(isPositiveIntegerId(v)).toBe(false));
  test('rejects junk', () => expectRejectsJunk(isPositiveIntegerId));
});

describe('isText / isOptionalText', () => {
  const isShort = isText(5);

  test('accepts real content within the cap', () => {
    expect(isShort('hi')).toBe(true);
    expect(isShort('12345')).toBe(true);
  });

  test('rejects empty and whitespace-only content', () => {
    expect(isShort('')).toBe(false);
    expect(isShort('   ')).toBe(false);
  });

  test('measures length before trimming, so padding cannot smuggle past the cap', () => {
    expect(isShort('a     ')).toBe(false);
  });

  test('rejects over-long content and non-strings', () => {
    expect(isShort('123456')).toBe(false);
    expectRejectsJunk(isShort);
  });

  test('isOptionalText allows absent or cleared, but still caps content', () => {
    const optionalShort = isOptionalText(5);
    expect(optionalShort(undefined)).toBe(true);
    expect(optionalShort(null)).toBe(true);
    expect(optionalShort('')).toBe(true);
    expect(optionalShort('12345')).toBe(true);
    expect(optionalShort('123456')).toBe(false);
    expect(optionalShort(42)).toBe(false);
  });
});

describe('isBoundaryNote (a comma-joined list with exclusivity rules)', () => {
  test('treats absent/empty as valid — leaving it unset means "did not look"', () => {
    expect(isBoundaryNote(undefined)).toBe(true);
    expect(isBoundaryNote(null)).toBe(true);
    expect(isBoundaryNote('')).toBe(true);
  });

  test.each(BOUNDARY_NOTES)('accepts the single verdict %p', (note) => {
    expect(isBoundaryNote(note)).toBe(true);
  });

  test('accepts the two independent problems together, in either order', () => {
    expect(isBoundaryNote('started_too_late,cut_off_early')).toBe(true);
    expect(isBoundaryNote('cut_off_early,started_too_late')).toBe(true);
  });

  test.each([
    ['ok,should_split', 'two contradictory whole-clip verdicts'],
    ['ok,cut_off_early', "'ok' cannot coexist with a reported problem"],
    ['should_split,started_too_late', "'should_split' must stand alone"],
    ['cut_off_early,cut_off_early', 'duplicate entries'],
    ['cut_off_early,bogus', 'an unknown token alongside a valid one'],
    ['perfect', 'a label rather than a value'],
    ['cut_off_early, started_too_late', 'a space after the comma is not the stored format'],
    [',', 'empty tokens'],
  ])('rejects %p (%s)', (value) => {
    expect(isBoundaryNote(value)).toBe(false);
  });

  test('rejects non-strings', () => {
    expectRejectsJunk(isBoundaryNote, { except: [undefined, null] });
  });
});
