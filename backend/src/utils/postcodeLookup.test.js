const { lookupPostcode, bulkLookupPostcodes } = require('./postcodeLookup');

describe('lookupPostcode', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  test('returns the nearest postcode on a successful lookup', async () => {
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({ result: [{ postcode: 'SW1A 1AA' }] }),
    }));
    expect(await lookupPostcode(51.5, -0.12)).toBe('SW1A 1AA');
  });

  test('returns null (not a throw) when postcodes.io has nothing nearby', async () => {
    global.fetch = jest.fn(async () => ({ ok: true, json: async () => ({ result: null }) }));
    expect(await lookupPostcode(0, 0)).toBeNull();
  });

  test('returns null (not a throw) on a non-ok response', async () => {
    global.fetch = jest.fn(async () => ({ ok: false }));
    expect(await lookupPostcode(51.5, -0.12)).toBeNull();
  });

  test('returns null (not a throw) when the network call itself fails', async () => {
    global.fetch = jest.fn(async () => { throw new Error('network down'); });
    expect(await lookupPostcode(51.5, -0.12)).toBeNull();
  });
});

describe('bulkLookupPostcodes', () => {
  const originalFetch = global.fetch;
  afterEach(() => { global.fetch = originalFetch; });

  test('maps each point id to its resolved postcode, preserving request order', async () => {
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({
        result: [
          { query: {}, result: [{ postcode: 'SW1A 1AA' }] },
          { query: {}, result: [{ postcode: 'E1 6AN' }] },
        ],
      }),
    }));
    const points = [
      { id: 1, latitude: 51.5, longitude: -0.12 },
      { id: 2, latitude: 51.52, longitude: -0.06 },
    ];
    const result = await bulkLookupPostcodes(points);
    expect(result.get(1)).toBe('SW1A 1AA');
    expect(result.get(2)).toBe('E1 6AN');
  });

  test('maps a point with no resolvable postcode to null without dropping other points', async () => {
    global.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({
        result: [
          { query: {}, result: [{ postcode: 'SW1A 1AA' }] },
          { query: {}, result: null },
        ],
      }),
    }));
    const points = [
      { id: 1, latitude: 51.5, longitude: -0.12 },
      { id: 2, latitude: 0, longitude: 0 },
    ];
    const result = await bulkLookupPostcodes(points);
    expect(result.get(1)).toBe('SW1A 1AA');
    expect(result.get(2)).toBeNull();
  });

  test('chunks a batch over 100 points into multiple requests', async () => {
    global.fetch = jest.fn(async (url, opts) => {
      const body = JSON.parse(opts.body);
      return {
        ok: true,
        json: async () => ({
          result: body.geolocations.map(() => ({ query: {}, result: [{ postcode: 'X1 1XX' }] })),
        }),
      };
    });
    const points = Array.from({ length: 150 }, (_, i) => ({ id: i, latitude: 51.5, longitude: -0.12 }));
    const result = await bulkLookupPostcodes(points);

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(result.size).toBe(150);
    expect(result.get(149)).toBe('X1 1XX');
  });

  test('a whole failed batch maps every point in it to null instead of throwing', async () => {
    global.fetch = jest.fn(async () => { throw new Error('network down'); });
    const points = [{ id: 1, latitude: 51.5, longitude: -0.12 }];
    const result = await bulkLookupPostcodes(points);
    expect(result.get(1)).toBeNull();
  });
});
