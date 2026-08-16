// Small line-icon set ported 1:1 (same path data / viewBoxes) from the
// redesign mockup's inline SVGs. Each takes {size, color, strokeWidth}.
import Svg, { Path, Circle, Rect } from 'react-native-svg';

export function HomeIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M3 9.5L10 3l7 6.5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M5 8.5V17h10V8.5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinejoin="round" />
    </Svg>
  );
}

export function HistoryIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Circle cx={10} cy={10} r={7} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Path d="M10 6v4l3 2" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" />
    </Svg>
  );
}

export function PremiumIcon({ size = 20, color = '#000', strokeWidth = 1.4, filled = false }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path
        d="M10 2l2.2 5.8L18 10l-5.8 2.2L10 18l-2.2-5.8L2 10l5.8-2.2z"
        stroke={filled ? 'none' : color}
        strokeWidth={strokeWidth}
        fill={filled ? color : 'none'}
        strokeLinejoin="round"
      />
    </Svg>
  );
}

export function ProfileIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Circle cx={10} cy={7} r={3.4} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Path d="M3.5 17c1.3-3.5 4-5 6.5-5s5.2 1.5 6.5 5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" />
    </Svg>
  );
}

export function FriendsIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Circle cx={7} cy={6.5} r={2.6} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Path d="M2 16c0.8-2.8 2.6-4.2 5-4.2s4.2 1.4 5 4.2" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" />
      <Circle cx={14.5} cy={7.5} r={2.1} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Path d="M12.8 12.2c1.9-0.5 3.7 0.6 4.5 3" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" />
    </Svg>
  );
}

export function LeaderboardIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Rect x={3} y={11} width={4} height={6} rx={1} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Rect x={8} y={6} width={4} height={11} rx={1} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Rect x={13} y={3} width={4} height={14} rx={1} stroke={color} strokeWidth={strokeWidth} fill="none" />
    </Svg>
  );
}

export function MapPinIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M10 18s6-6.2 6-10.8A6 6 0 0 0 4 7.2C4 11.8 10 18 10 18z" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinejoin="round" />
      <Circle cx={10} cy={7.2} r={2.1} stroke={color} strokeWidth={strokeWidth} fill="none" />
    </Svg>
  );
}

export function MessageIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M3 4.5h14a1 1 0 0 1 1 1V13a1 1 0 0 1-1 1H8l-4 3v-3H3a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1z" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinejoin="round" />
    </Svg>
  );
}

export function BackChevronIcon({ size = 14, color = '#000', strokeWidth = 1.8 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 14 14">
      <Path d="M9 2L3 7l6 5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ChevronRightIcon({ size = 7, color = '#000', strokeWidth = 1.5 }) {
  return (
    <Svg width={size} height={size * (12 / 7)} viewBox="0 0 7 12">
      <Path d="M1 1l5 5-5 5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function ChevronDownIcon({ size = 14, color = '#000', strokeWidth = 1.8 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 14 14">
      <Path d="M3 5l4 4 4-4" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function TennisBallIcon({ size = 15, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 15 15">
      <Circle cx={7.5} cy={7.5} r={6.3} fill="none" stroke={color} strokeWidth={1.6} />
      <Path d="M2.5 4.5c3 2.5 7 2.5 10 0M2.5 10.5c3-2.5 7-2.5 10 0" stroke={color} strokeWidth={1.3} fill="none" />
    </Svg>
  );
}

export function PlusIcon({ size = 13, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 13 13">
      <Path d="M6.5 1v11M1 6.5h11" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}

export function VideoIcon({ size = 22, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 22 22">
      <Rect x={2} y={6} width={14} height={10} rx={2} stroke={color} strokeWidth={1.6} fill="none" />
      <Path d="M16 9.5l4-2.5v8l-4-2.5" stroke={color} strokeWidth={1.6} fill="none" strokeLinejoin="round" />
    </Svg>
  );
}

export function CameraIcon({ size = 22, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 22 22">
      <Circle cx={11} cy={11} r={8} stroke={color} strokeWidth={1.6} fill="none" />
      <Circle cx={11} cy={11} r={3.2} fill={color} />
    </Svg>
  );
}

export function CheckIcon({ size = 14, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 14 14">
      <Path d="M2 7l3.5 3.5L12 3" stroke={color} strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function SwapIcon({ size = 20, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M4 4l6 6-6 6M16 4l-6 6 6 6" stroke={color} strokeWidth={1.8} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function FilmIcon({ size = 20, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Rect x={2} y={4} width={16} height={12} rx={2} stroke={color} strokeWidth={1.6} fill="none" />
      <Path d="M8 8l5 2.5-5 2.5z" fill={color} />
    </Svg>
  );
}

export function LockIcon({ size = 13, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 13 13">
      <Rect x={2} y={5.5} width={9} height={6} rx={1.3} stroke={color} strokeWidth={1.3} fill="none" />
      <Path d="M4.5 5.5V3.8a2 2 0 0 1 4 0V5.5" stroke={color} strokeWidth={1.3} fill="none" />
    </Svg>
  );
}

export function SettingsIcon({ size = 15, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Circle cx={10} cy={10} r={2.6} stroke={color} strokeWidth={1.5} fill="none" />
      <Path
        d="M10 3v2M10 15v2M3 10h2M15 10h2M5.5 5.5l1.4 1.4M13.1 13.1l1.4 1.4M14.5 5.5l-1.4 1.4M6.9 13.1l-1.4 1.4"
        stroke={color}
        strokeWidth={1.4}
        strokeLinecap="round"
      />
    </Svg>
  );
}

export function HelpIcon({ size = 15, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Circle cx={10} cy={10} r={7.5} stroke={color} strokeWidth={1.5} fill="none" />
      <Path d="M7.8 7.8a2.2 2.2 0 1 1 3.2 2c-.9.6-1 1-1 2" stroke={color} strokeWidth={1.4} fill="none" strokeLinecap="round" />
      <Circle cx={10} cy={14.3} r={0.9} fill={color} />
    </Svg>
  );
}

export function ShareIcon({ size = 18, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M10 13V3M10 3L6.5 6.5M10 3l3.5 3.5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M4 10v5.5a1.5 1.5 0 001.5 1.5h9a1.5 1.5 0 001.5-1.5V10" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </Svg>
  );
}

export function DrillsIcon({ size = 20, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M3 3l14 14M3 6.5L6.5 3M13.5 17L17 13.5" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <Circle cx={5.2} cy={5.2} r={2.3} stroke={color} strokeWidth={strokeWidth} fill="none" />
      <Circle cx={14.8} cy={14.8} r={2.3} stroke={color} strokeWidth={strokeWidth} fill="none" />
    </Svg>
  );
}

export function FlagIcon({ size = 13, color = '#000', strokeWidth = 1.6 }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 16 16">
      <Path d="M3 1.5v13" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
      <Path d="M3 2c2-1 4 1 6 0s4 1 4 1v6c0 0-2-1-4 0s-4-1-6 0V2z" stroke={color} strokeWidth={strokeWidth} fill="none" strokeLinejoin="round" />
    </Svg>
  );
}

export function LinesIcon({ size = 15, color = '#000' }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 20 20">
      <Path d="M6 3.5h8M4 10h12M6 16.5h8" stroke={color} strokeWidth={1.8} strokeLinecap="round" />
    </Svg>
  );
}
