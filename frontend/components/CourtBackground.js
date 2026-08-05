import Svg, { Path } from 'react-native-svg';
import { StyleSheet } from 'react-native';
import { colors } from '../theme';

// Decorative net-curve wallpaper ported 1:1 from the redesign mockup's
// inline SVG (4 Bezier paths, 402x874 viewBox, 7% opacity).
export default function CourtBackground({ color = colors.primary }) {
  return (
    <Svg
      style={StyleSheet.absoluteFillObject}
      width="100%"
      height="100%"
      viewBox="0 0 402 874"
      preserveAspectRatio="xMidYMid slice"
      pointerEvents="none"
      opacity={0.07}
    >
      <Path d="M -60 130 C 80 260, 80 480, -60 610" fill="none" stroke={color} strokeWidth={26} />
      <Path d="M 462 130 C 322 260, 322 480, 462 610" fill="none" stroke={color} strokeWidth={26} />
      <Path d="M -40 640 C 100 770, 100 990, -40 1120" fill="none" stroke={color} strokeWidth={18} />
      <Path d="M 442 640 C 302 770, 302 990, 442 1120" fill="none" stroke={color} strokeWidth={18} />
    </Svg>
  );
}
