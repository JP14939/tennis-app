import { memo, useMemo } from 'react';
import { StyleSheet } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';

// trajectory: [{ t: seconds, point: {x,y} | null }]
// Same conventions as RacketPathOverlay: draw the whole traced arc (faint at
// the start of the window, bright approaching contact), a gap in detection
// just breaks the trail there, and a linearly-interpolated dot marks the
// current playhead position. The backend already Kalman-bridges brief
// occlusion and fills short gaps, so an interior break here means a genuine
// sustained tracking loss, not a one-frame miss.
function interpolatePoint(trajectory, currentTimeSec) {
  if (!trajectory || trajectory.length === 0) return null;
  if (currentTimeSec <= trajectory[0].t) return trajectory[0].point;
  if (currentTimeSec >= trajectory[trajectory.length - 1].t) return trajectory[trajectory.length - 1].point;

  let lo = trajectory[0];
  let hi = trajectory[trajectory.length - 1];
  for (let i = 0; i < trajectory.length - 1; i++) {
    if (trajectory[i].t <= currentTimeSec && trajectory[i + 1].t >= currentTimeSec) {
      lo = trajectory[i];
      hi = trajectory[i + 1];
      break;
    }
  }
  const a = lo.point;
  const b = hi.point;
  if (!a || !b) return a || b || null;

  const span = hi.t - lo.t;
  const frac = span > 0 ? (currentTimeSec - lo.t) / span : 0;
  return { x: a.x + (b.x - a.x) * frac, y: a.y + (b.y - a.y) * frac };
}

function BallPathOverlay({ trajectory, currentTimeSec, width, height, color }) {
  const segments = useMemo(() => {
    if (!trajectory || trajectory.length === 0) return [];
    const built = [];
    for (let i = 0; i < trajectory.length - 1; i++) {
      const a = trajectory[i].point;
      const b = trajectory[i + 1].point;
      if (a && b) built.push({ a, b, idx: i });
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
        const opacity = 0.12 + 0.5 * (idx / Math.max(1, segments.length - 1));
        return (
          <Line
            key={idx}
            x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
            stroke={color} strokeWidth={2} strokeLinecap="round" opacity={opacity}
          />
        );
      })}
      {currentPx && (
        <Circle cx={currentPx.x} cy={currentPx.y} r={5} fill={color} opacity={0.95} stroke="#fff" strokeWidth={1} />
      )}
    </Svg>
  );
}

export default memo(BallPathOverlay);
