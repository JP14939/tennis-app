import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import { colors, fonts } from '../theme';
import { HomeIcon, HistoryIcon, PremiumIcon, ProfileIcon } from './icons';

const ICONS = { Home: HomeIcon, History: HistoryIcon, Premium: PremiumIcon, Profile: ProfileIcon };
const BAR_PAD = 8;

export default function FloatingTabBar({ state, descriptors, navigation }) {
  const [barWidth, setBarWidth] = useState(0);
  const indicatorX = useRef(new Animated.Value(0)).current;

  const itemWidth = barWidth > 0 ? (barWidth - BAR_PAD * 2) / state.routes.length : 0;

  useEffect(() => {
    if (itemWidth === 0) return;
    Animated.timing(indicatorX, {
      toValue: BAR_PAD + state.index * itemWidth + 3,
      duration: 350,
      useNativeDriver: true,
    }).start();
  }, [state.index, itemWidth]);

  return (
    <View style={styles.wrap} onLayout={(e) => setBarWidth(e.nativeEvent.layout.width)}>
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
          <TouchableOpacity key={route.key} onPress={onPress} style={styles.item} activeOpacity={0.8}>
            {Icon && <Icon size={20} color={focused ? colors.white : colors.muted} />}
            <Text style={[styles.label, { color: focused ? colors.white : colors.muted }]}>{label}</Text>
          </TouchableOpacity>
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
