import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import FenceTutorialContent from '../components/FenceTutorialContent';

const DARK = '#0d0d0d';

export default function FenceTutorialScreen() {
  return (
    <SafeAreaView style={s.safe}>
      <FenceTutorialContent />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
});
