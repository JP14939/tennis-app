import { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, Alert, ActivityIndicator,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { MOCK_DETECTED_CLIPS } from '../data/mockHighlights';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

export default function HighlightUploadScreen({ navigation }) {
  const [videoUri, setVideoUri] = useState(null);
  const [videoName, setVideoName] = useState(null);
  const [picking, setPicking] = useState(false);
  const [processing, setProcessing] = useState(false);

  const pick = async () => {
    setPicking(true);
    try {
      const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission needed', 'Allow access to your photo library.');
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['videos'], quality: 1 });
      if (!result.canceled && result.assets?.[0]?.uri) {
        setVideoUri(result.assets[0].uri);
        setVideoName(result.assets[0].uri.split('/').pop() || 'match.mp4');
      }
    } finally {
      setPicking(false);
    }
  };

  const findShots = () => {
    if (!videoUri) return;
    setProcessing(true);
    // TODO: replace with a real upload — backend needs to run pose
    // extraction + swing detection (scripts/03_swing_detection/detect_swings.py
    // already does this for pre-extracted pose data, but has no shot-type
    // classifier yet and has never been run against arbitrary match footage
    // end-to-end). Mocked here so the review/tag UI can be built now.
    setTimeout(() => {
      setProcessing(false);
      navigation.navigate('HighlightReview', { videoUri, clips: MOCK_DETECTED_CLIPS });
    }, 2200);
  };

  if (processing) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={GREEN} />
          <Text style={s.loadingTitle}>Finding your shots...</Text>
          <Text style={s.loadingSub}>Scanning the match for every swing</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Upload a match</Text>
        <Text style={s.sub}>We'll scan it and clip out every shot you hit — up to 10 minutes per upload for now.</Text>

        <TouchableOpacity style={s.uploadBtn} onPress={pick} disabled={picking}>
          {videoUri ? (
            <>
              <Text style={s.uploadIcon}>✅</Text>
              <Text style={s.uploadBtnText}>Match selected</Text>
              <Text style={s.uploadBtnSub} numberOfLines={1}>{videoName}</Text>
              <Text style={s.changeText}>Tap to change</Text>
            </>
          ) : (
            <>
              <Text style={s.uploadIcon}>🎬</Text>
              <Text style={s.uploadBtnText}>{picking ? 'Opening...' : 'Choose match video'}</Text>
              <Text style={s.uploadBtnSub}>MP4 · MOV · up to 10 minutes</Text>
            </>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={[s.continueBtn, !videoUri && s.continueDisabled]}
          onPress={findShots}
          disabled={!videoUri}
        >
          <Text style={s.continueBtnText}>Find my shots →</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 24, paddingTop: 24, paddingBottom: 48, flexGrow: 1 },

  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingTitle: { color: TEXT, fontSize: 18, fontWeight: '700', marginTop: 20, textAlign: 'center' },
  loadingSub: { color: MUTED, fontSize: 14, marginTop: 8, textAlign: 'center', lineHeight: 20 },

  h1:  { color: TEXT, fontSize: 26, fontWeight: '800', letterSpacing: -0.5, marginBottom: 8 },
  sub: { color: MUTED, fontSize: 14, lineHeight: 21, marginBottom: 28 },

  uploadBtn: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 16, padding: 28, alignItems: 'center', gap: 6,
  },
  uploadIcon:    { fontSize: 36, marginBottom: 4 },
  uploadBtnText: { color: TEXT, fontSize: 16, fontWeight: '600' },
  uploadBtnSub:  { color: MUTED, fontSize: 13 },
  changeText:    { color: GREEN, fontSize: 12, marginTop: 4 },

  continueBtn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 15, alignItems: 'center', marginTop: 24 },
  continueDisabled: { opacity: 0.4 },
  continueBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
});
