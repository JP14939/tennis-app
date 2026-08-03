import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  Dimensions, Alert, Platform, ScrollView,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import PlatformVideo from '../components/PlatformVideo';

const ASSUMED_FPS = 30;
const FINE_RADIUS = 10;
const SHOT_TYPES  = ['forehand', 'backhand', 'serve'];
const IS_WEB      = Platform.OS === 'web';

function useDims() {
  const [dims, setDims] = useState(Dimensions.get('window'));
  useEffect(() => {
    const sub = Dimensions.addEventListener('change', ({ window }) => setDims(window));
    return () => sub?.remove();
  }, []);
  return dims;
}

export default function ContactMarkingScreen({ navigation, route }) {
  const [uri, setUri]           = useState(route.params?.videoUri ?? null);
  const [shotType, setShotType] = useState(route.params?.shotType ?? 'forehand');
  const [phase, setPhase]       = useState(uri ? 'rough' : 'pick');
  const [status, setStatus]     = useState({});
  const [roughTime, setRoughTime]   = useState(null);
  const [fineOffset, setFineOffset] = useState(0);
  const videoRef  = useRef(null);
  const slowMoRef = useRef(null);
  const dims = useDims();

  // Derived from status (expo-av shape — web PlatformVideo pushes same shape)
  const currentTime = (status.positionMillis  ?? 0) / 1000;
  const duration    = (status.durationMillis  ?? 1000) / 1000;
  const isPlaying   = status.isPlaying ?? false;

  // Keep video paused at fine-offset frame whenever it changes
  useEffect(() => {
    if (phase !== 'fine' || roughTime === null) return;
    videoRef.current?.pauseAsync();
    videoRef.current?.setPositionAsync(
      Math.round(Math.max(0, roughTime + fineOffset / ASSUMED_FPS) * 1000)
    );
  }, [fineOffset, phase]);

  // ── Controls ──────────────────────────────────────────────────────────────
  const play   = () => videoRef.current?.playAsync();
  const pause  = () => videoRef.current?.pauseAsync();
  const seekTo = (sec) =>
    videoRef.current?.setPositionAsync(Math.round(Math.max(0, sec) * 1000));

  // ── Actions ───────────────────────────────────────────────────────────────
  const pickVideo = async () => {
    const { status: perm } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm !== 'granted') {
      Alert.alert('Permission needed', 'Allow access to your photo library.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      quality: 1,
    });
    if (!result.canceled && result.assets?.[0]?.uri) {
      setUri(result.assets[0].uri);
      setPhase('rough');
    }
  };

  const markWindow = async () => {
    await pause();
    setRoughTime(currentTime);
    setFineOffset(0);
    setPhase('fine');
  };

  const prevFrame = () => setFineOffset(o => Math.max(o - 1, -FINE_RADIUS));
  const nextFrame = () => setFineOffset(o => Math.min(o + 1, FINE_RADIUS));

  const playSlowMo = async () => {
    if (roughTime === null) return;
    clearTimeout(slowMoRef.current);
    await videoRef.current?.setRateAsync?.(0.25, true).catch(() =>
      videoRef.current?.setRateAsync(0.25)  // web version doesn't take 2nd arg
    );
    await seekTo(Math.max(0, roughTime - FINE_RADIUS / ASSUMED_FPS));
    await play();
    const windowMs = (FINE_RADIUS * 2 / ASSUMED_FPS / 0.25) * 1000 + 400;
    slowMoRef.current = setTimeout(async () => {
      await pause();
      await videoRef.current?.setRateAsync?.(1.0, true).catch(() =>
        videoRef.current?.setRateAsync(1.0)
      );
      await seekTo(roughTime + fineOffset / ASSUMED_FPS);
    }, windowMs);
  };

  const confirmFrame = async () => {
    if (roughTime === null) return;
    const fineT = roughTime + fineOffset / ASSUMED_FPS;
    const frame = Math.round(fineT * ASSUMED_FPS);
    await pause();
    const marked = { videoUri: uri, shotType, contactFrame: frame, contactTimeSec: fineT };
    // Reused by flows that need contact marked on more than one video (e.g.
    // 1v1 comparison) — they pass onConfirmed instead of relying on the
    // default single-video "go to Results" behaviour.
    if (route.params?.onConfirmed) {
      route.params.onConfirmed(marked);
      return;
    }
    navigation.navigate('Results', marked);
  };

  // ── Layout ────────────────────────────────────────────────────────────────
  const progressFraction = duration > 0 ? Math.min(1, currentTime / duration) : 0;
  const fineT        = roughTime !== null ? roughTime + fineOffset / ASSUMED_FPS : 0;
  const fineFrameAbs = Math.round(fineT * ASSUMED_FPS);
  const videoH       = Math.round(Math.min(dims.width * 0.56, dims.height * 0.42));

  // ── PICK ──────────────────────────────────────────────────────────────────
  if (phase === 'pick') {
    return (
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.pickScroll} showsVerticalScrollIndicator={false}>
          <Text style={s.h1}>Analyse your swing</Text>
          <Text style={s.sub}>Upload a 10–30 second video of your shot</Text>

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

          <TouchableOpacity style={s.uploadBtn} onPress={pickVideo}>
            <Text style={s.uploadIcon}>📹</Text>
            <Text style={s.uploadBtnText}>Choose video from library</Text>
            <Text style={s.uploadBtnSub}>MP4 · MOV · any resolution</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── VIDEO PHASES ──────────────────────────────────────────────────────────
  return (
    <SafeAreaView style={s.safe}>

      {/* Video — sized explicitly so it always occupies real pixels */}
      <TouchableOpacity
        activeOpacity={1}
        style={{ width: dims.width, height: videoH, backgroundColor: '#000' }}
        onPress={() => isPlaying ? pause() : play()}
      >
        <PlatformVideo
          ref={videoRef}
          uri={uri}
          width={dims.width}
          height={videoH}
          onStatusUpdate={setStatus}
        />
        {!isPlaying && (
          <View pointerEvents="none" style={StyleSheet.absoluteFill} >
            <View style={s.playHint}>
              <Text style={s.playHintText}>▶</Text>
            </View>
          </View>
        )}
      </TouchableOpacity>

      {/* Panel */}
      <View style={s.panel}>

        {/* ROUGH */}
        {phase === 'rough' && (
          <>
            <Text style={s.panelTitle}>Step 1 — Find the contact frame</Text>
            <Text style={s.panelSub}>Tap video to play/pause · drag slider to scrub</Text>

            {IS_WEB
              ? React.createElement('input', {
                  type: 'range',
                  min: '0', max: '1', step: '0.001',
                  value: String(progressFraction),
                  onChange: (e) => seekTo(parseFloat(e.target.value) * duration),
                  style: {
                    width: '100%', accentColor: '#4ade80',
                    marginBottom: '8px', cursor: 'pointer', height: '20px',
                  },
                })
              : (
                <View
                  style={s.progressTrack}
                  onStartShouldSetResponder={() => true}
                  onResponderGrant={(e) => seekTo((e.nativeEvent.locationX / (dims.width - 40)) * duration)}
                  onResponderMove={(e)  => seekTo((e.nativeEvent.locationX / (dims.width - 40)) * duration)}
                >
                  <View style={[s.progressFill, { width: `${progressFraction * 100}%` }]} />
                  <View style={[s.progressThumb, { left: `${progressFraction * 100}%` }]} />
                </View>
              )
            }

            <Text style={s.timeText}>{currentTime.toFixed(2)}s / {duration.toFixed(1)}s</Text>

            <TouchableOpacity style={s.btnPrimary} onPress={markWindow}>
              <Text style={s.btnPrimaryText}>Mark contact window →</Text>
            </TouchableOpacity>
          </>
        )}

        {/* FINE */}
        {phase === 'fine' && (
          <>
            <Text style={s.panelTitle}>Step 2 — Pinpoint the exact frame</Text>
            <Text style={s.panelSub}>Tap ◀ / ▶ to step one frame at a time</Text>

            <View style={s.frameRow}>
              <TouchableOpacity style={s.frameBtn} onPress={prevFrame} disabled={fineOffset <= -FINE_RADIUS}>
                <Text style={[s.frameBtnText, fineOffset <= -FINE_RADIUS && s.frameBtnDisabled]}>◀</Text>
              </TouchableOpacity>
              <View style={s.frameCenter}>
                <Text style={s.frameNumber}>Frame {fineFrameAbs}</Text>
                <Text style={s.frameOffset}>{fineOffset >= 0 ? '+' : ''}{fineOffset} · {fineT.toFixed(2)}s</Text>
              </View>
              <TouchableOpacity style={s.frameBtn} onPress={nextFrame} disabled={fineOffset >= FINE_RADIUS}>
                <Text style={[s.frameBtnText, fineOffset >= FINE_RADIUS && s.frameBtnDisabled]}>▶</Text>
              </TouchableOpacity>
            </View>

            <View style={s.offsetTrack}>
              <View style={[s.offsetThumb, {
                left: `${((fineOffset + FINE_RADIUS) / (FINE_RADIUS * 2)) * 92 + 2}%`
              }]} />
            </View>
            <View style={s.offsetLabels}>
              <Text style={s.offsetLabel}>-{FINE_RADIUS}</Text>
              <Text style={s.offsetLabel}>0</Text>
              <Text style={s.offsetLabel}>+{FINE_RADIUS}</Text>
            </View>

            <View style={s.rowBtns}>
              <TouchableOpacity style={s.btnGhost} onPress={playSlowMo}>
                <Text style={s.btnGhostText}>0.25× slow-mo</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.btnPrimary2} onPress={confirmFrame}>
                <Text style={s.btnPrimaryText}>This is it ✓</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={s.backLink} onPress={() => { play(); setPhase('rough'); }}>
              <Text style={s.backLinkText}>← Back to rough selection</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },

  pickScroll: { padding: 24, paddingTop: 48, flexGrow: 1 },
  h1:  { color: TEXT, fontSize: 28, fontWeight: '800', letterSpacing: -0.5, marginBottom: 8 },
  sub: { color: MUTED, fontSize: 15, lineHeight: 22, marginBottom: 32 },

  fieldLabel: { color: '#aaa', fontSize: 13, fontWeight: '600', marginBottom: 10 },
  shotRow: { flexDirection: 'row', gap: 8, marginBottom: 28 },
  shotPill: {
    flex: 1, borderWidth: 1, borderColor: BORDER,
    borderRadius: 20, paddingVertical: 10, alignItems: 'center',
  },
  shotPillActive:     { backgroundColor: '#1a2e1a', borderColor: '#2a4a2a' },
  shotPillText:       { color: MUTED, fontSize: 14, fontWeight: '500' },
  shotPillTextActive: { color: GREEN, fontWeight: '700' },

  uploadBtn: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 16, padding: 28, alignItems: 'center', gap: 6,
  },
  uploadIcon:    { fontSize: 36, marginBottom: 4 },
  uploadBtnText: { color: TEXT, fontSize: 16, fontWeight: '600' },
  uploadBtnSub:  { color: MUTED, fontSize: 13 },

  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.35)', fontSize: 52 },

  panel:      { backgroundColor: DARK, padding: 20, paddingTop: 18, flex: 1 },
  panelTitle: { color: TEXT, fontSize: 16, fontWeight: '700', marginBottom: 4 },
  panelSub:   { color: MUTED, fontSize: 13, marginBottom: 14 },

  progressTrack: {
    height: 8, backgroundColor: '#1a1a1a', borderRadius: 4,
    marginBottom: 8, position: 'relative',
  },
  progressFill:  { height: 8, backgroundColor: GREEN, borderRadius: 4 },
  progressThumb: {
    position: 'absolute', top: -4,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: GREEN, marginLeft: -8,
  },
  timeText: { color: MUTED, fontSize: 12, textAlign: 'right', marginBottom: 14 },

  rowBtns:  { flexDirection: 'row', gap: 10, marginTop: 4 },
  btnPrimary: {
    backgroundColor: GREEN, borderRadius: 12,
    paddingVertical: 14, alignItems: 'center',
  },
  btnPrimary2: {
    flex: 1, backgroundColor: GREEN, borderRadius: 12,
    paddingVertical: 13, alignItems: 'center',
  },
  btnPrimaryText: { color: '#000', fontSize: 15, fontWeight: '700' },
  btnGhost: {
    flex: 1, borderWidth: 1, borderColor: BORDER,
    borderRadius: 12, paddingVertical: 13, alignItems: 'center',
  },
  btnGhostText: { color: '#aaa', fontSize: 15, fontWeight: '500' },

  frameRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 14, padding: 16, marginBottom: 16,
  },
  frameBtn:         { padding: 8 },
  frameBtnText:     { color: GREEN, fontSize: 26, fontWeight: '700' },
  frameBtnDisabled: { color: '#2a2a2a' },
  frameCenter:      { alignItems: 'center' },
  frameNumber:      { color: TEXT, fontSize: 22, fontWeight: '800' },
  frameOffset:      { color: MUTED, fontSize: 12, marginTop: 2 },

  offsetTrack: {
    height: 4, backgroundColor: '#1a1a1a', borderRadius: 2,
    marginBottom: 6, position: 'relative',
  },
  offsetThumb: {
    position: 'absolute', top: -6,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: GREEN, marginLeft: -8,
  },
  offsetLabels: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14 },
  offsetLabel:  { color: '#444', fontSize: 11 },

  backLink:     { alignItems: 'center', marginTop: 14 },
  backLinkText: { color: '#555', fontSize: 13 },
});
