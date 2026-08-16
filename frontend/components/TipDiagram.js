import { View, Image, StyleSheet } from 'react-native';
import Svg, { Circle, Line, Path, Polygon } from 'react-native-svg';
import PlayerSilhouette from './tipDiagrams/PlayerSilhouette';
import { LANDMARK_POINTS, TORSO_CENTER, SHOULDER_LINE, HIP_LINE, RACKET_TIP, VIEWBOX } from './tipDiagrams/landmarks';
import { TIP_VISUALS } from './tipDiagrams/tipVisuals';
import { TIP_PHOTOS } from './tipDiagrams/tipPhotos';
import { colors } from '../theme';

const ACCENT = colors.coral;

function unitVector(dx, dy) {
  const len = Math.hypot(dx, dy) || 1;
  return { dx: dx / len, dy: dy / len };
}

// 'in'/'out' are relative to the torso center; 'up'/'down' are fixed screen
// directions -- covers every direction used in tipVisuals.js.
function directionVector(point, direction) {
  if (direction === 'up') return { dx: 0, dy: -1 };
  if (direction === 'down') return { dx: 0, dy: 1 };
  const out = unitVector(point.x - TORSO_CENTER.x, point.y - TORSO_CENTER.y);
  return direction === 'out' ? out : { dx: -out.dx, dy: -out.dy };
}

function Arrow({ point, direction, color = ACCENT, length = 26 }) {
  const v = directionVector(point, direction);
  const startX = point.x + v.dx * 10;
  const startY = point.y + v.dy * 10;
  const tipX = point.x + v.dx * (10 + length);
  const tipY = point.y + v.dy * (10 + length);
  const headLen = 8, headWidth = 6;
  const backX = tipX - v.dx * headLen;
  const backY = tipY - v.dy * headLen;
  const px = -v.dy, py = v.dx; // perpendicular
  return (
    <>
      <Line x1={startX} y1={startY} x2={backX} y2={backY} stroke={color} strokeWidth={4} strokeLinecap="round" />
      <Polygon
        points={`${tipX},${tipY} ${backX + px * headWidth},${backY + py * headWidth} ${backX - px * headWidth},${backY - py * headWidth}`}
        fill={color}
      />
    </>
  );
}

// A partial dashed ring around a center point -- stands in for "rotate /
// snap this" without the complexity of a precise arrowhead-on-a-curve.
function RotateArc({ center, radius, color = ACCENT }) {
  const start = -40 * (Math.PI / 180);
  const end = 210 * (Math.PI / 180);
  const sx = center.x + radius * Math.cos(start);
  const sy = center.y + radius * Math.sin(start);
  const ex = center.x + radius * Math.cos(end);
  const ey = center.y + radius * Math.sin(end);
  return (
    <Path
      d={`M ${sx} ${sy} A ${radius} ${radius} 0 1 1 ${ex} ${ey}`}
      stroke={color} strokeWidth={4} fill="none" strokeLinecap="round" strokeDasharray="3,7"
    />
  );
}

function PointVisual({ landmark, direction }) {
  const point = LANDMARK_POINTS[landmark];
  return (
    <>
      <Circle cx={point.x} cy={point.y} r={10} fill={ACCENT} fillOpacity={0.25} stroke={ACCENT} strokeWidth={3} />
      <Arrow point={point} direction={direction} />
    </>
  );
}

function RotateVisual({ landmark }) {
  const point = LANDMARK_POINTS[landmark];
  return (
    <>
      <Circle cx={point.x} cy={point.y} r={8} fill={ACCENT} fillOpacity={0.25} stroke={ACCENT} strokeWidth={3} />
      <RotateArc center={point} radius={18} />
    </>
  );
}

function SeparationVisual() {
  return (
    <>
      <Line x1={SHOULDER_LINE.from.x} y1={SHOULDER_LINE.from.y} x2={SHOULDER_LINE.to.x} y2={SHOULDER_LINE.to.y}
        stroke={ACCENT} strokeWidth={5} />
      <Line x1={HIP_LINE.from.x} y1={HIP_LINE.from.y} x2={HIP_LINE.to.x} y2={HIP_LINE.to.y}
        stroke={ACCENT} strokeWidth={5} />
      <RotateArc center={TORSO_CENTER} radius={34} />
    </>
  );
}

function ExtensionVisual() {
  const wrist = LANDMARK_POINTS.right_wrist;
  return (
    <>
      <Line x1={wrist.x} y1={wrist.y} x2={RACKET_TIP.x} y2={RACKET_TIP.y} stroke={ACCENT} strokeWidth={5} strokeLinecap="round" />
      <Circle cx={RACKET_TIP.x} cy={RACKET_TIP.y} r={12} stroke={ACCENT} strokeWidth={3} fill="none" />
      <Line x1={TORSO_CENTER.x} y1={TORSO_CENTER.y} x2={wrist.x} y2={wrist.y}
        stroke={ACCENT} strokeWidth={2.5} strokeDasharray="4,5" strokeOpacity={0.6} />
      <Arrow point={RACKET_TIP} direction="out" length={16} />
    </>
  );
}

function Visual({ visual }) {
  if (!visual) return null;
  switch (visual.type) {
    case 'point': return <PointVisual landmark={visual.landmark} direction={visual.direction} />;
    case 'rotate': return <RotateVisual landmark={visual.landmark} />;
    case 'separation': return <SeparationVisual />;
    case 'extension': return <ExtensionVisual />;
    default: return null;
  }
}

// Renders a small illustrative visual for a coaching tip -- a real photo
// when one has been added to tipPhotos.js, otherwise the SVG diagram (see
// tipDiagrams/tipVisuals.js for the id -> visual mapping and
// tipDiagrams/landmarks.js for the shared figure geometry). Returns null for
// any tip id with neither (e.g. the "great technique!" fallback tip has no
// id) so callers don't need to guard against a missing entry themselves.
export default function TipDiagram({ tipId }) {
  const photo = TIP_PHOTOS[tipId];
  if (photo) {
    return (
      <View style={s.wrap}>
        <Image source={photo} style={s.photo} resizeMode="cover" />
      </View>
    );
  }

  const visual = TIP_VISUALS[tipId];
  if (!visual) return null;

  return (
    <View style={s.wrap}>
      <Svg width={120} height={180} viewBox={VIEWBOX}>
        <PlayerSilhouette />
        <Visual visual={visual} />
      </Svg>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { alignItems: 'center', justifyContent: 'center', paddingVertical: 4 },
  photo: { width: 220, height: 160, borderRadius: 12 },
});
