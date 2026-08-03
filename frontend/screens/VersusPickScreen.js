import { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, Alert,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

const SHOT_TYPES = ['forehand', 'backhand', 'serve'];

function VideoPicker({ icon, label, sub, fileName, picking, onPress }) {
  return (
    <TouchableOpacity style={s.uploadBtn} onPress={onPress} disabled={picking}>
      {fileName ? (
        <>
          <Text style={s.uploadIcon}>✅</Text>
          <Text style={s.uploadBtnText}>{label} selected</Text>
          <Text style={s.uploadBtnSub} numberOfLines={1}>{fileName}</Text>
          <Text style={s.changeText}>Tap to change</Text>
        </>
      ) : (
        <>
          <Text style={s.uploadIcon}>{icon}</Text>
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
            navigation.navigate('VersusResults', { shotType, reference, yours });
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
          icon="🎯"
          label="Choose reference video"
          sub="MP4 · MOV · any resolution"
          fileName={refName}
          picking={picking === 'ref'}
          onPress={() => pick('ref')}
        />

        <Text style={[s.fieldLabel, { marginTop: 20 }]}>Your video</Text>
        <VideoPicker
          icon="📹"
          label="Choose your video"
          sub="MP4 · MOV · any resolution"
          fileName={yourName}
          picking={picking === 'yours'}
          onPress={() => pick('yours')}
        />

        <TouchableOpacity
          style={[s.continueBtn, !canContinue && s.continueDisabled]}
          onPress={start}
          disabled={!canContinue}
        >
          <Text style={s.continueBtnText}>Continue →</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 24, paddingTop: 24, paddingBottom: 48, flexGrow: 1 },

  h1:  { color: TEXT, fontSize: 26, fontWeight: '800', letterSpacing: -0.5, marginBottom: 8 },
  sub: { color: MUTED, fontSize: 14, lineHeight: 21, marginBottom: 28 },

  fieldLabel: { color: '#aaa', fontSize: 13, fontWeight: '600', marginBottom: 10 },
  shotRow: { flexDirection: 'row', gap: 8, marginBottom: 24 },
  shotPill: {
    flex: 1, borderWidth: 1, borderColor: BORDER,
    borderRadius: 20, paddingVertical: 10, alignItems: 'center',
  },
  shotPillActive:     { backgroundColor: '#1a2e1a', borderColor: '#2a4a2a' },
  shotPillText:       { color: MUTED, fontSize: 14, fontWeight: '500' },
  shotPillTextActive: { color: GREEN, fontWeight: '700' },

  uploadBtn: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 16, padding: 24, alignItems: 'center', gap: 4,
  },
  uploadIcon:    { fontSize: 30, marginBottom: 4 },
  uploadBtnText: { color: TEXT, fontSize: 15, fontWeight: '600' },
  uploadBtnSub:  { color: MUTED, fontSize: 12 },
  changeText:    { color: GREEN, fontSize: 12, marginTop: 4 },

  continueBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 28 },
  continueDisabled: { opacity: 0.4 },
  continueBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
});
