import { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet, SafeAreaView,
  ScrollView, PanResponder, Animated, Alert,
} from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import PlatformVideo from '../components/PlatformVideo';
import SkeletonOverlay from '../components/SkeletonOverlay';
import RacketPathOverlay from '../components/RacketPathOverlay';
import { playTapSound } from '../utils/sounds';
import AnnotationCanvas from '../components/AnnotationCanvas';
import { useAuth } from '../context/AuthContext';
import { getNotes, addNote } from '../api/coach';
import { getAnnotations, saveAnnotations } from '../api/annotations';
import { useWindowWidth } from '../utils/responsive';

const GREEN  = '#4ade80';
const GOLD   = '#fbbf24';
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

// Falls back to phase_breakdown.py's own PHASE_TARGET_T constants
// (backswing -0.5, contact 0.0, followthrough 1.0) if the backend response
// didn't include phase_markers (e.g. an older cached result) -- keeps this
// screen working either way, backend stays the source of truth when present.
const DEFAULT_PHASE_MARKERS = [
  { label: 'Backswing', t: -0.5 },
  { label: 'Contact', t: 0 },
  { label: 'Follow-through', t: 1.0 },
];

const SPEEDS = [0.5, 1, 2];

// Zoom range for the slider (see the zoom-slider block in the main
// component) -- 1.0 = no zoom (full original frame), 2.5 = closest in.
const ZOOM_MIN = 1.0;
const ZOOM_MAX = 2.5;
const ZOOM_DEFAULT = 1.6;

const TOOLS = ['pen', 'line', 'arrow', 'circle'];
const TOOL_LABELS = { pen: '✎ Pen', line: '╱ Line', arrow: '↗ Arrow', circle: '○ Circle' };
const ANNOTATION_COLORS = ['#f87171', '#fbbf24', '#4ade80', '#60a5fa', '#ffffff'];

