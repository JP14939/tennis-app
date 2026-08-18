import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  Dimensions, Alert, Platform, ScrollView, LayoutAnimation, UIManager,
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import PlatformVideo from '../components/PlatformVideo';
import FenceTutorialContent from '../components/FenceTutorialContent';
import LiveCalibrationCamera from '../components/LiveCalibrationCamera';
import { storage } from '../utils/storage';
import { playTapSound } from '../utils/sounds';
import { API_BASE } from '../config/api';
import { colors, fonts, radius, spacing } from '../theme';
import CourtBackground from '../components/CourtBackground';
import { BackChevronIcon, VideoIcon, CameraIcon } from '../components/icons';

const ASSUMED_FPS = 30;
const FINE_RADIUS = 50;
const SHOT_TYPES  = ['forehand', 'backhand', 'serve'];
const IS_WEB      = Platform.OS === 'web';
const TUTORIAL_SEEN_KEY = 'tennisai_seen_fence_tutorial';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

async function checkCameraSetup(videoUri) {
  const formData = new FormData();
  if (Platform.OS === 'web') {
    const response = await fetch(videoUri);
    const blob = await response.blob();
    formData.append('video', blob, 'swing.mp4');
  } else {
    formData.append('video', { uri: videoUri, name: 'swing.mp4', type: 'video/mp4' });
  }
  const response = await fetch(`${API_BASE}/api/check-setup`, { method: 'POST', body: formData });
  return response.json();
}

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
  // Immediate visual feedback while dragging the rough-scrub slider on
  // native -- the real progressFraction only updates once the video's
  // async seek resolves and the status callback fires, which lags behind
  // a finger drag. Cleared on release so display falls back to the
  // (by-then-settled) real position.
  const [scrubFraction, setScrubFraction] = useState(null);
  const [calibration, setCalibration] = useState({ status: 'idle' }); // idle | checking | done
  const [viewDirectionHint, setViewDirectionHint] = useState(null); // 'front' | 'back' | null (diagonal/side, no hint)
  const [filmingTutorialVariant, setFilmingTutorialVariant] = useState(null); // set to open the tutorial from the filming-position screen
  const videoRef  = useRef(null);
  const slowMoRef = useRef(null);
  const dims = useDims();

  // Gate the fence-mount tutorial before the first video pick of a fresh session
  // (skip it if a video was already supplied, e.g. the 1v1 comparison flow).
  useEffect(() => {
    if (uri) return;
    (async () => {
      const seen = await storage.getItem(TUTORIAL_SEEN_KEY);
      if (!seen) setPhase('tutorial');
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
      useVideo(result.assets[0].uri);
    }
  };

  // Shared by both entry points (library pick and live recording) -- lands
  // in the same 'rough' phase with the same post-record authoritative
  // check, so everything downstream is identical regardless of source.
  const useVideo = (videoUri) => {
    setUri(videoUri);
    setPhase('rough');
    setCalibration({ status: 'checking' });
    checkCameraSetup(videoUri)
      .then((data) => setCalibration({ status: 'done', ...data }))
      .catch(() => setCalibration({ status: 'done', ok: null, message: 'Could not check camera setup.' }));
  };

  const markWindow = async () => {
    await pause();
    if (!IS_WEB) LayoutAnimation.easeInEaseOut();
    setRoughTime(currentTime);
    setFineOffset(0);
    setPhase('fine');
  };

  const backToRough = () => {
    if (!IS_WEB) LayoutAnimation.easeInEaseOut();
    play();
    setPhase('rough');
  };

  const prevFrame = () => setFineOffset(o => Math.max(o - 1, -FINE_RADIUS));
  const nextFrame = () => setFineOffset(o => Math.min(o + 1, FINE_RADIUS));

  // Shared by both slider drag handlers -- maps a touch's x position within
  // the panel to a value, given the panel's horizontal padding (20 either
  // side, same assumption progressTrack already made).
  const trackWidth = dims.width - 40;
  const fractionFromLocationX = (x) => Math.min(1, Math.max(0, x / trackWidth));
  const onScrubMove = (e) => {
    const frac = fractionFromLocationX(e.nativeEvent.locationX);
    setScrubFraction(frac);
    seekTo(frac * duration);
  };
  const onOffsetMove = (e) => {
    const frac = fractionFromLocationX(e.nativeEvent.locationX);
    const raw = Math.round(frac * (FINE_RADIUS * 2) - FINE_RADIUS);
    setFineOffset(Math.min(FINE_RADIUS, Math.max(-FINE_RADIUS, raw)));
  };

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
    // Clamped the same way the seek call sites already are (lines ~80, 88) --
    // scrubbing fineOffset negative near the start of a clip could otherwise
    // submit a negative contactFrame/contactTimeSec downstream.
    const fineT = Math.max(0, roughTime + fineOffset / ASSUMED_FPS);
    const frame = Math.round(fineT * ASSUMED_FPS);
    await pause();
    const marked = { videoUri: uri, shotType, contactFrame: frame, contactTimeSec: fineT, viewDirectionHint };
    // Reused by flows that need contact marked on more than one video (e.g.
    // 1v1 comparison) — they pass onConfirmed instead of relying on the
    // default single-video "go to Results" behaviour.
    if (route.params?.onConfirmed) {
      route.params.onConfirmed(marked);
      return;
    }
    // practiceStepId passes straight through from LessonDetailScreen's
    // navigation params so ResultsScreen can link the finished analysis
    // back to the lesson routine step it was practice for.
    navigation.navigate('Results', route.params?.practiceStepId
      ? { ...marked, practiceStepId: route.params.practiceStepId }
      : marked);
  };

  // ── Layout ────────────────────────────────────────────────────────────────
  const progressFraction = scrubFraction ?? (duration > 0 ? Math.min(1, currentTime / duration) : 0);
  const fineT        = roughTime !== null ? Math.max(0, roughTime + fineOffset / ASSUMED_FPS) : 0;
  const fineFrameAbs = Math.round(fineT * ASSUMED_FPS);
  const videoH       = Math.round(Math.min(dims.width * 0.56, dims.height * 0.42));

  // ── TUTORIAL ──────────────────────────────────────────────────────────────
  if (phase === 'tutorial') {
    return (
      <SafeAreaView style={s.safe}>
        <FenceTutorialContent
          onDismiss={async () => {
            await storage.setItem(TUTORIAL_SEEN_KEY, '1');
            setPhase('pick');
          }}
        />
      </SafeAreaView>
    );
  }

  // ── PICK ──────────────────────────────────────────────────────────────────
  if (phase === 'pick') {
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <ScrollView contentContainerStyle={s.pickScroll} showsVerticalScrollIndicator={false}>
          <TouchableOpacity style={s.backLinkTop} onPress={() => navigation.goBack()}>
            <BackChevronIcon size={13} color={colors.muted} />
            <Text style={s.backLinkTopText}>Home</Text>
          </TouchableOpacity>

          <Text style={s.h1}>Analyse your swing</Text>
          <Text style={s.sub}>Upload a 10–30 second video of your shot.</Text>

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

          <TouchableOpacity style={s.uploadBtn} onPress={pickVideo} activeOpacity={0.9}>
            <View style={s.uploadIconWrap}><VideoIcon size={22} color={colors.primary} /></View>
            <Text style={s.uploadBtnText}>Choose video from library</Text>
            <Text style={s.uploadBtnSub}>MP4 · MOV · any resolution</Text>
          </TouchableOpacity>

          {!IS_WEB && (
            <TouchableOpacity style={[s.uploadBtn, s.recordBtn]} onPress={() => setPhase('filming-position')} activeOpacity={0.9}>
              <View style={[s.uploadIconWrap, s.recordIconWrap]}><CameraIcon size={22} color={colors.mutedDark} /></View>
              <Text style={s.uploadBtnText}>Record now</Text>
              <Text style={s.uploadBtnSub}>Live camera positioning guide</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity style={s.tipLink} onPress={() => setPhase('tutorial')}>
            <Text style={s.tipLinkText}>How to mount your phone (rubber band method)</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── FILMING TUTORIAL (opened from the position picker below) ───────────────
  if (phase === 'filming-tutorial') {
    return (
      <SafeAreaView style={s.safe}>
        <FenceTutorialContent
          variant={filmingTutorialVariant}
          onDismiss={() => setPhase('filming-position')}
        />
      </SafeAreaView>
    );
  }

  // ── FILMING POSITION ─────────────────────────────────────────────────────
  // Where the camera is physically mounted determines which way the swing
  // is seen from (front-on at the net vs. from-behind at the fence) — both
  // land in the pro database, but the two are mirrored in pose landmarks,
  // so knowing which one this is helps match against the right clips.
  if (phase === 'filming-position') {
    const options = [
      {
        key: 'front', title: 'At the net',
        sub: "Front-on — we'll see your face and the front of your swing",
      },
      {
        key: 'back', title: 'Behind the baseline fence',
        sub: "From behind — we'll see your back as you swing",
      },
      {
        key: null, title: 'Beside the court',
        sub: 'Diagonal or side-on view',
      },
    ];
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <ScrollView contentContainerStyle={s.pickScroll} showsVerticalScrollIndicator={false}>
          <TouchableOpacity style={s.backLinkTop} onPress={() => setPhase('pick')}>
            <BackChevronIcon size={13} color={colors.muted} />
            <Text style={s.backLinkTopText}>Back</Text>
          </TouchableOpacity>

          <Text style={s.h1}>Where's your camera?</Text>
          <Text style={s.sub}>This helps us match you against the right pro footage.</Text>

          {options.map((opt) => (
            <TouchableOpacity
              key={opt.title}
              style={s.positionCard}
              activeOpacity={0.85}
              onPress={() => { setViewDirectionHint(opt.key); setPhase('record'); }}
            >
              <View style={{ flex: 1 }}>
                <Text style={s.positionTitle}>{opt.title}</Text>
                <Text style={s.positionSub}>{opt.sub}</Text>
              </View>
            </TouchableOpacity>
          ))}

          <View style={s.tipLinkRow}>
            <TouchableOpacity onPress={() => { setFilmingTutorialVariant('net'); setPhase('filming-tutorial'); }}>
              <Text style={s.tipLinkText}>Net setup tips</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => { setFilmingTutorialVariant('fence'); setPhase('filming-tutorial'); }}>
              <Text style={s.tipLinkText}>Fence setup tips</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── RECORD ────────────────────────────────────────────────────────────────
  if (phase === 'record') {
    return (
      <LiveCalibrationCamera
        shotType={shotType}
        onCancel={() => setPhase('pick')}
        onRecorded={useVideo}
      />
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

            {calibration.status === 'checking' && (
              <Text style={s.calibChecking}>Checking camera setup…</Text>
            )}
            {calibration.status === 'done' && calibration.message && (() => {
              // elevation_status can warn ("possibly_elevated") even when ok
              // is true (framing is fine, height is the separate concern) —
              // don't let a green checkmark contradict a height warning.
              const elevationWarn = calibration.elevation_status === 'possibly_elevated';
              const isWarn = calibration.ok === false || elevationWarn;
              return (
                <Text style={[s.calibMsg, isWarn && s.calibWarn]}>
                  {isWarn ? '⚠ ' : calibration.ok === true ? '✓ ' : ''}{calibration.message}
                </Text>
              );
            })()}

            {IS_WEB
              ? React.createElement('input', {
                  type: 'range',
                  min: '0', max: '1', step: '0.001',
                  value: String(progressFraction),
                  onChange: (e) => seekTo(parseFloat(e.target.value) * duration),
                  style: {
                    width: '100%', accentColor: colors.primary,
                    marginBottom: '8px', cursor: 'pointer', height: '20px',
                  },
                })
              : (
                <View
                  style={s.progressTrack}
                  onStartShouldSetResponder={() => true}
                  onResponderGrant={onScrubMove}
                  onResponderMove={onScrubMove}
                  onResponderRelease={() => setScrubFraction(null)}
                  onResponderTerminate={() => setScrubFraction(null)}
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
            <Text style={s.panelSub}>Drag the slider or tap ◀ / ▶ to step one frame at a time</Text>

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

            {IS_WEB
              ? React.createElement('input', {
                  type: 'range',
                  min: String(-FINE_RADIUS), max: String(FINE_RADIUS), step: '1',
                  value: String(fineOffset),
                  onChange: (e) => setFineOffset(parseInt(e.target.value, 10)),
                  style: {
                    width: '100%', accentColor: colors.primary,
                    marginBottom: '8px', cursor: 'pointer', height: '20px',
                  },
                })
              : (
                <View
                  style={s.offsetTrackHitArea}
                  onStartShouldSetResponder={() => true}
                  onResponderGrant={onOffsetMove}
                  onResponderMove={onOffsetMove}
                >
                  <View style={s.offsetTrack}>
                    <View style={[s.offsetThumb, {
                      left: `${((fineOffset + FINE_RADIUS) / (FINE_RADIUS * 2)) * 92 + 2}%`
                    }]} />
                  </View>
                </View>
              )
            }
            <View style={s.offsetLabels}>
              <Text style={s.offsetLabel}>-{FINE_RADIUS}</Text>
              <Text style={s.offsetLabel}>0</Text>
              <Text style={s.offsetLabel}>+{FINE_RADIUS}</Text>
            </View>

            <View style={s.rowBtns}>
              <TouchableOpacity style={s.btnGhost} onPress={playSlowMo}>
                <Text style={s.btnGhostText}>0.25× slow-mo</Text>
              </TouchableOpacity>
              <TouchableOpacity style={s.btnPrimary2} onPress={() => { playTapSound(); confirmFrame(); }}>
                <Text style={s.btnPrimaryText}>This is it ✓</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={s.backLink} onPress={backToRough}>
              <Text style={s.backLinkText}>← Back to rough selection</Text>
            </TouchableOpacity>
          </>
        )}
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },

  pickScroll: { padding: spacing.xl, paddingTop: 60, flexGrow: 1 },
  backLinkTop: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 20, alignSelf: 'flex-start' },
  backLinkTopText: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold },
  h1:  { color: colors.ink, fontSize: 30, fontFamily: fonts.serifItalic, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 14, lineHeight: 21, marginBottom: 26, fontFamily: fonts.regular },

  fieldLabel: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.bold, marginBottom: 10, textTransform: 'uppercase', letterSpacing: 0.3 },
  shotRow: { flexDirection: 'row', gap: 9, marginBottom: 26 },
  shotPill: {
    flex: 1, backgroundColor: colors.surface,
    borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center',
  },
  shotPillActive:     { backgroundColor: colors.primary },
  shotPillText:       { color: colors.ink, fontSize: 13, fontFamily: fonts.semibold },
  shotPillTextActive: { color: colors.white, fontFamily: fonts.bold },

  uploadBtn: {
    backgroundColor: colors.surface, borderWidth: 1.5, borderColor: colors.borderDashed, borderStyle: 'dashed',
    borderRadius: radius.xl, padding: 30, alignItems: 'center', gap: 4,
  },
  uploadIconWrap: {
    width: 52, height: 52, borderRadius: 26, backgroundColor: colors.primarySoft,
    alignItems: 'center', justifyContent: 'center', marginBottom: 12,
  },
  recordIconWrap: { backgroundColor: colors.border },
  uploadBtnText: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold },
  uploadBtnSub:  { color: colors.muted, fontSize: 12.5, fontFamily: fonts.regular },
  recordBtn:     { marginTop: 12, borderStyle: 'solid', borderColor: colors.border },

  tipLink:     { alignItems: 'center', marginTop: 18 },
  tipLinkText: { color: colors.muted, fontSize: 12.5, fontFamily: fonts.semibold },
  tipLinkRow:  { flexDirection: 'row', justifyContent: 'center', gap: 24, marginTop: 22 },

  positionCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: 18, marginBottom: 12,
  },
  positionTitle: { color: colors.ink, fontSize: 15.5, fontFamily: fonts.bold, marginBottom: 3 },
  positionSub:   { color: colors.muted, fontSize: 12.5, fontFamily: fonts.regular },

  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.35)', fontSize: 52 },

  panel:      { backgroundColor: colors.bg, padding: 20, paddingTop: 18, flex: 1 },
  panelTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 4 },
  panelSub:   { color: colors.muted, fontSize: 13, marginBottom: 14, fontFamily: fonts.regular },
  calibChecking: { color: colors.muted, fontSize: 12, marginBottom: 10, fontFamily: fonts.regular },
  calibMsg:      { color: colors.primary, fontSize: 12, marginBottom: 10, lineHeight: 17, fontFamily: fonts.regular },
  calibWarn:     { color: colors.gold },

  progressTrack: {
    height: 8, backgroundColor: colors.border, borderRadius: 4,
    marginBottom: 8, position: 'relative',
  },
  progressFill:  { height: 8, backgroundColor: colors.primary, borderRadius: 4 },
  progressThumb: {
    position: 'absolute', top: -4,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.primary, marginLeft: -8,
  },
  timeText: { color: colors.muted, fontSize: 12, textAlign: 'right', marginBottom: 14, fontFamily: fonts.regular },

  rowBtns:  { flexDirection: 'row', gap: 10, marginTop: 4 },
  btnPrimary: {
    backgroundColor: colors.primary, borderRadius: radius.md,
    paddingVertical: 14, alignItems: 'center',
  },
  btnPrimary2: {
    flex: 1, backgroundColor: colors.primary, borderRadius: radius.md,
    paddingVertical: 13, alignItems: 'center',
  },
  btnPrimaryText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
  btnGhost: {
    flex: 1, backgroundColor: colors.surface,
    borderRadius: radius.md, paddingVertical: 13, alignItems: 'center',
  },
  btnGhostText: { color: colors.mutedDark, fontSize: 15, fontFamily: fonts.medium },

  frameRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colors.surface,
    borderRadius: radius.lg, padding: 16, marginBottom: 16,
  },
  frameBtn:         { padding: 8 },
  frameBtnText:     { color: colors.primary, fontSize: 26, fontFamily: fonts.bold },
  frameBtnDisabled: { color: colors.divider },
  frameCenter:      { alignItems: 'center' },
  frameNumber:      { color: colors.ink, fontSize: 22, fontFamily: fonts.extrabold },
  frameOffset:      { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },

  offsetTrackHitArea: { paddingVertical: 14, marginTop: -14, marginBottom: -8 },
  offsetTrack: {
    height: 4, backgroundColor: colors.border, borderRadius: 2,
    position: 'relative',
  },
  offsetThumb: {
    position: 'absolute', top: -6,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.primary, marginLeft: -8,
  },
  offsetLabels: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14 },
  offsetLabel:  { color: colors.divider, fontSize: 11, fontFamily: fonts.regular },

  backLink:     { alignItems: 'center', marginTop: 14 },
  backLinkText: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },
});
