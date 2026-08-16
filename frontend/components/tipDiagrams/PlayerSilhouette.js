import { Circle, Line, Path } from 'react-native-svg';
import { LANDMARK_POINTS } from './landmarks';

const STROKE = '#c9c5b8';
const STROKE_WIDTH = 4;

// A plain, front-facing "ready position" figure -- deliberately generic
// (not a specific swing phase/shot pose, see tipVisuals.js's header comment
// for why) so it's one reusable base for all 30 tips rather than needing a
// distinct illustration per shot-type/phase combination.
export default function PlayerSilhouette() {
  const p = LANDMARK_POINTS;
  return (
    <>
      {/* head */}
      <Circle cx={p.nose.x} cy={p.nose.y + 8} r={20} stroke={STROKE} strokeWidth={STROKE_WIDTH} fill="none" />
      {/* torso */}
      <Line x1={100} y1={58} x2={100} y2={175} stroke={STROKE} strokeWidth={STROKE_WIDTH} />
      {/* shoulder line */}
      <Line x1={p.left_shoulder.x} y1={p.left_shoulder.y} x2={p.right_shoulder.x} y2={p.right_shoulder.y}
        stroke={STROKE} strokeWidth={STROKE_WIDTH} />
      {/* hip line */}
      <Line x1={p.left_hip.x} y1={p.left_hip.y} x2={p.right_hip.x} y2={p.right_hip.y}
        stroke={STROKE} strokeWidth={STROKE_WIDTH} />
      {/* left arm */}
      <Path
        d={`M ${p.left_shoulder.x} ${p.left_shoulder.y} L ${p.left_elbow.x} ${p.left_elbow.y} L ${p.left_wrist.x} ${p.left_wrist.y}`}
        stroke={STROKE} strokeWidth={STROKE_WIDTH} fill="none" strokeLinecap="round" strokeLinejoin="round"
      />
      {/* right arm (racket arm) */}
      <Path
        d={`M ${p.right_shoulder.x} ${p.right_shoulder.y} L ${p.right_elbow.x} ${p.right_elbow.y} L ${p.right_wrist.x} ${p.right_wrist.y}`}
        stroke={STROKE} strokeWidth={STROKE_WIDTH} fill="none" strokeLinecap="round" strokeLinejoin="round"
      />
      {/* legs */}
      <Path d={`M ${p.left_hip.x} ${p.left_hip.y} L 85 220 L 80 270`}
        stroke={STROKE} strokeWidth={STROKE_WIDTH} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Path d={`M ${p.right_hip.x} ${p.right_hip.y} L 115 220 L 120 270`}
        stroke={STROKE} strokeWidth={STROKE_WIDTH} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </>
  );
}
