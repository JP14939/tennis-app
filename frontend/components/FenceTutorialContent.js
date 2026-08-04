import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView } from 'react-native';

const GREEN  = '#4ade80';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

const STEPS = [
  {
    icon: '🎾',
    title: 'Find the right fence',
    body: "Use the shorter divider fence between courts (~3-4ft), not the tall perimeter fence around the whole facility — that's too high.",
  },
  {
    icon: '🔗',
    title: 'Two rubber bands',
    body: 'Loop one rubber band around your phone lengthwise and one crosswise, then hook both over a diamond of the fence mesh at roughly chest height.',
  },
  {
    icon: '📏',
    title: 'Distance back',
    body: "Position it a few feet behind the baseline, roughly level with the center of the court — you want your full swing in frame.",
  },
  {
    icon: '✅',
    title: "That's it",
    body: 'No tripod needed. A fixed fence mount also keeps the shot steadier than holding it by hand.',
  },
];

export default function FenceTutorialContent({ onDismiss, dismissLabel = 'Got it' }) {
  return (
    <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
      <Text style={s.h1}>Mount your phone with rubber bands</Text>
      <Text style={s.sub}>
        The pro comparisons work best when your phone is at a consistent, court-level
        height — here's the cheapest way to get that without buying a stand.
      </Text>

      {STEPS.map((step, i) => (
        <View key={i} style={s.stepCard}>
          <Text style={s.stepIcon}>{step.icon}</Text>
          <View style={s.stepTextWrap}>
            <Text style={s.stepTitle}>{step.title}</Text>
            <Text style={s.stepBody}>{step.body}</Text>
          </View>
        </View>
      ))}

      {onDismiss && (
        <TouchableOpacity style={s.btn} onPress={onDismiss}>
          <Text style={s.btnText}>{dismissLabel}</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: 24, paddingTop: 32, paddingBottom: 48, flexGrow: 1 },
  h1: { color: TEXT, fontSize: 24, fontWeight: '800', letterSpacing: -0.5, marginBottom: 8 },
  sub: { color: MUTED, fontSize: 14, lineHeight: 20, marginBottom: 24 },

  stepCard: {
    flexDirection: 'row', gap: 14, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 16, padding: 16, marginBottom: 12, alignItems: 'flex-start',
  },
  stepIcon: { fontSize: 26 },
  stepTextWrap: { flex: 1 },
  stepTitle: { color: TEXT, fontSize: 15, fontWeight: '700', marginBottom: 4 },
  stepBody: { color: '#ccc', fontSize: 13, lineHeight: 19 },

  btn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 12 },
  btnText: { color: '#000', fontSize: 15, fontWeight: '700' },
});
