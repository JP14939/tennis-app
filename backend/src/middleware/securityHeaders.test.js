const { securityHeaders, HTML_CSP } = require('./securityHeaders');

function makeReqRes(path) {
  const headers = {};
  const req = { path };
  const res = { set(k, v) { headers[k] = v; return this; } };
  let nextCalled = false;
  securityHeaders(req, res, () => { nextCalled = true; });
  return { headers, nextCalled };
}

describe('securityHeaders', () => {
  test('sets the baseline headers on a JSON API path and calls next', () => {
    const { headers, nextCalled } = makeReqRes('/api/history');
    expect(nextCalled).toBe(true);
    expect(headers['X-Content-Type-Options']).toBe('nosniff');
    expect(headers['X-Frame-Options']).toBe('DENY');
    expect(headers['Referrer-Policy']).toBe('no-referrer');
    // The Expo app is a different origin and must still be able to load clips.
    expect(headers['Cross-Origin-Resource-Policy']).toBe('cross-origin');
    // No CSP on non-HTML responses.
    expect(headers['Content-Security-Policy']).toBeUndefined();
  });

  test('adds a strict CSP only for the served HTML page', () => {
    const { headers } = makeReqRes('/reset-password.html');
    expect(headers['Content-Security-Policy']).toBe(HTML_CSP);
    expect(HTML_CSP).toContain("default-src 'none'");
    expect(HTML_CSP).toContain("frame-ancestors 'none'");
    expect(HTML_CSP).toContain("connect-src 'self'");
  });
});
