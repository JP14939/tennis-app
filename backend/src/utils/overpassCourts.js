// Shared OpenStreetMap Overpass fetch-and-upsert logic used both by the
// one-off `scripts/seedCourts.js` CLI and by the self-healing lazy-seed path
// in `routes/courts.js` (GET /courts seeds an area on first empty query).
const db = require('../db');

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

function boundingBox(lat, lng, radiusKm) {
  const latDelta = radiusKm / 111;
  const lngDelta = radiusKm / (111 * Math.cos((lat * Math.PI) / 180) || 1);
  return {
    south: lat - latDelta, north: lat + latDelta,
    west: lng - lngDelta, east: lng + lngDelta,
  };
}

function elementLatLng(el) {
  if (el.type === 'node') return { latitude: el.lat, longitude: el.lon };
  if (el.center) return { latitude: el.center.lat, longitude: el.center.lon };
  return null;
}

async function fetchCourtsFromOverpass(bbox) {
  const { south, west, north, east } = bbox;
  const query = `
    [out:json][timeout:25];
    (
      nwr["sport"="tennis"](${south},${west},${north},${east});
    );
    out center tags;
  `;
  // Overpass 406s requests without an explicit Accept/User-Agent -- Node's
  // default fetch headers aren't enough.
  const res = await fetch(OVERPASS_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'text/plain',
      'Accept': 'application/json',
      'User-Agent': 'RallyMax-Tennis-App/1.0',
    },
    body: query,
  });
  if (!res.ok) {
    throw new Error(`Overpass API returned ${res.status}`);
  }
  const data = await res.json();
  return data.elements ?? [];
}

function upsertElements(elements) {
  const upsert = db.prepare(`
    INSERT INTO courts (name, latitude, longitude, source, osm_id)
    VALUES (?, ?, ?, 'osm', ?)
    ON CONFLICT(osm_id) DO UPDATE SET name = excluded.name, latitude = excluded.latitude, longitude = excluded.longitude
  `);

  let inserted = 0;
  for (const el of elements) {
    const coords = elementLatLng(el);
    if (!coords) continue;
    const osmId = `${el.type}/${el.id}`;
    const name = el.tags?.name || 'Tennis Court';
    upsert.run(name, coords.latitude, coords.longitude, osmId);
    inserted += 1;
  }
  return inserted;
}

async function seedCourtsNear(lat, lng, radiusKm) {
  const elements = await fetchCourtsFromOverpass(boundingBox(lat, lng, radiusKm));
  return upsertElements(elements);
}

// Whole-country bulk seed, used once (not on the request path -- this is a
// single heavy Overpass query, unlike seedCourtsNear's small per-area boxes
// used by the lazy self-heal path). Named-area query instead of tiling many
// bounding boxes: Overpass resolves "England" to its real administrative
// boundary polygon, so this doesn't miss coastal/border courts the way a
// bounding box covering the same area would, and it's one request instead
// of dozens. Longer timeout than the per-area query -- a whole-country
// result set is large and Overpass's default 25s budget isn't enough.
async function fetchCourtsInNamedArea(areaName) {
  const query = `
    [out:json][timeout:180];
    area["name"="${areaName}"]["boundary"="administrative"]->.searchArea;
    (
      nwr["sport"="tennis"](area.searchArea);
    );
    out center tags;
  `;
  const res = await fetch(OVERPASS_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'text/plain',
      'Accept': 'application/json',
      'User-Agent': 'RallyMax-Tennis-App/1.0',
    },
    body: query,
  });
  if (!res.ok) {
    throw new Error(`Overpass API returned ${res.status}`);
  }
  const data = await res.json();
  return data.elements ?? [];
}

async function seedCourtsInArea(areaName) {
  const elements = await fetchCourtsInNamedArea(areaName);
  return upsertElements(elements);
}

module.exports = { seedCourtsNear, seedCourtsInArea };
