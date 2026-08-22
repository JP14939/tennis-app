import { memo, useMemo } from 'react';
import { StyleSheet } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';

// Prefer the string-bed 'tip' point (where contact actually happens) for
// tracing the swing path; fall back to points closer to the hand when tip
// wasn't detected on a given frame, same fallback order verify_shot_contact.py
// already uses for contact-frame checking.
const FALLBACK_ORDER = ['tip', 'throat', 'handle'];

function pointFor(points) {
  for (const name of FALLBACK_ORDER) {
    const p = points?.[name];
    if (p) return p;
  }
  return null;
}

// trajectory: [{ t: seconds, points: { tip: {x,y}|null, ... } }]
function interpolatePoint(trajectory, currentTimeSec) {
  if (!trajectory || trajectory.length === 0) return null;

  if (currentTimeSec <= trajectory[0].t) return pointFor(trajectory[0].points);
  if (currentTimeSec >= trajectory[trajectory.length - 1].t) return pointFor(trajectory[trajectory.length - 1].points);

  let lo = trajectory[0];
  let hi = trajectory[trajectory.length - 1];
  for (let i = 0; i < trajectory.length - 1; i++) {
    if (trajectory[i].t <= currentTimeSec && trajectory[i + 1].t >= currentTimeSec) {
      lo = trajectory[i];
      hi = trajectory[i + 1];
      break;
    }
  }

  const a = pointFor(lo.points);
  const b = pointFor(hi.points);
  if (!a || !b) return a || b || null;

  const span = hi.t - lo.t;
  const frac = span > 0 ? (currentTimeSec - lo.t) / span : 0;
  return { x: a.x + (b.x - a.x) * frac, y: a.y + (b.y - a.y) * frac };
}

function RacketPathOverlay({ trajectory, currentTimeSec, width, height, color }) {
  // Draw the whole swing's path (not just the current scrub position) --
  // that's the point of a "path", the arc the racket traced through the
  // whole window. Segments fade from faint (start of the window) to bright
  // (approaching contact/end) so it reads as a directional trail, and a gap
  // in detection just breaks the trail there rather than interpolating
  // through it (would draw a fake straight line across a tracking loss).
  //
  // Keyed on `trajectory` alone, deliberately not on currentTimeSec: the path
  // is fixed for the whole clip, so rebuilding it on every playback status
  // tick (20Hz on native, once per animation frame on web) was pure waste --
  // only the moving dot below actually changes as the playhead moves.
  const segments = useMemo(() => {
    if (!trajectory || trajectory.length === 0) return [];
    const points = trajectory.map((f) => pointFor(f.points));
    const built = [];
    for (let i = 0; i < points.length - 1; i++) {
      if (points[i] && points[i + 1]) built.push({ a: points[i], b: points[i + 1], idx: i });
    }
    return built;
  }, [trajectory]);

  if (!trajectory || trajectory.length === 0 || !width || !height) return null;

  const px = (p) => ({ x: p.x * width, y: p.y * height });

  const currentPoint = interpolatePoint(trajectory, currentTimeSec ?? 0);
  const currentPx = currentPoint ? px(currentPoint) : null;

  return (
    <Svg style={StyleSheet.absoluteFill} width={width} height={height} pointerEvents="none">
      {segments.map(({ a, b, idx }) => {
        const pa = px(a);
        const pb = px(b);
        const opacity = 0.15 + 0.55 * (idx / Math.max(1, segments.length - 1));
        return (
          <Line
            key={idx}
            x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
            stroke={color} strokeWidth={2.5} strokeLinecap="round" opacity={opacity}
          />
        );
      })}
      {currentPx && (
        <Circle cx={currentPx.x} cy={currentPx.y} r={6} fill={color} opacity={0.95} stroke="#fff" strokeWidth={1.5} />
      )}
    </Svg>
  );
}

export default memo(RacketPathOverlay);
