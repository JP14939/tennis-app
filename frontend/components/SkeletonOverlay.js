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

// Catmull-Rom spline through 4 points (p0..p3), evaluated at t in [0,1]
// between p1 and p2 -- unlike a straight lerp, this curves through the
// samples using the neighbors on either side to estimate tangents, so a
// fast, curving arm path (racket swings, especially pros' faster ones)
// doesn't get visibly "cut across" between two sparse pose samples.
function catmullRom(p0, p1, p2, p3, t) {
  const t2 = t * t;
  const t3 = t2 * t;
  return (
    0.5 * (
      (2 * p1) +
      (-p0 + p2) * t +
      (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
      (-p0 + 3 * p1 - 3 * p2 + p3) * t3
    )
  );
}

// Walks outward from startIdx in `step` direction (-1 or +1), returning the
// first index whose landmarks[jointName] is non-null, or -1 if none exists
// anywhere in that direction. MediaPipe frequently loses confidence on a
// fast-moving joint (motion blur, most common right around/after contact --
// exactly the moment this overlay matters most) for several consecutive
// sparse samples in a row, not just one -- a real trajectory checked
// directly had right_wrist null in 8 of 9 samples across the 0.55s-0.95s
// post-contact window. Only ever checking the immediately-adjacent sample
// (the previous version of this function) meant the joint would vanish for
// that entire stretch instead of bridging across the gap.
function findNearestValid(trajectory, startIdx, jointName, step) {
  for (let i = startIdx; i >= 0 && i < trajectory.length; i += step) {
    if (trajectory[i].landmarks[jointName]) return i;
  }
  return -1;
}

// trajectory: [{ t: seconds (this video's own playback timeline), landmarks: { name: {x,y}|null } }]
// currentTimeSec: this pane's own video playhead position, in seconds.
function interpolatedLandmarks(trajectory, currentTimeSec) {
  if (!trajectory || trajectory.length === 0) return null;

  if (currentTimeSec <= trajectory[0].t) return trajectory[0].landmarks;
  if (currentTimeSec >= trajectory[trajectory.length - 1].t) return trajectory[trajectory.length - 1].landmarks;

  let loIdx = 0;
  for (let i = 0; i < trajectory.length - 1; i++) {
    if (trajectory[i].t <= currentTimeSec && trajectory[i + 1].t >= currentTimeSec) {
      loIdx = i;
      break;
    }
  }

  // Per-joint, not per-sample: each joint independently finds its own
  // nearest valid sample on either side of currentTimeSec, skipping over
  // any null gap rather than requiring the immediately-bracketing pair
  // (loIdx/loIdx+1) to both happen to have this joint. Keeps a joint drawn
  // continuously through a motion-blur gap instead of vanishing and
  // snapping back once real data resumes.
  const jointNames = Object.keys(trajectory[loIdx].landmarks);
  const landmarks = {};
  for (const name of jointNames) {
    const beforeIdx = findNearestValid(trajectory, loIdx, name, -1);
    const afterIdx = findNearestValid(trajectory, loIdx + 1, name, 1);
    if (beforeIdx === -1 || afterIdx === -1) {
      // No valid sample at all on one side -- genuinely no data to bridge
      // to (e.g. right at a trajectory edge), not a temporary gap.
      landmarks[name] = null;
      continue;
    }
    const before = trajectory[beforeIdx];
    const after = trajectory[afterIdx];
    const p1 = before.landmarks[name];
    const p2 = after.landmarks[name];
    const span = after.t - before.t;
    const frac = span > 0 ? (currentTimeSec - before.t) / span : 0;

    // One more valid sample beyond each side (found the same skip-nulls
    // way) lets the Catmull-Rom curve shape the path through this segment;
    // otherwise a plain lerp between the two real points still bridges the
    // gap correctly, just without the extra curve refinement.
    const beforeOuterIdx = beforeIdx > 0 ? findNearestValid(trajectory, beforeIdx - 1, name, -1) : -1;
    const afterOuterIdx = afterIdx < trajectory.length - 1 ? findNearestValid(trajectory, afterIdx + 1, name, 1) : -1;
    const p0 = beforeOuterIdx !== -1 ? trajectory[beforeOuterIdx].landmarks[name] : null;
    const p3 = afterOuterIdx !== -1 ? trajectory[afterOuterIdx].landmarks[name] : null;

    landmarks[name] = (p0 && p3)
      ? { x: catmullRom(p0.x, p1.x, p2.x, p3.x, frac), y: catmullRom(p0.y, p1.y, p2.y, p3.y, frac) }
      : { x: p1.x + (p2.x - p1.x) * frac, y: p1.y + (p2.y - p1.y) * frac };
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
