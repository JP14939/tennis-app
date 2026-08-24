// Proves the integrity checker actually catches each thing it claims to.
//
// A checker that never fires is indistinguishable from a checker that works,
// and `npm run verify:db` reports zero violations against the real database
// today -- so the only way to know those 48 checks mean anything is to feed
// each one a row that violates it and watch it fire. Every test also asserts
// that ONLY the intended check fires, which catches over-broad SQL.

process.env.DB_PATH = ':memory:';

const db = require('../db');
const { runIntegrityChecks, ALL_CHECKS } = require('./integrityChecks');

// Tables written by these tests, cleared between each one. Ordered
// children-before-parents so foreign keys (which better-sqlite3 enables by
// default) don't block the reset.
const TABLES_IN_DELETE_ORDER = [
  'drill_practice_attempts', 'drill_routine_steps', 'drill_items',
  'message_reports', 'messages', 'user_blocks',
  'shared_analyses', 'swing_annotations', 'coach_notes',
  'friend_matches', 'friend_links', 'coach_links',
  'availability_posts', 'court_confirmations', 'court_watches',
  'club_watches', 'club_courts', 'clubs', 'courts',
  'reel_jobs', 'rally_clips', 'highlight_jobs',
  'celebrity_scores', 'password_resets', 'analysis_usage', 'analyses', 'users',
];

function reset() {
  db.pragma('foreign_keys = OFF');
  for (const table of TABLES_IN_DELETE_ORDER) db.prepare(`DELETE FROM ${table}`).run();
  db.pragma('foreign_keys = ON');
}

function makeUser(email) {
  return db.prepare('INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)')
    .run(email, 'hash', 'Test User').lastInsertRowid;
}

function makeAnalysis(userId, overrides = {}) {
  const { shot_type = 'forehand', similarity = 80 } = overrides;
  return db.prepare(
    'INSERT INTO analyses (user_id, shot_type, similarity, result_json) VALUES (?, ?, ?, ?)'
  ).run(userId, shot_type, similarity, '{}').lastInsertRowid;
}

function makeHighlightJob(userId) {
  return db.prepare('INSERT INTO highlight_jobs (user_id, video_path) VALUES (?, ?)')
    .run(userId, '/tmp/v.mp4').lastInsertRowid;
}

