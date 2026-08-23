// Regression test for a live bug this verification work surfaced.
//
// computePlayerType filtered rally clips on `outcome_tag IN ('winner', 'ace',
// 'error')`, but HighlightReviewScreen's four buttons only ever write 'ace',
// 'winner_this_side', 'winner_other_side' and 'skip'. 'winner' and 'error'
// have never been written by this app -- confirmed against the real database,
// where all 25 tagged clips matched none of the filtered values. The whole
// rally-based branch was therefore dead: no matter how many rallies a user
// reviewed, they silently fell through to the shot-type heuristic.

process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const request = require('supertest');
const { appWith, makeUser, makeAnalysis, db } = require('./testSupport');

const app = appWith(require('./profile'));

// MIN_TAGGED_RALLIES in profile.js -- below this the rally signal is treated
// as too noisy to trust and the shot-type heuristic is used instead.
const MIN_TAGGED_RALLIES = 5;

function tagRallies(userId, tags, { swingCount = 2, durationSec = 6 } = {}) {
  const jobId = db.prepare('INSERT INTO highlight_jobs (user_id, video_path) VALUES (?, ?)')
    .run(userId, '/tmp/v.mp4').lastInsertRowid;
  const insert = db.prepare(
    `INSERT INTO rally_clips (job_id, user_id, clip_path, start_sec, end_sec, duration_sec, swing_count, outcome_tag)
     VALUES (?, ?, '/tmp/c.mp4', 0, ?, ?, ?, ?)`
  );
  for (const tag of tags) insert.run(jobId, userId, durationSec, durationSec, swingCount, tag);
}

function getPlayerType(token) {
  return request(app).get('/api/profile/player-type').set('Authorization', `Bearer ${token}`);
}

describe('rally-based classification actually runs', () => {
  test('enough real-vocabulary tags produce an estimate rather than falling through', async () => {
    const { id, token } = makeUser();
    tagRallies(id, Array(MIN_TAGGED_RALLIES).fill('winner_this_side'));

    const res = await getPlayerType(token);

    expect(res.status).toBe(200);
    expect(res.body.confidence).toBe('estimated');
    // Before the fix this returned { type: null, reason: 'not_enough_data' }
    // because the filter matched none of the tags.
    expect(res.body.reason).toBeUndefined();
  });

  test('short aggressive points classify as a finisher', async () => {
    const { id, token } = makeUser();
    tagRallies(id, ['ace', 'ace', 'winner_this_side', 'winner_this_side', 'ace'], { swingCount: 2, durationSec: 5 });

    const res = await getPlayerType(token);
    expect(res.body.type).toBe('finisher');
  });

  test('long points the user rarely finishes classify as a grinder', async () => {
    const { id, token } = makeUser();
    tagRallies(id, Array(6).fill('winner_other_side'), { swingCount: 12, durationSec: 25 });

    const res = await getPlayerType(token);
    expect(res.body.type).toBe('grinder');
  });
});

describe('the opponent winning is a rally, but not the user being aggressive', () => {
  test("winner_other_side counts toward the sample without inflating aggression", async () => {
    const { id, token } = makeUser();
    // 5 tagged rallies, all won by the opponent, all short. If
    // winner_other_side counted as aggression this would read as a finisher.
    tagRallies(id, Array(5).fill('winner_other_side'), { swingCount: 2, durationSec: 5 });

    const res = await getPlayerType(token);

    expect(res.body.confidence).toBe('estimated');
    expect(res.body.type).not.toBe('finisher');
  });

  test('the same rallies won by the user DO read as a finisher', async () => {
    const { id, token } = makeUser();
    tagRallies(id, Array(5).fill('winner_this_side'), { swingCount: 2, durationSec: 5 });

    expect((await getPlayerType(token)).body.type).toBe('finisher');
  });
});

describe("'skip' is not a rally", () => {
  test('skipped clips never reach the sample, so they cannot trigger an estimate', async () => {
    const { id, token } = makeUser();
    tagRallies(id, Array(10).fill('skip'));

    const res = await getPlayerType(token);

    expect(res.body.type).toBeNull();
    expect(res.body.reason).toBe('not_enough_data');
  });
});

describe('falling back when there is not enough rally data', () => {
  test('below the minimum sample it uses the shot-type heuristic', async () => {
    const { id, token } = makeUser();
    tagRallies(id, ['ace', 'ace']); // below MIN_TAGGED_RALLIES
    for (let i = 0; i < 10; i++) makeAnalysis(id, { shotType: 'serve' });

    const res = await getPlayerType(token);
    expect(res.body.type).toBe('big_server');
  });

  test('a brand-new account reports how many more swings it needs', async () => {
    const { token } = makeUser();
    const res = await getPlayerType(token);
    expect(res.body).toMatchObject({ type: null, reason: 'not_enough_data', swingsNeeded: 10 });
  });
});

describe('GET /profile/rank', () => {
  test('counts only swings at or above the great-swing threshold', async () => {
    const { id, token } = makeUser();
    for (const similarity of [74, 75, 90, 100, 20]) makeAnalysis(id, { similarity });

    const res = await request(app).get('/api/profile/rank').set('Authorization', `Bearer ${token}`);

    expect(res.status).toBe(200);
    expect(res.body.greatCount).toBe(3); // 75, 90, 100
    expect(res.body.rank.name).toBe('Rally Starter');
  });
});
