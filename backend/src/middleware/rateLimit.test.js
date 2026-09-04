// Regression test for the security-review fix: routes/auth.js had no
// request cap at all before this -- unlimited login attempts, unlimited
// free-account creation, unlimited forgot-password requests.
const { rateLimit } = require('./rateLimit');

function makeReqRes(ip) {
  const req = { ip };
  let statusCode = null;
  let body = null;
  const res = {
    status(code) { statusCode = code; return this; },
    json(payload) { body = payload; return this; },
  };
  return { req, res, get statusCode() { return statusCode; }, get body() { return body; } };
}

describe('rateLimit', () => {
  test('allows up to max requests, then rejects with 429', () => {
    const limiter = rateLimit({ windowMs: 60_000, max: 2, keyPrefix: 'test-basic' });
    const next = jest.fn();

    const first = makeReqRes('1.2.3.4');
    limiter(first.req, first.res, next);
    const second = makeReqRes('1.2.3.4');
    limiter(second.req, second.res, next);
    expect(next).toHaveBeenCalledTimes(2);

    const third = makeReqRes('1.2.3.4');
    limiter(third.req, third.res, next);
    expect(next).toHaveBeenCalledTimes(2); // not called a 3rd time
    expect(third.statusCode).toBe(429);
  });

  test('tracks different IPs independently', () => {
    const limiter = rateLimit({ windowMs: 60_000, max: 1, keyPrefix: 'test-per-ip' });
    const next = jest.fn();

    const a = makeReqRes('10.0.0.1');
    limiter(a.req, a.res, next);
    const b = makeReqRes('10.0.0.2');
    limiter(b.req, b.res, next);

    expect(next).toHaveBeenCalledTimes(2);
    expect(a.statusCode).toBeNull();
    expect(b.statusCode).toBeNull();
  });

  test('different keyPrefixes on the same IP do not share a bucket', () => {
    const loginLimiter = rateLimit({ windowMs: 60_000, max: 1, keyPrefix: 'test-login' });
    const signupLimiter = rateLimit({ windowMs: 60_000, max: 1, keyPrefix: 'test-signup' });
    const next = jest.fn();

    const loginCall = makeReqRes('5.5.5.5');
    loginLimiter(loginCall.req, loginCall.res, next);
    const signupCall = makeReqRes('5.5.5.5');
    signupLimiter(signupCall.req, signupCall.res, next);

    expect(next).toHaveBeenCalledTimes(2);
  });

  test('does not allow a 2x burst spanning a window boundary', () => {
    jest.useFakeTimers();
    try {
      const limiter = rateLimit({ windowMs: 1000, max: 4, keyPrefix: 'test-boundary' });
      const next = jest.fn();
      const ip = '9.9.9.9';

      // Exhaust the limit right at the start of the window.
      jest.setSystemTime(900);
      for (let i = 0; i < 4; i += 1) {
        const call = makeReqRes(ip);
        limiter(call.req, call.res, next);
      }
      expect(next).toHaveBeenCalledTimes(4);

      // Just past the window boundary (windowStart 900 + windowMs 1000 =
      // 1900): a fixed/tumbling window would have reset the bucket and
      // allowed a fresh burst of `max` here, doubling the real rate over
      // that ~1s span. The sliding approximation should still reject.
      jest.setSystemTime(1950);
      const afterBoundary = makeReqRes(ip);
      limiter(afterBoundary.req, afterBoundary.res, next);
      expect(afterBoundary.statusCode).toBe(429);
      expect(next).toHaveBeenCalledTimes(4);

      // Once the previous window's weight has fully decayed, requests flow
      // again -- this isn't a permanent lockout, just a smoothed boundary.
      jest.setSystemTime(3000);
      const later = makeReqRes(ip);
      limiter(later.req, later.res, next);
      expect(next).toHaveBeenCalledTimes(5);
    } finally {
      jest.useRealTimers();
    }
  });
});