function makeRallyClip(userId, jobId, overrides = {}) {
  const {
    start_sec = 10, end_sec = 25, duration_sec = 15, outcome_tag = null, boundary_note = null,
  } = overrides;
  return db.prepare(
    `INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, outcome_tag, boundary_note)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(jobId, userId, '/tmp/c.mp4', start_sec, end_sec, duration_sec, outcome_tag, boundary_note).lastInsertRowid;
}

function makeCourt(overrides = {}) {
  const { name = 'Court', latitude = 51.5, longitude = -0.12, source = 'osm', verified = 1 } = overrides;
  return db.prepare(
    'INSERT INTO courts (name, latitude, longitude, source, verified) VALUES (?, ?, ?, ?, ?)'
  ).run(name, latitude, longitude, source, verified).lastInsertRowid;
}

// Writes that deliberately break an invariant often ALSO break a foreign key
// or CHECK constraint that SQLite enforces at write time. This bypasses those
// so the row can exist to be found -- which is exactly the situation the
// checker exists for (a row that got in before a rule existed, or via a
// direct sqlite3 session).
function withoutConstraints(fn) {
  db.pragma('foreign_keys = OFF');
  try {
    return fn();
  } finally {
    db.pragma('foreign_keys = ON');
  }
}

function violationNames() {
  return runIntegrityChecks(db).map((v) => v.name).sort();
}

beforeEach(reset);

describe('a clean database', () => {
  test('reports no violations when empty', () => {
    expect(runIntegrityChecks(db)).toEqual([]);
  });

  test('reports no violations for a fully-populated, valid dataset', () => {
    const alice = makeUser('alice@test.com');
    const bob = makeUser('bob@test.com');
    const [low, high] = alice < bob ? [alice, bob] : [bob, alice];

    const analysis = makeAnalysis(alice);
    const job = makeHighlightJob(alice);
    makeRallyClip(alice, job, { outcome_tag: 'winner_this_side', boundary_note: 'started_too_late,cut_off_early' });
    const court = makeCourt();

    db.prepare('INSERT INTO friend_links (user_a_id, user_b_id) VALUES (?, ?)').run(low, high);
    db.prepare('INSERT INTO messages (user_a_id, user_b_id, sender_id, body) VALUES (?, ?, ?, ?)')
      .run(low, high, alice, 'hello');
    db.prepare('INSERT INTO coach_links (coach_id, student_id) VALUES (?, ?)').run(bob, alice);
    db.prepare('INSERT INTO shared_analyses (analysis_id, owner_id, friend_id) VALUES (?, ?, ?)')
      .run(analysis, alice, bob);
    db.prepare('INSERT INTO friend_matches (logged_by, opponent_id, played_at, sets_won, sets_lost) VALUES (?, ?, ?, ?, ?)')
      .run(alice, bob, '2026-08-01', 2, 1);
    db.prepare('INSERT INTO availability_posts (user_id, court_id, start_time, end_time) VALUES (?, ?, ?, ?)')
      .run(alice, court, '2026-08-22T10:00:00Z', '2026-08-22T12:00:00Z');

    expect(runIntegrityChecks(db)).toEqual([]);
  });
});

describe('value-domain violations', () => {
  test('catches a shot type outside the ML pipeline vocabulary', () => {
    const user = makeUser('a@test.com');
    makeAnalysis(user, { shot_type: 'banana' });
    expect(violationNames()).toEqual(['analyses.shot_type']);
  });

  test.each([
    ['a score above 100', 999999],
    ['a negative score', -1],
  ])('catches %s', (_label, similarity) => {
    const user = makeUser('a@test.com');
    makeAnalysis(user, { similarity });
    expect(violationNames()).toEqual(['analyses.similarity']);
  });

  // The specific shape that poisons ORDER BY: SQLite stores a bound string in
  // a REAL column as text, and text sorts above every number.
  test('catches a score stored as text via type affinity', () => {
    const user = makeUser('a@test.com');
    makeAnalysis(user, { similarity: 'zzz' });

    const stored = db.prepare('SELECT typeof(similarity) AS t FROM analyses').get();
    expect(stored.t).toBe('text');
    expect(violationNames()).toEqual(['analyses.similarity']);
  });

  test('catches an analysis both flagged as not-a-shot and confirmed real', () => {
    const user = makeUser('a@test.com');
    const analysis = makeAnalysis(user);
    db.prepare('UPDATE analyses SET flagged_not_shot = 1, confirmed_real_shot = 1 WHERE id = ?').run(analysis);
    expect(violationNames()).toEqual(['analyses.shot_verdict']);
  });

  test('catches an outcome tag the review screen never produces', () => {
    const user = makeUser('a@test.com');
    // 'winner' is precisely the value profile.js used to filter on.
    makeRallyClip(user, makeHighlightJob(user), { outcome_tag: 'winner' });
    expect(violationNames()).toEqual(['rally_clips.outcome_tag']);
  });

  test.each([
    ['two contradictory whole-clip verdicts', 'ok,should_split'],
    ['an unknown token', 'perfect'],
    ['a duplicate token', 'cut_off_early,cut_off_early'],
  ])('catches a malformed boundary note: %s', (_label, boundary_note) => {
    const user = makeUser('a@test.com');
    makeRallyClip(user, makeHighlightJob(user), { boundary_note });
    expect(violationNames()).toEqual(['rally_clips.boundary_note']);
  });

  test.each([
    ['a clip ending before it starts', { start_sec: 30, end_sec: 10, duration_sec: -20 }],
    ['a negative start', { start_sec: -5, end_sec: 10, duration_sec: 15 }],
    ['a duration that contradicts the span', { start_sec: 0, end_sec: 10, duration_sec: 60 }],
  ])('catches %s', (_label, overrides) => {
    const user = makeUser('a@test.com');
    makeRallyClip(user, makeHighlightJob(user), overrides);
    expect(violationNames()).toEqual(['rally_clips.timing']);
  });

  test.each([
    ['an impossible latitude', { latitude: 5000 }],
    ['an impossible longitude', { longitude: 360 }],
  ])('catches %s', (_label, overrides) => {
    makeCourt(overrides);
    expect(violationNames()).toEqual(['courts.coordinates']);
  });

  // A handful of vocabularies already have a schema-level CHECK constraint,
  // so a bad value can't be written at all -- not even with foreign keys off,
  // since PRAGMA foreign_keys has no effect on CHECK. The checker still covers
  // them (cheap, and a schema change could drop a constraint), but the real
  // enforcement is the constraint itself, so that's what's asserted here.
  test.each([
    ['courts.source', "INSERT INTO courts (name, latitude, longitude, source) VALUES ('C', 51.5, -0.12, 'guess')"],
    ['users.tier', "INSERT INTO users (email, password_hash, name, tier) VALUES ('t@test.com', 'h', 'N', 'gold')"],
    ['drill_items.kind', "INSERT INTO drill_items (kind, shot_type, title, explanation) VALUES ('routine', 'forehand', 'T', 'E')"],
    ['celebrity_scores.shot_type', "INSERT INTO celebrity_scores (name, shot_type, score, added_by) VALUES ('X', 'volley', 50, 1)"],
    ['availability_posts.status', "INSERT INTO availability_posts (user_id, court_id, start_time, status) VALUES (1, 1, '2026-08-22', 'maybe')"],
  ])('%s is refused by a schema CHECK constraint, not just by the checker', (_name, sql) => {
    expect(() => withoutConstraints(() => db.prepare(sql).run())).toThrow(/CHECK constraint failed/i);
  });

  test.each([
    ['negative sets', -1, 2],
    ['more sets than a match can contain', 99, 0],
  ])('catches %s in a logged match', (_label, setsWon, setsLost) => {
    const alice = makeUser('a@test.com');
    const bob = makeUser('b@test.com');
    db.prepare('INSERT INTO friend_matches (logged_by, opponent_id, played_at, sets_won, sets_lost) VALUES (?, ?, ?, ?, ?)')
      .run(alice, bob, '2026-08-01', setsWon, setsLost);
    expect(violationNames()).toEqual(['friend_matches.sets']);
  });

  test('catches an unparseable match date', () => {
    const alice = makeUser('a@test.com');
    const bob = makeUser('b@test.com');
    db.prepare('INSERT INTO friend_matches (logged_by, opponent_id, played_at, sets_won, sets_lost) VALUES (?, ?, ?, ?, ?)')
      .run(alice, bob, 'last tuesday', 2, 1);
    expect(violationNames()).toEqual(['friend_matches.played_at']);
  });

  test('catches an availability post that ends before it starts', () => {
    const user = makeUser('a@test.com');
    db.prepare('INSERT INTO availability_posts (user_id, court_id, start_time, end_time) VALUES (?, ?, ?, ?)')
      .run(user, makeCourt(), '2026-08-22T12:00:00Z', '2026-08-22T10:00:00Z');
    expect(violationNames()).toEqual(['availability_posts.window']);
  });

  // coach.js validates both of these at write time; neither had an at-rest
  // counterpart until now, so a row that predates the rule (or arrived via a
  // direct sqlite3 session) went unreported forever.
  test.each([
    ['a phase-pinned note naming a phase that does not exist', { phase_key: 'finish' }, 'coach_notes.phase_key'],
    ['a note pinned past the end of any real video', { timestamp_sec: 999999 }, 'coach_notes.timestamp_sec'],
    ['a note pinned to a negative video offset', { timestamp_sec: -1 }, 'coach_notes.timestamp_sec'],
  ])('catches %s', (_label, overrides, expected) => {
    const student = makeUser('s@test.com');
    const coach = makeUser('c@test.com');
    const analysisId = makeAnalysis(student);
    withoutConstraints(() => db.prepare(
      'INSERT INTO coach_notes (coach_id, analysis_id, note_text, phase_key, timestamp_sec) VALUES (?, ?, ?, ?, ?)'
    ).run(coach, analysisId, 'Note', overrides.phase_key ?? null, overrides.timestamp_sec ?? null));
    expect(violationNames()).toEqual([expected]);
  });

  test('catches an availability post whose end time is not a real date', () => {
    const user = makeUser('a@test.com');
    db.prepare('INSERT INTO availability_posts (user_id, court_id, start_time, end_time) VALUES (?, ?, ?, ?)')
      .run(user, makeCourt(), '2026-08-22T10:00:00Z', 'whenever');
    expect(violationNames()).toEqual(['availability_posts.end_time']);
  });

  test('catches a curated leaderboard score outside 0-100', () => {
    const admin = makeUser('admin@test.com');
    db.prepare('INSERT INTO celebrity_scores (name, shot_type, score, added_by) VALUES (?, ?, ?, ?)')
      .run('Someone', 'serve', 150, admin);
    expect(violationNames()).toEqual(['celebrity_scores.score']);
  });

  test('catches an email that was not normalised to lowercase', () => {
    makeUser('MixedCase@Test.com');
    expect(violationNames()).toEqual(['users.email']);
  });
});

describe('structural violations', () => {
  test('catches a message thread whose user pair is not sorted', () => {
    const alice = makeUser('a@test.com');
    const bob = makeUser('b@test.com');
    const [low, high] = alice < bob ? [alice, bob] : [bob, alice];
    // Stored backwards -- every thread query looks up [min, max], so this
    // conversation is invisible to both participants.
    db.prepare('INSERT INTO messages (user_a_id, user_b_id, sender_id, body) VALUES (?, ?, ?, ?)')
      .run(high, low, alice, 'hello');
    expect(violationNames()).toEqual(['messages.pair_ordering']);
  });

  test('catches a message sent by someone outside its own thread', () => {
    const alice = makeUser('a@test.com');
    const bob = makeUser('b@test.com');
    const mallory = makeUser('m@test.com');
    const [low, high] = alice < bob ? [alice, bob] : [bob, alice];
    db.prepare('INSERT INTO messages (user_a_id, user_b_id, sender_id, body) VALUES (?, ?, ?, ?)')
      .run(low, high, mallory, 'hello');
    expect(violationNames()).toEqual(['messages.sender_in_thread']);
  });

  test('catches a self-friendship', () => {
    const alice = makeUser('a@test.com');
    db.prepare('INSERT INTO friend_links (user_a_id, user_b_id) VALUES (?, ?)').run(alice, alice);
    expect(violationNames()).toEqual(['friend_links.pair_ordering']);
  });

  test('catches someone coaching themselves', () => {
    const alice = makeUser('a@test.com');
    db.prepare('INSERT INTO coach_links (coach_id, student_id) VALUES (?, ?)').run(alice, alice);
    expect(violationNames()).toEqual(['coach_links.self']);
  });

  test('catches someone blocking themselves', () => {
    const alice = makeUser('a@test.com');
    db.prepare('INSERT INTO user_blocks (blocker_id, blocked_id) VALUES (?, ?)').run(alice, alice);
    expect(violationNames()).toEqual(['user_blocks.self']);
  });

  test('catches a share whose recorded owner is not the analysis owner', () => {
    const alice = makeUser('a@test.com');
    const bob = makeUser('b@test.com');
    const carol = makeUser('c@test.com');
    db.prepare('INSERT INTO shared_analyses (analysis_id, owner_id, friend_id) VALUES (?, ?, ?)')
      .run(makeAnalysis(alice), bob, carol);
    expect(violationNames()).toEqual(['shared_analyses.owner']);
  });

  test('catches a rally clip attributed to a different user than its job', () => {
    const alice = makeUser('a@test.com');
    const bob = makeUser('b@test.com');
    makeRallyClip(bob, makeHighlightJob(alice));
    expect(violationNames()).toEqual(['rally_clips.job_owner']);
  });

  test('catches two practice steps claiming the same position in a lesson', () => {
    const item = db.prepare(
      "INSERT INTO drill_items (kind, shot_type, title, explanation) VALUES ('lesson', 'forehand', 'L', 'E')"
    ).run().lastInsertRowid;
    const insertStep = db.prepare('INSERT INTO drill_routine_steps (drill_item_id, step_order, label) VALUES (?, ?, ?)');
    insertStep.run(item, 0, 'First');
    insertStep.run(item, 0, 'Also first');
    expect(violationNames()).toEqual(['drill_routine_steps.ordering']);
  });
});

describe('orphan canaries', () => {
  // better-sqlite3 enables PRAGMA foreign_keys by default, so producing an
  // orphan requires deliberately turning that off -- which is the scenario
  // these checks exist to notice.
  test('foreign keys are on by default, so orphans cannot normally be created', () => {
    expect(db.pragma('foreign_keys', { simple: true })).toBe(1);
    const user = makeUser('a@test.com');
    const analysis = makeAnalysis(user);
    db.prepare('INSERT INTO coach_notes (coach_id, analysis_id, note_text) VALUES (?, ?, ?)')
      .run(user, analysis, 'note');

    expect(() => db.prepare('DELETE FROM analyses WHERE id = ?').run(analysis))
      .toThrow(/FOREIGN KEY/i);
  });

  test('catches a coach note pointing at a deleted analysis', () => {
    const user = makeUser('a@test.com');
    const analysis = makeAnalysis(user);
    db.prepare('INSERT INTO coach_notes (coach_id, analysis_id, note_text) VALUES (?, ?, ?)')
      .run(user, analysis, 'note');

    withoutConstraints(() => db.prepare('DELETE FROM analyses WHERE id = ?').run(analysis));
    expect(violationNames()).toEqual(['coach_notes.analysis_id']);
  });

  test('catches a rally clip whose detection job is gone', () => {
    const user = makeUser('a@test.com');
    const job = makeHighlightJob(user);
    makeRallyClip(user, job);

    withoutConstraints(() => db.prepare('DELETE FROM highlight_jobs WHERE id = ?').run(job));
    expect(violationNames()).toEqual(['rally_clips.job_id']);
  });
});

describe('report shape', () => {
  test('every check has a distinct name, a category, and a plain-English description', () => {
    const names = ALL_CHECKS.map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
    for (const check of ALL_CHECKS) {
      expect(check.description).toEqual(expect.any(String));
      expect(check.description.length).toBeGreaterThan(10);
      expect(['value-domain', 'structural', 'orphan']).toContain(check.category);
    }
  });

  test('a violation reports how many rows are wrong and shows samples of them', () => {
    const user = makeUser('a@test.com');
    for (let i = 0; i < 8; i++) makeAnalysis(user, { shot_type: 'banana' });

    const [violation] = runIntegrityChecks(db);
    expect(violation.name).toBe('analyses.shot_type');
    expect(violation.count).toBe(8);
    expect(violation.sample).toHaveLength(5); // SAMPLE_LIMIT
    expect(violation.sample[0]).toMatchObject({ shot_type: 'banana' });
  });
});
