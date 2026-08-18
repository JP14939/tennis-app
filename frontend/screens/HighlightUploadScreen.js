import { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ScrollView, Alert, ActivityIndicator, Platform,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { colors, fonts, radius, spacing } from '../theme';

async function uploadMatch(videoUri, token) {
  const formData = new FormData();
  if (Platform.OS === 'web') {
    const response = await fetch(videoUri);
    const blob = await response.blob();
    formData.append('video', blob, 'match.mp4');
  } else {
    formData.append('video', { uri: videoUri, name: 'match.mp4', type: 'video/mp4' });
  }
  const response = await fetch(`${API_BASE}/api/highlights/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Upload failed');
  return data;
}

export default function HighlightUploadScreen({ navigation }) {
  const { token } = useAuth();
  const [videoUri, setVideoUri] = useState(null);
  const [videoName, setVideoName] = useState(null);
  const [picking, setPicking] = useState(false);
  // idle | uploading | uploaded | error -- "uploaded" means the job is
  // running in the background on the server; this screen doesn't wait for
  // it to finish (that can take a long time for a full match video).
  const [status, setStatus] = useState('idle');
  const [errorMsg, setErrorMsg] = useState('');

  const pick = async () => {
    setPicking(true);
    try {
      const { status: perm } = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (perm !== 'granted') {
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

  const startUpload = async () => {
    if (!videoUri) return;
    setStatus('uploading');
    setErrorMsg('');
    try {
      await uploadMatch(videoUri, token);
      setStatus('uploaded');
    } catch (err) {
      setErrorMsg(err.message || 'Something went wrong');
      setStatus('error');
    }
  };

  if (status === 'uploading') {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={s.loadingTitle}>Uploading your match...</Text>
          <Text style={s.loadingSub}>Rally detection runs in the background — this can take a while for a full match.</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (status === 'uploaded') {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={s.loadingTitle}>Upload complete</Text>
          <Text style={s.loadingSub}>We're scanning your match for rallies now — you'll get a notification when it's ready to review.</Text>
          <TouchableOpacity style={s.continueBtn} onPress={() => navigation.navigate('HighlightArchive')}>
            <Text style={s.continueBtnText}>Go to Archive</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Upload a match</Text>
        <Text style={s.sub}>We'll scan it and clip out every rally you play — full matches or practice sessions welcome.</Text>

        {status === 'error' && <Text style={s.errorText}>{errorMsg}</Text>}

        <TouchableOpacity style={s.uploadBtn} onPress={pick} disabled={picking}>
          {videoUri ? (
            <>
              <Text style={s.uploadBtnText}>Match selected</Text>
              <Text style={s.uploadBtnSub} numberOfLines={1}>{videoName}</Text>
              <Text style={s.changeText}>Tap to change</Text>
            </>
          ) : (
            <>
              <Text style={s.uploadBtnText}>{picking ? 'Opening...' : 'Choose match video'}</Text>
              <Text style={s.uploadBtnSub}>MP4 · MOV · any length</Text>
            </>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={[s.continueBtn, !videoUri && s.continueDisabled]}
          onPress={() => { playTapSound(); startUpload(); }}
          disabled={!videoUri}
        >
          <Text style={s.continueBtnText}>Find my rallies →</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48, flexGrow: 1 },

  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingTitle: { color: colors.ink, fontSize: 18, fontFamily: fonts.bold, marginTop: 20, textAlign: 'center' },
  loadingSub: { color: colors.muted, fontSize: 14, marginTop: 8, textAlign: 'center', lineHeight: 20, fontFamily: fonts.regular },
  errorText: { color: colors.coral, fontSize: 13, marginBottom: 16, textAlign: 'center', fontFamily: fonts.regular },

  h1:  { color: colors.ink, fontSize: 26, fontFamily: fonts.bold, letterSpacing: -0.5, marginBottom: 8 },
  sub: { color: colors.muted, fontSize: 14, lineHeight: 21, marginBottom: 28, fontFamily: fonts.regular },

  uploadBtn: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 28, alignItems: 'center', gap: 6,
  },
  uploadBtnText: { color: colors.ink, fontSize: 16, fontFamily: fonts.semibold },
  uploadBtnSub:  { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },
  changeText:    { color: colors.primary, fontSize: 12, marginTop: 4, fontFamily: fonts.semibold },

  continueBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 15, alignItems: 'center', marginTop: 24 },
  continueDisabled: { opacity: 0.4 },
  continueBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
});
