// Route-manifest assertion for the requireAuth/optionalAuth convention.
//
// There's no enforced rule that every route must pick one of requireAuth or
// optionalAuth -- that gap caused a real free-tier-cap bypass (fixed
// 2026-08-22, see TODO_MANUAL.md). Each known site was patched individually,
// but nothing stops the *next* new route from repeating it. This test walks
// every router's actual middleware chain (not the source text) and fails on
// any route missing both, unless it's explicitly listed in
// domain/routeAuthExceptions.js with a reason.
process.env.DB_PATH = ':memory:';
process.env.JWT_SECRET = 'test-secret';

const fs = require('fs');
const path = require('path');

const exceptions = require('./domain/routeAuthExceptions');

const ROUTES_DIR = path.join(__dirname, 'routes');
const AUTH_MIDDLEWARE_NAMES = new Set(['requireAuth', 'optionalAuth']);

function exceptionKey(method, routePath) {
  return `${method.toLowerCase()} ${routePath}`;
}
const exceptionSet = new Set(exceptions.map((e) => exceptionKey(e.method, e.path)));

// Every real route file exports its Router directly (module.exports =
// router) -- confirmed across all 17 files in routes/. Test/support files
// don't match this glob.
const routeFiles = fs.readdirSync(ROUTES_DIR)
  .filter((f) => f.endsWith('.js') && !f.endsWith('.test.js') && f !== 'testSupport.js');

// { file, method, path, middlewareNames }
function collectRoutes() {
  const found = [];
  for (const file of routeFiles) {
    const router = require(path.join(ROUTES_DIR, file));
    if (!router || !Array.isArray(router.stack)) continue; // defensive, shouldn't happen
    for (const layer of router.stack) {
      if (!layer.route) continue; // skip router.use() middleware-only layers
      const methods = Object.keys(layer.route.methods);
      const middlewareNames = layer.route.stack.map((s) => s.name);
      for (const method of methods) {
        found.push({ file, method, path: layer.route.path, middlewareNames });
      }
    }
  }
  return found;
}

describe('route auth convention', () => {
  const routes = collectRoutes();

  test('at least one route was found in each router file (sanity check the walk itself works)', () => {
    expect(routes.length).toBeGreaterThan(50);
  });

  test('every route has requireAuth or optionalAuth, or is a listed exception', () => {
    const violations = routes.filter((r) => {
      const hasAuthMiddleware = r.middlewareNames.some((n) => AUTH_MIDDLEWARE_NAMES.has(n));
      const isException = exceptionSet.has(exceptionKey(r.method, r.path));
      return !hasAuthMiddleware && !isException;
    });

    if (violations.length > 0) {
      const details = violations
        .map((v) => `  ${v.method.toUpperCase()} ${v.path} (${v.file}) -- middleware: [${v.middlewareNames.join(', ')}]`)
        .join('\n');
      throw new Error(
        `Route(s) missing requireAuth/optionalAuth and not in domain/routeAuthExceptions.js:\n${details}\n\n` +
        `Fix by adding the appropriate middleware, or -- only if this route is ` +
        `deliberately public -- add it to domain/routeAuthExceptions.js with a reason.`
      );
    }
  });

  test('every listed exception still matches a real, still-unauthenticated route', () => {
    const stale = exceptions.filter((e) => {
      const match = routes.find((r) => r.method === e.method.toLowerCase() && r.path === e.path);
      if (!match) return true; // route renamed/removed -- exception is dead weight
      return match.middlewareNames.some((n) => AUTH_MIDDLEWARE_NAMES.has(n)); // now authed -- exception is stale
    });

    if (stale.length > 0) {
      const details = stale
        .map((e) => `  ${e.method.toUpperCase()} ${e.path} -- ${e.reason}`)
        .join('\n');
      throw new Error(
        `Stale entries in domain/routeAuthExceptions.js (route no longer exists, or now has ` +
        `auth middleware -- remove the exception):\n${details}`
      );
    }
  });
});
