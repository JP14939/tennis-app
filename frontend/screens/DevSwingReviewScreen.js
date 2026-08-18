import React, { useEffect, useRef, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator, Alert, Platform } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowWidth } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius, spacing } from '../theme';

// Free, no-Claude-cost manual review: Jack watches each raw wrist-velocity
// swing candidate himself and taps his own verdict, one at a time (built
// for reviewing on the phone away from a desk) -- POST /dev/swing-
// candidates/label logs it with the exact same shape a paid Claude
// verdict would have (source='user_flag'), so it feeds should_trust_
// bucket()/should_trust_student() identically, at zero API cost. Real
// shots also get a third step: mark the EXACT contact frame, training
// find_contact_frame() (previously untrained -- see
// contact_frame_training_log.py's module docstring).
//
// The student's own guesses (student_is_real_shot/student_shot_type/
// student_contact_frame_guess) are deliberately never shown here -- seeing
// them first would bias Jack's independent judgment, which is the whole
// point of this being a real teacher signal rather than a rubber stamp.
const SHOT_TYPES = [
  { value: 'forehand', label: 'Forehand' },
  { value: 'backhand', label: 'Backhand' },
  { value: 'serve',    label: 'Serve' },
];

// Same ±50-frame draggable fine-offset slider built for
// ContactMarkingScreen.js this session -- ported here rather than
// duplicated logic-first (the JSX/styles are small enough that copying
// them is simpler than extracting a shared component across two screens
// with otherwise-unrelated layouts).
const FINE_RADIUS = 50;
const IS_WEB = Platform.OS === 'web';

function formatTime(sec) {
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1);
  return `${m}:${s.padStart(4, '0')}`;
}