function VideoPane({
  label, uri, videoRef, onStatusUpdate, overlayTrajectory, overlayTimeSec, overlayColor, showOverlay,
  racketTrajectory, racketColor, showRacketPath, isPlaying, paneWidth, paneHeight,
  zoom, panX, panY, onZoomPanChange, annotationRef, annotateActive, tool, annColor, onClearAnnotation, onUndoAnnotation,
}) {
  const zoomedWidth = paneWidth * zoom;
  const zoomedHeight = paneHeight * zoom;
  const offsetX = -(zoomedWidth - paneWidth) / 2 + panX;
  const offsetY = -(zoomedHeight - paneHeight) / 2 + panY;

  // The video renders with resizeMode/objectFit CONTAIN inside the
  // zoomedWidth x zoomedHeight box -- when the video's real aspect ratio
  // doesn't match that box, CONTAIN letterboxes it (black bars), and the
  // actual visible content sits in a smaller, offset sub-rect. Overlay
  // coordinates are normalized against the full original video frame, so
  // they need to be mapped against that content sub-rect, not the raw box --
  // otherwise every point is off by the letterbox offset (this was the
  // "skeleton is too high" bug: purely a mapping bug, not a data bug).
  const [videoSize, setVideoSize] = useState(null);
  const [videoError, setVideoError] = useState(null);
  const content = useMemo(() => {
    if (!videoSize?.width || !videoSize?.height) {
      return { width: zoomedWidth, height: zoomedHeight, left: 0, top: 0 };
    }
    const boxRatio = zoomedWidth / zoomedHeight;
    const videoRatio = videoSize.width / videoSize.height;
    if (videoRatio > boxRatio) {
      const h = zoomedWidth / videoRatio;
      return { width: zoomedWidth, height: h, left: 0, top: (zoomedHeight - h) / 2 };
    }
    const w = zoomedHeight * videoRatio;
    return { width: w, height: zoomedHeight, left: (zoomedWidth - w) / 2, top: 0 };
  }, [videoSize, zoomedWidth, zoomedHeight]);

  // Gesture-start baselines -- pinch/pan report cumulative scale/translation
  // since the gesture began, not deltas, so each update is computed as
  // "value at gesture start" combined with the gesture's own cumulative
  // change, rather than accumulating deltas onto the live (already-changing)
  // zoom/pan state.
  const startZoom = useRef(zoom);
  const startPan = useRef({ x: panX, y: panY });

  const pinchGesture = Gesture.Pinch()
    .enabled(!annotateActive)
    .onStart(() => { startZoom.current = zoom; })
    .onUpdate((e) => {
      const newZoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, startZoom.current * e.scale));
      onZoomPanChange(newZoom, panX, panY);
    });

  const panGesture = Gesture.Pan()
    .enabled(!annotateActive)
    .onStart(() => { startPan.current = { x: panX, y: panY }; })
    .onUpdate((e) => {
      onZoomPanChange(zoom, startPan.current.x + e.translationX, startPan.current.y + e.translationY);
    });

  const composedGesture = Gesture.Simultaneous(pinchGesture, panGesture);

  return (
    <View style={p.wrap}>
      <Text style={p.label}>{label}</Text>
      <GestureDetector gesture={composedGesture}>
        <View style={[p.videoBox, { width: paneWidth, height: paneHeight }]}>
          <View style={{ position: 'absolute', left: offsetX, top: offsetY, width: zoomedWidth, height: zoomedHeight }}>
            <PlatformVideo
              ref={videoRef}
              uri={uri}
              width={zoomedWidth}
              height={zoomedHeight}
              onStatusUpdate={onStatusUpdate}
              highFrequencyUpdates={(showOverlay || showRacketPath) && isPlaying}
              onVideoSize={setVideoSize}
              onError={setVideoError}
            />
            {(showOverlay || showRacketPath) && (
              <View style={{ position: 'absolute', left: content.left, top: content.top, width: content.width, height: content.height }}>
                {showOverlay && (
                  <SkeletonOverlay
                    trajectory={overlayTrajectory}
                    currentTimeSec={overlayTimeSec}
                    width={content.width}
                    height={content.height}
                    color={overlayColor}
                  />
                )}
                {showRacketPath && (
                  <RacketPathOverlay
                    trajectory={racketTrajectory}
                    currentTimeSec={overlayTimeSec}
                    width={content.width}
                    height={content.height}
                    color={racketColor}
                  />
                )}
              </View>
            )}
            {videoError && (
              <View style={p.errorOverlay} pointerEvents="none">
                <Text style={p.errorText}>Video unavailable</Text>
              </View>
            )}
          </View>
          {/* Drawn in fixed screen-space (the visible pane box), independent
              of zoom/pan -- marks stay put on screen even as the video moves
              underneath, rather than being tied to the underlying video's own
              (zoomable/pannable) coordinate space. */}
          <AnnotationCanvas
            ref={annotationRef}
            width={paneWidth}
            height={paneHeight}
            tool={tool}
            color={annColor}
            active={annotateActive}
          />
          {annotateActive && (
            <View style={p.annotateActions}>
              <TouchableOpacity style={p.annotateActionBtn} onPress={onUndoAnnotation}>
                <Text style={p.annotateActionText}>Undo</Text>
              </TouchableOpacity>
              <TouchableOpacity style={p.annotateActionBtn} onPress={onClearAnnotation}>
                <Text style={p.annotateActionText}>Clear</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
      </GestureDetector>
    </View>
  );
}
const p = StyleSheet.create({
  wrap: { flex: 1 },
  label: { color: MUTED, fontSize: 12, fontWeight: '700', marginBottom: 6, textAlign: 'center' },
  videoBox: { borderRadius: 12, overflow: 'hidden', backgroundColor: '#000', position: 'relative' },
  annotateActions: { position: 'absolute', top: 6, right: 6, flexDirection: 'row', gap: 6 },
  annotateActionBtn: {
    backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4,
  },
  annotateActionText: { color: '#fff', fontSize: 10.5, fontWeight: '700' },
  errorOverlay: {
    ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  errorText: { color: '#f87171', fontSize: 12.5, fontWeight: '700' },
});

export default function SyncCompareScreen({ route, navigation }) {
  const {
    videoAUrl, videoBUrl,
    contactASec = 0, contactBSec = 0,
    overlayA = null, overlayB = null,
    racketPathA = null, racketPathB = null,
    labelA = 'Reference', labelB = 'You',
    analysisId = null, canAddNotes = false,
    phaseMarkers = DEFAULT_PHASE_MARKERS,
  } = route.params ?? {};

  // Taller than a plain video aspect ratio (closer to a real portrait phone
  // recording's ~9:16) so each pane takes up more of the screen -- pushes the
  // scrubber/controls further down, requiring a scroll to reach them.
  // Reactive to useWindowWidth() rather than a module-level constant so
  // rotating the device or running on a different Android screen size
  // actually resizes the panes instead of staying stuck at whatever width
  // was current the first time this file was ever loaded.
  const windowWidth = useWindowWidth();
  const videoWidth = Math.min(windowWidth - 48, 460);
  const videoHeight = Math.round(videoWidth * 1.85);

  const { token, user } = useAuth();
  const videoARef = useRef(null);
  const videoBRef = useRef(null);
  const annotationARef = useRef(null);
  const annotationBRef = useRef(null);

  const [showSkeleton, setShowSkeleton] = useState(true);
  const [showRacketPath, setShowRacketPath] = useState(true);
  const [annotateActive, setAnnotateActive] = useState(false);
  const [tool, setTool] = useState('pen');
  const [annColor, setAnnColor] = useState(ANNOTATION_COLORS[0]);

  // Timestamp notes here are keyed to the shared scrubber's contact-relative
  // 't' (not a single video's raw playhead) -- the meaningful "moment" in
  // this view is shared between both clips regardless of their individual
  // lengths, same reference frame the scrubber/contact-mark already use.
  const [timeNotes, setTimeNotes] = useState([]);
  const [addingNote, setAddingNote] = useState(false);
  const [noteText, setNoteText] = useState('');

  useEffect(() => {
    if (!analysisId) return;
    getNotes(token, analysisId)
      .then((data) => setTimeNotes(data.notes.filter((nt) => nt.timestamp_sec != null)))
      .catch(() => {});
  }, [analysisId, token]);

  // Persisted freehand annotations -- every saved set for this analysis
  // (could be more than one author, e.g. two different coaches), with the
  // viewer's own set auto-loaded onto both canvases if they have one.
  const [annotationSets, setAnnotationSets] = useState([]);
  const [savingAnnotation, setSavingAnnotation] = useState(false);

  const loadAnnotationSets = () => {
    if (!analysisId) return;
    getAnnotations(token, analysisId)
      .then((data) => {
        setAnnotationSets(data.annotations);
        const mine = data.annotations.find((a) => a.author_id === user?.id);
        if (mine) {
          annotationARef.current?.loadStrokes(mine.pane_a_strokes);
          annotationBRef.current?.loadStrokes(mine.pane_b_strokes);
        }
      })
      .catch(() => {});
  };
  useEffect(loadAnnotationSets, [analysisId, token]);

  const handleSaveAnnotation = async () => {
    if (!analysisId) return;
    setSavingAnnotation(true);
    try {
      await saveAnnotations(token, analysisId, {
        paneAStrokes: annotationARef.current?.getStrokes() ?? [],
        paneBStrokes: annotationBRef.current?.getStrokes() ?? [],
      });
      loadAnnotationSets();
    } catch (err) {
      Alert.alert('Could not save annotation', err.message || 'Something went wrong');
    } finally {
      setSavingAnnotation(false);
    }
  };

  const handleSelectAnnotationSet = (set) => {
    annotationARef.current?.loadStrokes(set.pane_a_strokes);
    annotationBRef.current?.loadStrokes(set.pane_b_strokes);
  };

  const submitTimeNote = async () => {
    if (!noteText.trim()) return;
    try {
      await addNote(token, { analysisId, noteText: noteText.trim(), timestampSec: t });
      const data = await getNotes(token, analysisId);
      setTimeNotes(data.notes.filter((nt) => nt.timestamp_sec != null));
      setNoteText('');
      setAddingNote(false);
    } catch (err) {
      Alert.alert('Could not add note', err.message || 'Something went wrong');
    }
  };

  // Always the original video for both sides now (no more crop_to_subject.py
  // pre-cropped clips) -- ZOOM in VideoPane compensates visually instead.
  const uriA = videoAUrl;
  const uriB = videoBUrl;

  const hasOverlayData = !!(overlayA || overlayB);
  const showOverlay = hasOverlayData && showSkeleton;
  const hasRacketData = !!(racketPathA || racketPathB);
  const showRacket = hasRacketData && showRacketPath;
  const [timeA, setTimeA] = useState(0);
  const [timeB, setTimeB] = useState(0);

  const [t, setT] = useState(0); // seconds relative to contact, shared by both videos
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const trackWidth = useRef(0);
  const handleX = useRef(new Animated.Value(0)).current;

  const changeSpeed = (newSpeed) => {
    setSpeed(newSpeed);
    videoARef.current?.setRateAsync(newSpeed);
    videoBRef.current?.setRateAsync(newSpeed);
  };

  const setHandleFromT = (newT) => {
    const frac = (newT - T_MIN) / (T_MAX - T_MIN);
    handleX.setValue(Math.max(0, Math.min(1, frac)) * trackWidth.current);
  };

  // Zoom slider -- same track+handle PanResponder pattern as the scrubber
  // below, kept as a fallback/secondary control alongside the pinch/pan
  // gesture on the video panes themselves (useful on web, where trackpad
  // pinch isn't reliably mapped to gesture-handler's pinch recognizer).
  const [zoom, setZoom] = useState(ZOOM_DEFAULT);
  // Pan offset (px), shared by both panes so pinching/panning either video
  // keeps them at the same zoomed-in region for a like-for-like comparison.
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const zoomTrackWidth = useRef(0);
  const zoomHandleX = useRef(new Animated.Value(0)).current;

  const setZoomHandleFromValue = (z) => {
    const frac = (z - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN);
    zoomHandleX.setValue(Math.max(0, Math.min(1, frac)) * zoomTrackWidth.current);
  };

  // paneWidth/paneHeight mirror VideoPane's own layout math (both derived
  // from the same reactive videoWidth/videoHeight above), so pan can be
  // clamped here without needing to lift the clamp logic into the child.
  const paneWidth = videoWidth / 2 - 10;
  const paneHeight = (videoHeight / 2) - 10;
  const clampPan = (z, x, y) => {
    const maxX = Math.max(0, (paneWidth * z - paneWidth) / 2);
    const maxY = Math.max(0, (paneHeight * z - paneHeight) / 2);
    return [Math.max(-maxX, Math.min(maxX, x)), Math.max(-maxY, Math.min(maxY, y))];
  };

  // Shared by both VideoPanes' pinch/pan gestures -- whichever pane is
  // touched drives this same zoom/pan state for both.
  const handleZoomPanChange = (z, x, y) => {
    const zClamped = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
    const [xClamped, yClamped] = clampPan(zClamped, x, y);
    setZoom(zClamped);
    setPanX(xClamped);
    setPanY(yClamped);
    setZoomHandleFromValue(zClamped);
  };

  const zoomTouchStartX = useRef(0);
  const handleZoomTouch = (localX) => {
    if (!zoomTrackWidth.current) return;
    const clamped = Math.max(0, Math.min(zoomTrackWidth.current, localX));
    const frac = clamped / zoomTrackWidth.current;
    const z = ZOOM_MIN + frac * (ZOOM_MAX - ZOOM_MIN);
    setZoom(z);
    // The slider has no pan concept -- recenter when it's used, so it
    // always behaves as "zoom in on the middle" like it did before pan existed.
    setPanX(0);
    setPanY(0);
    setZoomHandleFromValue(z);
  };
  const zoomResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        setScrollEnabled(false);
        zoomTouchStartX.current = evt.nativeEvent.locationX;
        handleZoomTouch(zoomTouchStartX.current);
      },
      onPanResponderMove: (evt, gesture) => handleZoomTouch(zoomTouchStartX.current + gesture.dx),
      onPanResponderRelease: () => setScrollEnabled(true),
      onPanResponderTerminate: () => setScrollEnabled(true),
    })
  ).current;

  const handleToggleAnnotate = async () => {
    const next = !annotateActive;
    setAnnotateActive(next);
    if (next && isPlaying) {
      setIsPlaying(false);
      await Promise.all([videoARef.current?.pauseAsync(), videoBRef.current?.pauseAsync()]);
    }
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
  // Disabled while actively dragging the scrubber -- the screen now scrolls
  // (taller video panes push the track further down), and without this the
  // surrounding ScrollView's own gesture handling can compete with this
  // PanResponder for touch capture.
  const [scrollEnabled, setScrollEnabled] = useState(true);
  const scrubResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: async (evt) => {
        setScrollEnabled(false);
        if (isPlaying) {
          setIsPlaying(false);
          await Promise.all([videoARef.current?.pauseAsync(), videoBRef.current?.pauseAsync()]);
        }
        touchStartX.current = evt.nativeEvent.locationX;
        handleTouch(touchStartX.current);
      },
      onPanResponderMove: (evt, gesture) => handleTouch(touchStartX.current + gesture.dx),
      onPanResponderRelease: () => setScrollEnabled(true),
      onPanResponderTerminate: () => setScrollEnabled(true),
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
  const onAStatusUpdate = (status) => {
    if (status.isLoaded) setTimeA(status.positionMillis / 1000);
  };

  const onBStatusUpdate = (status) => {
    if (status.isLoaded) setTimeB(status.positionMillis / 1000);
    if (!isPlaying || !status.isLoaded) return;
    // A momentary `status.isPlaying === false` here can just mean B is
    // mid-buffer-stall, not actually stopped -- expo-av reports that
    // distinctly from a genuine finish, and flipping the shared isPlaying
    // flag on a stall alone desynced the UI from A (which kept playing),
    // producing "only one of the two videos plays". Only treat this as
    // stopped on a real end-of-clip, not any transient isPlaying:false.
    const finished = status.didJustFinish
      || (status.durationMillis > 0 && status.positionMillis >= status.durationMillis - 50);
    if (finished) {
      setIsPlaying(false);
      return;
    }
    if (!status.isPlaying) return;
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
        <View style={{ width: 60 }} />
      </View>

      <ScrollView contentContainerStyle={s.scrollContent} scrollEnabled={scrollEnabled}>
      <View style={s.videosRow}>
        <VideoPane
          label={labelA} uri={uriA} videoRef={videoARef} onStatusUpdate={onAStatusUpdate}
          overlayTrajectory={overlayA} overlayTimeSec={timeA} overlayColor={GOLD} showOverlay={showOverlay}
          racketTrajectory={racketPathA} racketColor={GOLD} showRacketPath={showRacket}
          isPlaying={isPlaying} paneWidth={paneWidth} paneHeight={paneHeight}
          zoom={zoom} panX={panX} panY={panY} onZoomPanChange={handleZoomPanChange}
          annotationRef={annotationARef} annotateActive={annotateActive}
          tool={tool} annColor={annColor}
          onClearAnnotation={() => annotationARef.current?.clear()}
          onUndoAnnotation={() => annotationARef.current?.undo()}
        />
        <VideoPane
          label={labelB} uri={uriB} videoRef={videoBRef} onStatusUpdate={onBStatusUpdate}
          overlayTrajectory={overlayB} overlayTimeSec={timeB} overlayColor={GREEN} showOverlay={showOverlay}
          racketTrajectory={racketPathB} racketColor={GREEN} showRacketPath={showRacket}
          isPlaying={isPlaying} paneWidth={paneWidth} paneHeight={paneHeight}
          zoom={zoom} panX={panX} panY={panY} onZoomPanChange={handleZoomPanChange}
          annotationRef={annotationBRef} annotateActive={annotateActive}
          tool={tool} annColor={annColor}
          onClearAnnotation={() => annotationBRef.current?.clear()}
          onUndoAnnotation={() => annotationBRef.current?.undo()}
        />
      </View>

      <View style={s.zoomRow}>
        <Text style={s.zoomLabel}>Zoom: {zoom.toFixed(2)}×</Text>
        <View
          style={s.zoomTrack}
          onLayout={(e) => {
            zoomTrackWidth.current = e.nativeEvent.layout.width;
            setZoomHandleFromValue(zoom);
          }}
          {...zoomResponder.panHandlers}
        >
          <View style={s.zoomTrackLine} />
          <Animated.View style={[s.zoomHandle, { transform: [{ translateX: zoomHandleX }] }]} />
        </View>
      </View>

      <View style={s.toolsRow}>
        {hasOverlayData && (
          <TouchableOpacity
            style={[s.toggleChip, showSkeleton && s.toggleChipActive]}
            onPress={() => setShowSkeleton((v) => !v)}
          >
            <Text style={[s.toggleChipText, showSkeleton && s.toggleChipTextActive]}>
              {showSkeleton ? 'Hide skeleton' : 'Show skeleton'}
            </Text>
          </TouchableOpacity>
        )}
        {hasRacketData && (
          <TouchableOpacity
            style={[s.toggleChip, showRacketPath && s.toggleChipActive]}
            onPress={() => setShowRacketPath((v) => !v)}
          >
            <Text style={[s.toggleChipText, showRacketPath && s.toggleChipTextActive]}>
              {showRacketPath ? 'Hide racket path' : 'Show racket path'}
            </Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity
          style={[s.toggleChip, annotateActive && s.toggleChipActive]}
          onPress={handleToggleAnnotate}
        >
          <Text style={[s.toggleChipText, annotateActive && s.toggleChipTextActive]}>
            {annotateActive ? 'Done annotating' : '✏ Annotate'}
          </Text>
        </TouchableOpacity>
      </View>

      {annotateActive && (
        <View style={s.annotateToolbar}>
          <View style={s.toolBtnRow}>
            {TOOLS.map((tl) => (
              <TouchableOpacity
                key={tl}
                style={[s.toolBtn, tool === tl && s.toolBtnActive]}
                onPress={() => setTool(tl)}
              >
                <Text style={[s.toolBtnText, tool === tl && s.toolBtnTextActive]}>{TOOL_LABELS[tl]}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={s.colorRow}>
            {ANNOTATION_COLORS.map((clr) => (
              <TouchableOpacity
                key={clr}
                style={[s.colorSwatch, { backgroundColor: clr }, annColor === clr && s.colorSwatchActive]}
                onPress={() => setAnnColor(clr)}
              />
            ))}
          </View>
          {analysisId && (
            <TouchableOpacity style={s.saveAnnotationBtn} onPress={handleSaveAnnotation} disabled={savingAnnotation}>
              <Text style={s.saveAnnotationBtnText}>{savingAnnotation ? 'Saving...' : 'Save annotation'}</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Lets a viewer switch whose saved annotations are displayed --
          shown even outside annotate mode so someone can just look without
          needing to be in drawing mode themselves. */}
      {annotationSets.length > 1 && (
        <View style={s.annotatorRow}>
          <Text style={s.annotatorLabel}>Viewing:</Text>
          {annotationSets.map((set) => (
            <TouchableOpacity
              key={set.author_id}
              style={s.annotatorChip}
              onPress={() => handleSelectAnnotationSet(set)}
            >
              <Text style={s.annotatorChipText}>{set.author_id === user?.id ? 'You' : set.author_name}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}

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
        {phaseMarkers.map((marker) => {
          const frac = Math.max(0, Math.min(1, (marker.t - T_MIN) / (T_MAX - T_MIN)));
          const isContact = marker.label === 'Contact';
          return (
            <TouchableOpacity
              key={marker.label}
              style={[s.phaseMarkTouch, { left: `${frac * 100}%` }]}
              onPress={() => seekBoth(marker.t)}
            >
              <View style={[s.phaseMark, isContact && s.phaseMarkContact]} />
            </TouchableOpacity>
          );
        })}
        {timeNotes.map((note) => {
          const frac = Math.max(0, Math.min(1, (note.timestamp_sec - T_MIN) / (T_MAX - T_MIN)));
          return (
            <TouchableOpacity
              key={note.id}
              style={[s.noteMark, { left: `${frac * 100}%` }]}
              onPress={() => Alert.alert(note.coach_name, note.note_text)}
            >
              <View style={s.noteMarkDot} />
            </TouchableOpacity>
          );
        })}
        <Animated.View style={[s.handle, { transform: [{ translateX: handleX }] }]} />
      </View>
      <Text style={s.phaseLegend}>
        {phaseMarkers.map((m) => m.label).join('  ·  ')} — tap a mark to jump there
      </Text>

      <View style={s.speedRow}>
        {SPEEDS.map((sp) => (
          <TouchableOpacity
            key={sp}
            style={[s.speedBtn, speed === sp && s.speedBtnActive]}
            onPress={() => changeSpeed(sp)}
          >
            <Text style={[s.speedBtnText, speed === sp && s.speedBtnTextActive]}>{sp}×</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity style={s.playBtn} onPress={() => { playTapSound(); togglePlay(); }}>
        <Text style={s.playBtnText}>{isPlaying ? '⏸ Pause' : '▶ Play both'}</Text>
      </TouchableOpacity>
      <Text style={s.playNote}>
        Drag the scrubber to compare frame-by-frame — dragging keeps both swings' contact
        moments exactly aligned. Play starts both together but they may drift apart if the
        clips differ in length.
      </Text>

      {canAddNotes && analysisId && (
        addingNote ? (
          <View style={s.noteComposer}>
            <TextInput
              style={s.noteInput}
              value={noteText}
              onChangeText={setNoteText}
              placeholder="Note at this moment..."
              placeholderTextColor={MUTED}
              multiline
            />
            <View style={s.noteComposerBtns}>
              <TouchableOpacity onPress={() => { setAddingNote(false); setNoteText(''); }}>
                <Text style={s.noteCancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={submitTimeNote}>
                <Text style={s.noteSaveText}>Save note</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <TouchableOpacity style={s.addNoteBtn} onPress={() => setAddingNote(true)}>
            <Text style={s.addNoteBtnText}>+ Add note at current time</Text>
          </TouchableOpacity>
        )
      )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scrollContent: { paddingBottom: 40 },

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 8,
  },
  backText: { color: MUTED, fontSize: 14, fontWeight: '600' },
  title: { color: TEXT, fontSize: 16, fontWeight: '700' },

  videosRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, marginTop: 8 },

  zoomRow: { paddingHorizontal: 28, marginTop: 16 },
  zoomLabel: { color: MUTED, fontSize: 12, fontWeight: '700', marginBottom: 8 },
  zoomTrack: { height: 32, justifyContent: 'center' },
  zoomTrackLine: {
    position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
  },
  zoomHandle: {
    position: 'absolute', left: -9, width: 18, height: 18, borderRadius: 9,
    backgroundColor: GOLD, borderWidth: 2, borderColor: DARK,
  },

  toolsRow: { flexDirection: 'row', justifyContent: 'center', gap: 10, marginTop: 16, paddingHorizontal: 20 },
  toggleChip: {
    borderWidth: 1, borderColor: BORDER, borderRadius: 8,
    paddingVertical: 8, paddingHorizontal: 14, backgroundColor: CARD,
  },
  toggleChipActive: { borderColor: GOLD, backgroundColor: GOLD },
  toggleChipText: { color: MUTED, fontSize: 12.5, fontWeight: '700' },
  toggleChipTextActive: { color: '#000' },

  annotateToolbar: {
    marginTop: 12, marginHorizontal: 20, backgroundColor: CARD, borderRadius: 12,
    borderWidth: 1, borderColor: BORDER, padding: 12,
  },
  toolBtnRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  toolBtn: {
    flex: 1, alignItems: 'center', borderRadius: 8, paddingVertical: 8,
    backgroundColor: DARK, borderWidth: 1, borderColor: BORDER,
  },
  toolBtnActive: { borderColor: GREEN, backgroundColor: GREEN },
  toolBtnText: { color: MUTED, fontSize: 12, fontWeight: '700' },
  toolBtnTextActive: { color: '#000' },
  colorRow: { flexDirection: 'row', justifyContent: 'center', gap: 12 },
  colorSwatch: { width: 26, height: 26, borderRadius: 13, borderWidth: 2, borderColor: 'transparent' },
  colorSwatchActive: { borderColor: TEXT },
  saveAnnotationBtn: {
    marginTop: 12, backgroundColor: GREEN, borderRadius: 8, paddingVertical: 10, alignItems: 'center',
  },
  saveAnnotationBtnText: { color: '#000', fontSize: 12.5, fontWeight: '700' },

  annotatorRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    marginTop: 12, marginHorizontal: 20,
  },
  annotatorLabel: { color: MUTED, fontSize: 12, fontWeight: '700' },
  annotatorChip: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER, borderRadius: 14,
    paddingHorizontal: 10, paddingVertical: 5,
  },
  annotatorChipText: { color: TEXT, fontSize: 11.5, fontWeight: '700' },

  tHint: { color: MUTED, fontSize: 12, textAlign: 'center', marginTop: 14 },

  track: {
    height: 40, marginHorizontal: 28, marginTop: 8, justifyContent: 'center',
  },
  trackLine: {
    position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
  },
  phaseMarkTouch: { position: 'absolute', marginLeft: -8, padding: 8, alignItems: 'center', justifyContent: 'center' },
  phaseMark: { width: 2, height: 16, backgroundColor: GOLD },
  phaseMarkContact: { backgroundColor: '#f87171', width: 2.5, height: 20 },
  phaseLegend: { color: MUTED, fontSize: 10.5, textAlign: 'center', marginTop: 4 },
  handle: {
    position: 'absolute', left: -11, width: 22, height: 22, borderRadius: 11,
    backgroundColor: GREEN, borderWidth: 2, borderColor: DARK,
  },

  speedRow: { flexDirection: 'row', justifyContent: 'center', gap: 10, marginTop: 18 },
  speedBtn: {
    borderWidth: 1, borderColor: BORDER, borderRadius: 8,
    paddingVertical: 6, paddingHorizontal: 16, backgroundColor: CARD,
  },
  speedBtnActive: { borderColor: GREEN, backgroundColor: GREEN },
  speedBtnText: { color: MUTED, fontSize: 13, fontWeight: '700' },
  speedBtnTextActive: { color: '#000' },

  playBtn: {
    backgroundColor: GREEN, borderRadius: 12, paddingVertical: 14,
    alignItems: 'center', marginHorizontal: 20, marginTop: 20,
  },
  playBtnText: { color: '#000', fontSize: 15, fontWeight: '700' },
  playNote: { color: MUTED, fontSize: 11.5, lineHeight: 16, textAlign: 'center', paddingHorizontal: 28, marginTop: 12 },

  noteMark: { position: 'absolute', top: -14, marginLeft: -5 },
  noteMarkDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: '#4ade80', borderWidth: 2, borderColor: '#0d0d0d' },

  addNoteBtn: { alignItems: 'center', marginTop: 16 },
  addNoteBtnText: { color: GOLD, fontSize: 13, fontWeight: '700' },
  noteComposer: { marginHorizontal: 20, marginTop: 16 },
  noteInput: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER, borderRadius: 10,
    padding: 12, color: TEXT, fontSize: 13.5, minHeight: 60, textAlignVertical: 'top',
  },
  noteComposerBtns: { flexDirection: 'row', justifyContent: 'flex-end', gap: 20, marginTop: 8 },
  noteCancelText: { color: MUTED, fontSize: 13, fontWeight: '600' },
  noteSaveText: { color: GREEN, fontSize: 13, fontWeight: '700' },
});
