import { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  PanResponder, Animated, Dimensions,
} from 'react-native';
import PlatformVideo from '../components/PlatformVideo';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

// Shared relative-time window around contact (t=0) that both videos are
// scrubbed over. Fixed rather than derived per-clip -- swing clips in this
// app are consistently a few seconds long, and a fixed window keeps the
// scrubber's meaning (seconds from contact) the same across every pair of
// videos instead of rescaling per comparison.
const T_MIN = -1.0;
const T_MAX = 1.5;

const videoWidth = Math.min(Dimensions.get('window').width - 48, 460);
const videoHeight = Math.round(videoWidth * 1.5);

function VideoPane({ label, uri, videoRef, onStatusUpdate }) {
  return (
    <View style={p.wrap}>
      <Text style={p.label}>{label}</Text>
      <View style={p.videoBox}>
        <PlatformVideo
          ref={videoRef}
          uri={uri}
          width={videoWidth / 2 - 10}
          height={(videoHeight / 2) - 10}
          onStatusUpdate={onStatusUpdate}
        />
      </View>
    </View>
  );
}
const p = StyleSheet.create({
  wrap: { flex: 1 },
  label: { color: MUTED, fontSize: 12, fontWeight: '700', marginBottom: 6, textAlign: 'center' },
  videoBox: { borderRadius: 12, overflow: 'hidden', backgroundColor: '#000' },
});

export default function SyncCompareScreen({ route, navigation }) {
  const {
    videoAUrl, videoBUrl, croppedAUrl, croppedBUrl,
    contactASec = 0, contactBSec = 0,
    labelA = 'Reference', labelB = 'You',
  } = route.params ?? {};

  const videoARef = useRef(null);
  const videoBRef = useRef(null);

  const bothCropped = !!(croppedAUrl && croppedBUrl);
  const [showCropped, setShowCropped] = useState(bothCropped);
  const uriA = showCropped && croppedAUrl ? croppedAUrl : videoAUrl;
  const uriB = showCropped && croppedBUrl ? croppedBUrl : videoBUrl;

  const [t, setT] = useState(0); // seconds relative to contact, shared by both videos
  const [isPlaying, setIsPlaying] = useState(false);
  const trackWidth = useRef(0);
  const handleX = useRef(new Animated.Value(0)).current;

  const setHandleFromT = (newT) => {
    const frac = (newT - T_MIN) / (T_MAX - T_MIN);
    handleX.setValue(Math.max(0, Math.min(1, frac)) * trackWidth.current);
  };

  const seekBoth = async (newT) => {
    const clamped = Math.max(T_MIN, Math.min(T_MAX, newT));
    setT(clamped);
    setHandleFromT(clamped);
    await Promise.all([
      videoARef.current?.setPositionAsync(Math.max(0, (contactASec + clamped) * 1000)),
      videoBRef.current?.setPositionAsync(Math.max(0, (contactBSec + clamped) * 1000)),
    ]);
  };

  useEffect(() => {
    seekBoth(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uriA, uriB]);

  // Uses locationX (relative to the track view itself) at gesture start,
  // then tracks movement via the gesture's own dx delta -- avoids needing
  // the track's absolute screen position, which isn't resolved the same
  // way on web vs. native.
  const touchStartX = useRef(0);
  const handleTouch = (localX) => {
    if (!trackWidth.current) return;
    const clamped = Math.max(0, Math.min(trackWidth.current, localX));
    const frac = clamped / trackWidth.current;
    seekBoth(T_MIN + frac * (T_MAX - T_MIN));
  };
  const scrubResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: async (evt) => {
        if (isPlaying) {
          setIsPlaying(false);
          await Promise.all([videoARef.current?.pauseAsync(), videoBRef.current?.pauseAsync()]);
        }
        touchStartX.current = evt.nativeEvent.locationX;
        handleTouch(touchStartX.current);
      },
      onPanResponderMove: (evt, gesture) => handleTouch(touchStartX.current + gesture.dx),
    })
  ).current;

  const togglePlay = async () => {
    if (isPlaying) {
      setIsPlaying(false);
      await Promise.all([videoARef.current?.pauseAsync(), videoBRef.current?.pauseAsync()]);
    } else {
      setIsPlaying(true);
      await Promise.all([videoARef.current?.playAsync(), videoBRef.current?.playAsync()]);
    }
  };

  // Drives the scrubber handle during playback (visual feedback only --
  // seeking is what actually keeps the two videos aligned; continuous
  // playback is only approximately synced, since the two clips can differ
  // in length/tempo after the shared start).
  const onBStatusUpdate = (status) => {
    if (!isPlaying || !status.isLoaded) return;
    if (!status.isPlaying) {
      setIsPlaying(false);
      return;
    }
    const newT = status.positionMillis / 1000 - contactBSec;
    setT(newT);
    setHandleFromT(newT);
  };

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={s.backText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>Side-by-side</Text>
        {bothCropped ? (
          <TouchableOpacity onPress={() => setShowCropped((v) => !v)}>
            <Text style={s.toggleText}>{showCropped ? 'Original' : 'Cropped'}</Text>
          </TouchableOpacity>
        ) : (
          <View style={{ width: 60 }} />
        )}
      </View>

      <View style={s.videosRow}>
        <VideoPane label={labelA} uri={uriA} videoRef={videoARef} onStatusUpdate={() => {}} />
        <VideoPane label={labelB} uri={uriB} videoRef={videoBRef} onStatusUpdate={onBStatusUpdate} />
      </View>

      <Text style={s.tHint}>{t >= 0 ? '+' : ''}{t.toFixed(2)}s from contact</Text>

      <View
        style={s.track}
        onLayout={(e) => {
          trackWidth.current = e.nativeEvent.layout.width;
          setHandleFromT(t);
        }}
        {...scrubResponder.panHandlers}
      >
        <View style={s.trackLine} />
        <View style={s.contactMark} />
        <Animated.View style={[s.handle, { transform: [{ translateX: handleX }] }]} />
      </View>

      <TouchableOpacity style={s.playBtn} onPress={togglePlay}>
        <Text style={s.playBtnText}>{isPlaying ? '⏸ Pause' : '▶ Play both'}</Text>
      </TouchableOpacity>
      <Text style={s.playNote}>
        Drag the scrubber to compare frame-by-frame — dragging keeps both swings' contact
        moments exactly aligned. Play starts both together but they may drift apart if the
        clips differ in length.
      </Text>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
  },
  backText: { color: MUTED, fontSize: 14, fontWeight: '600' },
  title: { color: TEXT, fontSize: 16, fontWeight: '700' },
  toggleText: { color: GREEN, fontSize: 13, fontWeight: '700' },

  videosRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, marginTop: 8 },

  tHint: { color: MUTED, fontSize: 12, textAlign: 'center', marginTop: 14 },

  track: {
    height: 40, marginHorizontal: 28, marginTop: 8, justifyContent: 'center',
  },
  trackLine: {
    position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
  },
  contactMark: {
    position: 'absolute', left: `${((0 - T_MIN) / (T_MAX - T_MIN)) * 100}%`,
    width: 2, height: 16, backgroundColor: '#f87171', marginLeft: -1,
  },
  handle: {
    position: 'absolute', left: -11, width: 22, height: 22, borderRadius: 11,
    backgroundColor: GREEN, borderWidth: 2, borderColor: DARK,
  },

  playBtn: {
    backgroundColor: GREEN, borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginHorizontal: 20, marginTop: 20,
  },
  playBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
  playNote: { color: MUTED, fontSize: 11.5, lineHeight: 16, textAlign: 'center', paddingHorizontal: 28, marginTop: 12 },
});
