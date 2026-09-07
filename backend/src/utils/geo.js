// Shared geo math -- previously three near-identical copies existed
// (routes/courts.js, scripts/clusterCourts.js, utils/overpassCourts.js),
// each hand-rolling the same haversine distance and lat/lng bounding-box
// formulas. Consolidated here so a future fix (or precision change) lands
// in one place instead of three.
const EARTH_RADIUS_KM = 6371;

function haversineKm(lat1, lng1, lat2, lng2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return EARTH_RADIUS_KM * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Degree-delta box, not exact -- longitude delta widens/shrinks with
// latitude (a degree of longitude is shorter near the poles), so this box
// is intentionally a bit generous rather than exact. Callers that need an
// exact radius filter the candidates further with haversineKm.
function boundingBox(lat, lng, radiusKm) {
  const latDelta = radiusKm / 111;
  const lngDelta = radiusKm / (111 * Math.cos((lat * Math.PI) / 180) || 1);
  return {
    south: lat - latDelta, north: lat + latDelta,
    west: lng - lngDelta, east: lng + lngDelta,
  };
}

module.exports = { EARTH_RADIUS_KM, haversineKm, boundingBox };
