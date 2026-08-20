import { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
} from 'react-native';
import Alert from '../utils/alert';
import * as ImagePicker from 'expo-image-picker';
import { playTapSound } from '../utils/sounds';
import { colors, fonts, radius, spacing } from '../theme';

const SHOT_TYPES = ['forehand', 'backhand', 'serve'];

function VideoPicker({ label, sub, fileName, picking, onPress }) {
  return (
    <TouchableOpacity style={s.uploadBtn} onPress={onPress} disabled={picking}>
      {fileName ? (
        <>
          <Text style={s.uploadBtnText}>{label} selected</Text>
          <Text style={s.uploadBtnSub} numberOfLines={1}>{fileName}</Text>
          <Text style={s.changeText}>Tap to change</Text>
        </>
      ) : (
        <>
          <Text style={s.uploadBtnText}>{picking ? 'Opening...' : label}</Text>
          <Text style={s.uploadBtnSub}>{sub}</Text>
        </>
      )}
    </TouchableOpacity>
  );
}

export default function VersusPickScreen({ navigation }) {
  const [shotType, setShotType] = useState('forehand');
  const [refUri, setRefUri] = useState(null);
  const [refName, setRefName] = useState(null);
  const [yourUri, setYourUri] = useState(null);
  const [yourName, setYourName] = useState(null);
  const [picking, setPicking] = useState(null); // 'ref' | 'yours' | null

  const pick = async (which) => {
    setPicking(which);
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Allow access to your photo library.');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'], quality: 1 });
      if (!result.canceled && result.assets?.[0]?.uri) {
        const uri = result.assets[0].uri;
        const name = uri.split('/').pop() || 'video.mp4';
        if (which === 'ref') { setRefUri(uri); setRefName(name); }
        else { setYourUri(uri); setYourName(name); }
      }
    } finally {
      setPicking(null);
    }
  };

  const canContinue = !!refUri && !!yourUri;

  const start = () => {
    if (!canContinue) return;
    // Mark contact on the reference video first, then your video — each hop
    // reuses ContactMarkingScreen via its onConfirmed escape hatch, so the
    // same frame-marking UI works for both without duplicating that logic.
    navigation.push('Upload', {
      videoUri: refUri,
      shotType,
      onConfirmed: (reference) => {
        navigation.push('Upload', {
          videoUri: yourUri,
          shotType,
          onConfirmed: (yours) => {
            // reset (not navigate) -- push()ing twice left both completed
            // ContactMarkingScreen instances on the stack, so pressing back
            // from VersusResults landed on an already-finished fine-tune
            // screen instead of returning here. Replaces the whole stack
            // with just [VersusPick, VersusResults], so back goes straight
            // to re-picking videos, not through the marking flow again.
            navigation.reset({
              index: 1,
              routes: [
                { name: 'VersusPick' },
                { name: 'VersusResults', params: { shotType, reference, yours } },
              ],
            });
          },
        });
      },
    });
  };

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Compare to a video</Text>
        <Text style={s.sub}>Upload a video you want to copy, then your own swing — we'll mark contact on both and show you exactly what's different.</Text>

        <Text style={s.fieldLabel}>Shot type</Text>
        <View style={s.shotRow}>
          {SHOT_TYPES.map(t => (
            <TouchableOpacity
              key={t}
              style={[s.shotPill, shotType === t && s.shotPillActive]}
              onPress={() => setShotType(t)}
            >
              <Text style={[s.shotPillText, shotType === t && s.shotPillTextActive]}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={s.fieldLabel}>Video you want to copy</Text>
        <VideoPicker
          label="Choose reference video"
          sub="MP4 · MOV · any resolution"
          fileName={refName}
          picking={picking === 'ref'}
          onPress={() => pick('ref')}
        />

        <Text style={[s.fieldLabel, { marginTop: 20 }]}>Your video</Text>
        <VideoPicker
          label="Choose your video"
          sub="MP4 · MOV · any resolution"
          fileName={yourName}
          picking={picking === 'yours'}
          onPress={() => pick('yours')}
        />

        <TouchableOpacity
          style={[s.continueBtn, !canContinue && s.continueDisabled]}
          onPress={() => { playTapSound(); start(); }}
          disabled={!canContinue}
        >
          <Text style={s.continueBtnText}>Continue →</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48, flexGrow: 1 },

  h1:  { color: colors.ink, fontSize: 26, fontFamily: fonts.bold, letterSpacing: -0.5, marginBottom: 8 },
  sub: { color: colors.muted, fontSize: 14, lineHeight: 21, marginBottom: 28, fontFamily: fonts.regular },

  fieldLabel: { color: colors.mutedDark, fontSize: 13, fontFamily: fonts.semibold, marginBottom: 10 },
  shotRow: { flexDirection: 'row', gap: 8, marginBottom: 24 },
  shotPill: {
    flex: 1, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill, paddingVertical: 10, alignItems: 'center',
  },
  shotPillActive:     { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  shotPillText:       { color: colors.muted, fontSize: 14, fontFamily: fonts.medium },
  shotPillTextActive: { color: colors.primary, fontFamily: fonts.bold },

  uploadBtn: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 24, alignItems: 'center', gap: 4,
  },
  uploadBtnText: { color: colors.ink, fontSize: 15, fontFamily: fonts.semibold },
  uploadBtnSub:  { color: colors.muted, fontSize: 12, fontFamily: fonts.regular },
  changeText:    { color: colors.primary, fontSize: 12, marginTop: 4, fontFamily: fonts.semibold },

  continueBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 15, alignItems: 'center', marginTop: 28 },
  continueDisabled: { opacity: 0.4 },
  continueBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
});
