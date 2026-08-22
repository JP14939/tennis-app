import { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet, Animated, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import { colors, fonts, springs, durations, easing } from '../theme';
import { useReducedMotion } from '../utils/useReducedMotion';
import PressableScale from './PressableScale';
import { useWindowWidth } from '../utils/responsive';
import { HomeIcon, HistoryIcon, FriendsIcon, ProfileIcon, MapPinIcon } from './icons';

const ICONS = { Home: HomeIcon, History: HistoryIcon, Friends: FriendsIcon, FindGames: MapPinIcon, Profile: ProfileIcon };
const BAR_PAD = 8;

// Below this width (a genuinely small phone, e.g. iPhone SE at 375 or a
// small Android at 360), the bar's fixed margins/icon/label sizes were
// reported as visibly compressed -- these are the smaller values used
// under that breakpoint. Was compounded by Premium being a 6th tab; now
// 5 tabs (Premium moved to Home, see PremiumFeaturesSection) but still
// worth scaling down for genuinely narrow screens rather than relying on
// one fewer tab alone to fix it.
const SMALL_SCREEN_BREAKPOINT = 375;
const SIDE_MARGIN = { normal: 16, small: 10 };
const ICON_SIZE = { normal: 20, small: 17 };
const LABEL_FONT_SIZE = { normal: 10.5, small: 9.5 };

export default function FloatingTabBar({ state, descriptors, navigation }) {
  const [barWidth, setBarWidth] = useState(0);
  const indicatorX = useRef(new Animated.Value(0)).current;
  const reducedMotion = useReducedMotion();
  const hasPositioned = useRef(false);
  const windowWidth = useWindowWidth();
  const isSmallScreen = windowWidth < SMALL_SCREEN_BREAKPOINT;
  const sideMargin = isSmallScreen ? SIDE_MARGIN.small : SIDE_MARGIN.normal;
  const iconSize = isSmallScreen ? ICON_SIZE.small : ICON_SIZE.normal;
  const labelFontSize = isSmallScreen ? LABEL_FONT_SIZE.small : LABEL_FONT_SIZE.normal;

  const itemWidth = barWidth > 0 ? (barWidth - BAR_PAD * 2) / state.routes.length : 0;

  // The indicator is a physical object sliding between slots, so it springs
  // rather than following a timing curve. This was 350ms of the default
  // ease-in-out -- on the control people touch more than any other in the
  // app, that start-slow ramp read as lag every single time.
  //
  // Two cases deliberately don't animate: the very first positioning (there's
  // nothing to travel *from*, so a slide-in from the left edge on mount is
  // motion that communicates nothing), and a width change from rotation or a
  // resize, which would otherwise animate the indicator sideways for reasons
  // unrelated to anything the user did.
  const prevItemWidth = useRef(itemWidth);
  useEffect(() => {
    if (itemWidth === 0) return;
    const target = BAR_PAD + state.index * itemWidth + 3;
    const widthChanged = prevItemWidth.current !== itemWidth;
    prevItemWidth.current = itemWidth;

    if (!hasPositioned.current || widthChanged) {
      hasPositioned.current = true;
      indicatorX.setValue(target);
      return;
    }

    if (reducedMotion) {
      // Still moves -- this indicator is how you tell which tab is selected,
      // so removing it outright would cost information. Just made quick and
      // linear-ish instead of springy.
      Animated.timing(indicatorX, {
        toValue: target,
        duration: durations.instant,
        easing: easing.out,
        useNativeDriver: true,
      }).start();
      return;
    }

    Animated.spring(indicatorX, { toValue: target, ...springs.slide }).start();
  }, [state.index, itemWidth, reducedMotion]);

  return (
    <View
      style={[styles.wrap, { left: sideMargin, right: sideMargin }]}
      onLayout={(e) => setBarWidth(e.nativeEvent.layout.width)}
    >
      <BlurView intensity={60} tint="light" style={StyleSheet.absoluteFillObject} />
      <View style={styles.tint} pointerEvents="none" />
      {itemWidth > 0 && (
        <Animated.View
          style={[
            styles.indicator,
            { width: itemWidth - 6, transform: [{ translateX: indicatorX }] },
          ]}
        />
      )}
      {state.routes.map((route, index) => {
        const { options } = descriptors[route.key];
        const label = options.tabBarLabel ?? options.title ?? route.name;
        const focused = state.index === index;
        const Icon = ICONS[route.name];

        const onPress = () => {
          const event = navigation.emit({ type: 'tabPress', target: route.key, canPreventDefault: true });
          if (!focused && !event.defaultPrevented) {
            navigation.navigate(route.name);
          }
        };

        return (
          <PressableScale key={route.key} onPress={onPress} style={styles.item} scaleTo={0.9}>
            {Icon && <Icon size={iconSize} color={focused ? colors.white : colors.muted} />}
            <Text style={[styles.label, { fontSize: labelFontSize, color: focused ? colors.white : colors.muted }]}>{label}</Text>
          </PressableScale>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute', left: 16, right: 16, bottom: 14, height: 64,
    borderRadius: 32, overflow: 'hidden',
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: BAR_PAD,
    shadowColor: '#000', shadowOpacity: 0.12, shadowRadius: 20, shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  tint: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: Platform.OS === 'web' ? 'rgba(255,255,255,0.72)' : 'rgba(255,255,255,0.35)',
  },
  indicator: {
    position: 'absolute', top: 8, bottom: 8, left: 0,
    borderRadius: 24, backgroundColor: colors.primary,
  },
  item: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 4, height: '100%' },
  label: { fontSize: 10.5, fontFamily: fonts.bold },
});
