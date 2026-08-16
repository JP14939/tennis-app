import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated } from 'react-native';
import { colors, fonts, radius } from '../theme';
import TipDiagram from './TipDiagram';
import { ChevronDownIcon } from './icons';

// Measured-height collapsible -- RN has no CSS max-height:auto equivalent,
// so natural content height is measured once via onLayout then animated
// between 0 and that value.
export function Collapsible({ open, children }) {
  const [contentHeight, setContentHeight] = useState(0);
  const heightAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(heightAnim, {
      toValue: open ? contentHeight : 0,
      duration: 300,
      useNativeDriver: false,
    }).start();
  }, [open, contentHeight]);
  return (
    <Animated.View style={{ height: heightAnim, overflow: 'hidden' }}>
      {/* position:absolute pulls this out of the parent's own flow layout so
          it always measures its natural height via onLayout, even while the
          parent itself is clipped to height 0 -- a plain flow child here can
          get skipped by the native layout pass entirely when the parent's
          computed height is 0, leaving contentHeight stuck at 0 forever and
          the toggle visually doing nothing on press. */}
      <View style={{ position: 'absolute', left: 0, right: 0, top: 0 }}
        onLayout={(e) => setContentHeight(e.nativeEvent.layout.height)}>
        {children}
      </View>
    </Animated.View>
  );
}

export function useRotate(open) {
  const rotateAnim = useRef(new Animated.Value(open ? 1 : 0)).current;
  useEffect(() => {
    Animated.timing(rotateAnim, { toValue: open ? 1 : 0, duration: 250, useNativeDriver: true }).start();
  }, [open]);
  return rotateAnim.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '180deg'] });
}

export function TipRow({ tip }) {
  const [open, setOpen] = useState(false);
  const rotate = useRotate(open);

  if (!tip.drill) {
    return (
      <View style={t.row}>
        <Text style={t.fixText}><Text style={t.fixLabel}>Fix: </Text>{tip.tip_text ?? tip}</Text>
      </View>
    );
  }

  return (
    <View style={t.rowWrap}>
      <TouchableOpacity style={t.row} onPress={() => setOpen(o => !o)} activeOpacity={0.85}>
        <Text style={t.fixText}><Text style={t.fixLabel}>Fix: </Text>{tip.tip_text}</Text>
        <Animated.View style={{ transform: [{ rotate }] }}>
          <ChevronDownIcon size={12} color={colors.mutedDark} />
        </Animated.View>
      </TouchableOpacity>
      <Collapsible open={open}>
        <View style={t.drillPanel}>
          <TipDiagram tipId={tip.id} />
          <Text style={t.drillText}><Text style={t.drillLabel}>Drill — </Text>{tip.drill}</Text>
        </View>
      </Collapsible>
    </View>
  );
}
const t = StyleSheet.create({
  rowWrap: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: 'hidden', marginBottom: 9 },
  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10,
    padding: 14,
  },
  fixText: { flex: 1, color: colors.ink, fontSize: 13, lineHeight: 19.5, fontFamily: fonts.regular },
  fixLabel: { fontFamily: fonts.bold },
  drillPanel: { backgroundColor: colors.primarySoft, padding: 14 },
  drillText: { color: colors.limeText, fontSize: 13, lineHeight: 19.5, fontFamily: fonts.regular },
  drillLabel: { fontFamily: fonts.bold },
});

export default function TipsSection({ tips }) {
  // Starts open -- this is valuable, actionable content, and a collapsed
  // accordion with a subtle chevron was easy to miss entirely (reported
  // as "no tips show up" when the data was there the whole time). Still
  // collapsible for anyone who wants to hide it after reading.
  const [open, setOpen] = useState(true);
  const rotate = useRotate(open);

  return (
    <>
      <TouchableOpacity style={ts.toggle} onPress={() => setOpen(o => !o)} activeOpacity={0.85}>
        <Text style={ts.toggleText}>Tips & drills to fix</Text>
        <Animated.View style={{ transform: [{ rotate }] }}>
          <ChevronDownIcon size={14} color={colors.mutedDark} />
        </Animated.View>
      </TouchableOpacity>
      <Collapsible open={open}>
        <View style={ts.reveal}>
          {tips.map((tip, i) => <TipRow key={i} tip={tip} />)}
        </View>
      </Collapsible>
    </>
  );
}
const ts = StyleSheet.create({
  toggle: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 15, marginBottom: 22,
  },
  toggleText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  reveal: { marginTop: -12, paddingTop: 10 },
});