export default function DevSwingReviewScreen({ route, navigation }) {
  const { jobId } = route.params ?? {};
  const { token } = useAuth();
  const videoRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [index, setIndex] = useState(0);
  // 'outcome' -> 'shotType' -> 'contactRough' -> 'contactFrame'
  const [step, setStep] = useState('outcome');
  const [selectedShotType, setSelectedShotType] = useState(null);
  // The user's own rough pick (frame, from freely scrubbing the clip in the
  // 'contactRough' step) -- the fine ±FINE_RADIUS slider in 'contactFrame'
  // is anchored on THIS, not the automatic peak_frame guess, since the real
  // contact frame is routinely more than 50 frames from a noisy auto-guess.
  const [roughFrame, setRoughFrame] = useState(null);
  const [contactOffset, setContactOffset] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  // Only tracked for the 'contactRough' step's free scrub/play-pause UI --
  // every other step drives the video imperatively without reading state back.
  const [status, setStatus] = useState({});
  // Same immediate-drag-feedback pattern as ContactMarkingScreen.js's rough
  // scrubber -- the real progressFraction lags behind a finger drag until
  // the async seek's status update lands.
  const [scrubFraction, setScrubFraction] = useState(null);

  const windowWidth = useWindowWidth();
  const videoWidth = Math.min(windowWidth - 48, 500);
  const videoHeight = Math.round(videoWidth * 0.56);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/swing-candidates/${jobId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        setCandidates(data.candidates ?? []);
        setIndex(0);
        setDoneCount(0);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [jobId, token, reloadKey]);

  const current = candidates[index];
  const next = candidates[index + 1];
  const fps = current?.fps || 30;

  // Seek to just before the swing (so the windup is visible) and play,
  // every time the current candidate changes.
  useEffect(() => {
    if (!current || !videoRef.current) return;
    const startSec = Math.max(0, current.peak_time_sec - 1.2);
    videoRef.current.setPositionAsync(Math.round(startSec * 1000));
    videoRef.current.playAsync();
  }, [current]);

  const replay = useCallback(() => {
    if (!current || !videoRef.current) return;
    const startSec = Math.max(0, current.peak_time_sec - 1.2);
    videoRef.current.setPositionAsync(Math.round(startSec * 1000));
    videoRef.current.playAsync();
  }, [current]);

  // Fine contact-frame scrubbing: pause on the exact frame whenever
  // contactOffset changes, anchored on the user's own roughFrame pick (from
  // 'contactRough') rather than the automatic peak_frame guess -- same
  // pattern as ContactMarkingScreen.js's fine phase.
  useEffect(() => {
    if (step !== 'contactFrame' || roughFrame === null || !videoRef.current) return;
    videoRef.current.pauseAsync();
    const t = Math.max(0, (roughFrame + contactOffset) / fps);
    videoRef.current.setPositionAsync(Math.round(t * 1000));
  }, [contactOffset, step, roughFrame, fps]);

  const advance = () => {
    setStep('outcome');
    setSelectedShotType(null);
    setRoughFrame(null);
    setContactOffset(0);
    setDoneCount((c) => c + 1);
    setIndex((i) => i + 1);
  };

  const submit = async (isRealShot, shotType, contactFrame) => {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/dev/swing-candidates/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          ...current,
          is_real_shot: isRealShot,
          shot_type: shotType ?? null,
          contact_frame: contactFrame ?? null,
        }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      advance();
    } catch {
      Alert.alert('Could not save', 'That verdict failed to log — try again.');
    } finally {
      setSubmitting(false);
    }
  };

  const onRealShot = () => {
    playTapSound();
    setStep('shotType');
  };

  const onNotAShot = () => {
    playTapSound();
    submit(false, null, null);
  };

  const onShotType = (value) => {
    playTapSound();
    setSelectedShotType(value);
    setStep('contactRough');
  };

  // Captures wherever the video is currently paused/scrubbed to as the
  // rough anchor, then hands off to the fine ±FINE_RADIUS slider centered
  // on it -- mirrors ContactMarkingScreen.js's markWindow().
  const markContactWindow = async () => {
    playTapSound();
    await videoRef.current?.pauseAsync();
    // (status.positionMillis ?? 0) / 1000 -- same value the component-body
    // `currentTime` below derives, computed inline here since that binding
    // isn't declared until after this function (still correct by the time
    // this actually runs, but recomputing directly reads clearer).
    const pausedAtSec = (status.positionMillis ?? 0) / 1000;
    setRoughFrame(Math.round(pausedAtSec * fps));
    setContactOffset(0);
    setStep('contactFrame');
  };

  const backToRough = () => {
    videoRef.current?.playAsync();
    setStep('contactRough');
  };

  const confirmContactFrame = () => {
    if (roughFrame === null) return;
    playTapSound();
    submit(true, selectedShotType, roughFrame + contactOffset);
  };

  // Shared by both sliders below -- same track-width assumption
  // ContactMarkingScreen.js's scrub/offset handlers make.
  const trackWidth = windowWidth - 40;

  // Free-scrub math for the 'contactRough' step, same as
  // ContactMarkingScreen.js's onScrubMove.
  const duration = (status.durationMillis ?? 1000) / 1000;
  const currentTime = (status.positionMillis ?? 0) / 1000;
  const isPlaying = status.isPlaying ?? false;
  const progressFraction = scrubFraction ?? (duration > 0 ? Math.min(1, currentTime / duration) : 0);
  const onScrubMove = (e) => {
    const frac = Math.min(1, Math.max(0, e.nativeEvent.locationX / trackWidth));
    setScrubFraction(frac);
    videoRef.current?.setPositionAsync(Math.round(frac * duration * 1000));
  };
  const toggleRoughPlay = () => {
    if (isPlaying) videoRef.current?.pauseAsync();
    else videoRef.current?.playAsync();
  };

  // Same drag-to-scrub math as ContactMarkingScreen.js's offset slider.
  const onOffsetMove = (e) => {
    const frac = Math.min(1, Math.max(0, e.nativeEvent.locationX / trackWidth));
    const raw = Math.round(frac * (FINE_RADIUS * 2) - FINE_RADIUS);
    setContactOffset(Math.min(FINE_RADIUS, Math.max(-FINE_RADIUS, raw)));
  };

  if (loading) {
    return (
      <RequireAdmin navigation={navigation}>
        <SafeAreaView style={s.safe}>
          <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  if (loadError) {
    return (
      <RequireAdmin navigation={navigation}>
        <SafeAreaView style={s.safe}>
          <View style={s.centerFill}>
            <Text style={s.errorText}>Couldn't load swing candidates — check your connection.</Text>
            <TouchableOpacity style={s.retryBtn} onPress={() => setReloadKey((k) => k + 1)}>
              <Text style={s.retryBtnText}>Try again</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  if (!current) {
    return (
      <RequireAdmin navigation={navigation}>
        <SafeAreaView style={s.safe}>
          <View style={s.centerFill}>
            <Text style={s.doneTitle}>All done!</Text>
            <Text style={s.errorText}>
              {candidates.length === 0
                ? 'No swing candidates found for this match.'
                : `You reviewed all ${candidates.length} swing candidates. Nice work.`}
            </Text>
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  const contactFrameAbs = (roughFrame ?? 0) + contactOffset;
  const contactTimeSec = Math.max(0, contactFrameAbs / fps);

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <View style={s.progressRow}>
          <Text style={s.progressText}>Swing {index + 1} of {candidates.length}</Text>
          <Text style={s.progressSub}>Rally #{current.rally_id} · {formatTime(current.peak_time_sec)}</Text>
        </View>

        <TouchableOpacity
          activeOpacity={1}
          style={[s.videoWrap, { width: videoWidth, height: videoHeight, alignSelf: 'center' }]}
          onPress={step === 'contactRough' ? toggleRoughPlay : replay}
        >
          <PlatformVideo
            ref={videoRef}
            uri={`${API_BASE}${current.clip_url}`}
            width={videoWidth}
            height={videoHeight}
            onStatusUpdate={setStatus}
          />
        </TouchableOpacity>
        {step !== 'contactFrame' && step !== 'contactRough' && (
          <TouchableOpacity style={s.replayBtn} onPress={replay}>
            <Text style={s.replayBtnText}>↺ Replay</Text>
          </TouchableOpacity>
        )}

        {/* Invisible prefetch of the next candidate's clip so advancing
            doesn't start its download cold -- never rendered visibly or
            played, just mounted so PlatformVideo begins buffering it. */}
        {next && (
          <View style={s.prefetchWrap} pointerEvents="none">
            <PlatformVideo uri={`${API_BASE}${next.clip_url}`} width={1} height={1} />
          </View>
        )}

        {step === 'outcome' && (
          <View style={s.questionBlock}>
            <Text style={s.question}>Is this a real racket-to-ball strike?</Text>
            <Text style={s.questionSub}>Not camera fiddling, a ball bounce, tossing/catching, or just walking.</Text>
            <View style={s.answerRow}>
              <TouchableOpacity style={[s.answerBtn, s.answerBtnNo]} onPress={onNotAShot} disabled={submitting}>
                <Text style={s.answerBtnText}>No, not a shot</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.answerBtn, s.answerBtnYes]} onPress={onRealShot} disabled={submitting}>
                <Text style={s.answerBtnText}>Yes, real shot</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {step === 'shotType' && (
          <View style={s.questionBlock}>
            <Text style={s.question}>What shot type?</Text>
            <View style={s.answerRow}>
              {SHOT_TYPES.map((opt) => (
                <TouchableOpacity
                  key={opt.value}
                  style={[s.answerBtn, s.answerBtnType]}
                  onPress={() => onShotType(opt.value)}
                  disabled={submitting}
                >
                  <Text style={s.answerBtnText}>{opt.label}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {step === 'contactRough' && (
          <View style={s.questionBlock}>
            <Text style={s.question}>Find the contact frame</Text>
            <Text style={s.questionSub}>Tap video to play/pause · drag slider to scrub · tap "Mark" roughly on contact</Text>

            {IS_WEB
              ? React.createElement('input', {
                  type: 'range',
                  min: '0', max: '1', step: '0.001',
                  value: String(progressFraction),
                  onChange: (e) => {
                    const frac = parseFloat(e.target.value);
                    videoRef.current?.setPositionAsync(Math.round(frac * duration * 1000));
                  },
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

            <TouchableOpacity style={s.answerBtn2} onPress={markContactWindow} disabled={submitting}>
              <Text style={s.answerBtnText}>Mark contact window →</Text>
            </TouchableOpacity>
          </View>
        )}

        {step === 'contactFrame' && (
          <View style={s.questionBlock}>
            <Text style={s.question}>Pinpoint the exact contact frame</Text>
            <Text style={s.questionSub}>Drag until the racket is touching the ball, then confirm.</Text>

            <View style={s.frameRow}>
              <TouchableOpacity style={s.frameBtn} onPress={() => setContactOffset((o) => Math.max(o - 1, -FINE_RADIUS))}>
                <Text style={s.frameBtnText}>◀</Text>
              </TouchableOpacity>
              <View style={s.frameCenter}>
                <Text style={s.frameNumber}>Frame {contactFrameAbs}</Text>
                <Text style={s.frameOffset}>{contactOffset >= 0 ? '+' : ''}{contactOffset} · {contactTimeSec.toFixed(2)}s</Text>
              </View>
              <TouchableOpacity style={s.frameBtn} onPress={() => setContactOffset((o) => Math.min(o + 1, FINE_RADIUS))}>
                <Text style={s.frameBtnText}>▶</Text>
              </TouchableOpacity>
            </View>

            <View
              style={s.offsetTrackHitArea}
              onStartShouldSetResponder={() => true}
              onResponderGrant={onOffsetMove}
              onResponderMove={onOffsetMove}
            >
              <View style={s.offsetTrack}>
                <View style={[s.offsetThumb, { left: `${((contactOffset + FINE_RADIUS) / (FINE_RADIUS * 2)) * 92 + 2}%` }]} />
              </View>
            </View>
            <View style={s.offsetLabels}>
              <Text style={s.offsetLabel}>-{FINE_RADIUS}</Text>
              <Text style={s.offsetLabel}>0</Text>
              <Text style={s.offsetLabel}>+{FINE_RADIUS}</Text>
            </View>

            <TouchableOpacity style={s.answerBtn2} onPress={confirmContactFrame} disabled={submitting}>
              <Text style={s.answerBtnText}>{submitting ? 'Saving...' : 'Confirm contact frame ✓'}</Text>
            </TouchableOpacity>

            <TouchableOpacity style={s.backLink} onPress={backToRough}>
              <Text style={s.backLinkText}>← Back to rough selection</Text>
            </TouchableOpacity>
          </View>
        )}
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg, padding: spacing.xl, paddingTop: 24 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },

  progressRow: { marginBottom: 14, alignItems: 'center' },
  progressText: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold },
  progressSub: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  videoWrap: { borderRadius: radius.lg, overflow: 'hidden', backgroundColor: '#000' },
  replayBtn: { alignSelf: 'center', marginTop: 10, paddingVertical: 6, paddingHorizontal: 14 },
  replayBtnText: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },
  prefetchWrap: { position: 'absolute', width: 1, height: 1, opacity: 0 },

  progressTrack: {
    height: 8, backgroundColor: colors.border, borderRadius: 4,
    marginBottom: 8, position: 'relative',
  },
  progressFill: { height: 8, backgroundColor: colors.primary, borderRadius: 4 },
  progressThumb: {
    position: 'absolute', top: -4,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.primary, marginLeft: -8,
  },
  timeText: { color: colors.muted, fontSize: 12, textAlign: 'right', marginBottom: 14, fontFamily: fonts.regular },

  backLink: { alignItems: 'center', marginTop: 14 },
  backLinkText: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },

  questionBlock: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 18, marginTop: 18,
  },
  question: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 4, textAlign: 'center' },
  questionSub: { color: colors.muted, fontSize: 12, lineHeight: 17, textAlign: 'center', marginBottom: 16, fontFamily: fonts.regular },
  answerRow: { flexDirection: 'row', gap: 10 },
  answerBtn: { flex: 1, borderRadius: radius.lg, paddingVertical: 16, alignItems: 'center' },
  answerBtn2: { borderRadius: radius.lg, paddingVertical: 16, alignItems: 'center', backgroundColor: colors.primary, marginTop: 4 },
  answerBtnYes: { backgroundColor: colors.primary },
  answerBtnNo: { backgroundColor: colors.coral },
  answerBtnType: { backgroundColor: colors.primary },
  answerBtnText: { color: colors.white, fontSize: 14, fontFamily: fonts.extrabold },

  frameRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 16,
  },
  frameBtn: { padding: 8 },
  frameBtnText: { color: colors.primary, fontSize: 26, fontFamily: fonts.extrabold },
  frameCenter: { alignItems: 'center' },
  frameNumber: { color: colors.ink, fontSize: 20, fontFamily: fonts.extrabold },
  frameOffset: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },

  offsetTrackHitArea: { paddingVertical: 14, marginTop: -14, marginBottom: -8 },
  offsetTrack: { height: 4, backgroundColor: colors.border, borderRadius: 2, position: 'relative' },
  offsetThumb: {
    position: 'absolute', top: -6,
    width: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.primary, marginLeft: -8,
  },
  offsetLabels: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  offsetLabel: { color: colors.muted, fontSize: 11, fontFamily: fonts.regular },

  doneTitle: { color: colors.primary, fontSize: 22, fontFamily: fonts.extrabold, marginBottom: 10 },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', lineHeight: 19, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11, marginTop: 14 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
