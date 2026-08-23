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
});
