import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import FenceTutorialContent from '../components/FenceTutorialContent';
import { colors } from '../theme';

export default function FenceTutorialScreen() {
  return (
    <SafeAreaView style={s.safe}>
      <FenceTutorialContent />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
});
