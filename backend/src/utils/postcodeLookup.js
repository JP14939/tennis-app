// Free, no-API-key UK postcode reverse-geocoding via postcodes.io
// (https://postcodes.io) -- chosen over a paid provider (Google Geocoding)
// specifically to avoid billing setup for a best-effort display field.
// UK-only, which matches this app's current data (OSM courts seeded so far
// are UK-focused, DEFAULT_REGION in FindGamesScreen is London).
const POSTCODES_IO_URL = 'https://api.postcodes.io/postcodes';

// postcodes.io's own bulk-endpoint limit -- a single POST accepts at most
// 100 geolocations, so a larger batch has to be chunked into multiple calls.
const BULK_CHUNK_SIZE = 100;

function chunk(arr, size) {
  const out = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

// Best-effort, single point -- used on the interactive write paths (a user
// dropping a court pin or creating an area watch) where a small extra
// network round trip is acceptable and the result is wanted immediately.
// Returns null (never throws) on any failure: a missing postcode is a
// cosmetic gap, not a reason to fail the write that triggered this lookup.
async function lookupPostcode(latitude, longitude) {
  try {
    const params = new URLSearchParams({ lon: longitude, lat: latitude, limit: '1' });
    const res = await fetch(`${POSTCODES_IO_URL}?${params}`);
    if (!res.ok) return null;
    const data = await res.json();
    return data.result?.[0]?.postcode ?? null;
  } catch (err) {
    console.error('[postcodeLookup] single lookup failed:', err.message);
    return null;
  }
}

// Bulk reverse geocode for an offline backfill (thousands of existing
// courts/clubs) -- one HTTP round trip per 100 points instead of one per
// point. `points` is [{id, latitude, longitude}]; returns a Map of
// id -> postcode|null (null for a point postcodes.io couldn't resolve, e.g.
// somewhere with no UK postcode nearby, or the fetch failing outright).
async function bulkLookupPostcodes(points) {
  const results = new Map();
  for (const batch of chunk(points, BULK_CHUNK_SIZE)) {
    try {
      const res = await fetch(POSTCODES_IO_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          geolocations: batch.map((p) => ({ longitude: p.longitude, latitude: p.latitude, limit: 1 })),
        }),
      });
      if (!res.ok) {
        for (const p of batch) results.set(p.id, null);
        continue;
      }
      const data = await res.json();
      // postcodes.io returns results in the same order as the request.
      batch.forEach((p, i) => {
        results.set(p.id, data.result?.[i]?.result?.[0]?.postcode ?? null);
      });
    } catch (err) {
      console.error('[postcodeLookup] bulk lookup failed for a batch:', err.message);
      for (const p of batch) results.set(p.id, null);
    }
  }
  return results;
}

module.exports = { lookupPostcode, bulkLookupPostcodes };
