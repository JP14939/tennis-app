import { StyleSheet } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';

// Upper-body-only skeleton -- matches the 9 KEY_LANDMARKS the whole pipeline
// already scores against (compare_swing.py / build_pro_database.py); legs
// were never tracked anywhere in this app.
const BONES = [
  ['left_shoulder', 'right_shoulder'],
  ['left_shoulder', 'left_elbow'],
  ['left_elbow', 'left_wrist'],
  ['right_shoulder', 'right_elbow'],
  ['right_elbow', 'right_wrist'],
  ['left_shoulder', 'left_hip'],
  ['right_shoulder', 'right_hip'],
  ['left_hip', 'right_hip'],
];

// trajectory: [{ t: seconds (this video's own playback timeline), landmarks: { name: {x,y}|null } }]
// currentTimeSec: this pane's own video playhead position, in seconds.
function interpolatedLandmarks(trajectory, currentTimeSec) {
  if (!trajectory || trajectory.length === 0) return null;

  if (currentTimeSec <= trajectory[0].t) return trajectory[0].landmarks;
  if (currentTimeSec >= trajectory[trajectory.length - 1].t) return trajectory[trajectory.length - 1].landmarks;

  let lo = trajectory[0];
  let hi = trajectory[trajectory.length - 1];
  for (let i = 0; i < trajectory.length - 1; i++) {
    if (trajectory[i].t <= currentTimeSec && trajectory[i + 1].t >= currentTimeSec) {
      lo = trajectory[i];
      hi = trajectory[i + 1];
      break;
    }
  }

  const span = hi.t - lo.t;
  const frac = span > 0 ? (currentTimeSec - lo.t) / span : 0;

  const landmarks = {};
  for (const name of Object.keys(lo.landmarks)) {
    const a = lo.landmarks[name];
    const b = hi.landmarks[name];
    // Only interpolate when both bracketing samples saw this joint --
    // otherwise show nothing for it rather than guess through an occlusion.
    landmarks[name] = (a && b)
      ? { x: a.x + (b.x - a.x) * frac, y: a.y + (b.y - a.y) * frac }
      : null;
  }
  return landmarks;
}

export default function SkeletonOverlay({ trajectory, currentTimeSec, width, height, color }) {
  if (!trajectory || trajectory.length === 0 || !width || !height) return null;

  const landmarks = interpolatedLandmarks(trajectory, currentTimeSec ?? 0);
  if (!landmarks) return null;

  const px = (lm) => ({ x: lm.x * width, y: lm.y * height });

  return (
    <Svg style={StyleSheet.absoluteFill} width={width} height={height} pointerEvents="none">
      {BONES.map(([a, b], i) => {
        const la = landmarks[a];
        const lb = landmarks[b];
        if (!la || !lb) return null;
        const pa = px(la);
        const pb = px(lb);
        return (
          <Line
            key={i}
            x1={pa.x} y1={pa.y} x2={pb.x} y2={pb.y}
            stroke={color} strokeWidth={3} strokeLinecap="round" opacity={0.85}
          />
        );
      })}
      {Object.entries(landmarks).map(([name, lm]) => {
        if (!lm) return null;
        const p = px(lm);
        return <Circle key={name} cx={p.x} cy={p.y} r={5} fill={color} opacity={0.95} />;
      })}
    </Svg>
  );
}
