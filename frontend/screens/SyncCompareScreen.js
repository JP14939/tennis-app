import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet, SafeAreaView,
  ScrollView, PanResponder, Animated,
} from 'react-native';
import Alert from '../utils/alert';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import PlatformVideo from '../components/PlatformVideo';
import SkeletonOverlay from '../components/SkeletonOverlay';
import RacketPathOverlay from '../components/RacketPathOverlay';
import { playTapSound } from '../utils/sounds';
import AnnotationCanvas from '../components/AnnotationCanvas';
import { useAuth } from '../context/AuthContext';
import { getNotes, addNote } from '../api/coach';
import { getAnnotations, saveAnnotations } from '../api/annotations';
import { useWindowSize } from '../utils/responsive';
import { colors, fonts, radius, spacing } from '../theme';

// Trajectory-overlay/scrubber accent colors -- distinct from each other so
// the two videos' skeleton/racket-path overlays stay tellable apart against
// a live video frame, so these stay bright theme accents (gold/lime) rather
// than the app's dark primary green, which would be nearly invisible
// overlaid on video.
const GREEN = colors.lime;
const GOLD  = colors.gold;

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

const trackFrac = (value) => Math.max(0, Math.min(1, (value - T_MIN) / (T_MAX - T_MIN)));

// Every component below is memo()'d and lives at module scope on purpose.
// This screen re-renders at the video status-update rate while playing (50ms
// on native, every animation frame on web), and without memo each of those
// ticks re-rendered both video panes, both gesture detectors, both SVG
// overlays and the whole control chrome. Memo only works if the props stay
// referentially stable, which is why the parent wraps its handlers in
// useCallback rather than passing inline arrows.

const VideoPane = memo(function VideoPane({
  label, uri, videoRef, onStatusUpdate, overlayTrajectory, overlayColor, showOverlay,
  racketTrajectory, racketColor, showRacketPath, isPlaying, paneWidth, paneHeight,
  zoom, panX, panY, onZoomPanChange, annotationRef, annotateActive, tool, annColor,
  onClearAnnotation, onUndoAnnotation,
}) {
  const zoomedWidth = paneWidth * zoom;
  const zoomedHeight = paneHeight * zoom;
  const offsetX = -(zoomedWidth - paneWidth) / 2 + panX;
  const offsetY = -(zoomedHeight - paneHeight) / 2 + panY;

  // This pane's own playhead, in its own video's timeline. Deliberately local
  // rather than lifted to the screen: nothing above needs it -- the two
  // overlays are its only consumer. When it lived in the parent, every status
  // tick from *either* video re-rendered the entire screen, including the
  // other pane's video and SVG overlays.
  const [time, setTime] = useState(0);
  const handleStatus = useCallback((status) => {
    if (status.isLoaded) setTime(status.positionMillis / 1000);
    onStatusUpdate?.(status);
  }, [onStatusUpdate]);

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

  const composedGesture = useMemo(() => {
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

    return Gesture.Simultaneous(pinchGesture, panGesture);
  }, [annotateActive, zoom, panX, panY, onZoomPanChange]);

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
              onStatusUpdate={handleStatus}
              highFrequencyUpdates={(showOverlay || showRacketPath) && isPlaying}
              onVideoSize={setVideoSize}
              onError={setVideoError}
            />
            {(showOverlay || showRacketPath) && (
              <View style={{ position: 'absolute', left: content.left, top: content.top, width: content.width, height: content.height }}>
                {showOverlay && (
                  <SkeletonOverlay
                    trajectory={overlayTrajectory}
                    currentTimeSec={time}
                    width={content.width}
                    height={content.height}
                    color={overlayColor}
                  />
                )}
                {showRacketPath && (
                  <RacketPathOverlay
                    trajectory={racketTrajectory}
                    currentTimeSec={time}
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
});
const p = StyleSheet.create({
  wrap: { flex: 1 },
  label: { color: colors.muted, fontSize: 12, fontFamily: fonts.bold, marginBottom: 6, textAlign: 'center' },
  videoBox: { borderRadius: radius.sm, overflow: 'hidden', backgroundColor: '#000', position: 'relative' },
  annotateActions: { position: 'absolute', top: 6, right: 6, flexDirection: 'row', gap: 6 },
  annotateActionBtn: {
    backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4,
  },
  annotateActionText: { color: '#fff', fontSize: 10.5, fontFamily: fonts.bold },
  errorOverlay: {
    ...StyleSheet.absoluteFillObject, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  errorText: { color: colors.coral, fontSize: 12.5, fontFamily: fonts.bold },
});

// The scrubber's own handle position is an Animated.Value driven imperatively,
// so `t` is deliberately NOT a prop here -- this subtree stays mounted and
// untouched through the ~20Hz `t` updates that playback produces.
const ScrubberTrack = memo(function ScrubberTrack({
  phaseMarkers, timeNotes, handleX, onSeek, onLayout, panHandlers,
}) {
  return (
    <View style={s.track} onLayout={onLayout} {...panHandlers}>
      <View style={s.trackLine} />
      {phaseMarkers.map((marker) => (
        <TouchableOpacity
          key={marker.label}
          style={[s.phaseMarkTouch, { left: `${trackFrac(marker.t) * 100}%` }]}
          onPress={() => onSeek(marker.t)}
        >
          <View style={[s.phaseMark, marker.label === 'Contact' && s.phaseMarkContact]} />
        </TouchableOpacity>
      ))}
      {timeNotes.map((note) => (
        <TouchableOpacity
          key={note.id}
          style={[s.noteMark, { left: `${trackFrac(note.timestamp_sec) * 100}%` }]}
          onPress={() => Alert.alert(note.coach_name, note.note_text)}
        >
          <View style={s.noteMarkDot} />
        </TouchableOpacity>
      ))}
      <Animated.View style={[s.handle, { transform: [{ translateX: handleX }] }]} />
    </View>
  );
});

const ZoomSlider = memo(function ZoomSlider({
  containerStyle, labelStyle, zoom, zoomHandleX, onLayout, panHandlers,
}) {
  return (
    <View style={containerStyle}>
      <Text style={labelStyle}>Zoom: {zoom.toFixed(2)}×</Text>
      <View style={s.zoomTrack} onLayout={onLayout} {...panHandlers}>
        <View style={s.zoomTrackLine} />
        <Animated.View style={[s.zoomHandle, { transform: [{ translateX: zoomHandleX }] }]} />
      </View>
    </View>
  );
});

const AnnotateToolbar = memo(function AnnotateToolbar({
  containerStyle, tool, onToolChange, annColor, onColorChange, canSave, saving, onSave,
}) {
  return (
    <View style={containerStyle}>
      <View style={s.toolBtnRow}>
        {TOOLS.map((tl) => (
          <TouchableOpacity
            key={tl}
            style={[s.toolBtn, tool === tl && s.toolBtnActive]}
            onPress={() => onToolChange(tl)}
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
            onPress={() => onColorChange(clr)}
          />
        ))}
      </View>
      {canSave && (
        <TouchableOpacity style={s.saveAnnotationBtn} onPress={onSave} disabled={saving}>
          <Text style={s.saveAnnotationBtnText}>{saving ? 'Saving...' : 'Save annotation'}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
});

const NoteComposer = memo(function NoteComposer({ containerStyle, value, onChangeText, onCancel, onSubmit }) {
  return (
    <View style={containerStyle}>
      <TextInput
        style={s.noteInput}
        value={value}
        onChangeText={onChangeText}
        placeholder="Note at this moment..."
        placeholderTextColor={colors.muted}
        multiline
      />
      <View style={s.noteComposerBtns}>
        <TouchableOpacity onPress={onCancel}>
          <Text style={s.noteCancelText}>Cancel</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={onSubmit}>
          <Text style={s.noteSaveText}>Save note</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
});

// Returns bare buttons rather than a wrapper -- the two layouts arrange them
// differently (a vertical rail vs. a horizontal row), but the buttons
// themselves are identical apart from their base style.
const SpeedButtons = memo(function SpeedButtons({ buttonStyle, speed, onChange }) {
  return SPEEDS.map((sp) => (
    <TouchableOpacity
      key={sp}
      style={[buttonStyle, speed === sp && s.speedBtnActive]}
      onPress={() => onChange(sp)}
    >
      <Text style={[s.speedBtnText, speed === sp && s.speedBtnTextActive]}>{sp}×</Text>
    </TouchableOpacity>
  ));
});

const ToggleChips = memo(function ToggleChips({
  chipStyle, chipTextStyle,
  hasOverlayData, showSkeleton, onToggleSkeleton,
  hasRacketData, showRacketPath, onToggleRacketPath,
  annotateActive, onToggleAnnotate,
}) {
  return (
    <>
      {hasOverlayData && (
        <TouchableOpacity style={[chipStyle, showSkeleton && s.toggleChipActive]} onPress={onToggleSkeleton}>
          <Text style={[chipTextStyle, showSkeleton && s.toggleChipTextActive]}>
            {showSkeleton ? 'Hide skeleton' : 'Show skeleton'}
          </Text>
        </TouchableOpacity>
      )}
      {hasRacketData && (
        <TouchableOpacity style={[chipStyle, showRacketPath && s.toggleChipActive]} onPress={onToggleRacketPath}>
          <Text style={[chipTextStyle, showRacketPath && s.toggleChipTextActive]}>
            {showRacketPath ? 'Hide racket path' : 'Show racket path'}
          </Text>
        </TouchableOpacity>
      )}
      <TouchableOpacity style={[chipStyle, annotateActive && s.toggleChipActive]} onPress={onToggleAnnotate}>
        <Text style={[chipTextStyle, annotateActive && s.toggleChipTextActive]}>
          {annotateActive ? 'Done annotating' : '✏ Annotate'}
        </Text>
      </TouchableOpacity>
    </>
  );
});

const AnnotatorChips = memo(function AnnotatorChips({ sets, viewerId, onSelect }) {
  return sets.map((set) => (
    <TouchableOpacity key={set.author_id} style={s.annotatorChip} onPress={() => onSelect(set)}>
      <Text style={s.annotatorChipText}>{set.author_id === viewerId ? 'You' : set.author_name}</Text>
    </TouchableOpacity>
  ));
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
  // recording's ~9:16) so each pane takes up more of the screen.
  // Reactive to useWindowSize() rather than a module-level constant so
  // rotating the device or resizing the browser window actually resizes
  // the panes instead of staying stuck at whatever size was current the
  // first time this file was ever loaded.
  const { width: windowWidth, height: windowHeight } = useWindowSize();
  const PANE_ASPECT = 1.85; // height / width
  // Below WIDE_BREAKPOINT, a vertical control rail between two video panes
  // wouldn't leave room for either -- keep the original phone-appropriate
  // stacked-below-videos layout unchanged there. At/above it, the panes
  // were previously capped at a combined 460px wide regardless of how much
  // wider the actual window was, leaving most of a desktop browser window
  // empty (confirmed directly from a real screenshot) -- this computes
  // real fill-the-page pane sizes instead, bounded by BOTH available width
  // and available height (a wide-but-short window must not let a tall
  // portrait clip overflow the viewport).
  const WIDE_BREAKPOINT = 900;
  const isWide = windowWidth >= WIDE_BREAKPOINT;
  const RAIL_WIDTH = 130;

  // paneWidth/paneHeight are the actual per-pane size VideoPane renders at
  // (and what its own pinch/pan clamping math below is derived from).
  let paneWidth, paneHeight;
  if (isWide) {
    // Full-screen overlay mode: the videos fill essentially the entire
    // viewport and every control (header, rail, scrubber/zoom/play) floats
    // on top as a semi-transparent absolute-positioned panel instead of
    // reserving its own vertical space below the videos -- so almost the
    // whole window height is available to the panes, just a small margin.
    const availableHeight = Math.max(280, windowHeight - 16);
    const availableWidthPerPane = (windowWidth - 16 - RAIL_WIDTH) / 2;
    // Fit to whichever dimension is more constraining, then derive the
    // other from PANE_ASPECT so the pane's own proportions stay correct
    // rather than stretching.
    if (availableWidthPerPane * PANE_ASPECT <= availableHeight) {
      paneWidth = availableWidthPerPane;
      paneHeight = paneWidth * PANE_ASPECT;
    } else {
      paneHeight = availableHeight;
      paneWidth = paneHeight / PANE_ASPECT;
    }
    paneWidth = Math.round(paneWidth);
    paneHeight = Math.round(paneHeight);
  } else {
    const videoWidth = Math.min(windowWidth - 48, 460);
    const videoHeight = Math.round(videoWidth * PANE_ASPECT);
    paneWidth = videoWidth / 2 - 10;
    paneHeight = videoHeight / 2 - 10;
  }

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

  const [t, setT] = useState(0); // seconds relative to contact, shared by both videos
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [scrollEnabled, setScrollEnabled] = useState(true);
  const trackWidth = useRef(0);
  const handleX = useRef(new Animated.Value(0)).current;

  // Mirrors of state that the PanResponders below need to read at gesture
  // time. See the `latest` ref comment for why reading the state directly
  // from inside those handlers does not work.
  const tRef = useRef(0);
  const isPlayingRef = useRef(false);

  const setPlaying = useCallback((next) => {
    isPlayingRef.current = next;
    setIsPlaying(next);
  }, []);

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

  const loadAnnotationSets = useCallback(() => {
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
  }, [analysisId, token, user?.id]);
  useEffect(() => { loadAnnotationSets(); }, [loadAnnotationSets]);

  const handleSaveAnnotation = useCallback(async () => {
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
  }, [analysisId, token, loadAnnotationSets]);

  const handleSelectAnnotationSet = useCallback((set) => {
    annotationARef.current?.loadStrokes(set.pane_a_strokes);
    annotationBRef.current?.loadStrokes(set.pane_b_strokes);
  }, []);

  const submitTimeNote = useCallback(async () => {
    if (!noteText.trim()) return;
    try {
      await addNote(token, { analysisId, noteText: noteText.trim(), timestampSec: tRef.current });
      const data = await getNotes(token, analysisId);
      setTimeNotes(data.notes.filter((nt) => nt.timestamp_sec != null));
      setNoteText('');
      setAddingNote(false);
    } catch (err) {
      Alert.alert('Could not add note', err.message || 'Something went wrong');
    }
  }, [noteText, token, analysisId]);

  // Always the original video for both sides now (no more crop_to_subject.py
  // pre-cropped clips) -- ZOOM in VideoPane compensates visually instead.
  const uriA = videoAUrl;
  const uriB = videoBUrl;

  const hasOverlayData = !!(overlayA || overlayB);
  const showOverlay = hasOverlayData && showSkeleton;
  const hasRacketData = !!(racketPathA || racketPathB);
  const showRacket = hasRacketData && showRacketPath;

  const changeSpeed = useCallback((newSpeed) => {
    setSpeed(newSpeed);
    videoARef.current?.setRateAsync(newSpeed);
    videoBRef.current?.setRateAsync(newSpeed);
  }, []);

  const setHandleFromT = useCallback((newT) => {
    handleX.setValue(trackFrac(newT) * trackWidth.current);
  }, [handleX]);

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

  const setZoomHandleFromValue = useCallback((z) => {
    const frac = (z - ZOOM_MIN) / (ZOOM_MAX - ZOOM_MIN);
    zoomHandleX.setValue(Math.max(0, Math.min(1, frac)) * zoomTrackWidth.current);
  }, [zoomHandleX]);

  // paneWidth/paneHeight are computed once, per breakpoint, up near
  // windowWidth/windowHeight above -- reused here for pan clamping without
  // needing to lift the clamp logic into VideoPane itself.
  const clampPan = useCallback((z, x, y) => {
    const maxX = Math.max(0, (paneWidth * z - paneWidth) / 2);
    const maxY = Math.max(0, (paneHeight * z - paneHeight) / 2);
    return [Math.max(-maxX, Math.min(maxX, x)), Math.max(-maxY, Math.min(maxY, y))];
  }, [paneWidth, paneHeight]);

  // Shared by both VideoPanes' pinch/pan gestures -- whichever pane is
  // touched drives this same zoom/pan state for both.
  const handleZoomPanChange = useCallback((z, x, y) => {
    const zClamped = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
    const [xClamped, yClamped] = clampPan(zClamped, x, y);
    setZoom(zClamped);
    setPanX(xClamped);
    setPanY(yClamped);
    setZoomHandleFromValue(zClamped);
  }, [clampPan, setZoomHandleFromValue]);

  const handleZoomTouch = useCallback((localX) => {
    if (!zoomTrackWidth.current) return;
    const clamped = Math.max(0, Math.min(zoomTrackWidth.current, localX));
    const z = ZOOM_MIN + (clamped / zoomTrackWidth.current) * (ZOOM_MAX - ZOOM_MIN);
    setZoom(z);
    // The slider has no pan concept -- recenter when it's used, so it
    // always behaves as "zoom in on the middle" like it did before pan existed.
    setPanX(0);
    setPanY(0);
    setZoomHandleFromValue(z);
  }, [setZoomHandleFromValue]);

  const pauseBoth = useCallback(async () => {
    setPlaying(false);
    await Promise.all([videoARef.current?.pauseAsync(), videoBRef.current?.pauseAsync()]);
  }, [setPlaying]);

  const seekBoth = useCallback(async (newT) => {
    const clamped = Math.max(T_MIN, Math.min(T_MAX, newT));
    tRef.current = clamped;
    setT(clamped);
    setHandleFromT(clamped);
    await Promise.all([
      videoARef.current?.setPositionAsync(Math.max(0, (contactASec + clamped) * 1000)),
      videoBRef.current?.setPositionAsync(Math.max(0, (contactBSec + clamped) * 1000)),
    ]);
  }, [contactASec, contactBSec, setHandleFromT]);

  useEffect(() => {
    seekBoth(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [uriA, uriB]);

  // Uses locationX (relative to the track view itself) at gesture start,
  // then tracks movement via the gesture's own dx delta -- avoids needing
  // the track's absolute screen position, which isn't resolved the same
  // way on web vs. native.
  const handleTouch = useCallback((localX) => {
    if (!trackWidth.current) return;
    const clamped = Math.max(0, Math.min(trackWidth.current, localX));
    seekBoth(T_MIN + (clamped / trackWidth.current) * (T_MAX - T_MIN));
  }, [seekBoth]);

  // PanResponder.create() runs once (it's the useRef initial value) and
  // permanently captures whatever closures it was handed on that first
  // render. Handlers therefore must never read render-scoped values
  // directly: that is exactly what silently broke "grab the scrubber while
  // playing" -- it tested the first render's `isPlaying`, which is false
  // forever, so the videos kept playing while you dragged and fought the
  // seek. Routing every call through this ref keeps the whole class of bug
  // out rather than just the one instance.
  const latest = useRef(null);
  latest.current = { handleTouch, handleZoomTouch, pauseBoth };

  const touchStartX = useRef(0);
  // Scrolling is disabled while actively dragging either slider -- the screen
  // scrolls in narrow mode (taller video panes push the track further down),
  // and without this the surrounding ScrollView's own gesture handling can
  // compete with these PanResponders for touch capture.
  const scrubResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        setScrollEnabled(false);
        touchStartX.current = evt.nativeEvent.locationX;
        latest.current.handleTouch(touchStartX.current);
        if (isPlayingRef.current) latest.current.pauseBoth().catch(() => {});
      },
      onPanResponderMove: (evt, gesture) => latest.current.handleTouch(touchStartX.current + gesture.dx),
      onPanResponderRelease: () => setScrollEnabled(true),
      onPanResponderTerminate: () => setScrollEnabled(true),
    })
  ).current;

  const zoomTouchStartX = useRef(0);
  const zoomResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        setScrollEnabled(false);
        zoomTouchStartX.current = evt.nativeEvent.locationX;
        latest.current.handleZoomTouch(zoomTouchStartX.current);
      },
      onPanResponderMove: (evt, gesture) => latest.current.handleZoomTouch(zoomTouchStartX.current + gesture.dx),
      onPanResponderRelease: () => setScrollEnabled(true),
      onPanResponderTerminate: () => setScrollEnabled(true),
    })
  ).current;

  const handleToggleAnnotate = useCallback(async () => {
    const next = !annotateActive;
    setAnnotateActive(next);
    if (next && isPlayingRef.current) await pauseBoth();
  }, [annotateActive, pauseBoth]);

  const togglePlay = useCallback(async () => {
    if (isPlayingRef.current) {
      await pauseBoth();
    } else {
      setPlaying(true);
      await Promise.all([videoARef.current?.playAsync(), videoBRef.current?.playAsync()]);
    }
  }, [pauseBoth, setPlaying]);

  // Pane A needs no parent-side status handling at all -- it owns its own
  // playhead for its overlays. Only B drives the shared scrubber, because
  // one of the two has to and they are seek-aligned at contact anyway.
  //
  // A momentary `status.isPlaying === false` here can just mean B is
  // mid-buffer-stall, not actually stopped -- expo-av reports that
  // distinctly from a genuine finish, and flipping the shared isPlaying
  // flag on a stall alone desynced the UI from A (which kept playing),
  // producing "only one of the two videos plays". Only treat this as
  // stopped on a real end-of-clip, not any transient isPlaying:false.
  const onBStatusUpdate = useCallback((status) => {
    if (!isPlayingRef.current || !status.isLoaded) return;
    const finished = status.didJustFinish
      || (status.durationMillis > 0 && status.positionMillis >= status.durationMillis - 50);
    if (finished) {
      setPlaying(false);
      return;
    }
    if (!status.isPlaying) return;
    const newT = status.positionMillis / 1000 - contactBSec;
    tRef.current = newT;
    setT(newT);
    setHandleFromT(newT);
  }, [contactBSec, setHandleFromT, setPlaying]);

  const onTrackLayout = useCallback((e) => {
    trackWidth.current = e.nativeEvent.layout.width;
    setHandleFromT(tRef.current);
  }, [setHandleFromT]);

  const onZoomTrackLayout = useCallback((e) => {
    zoomTrackWidth.current = e.nativeEvent.layout.width;
    setZoomHandleFromValue(zoom);
  }, [setZoomHandleFromValue, zoom]);

  const clearA = useCallback(() => annotationARef.current?.clear(), []);
  const undoA = useCallback(() => annotationARef.current?.undo(), []);
  const clearB = useCallback(() => annotationBRef.current?.clear(), []);
  const undoB = useCallback(() => annotationBRef.current?.undo(), []);
  const toggleSkeleton = useCallback(() => setShowSkeleton((v) => !v), []);
  const toggleRacketPath = useCallback(() => setShowRacketPath((v) => !v), []);
  const openNote = useCallback(() => setAddingNote(true), []);
  const cancelNote = useCallback(() => { setAddingNote(false); setNoteText(''); }, []);
  const handlePlayPress = useCallback(() => { playTapSound(); togglePlay(); }, [togglePlay]);

  // Both layouts render the same two panes with the same props -- only the
  // surrounding chrome differs -- so they're built once here rather than
  // written out twice.
  const paneA = (
    <VideoPane
      label={labelA} uri={uriA} videoRef={videoARef}
      overlayTrajectory={overlayA} overlayColor={GOLD} showOverlay={showOverlay}
      racketTrajectory={racketPathA} racketColor={GOLD} showRacketPath={showRacket}
      isPlaying={isPlaying} paneWidth={paneWidth} paneHeight={paneHeight}
      zoom={zoom} panX={panX} panY={panY} onZoomPanChange={handleZoomPanChange}
      annotationRef={annotationARef} annotateActive={annotateActive}
      tool={tool} annColor={annColor}
      onClearAnnotation={clearA} onUndoAnnotation={undoA}
    />
  );
  const paneB = (
    <VideoPane
      label={labelB} uri={uriB} videoRef={videoBRef} onStatusUpdate={onBStatusUpdate}
      overlayTrajectory={overlayB} overlayColor={GREEN} showOverlay={showOverlay}
      racketTrajectory={racketPathB} racketColor={GREEN} showRacketPath={showRacket}
      isPlaying={isPlaying} paneWidth={paneWidth} paneHeight={paneHeight}
      zoom={zoom} panX={panX} panY={panY} onZoomPanChange={handleZoomPanChange}
      annotationRef={annotationBRef} annotateActive={annotateActive}
      tool={tool} annColor={annColor}
      onClearAnnotation={clearB} onUndoAnnotation={undoB}
    />
  );

  const scrubber = (
    <ScrubberTrack
      phaseMarkers={phaseMarkers}
      timeNotes={timeNotes}
      handleX={handleX}
      onSeek={seekBoth}
      onLayout={onTrackLayout}
      panHandlers={scrubResponder.panHandlers}
    />
  );

  const phaseLegendText = `${phaseMarkers.map((m) => m.label).join('  ·  ')} — tap a mark to jump there`;
  const tHintText = `${t >= 0 ? '+' : ''}${t.toFixed(2)}s from contact`;
  const showNoteComposer = canAddNotes && analysisId && addingNote;

  // Wide (desktop-ish) layout: videos fill essentially the whole screen,
  // every control floats on top as a semi-transparent absolute overlay
  // instead of being stacked below the videos in normal document flow --
  // narrow/mobile layout below is untouched.
  if (isWide) {
    return (
      <SafeAreaView style={s.safeWide}>
        <View style={s.wideStage}>
          <View style={s.videosRowWide}>
            {paneA}

            <View style={[s.rail, { width: RAIL_WIDTH }]}>
              <ToggleChips
                chipStyle={s.railChip} chipTextStyle={s.railChipText}
                hasOverlayData={hasOverlayData} showSkeleton={showSkeleton} onToggleSkeleton={toggleSkeleton}
                hasRacketData={hasRacketData} showRacketPath={showRacketPath} onToggleRacketPath={toggleRacketPath}
                annotateActive={annotateActive} onToggleAnnotate={handleToggleAnnotate}
              />
              <View style={s.railDivider} />
              <Text style={s.railLabel}>Speed</Text>
              <SpeedButtons buttonStyle={s.railSpeedBtn} speed={speed} onChange={changeSpeed} />
            </View>

            {paneB}
          </View>

          {/* Top overlay: back/title, floating over the videos rather than
              taking its own reserved header row. */}
          <View style={s.overlayTop} pointerEvents="box-none">
            <TouchableOpacity style={s.overlayBackBtn} onPress={() => navigation.goBack()}>
              <Text style={s.backTextOverlay}>‹ Back</Text>
            </TouchableOpacity>
            <Text style={s.titleOverlay}>Side-by-side</Text>
            {annotationSets.length > 1 ? (
              <View style={s.annotatorRowOverlay}>
                <AnnotatorChips sets={annotationSets} viewerId={user?.id} onSelect={handleSelectAnnotationSet} />
              </View>
            ) : (
              <View style={{ width: 60 }} />
            )}
          </View>

          {/* Floating annotate toolbar, shown above the bottom overlay only
              while actively annotating -- same tool/color picker as narrow
              mode, just positioned as its own overlay panel here. */}
          {annotateActive && (
            <AnnotateToolbar
              containerStyle={s.annotateToolbarOverlay}
              tool={tool} onToolChange={setTool}
              annColor={annColor} onColorChange={setAnnColor}
              canSave={!!analysisId} saving={savingAnnotation} onSave={handleSaveAnnotation}
            />
          )}

          {/* Floating note composer, same trigger/content as narrow mode. */}
          {showNoteComposer && (
            <NoteComposer
              containerStyle={s.noteComposerOverlay}
              value={noteText} onChangeText={setNoteText}
              onCancel={cancelNote} onSubmit={submitTimeNote}
            />
          )}

          {/* Bottom overlay: zoom slider, scrubber + phase markers, play,
              and (when not composing a note) the add-note trigger -- all
              floating over the videos instead of stacked below them. */}
          <View style={s.overlayBottom} pointerEvents="box-none">
            <ZoomSlider
              containerStyle={s.zoomRowOverlay} labelStyle={s.zoomLabelOverlay}
              zoom={zoom} zoomHandleX={zoomHandleX}
              onLayout={onZoomTrackLayout} panHandlers={zoomResponder.panHandlers}
            />

            <Text style={s.tHintOverlay}>{tHintText}</Text>
            {scrubber}
            <Text style={s.phaseLegendOverlay}>{phaseLegendText}</Text>

            <View style={s.bottomRowOverlay}>
              <TouchableOpacity style={s.playBtnOverlay} onPress={handlePlayPress}>
                <Text style={s.playBtnText}>{isPlaying ? '⏸ Pause' : '▶ Play both'}</Text>
              </TouchableOpacity>
              {canAddNotes && analysisId && !addingNote && (
                <TouchableOpacity style={s.addNoteBtnOverlay} onPress={openNote}>
                  <Text style={s.addNoteBtnText}>+ Add note</Text>
                </TouchableOpacity>
              )}
            </View>
          </View>
        </View>
      </SafeAreaView>
    );
  }

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
          {paneA}
          {paneB}
        </View>

        <ZoomSlider
          containerStyle={s.zoomRow} labelStyle={s.zoomLabel}
          zoom={zoom} zoomHandleX={zoomHandleX}
          onLayout={onZoomTrackLayout} panHandlers={zoomResponder.panHandlers}
        />

        <View style={s.toolsRow}>
          <ToggleChips
            chipStyle={s.toggleChip} chipTextStyle={s.toggleChipText}
            hasOverlayData={hasOverlayData} showSkeleton={showSkeleton} onToggleSkeleton={toggleSkeleton}
            hasRacketData={hasRacketData} showRacketPath={showRacketPath} onToggleRacketPath={toggleRacketPath}
            annotateActive={annotateActive} onToggleAnnotate={handleToggleAnnotate}
          />
        </View>

        {annotateActive && (
          <AnnotateToolbar
            containerStyle={s.annotateToolbar}
            tool={tool} onToolChange={setTool}
            annColor={annColor} onColorChange={setAnnColor}
            canSave={!!analysisId} saving={savingAnnotation} onSave={handleSaveAnnotation}
          />
        )}

        {/* Lets a viewer switch whose saved annotations are displayed --
            shown even outside annotate mode so someone can just look without
            needing to be in drawing mode themselves. */}
        {annotationSets.length > 1 && (
          <View style={s.annotatorRow}>
            <Text style={s.annotatorLabel}>Viewing:</Text>
            <AnnotatorChips sets={annotationSets} viewerId={user?.id} onSelect={handleSelectAnnotationSet} />
          </View>
        )}

        <Text style={s.tHint}>{tHintText}</Text>
        {scrubber}
        <Text style={s.phaseLegend}>{phaseLegendText}</Text>

        <View style={s.speedRow}>
          <SpeedButtons buttonStyle={s.speedBtn} speed={speed} onChange={changeSpeed} />
        </View>

        <TouchableOpacity style={s.playBtn} onPress={handlePlayPress}>
          <Text style={s.playBtnText}>{isPlaying ? '⏸ Pause' : '▶ Play both'}</Text>
        </TouchableOpacity>
        <Text style={s.playNote}>
          Drag the scrubber to compare frame-by-frame — dragging keeps both swings' contact
          moments exactly aligned. Play starts both together but they may drift apart if the
          clips differ in length.
        </Text>

        {canAddNotes && analysisId && (
          addingNote ? (
            <NoteComposer
              containerStyle={s.noteComposer}
              value={noteText} onChangeText={setNoteText}
              onCancel={cancelNote} onSubmit={submitTimeNote}
            />
          ) : (
            <TouchableOpacity style={s.addNoteBtn} onPress={openNote}>
              <Text style={s.addNoteBtnText}>+ Add note at current time</Text>
            </TouchableOpacity>
          )
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scrollContent: { paddingBottom: 40 },

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.xl, paddingTop: 12, paddingBottom: 8,
  },
  backText: { color: colors.muted, fontSize: 14, fontFamily: fonts.semibold },
  title: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold },

  videosRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, marginTop: 8 },
  videosRowWide: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
  },

  // Wide/full-screen mode: the stage fills the whole safe area and every
  // control is an absolute-positioned overlay on top of it, rather than
  // the videos sharing document flow with rows of controls below them.
  safeWide: { flex: 1, backgroundColor: '#000' },
  wideStage: { flex: 1, position: 'relative', alignItems: 'center', justifyContent: 'center' },

  overlayTop: {
    position: 'absolute', top: 0, left: 0, right: 0,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.xl, paddingTop: 14, paddingBottom: 10,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  overlayBackBtn: { minWidth: 60 },
  backTextOverlay: { color: '#fff', fontSize: 14, fontFamily: fonts.semibold },
  titleOverlay: { color: '#fff', fontSize: 16, fontFamily: fonts.bold },
  annotatorRowOverlay: { flexDirection: 'row', gap: 6, minWidth: 60, justifyContent: 'flex-end' },

  annotateToolbarOverlay: {
    position: 'absolute', bottom: 210, alignSelf: 'center', width: 320, maxWidth: '92%',
    backgroundColor: 'rgba(20,20,20,0.85)', borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: 12,
  },
  noteComposerOverlay: {
    position: 'absolute', bottom: 210, alignSelf: 'center', width: 340, maxWidth: '92%',
    backgroundColor: 'rgba(20,20,20,0.9)', borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: 12,
  },

  overlayBottom: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: spacing.xl, paddingTop: 12, paddingBottom: 16,
  },
  zoomRowOverlay: { marginBottom: 8 },
  zoomLabelOverlay: { color: 'rgba(255,255,255,0.8)', fontSize: 11.5, fontFamily: fonts.bold, marginBottom: 6 },
  tHintOverlay: { color: 'rgba(255,255,255,0.8)', fontSize: 11.5, textAlign: 'center' },
  phaseLegendOverlay: { color: 'rgba(255,255,255,0.6)', fontSize: 10, textAlign: 'center', marginTop: 4 },
  bottomRowOverlay: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12, marginTop: 12 },
  playBtnOverlay: {
    backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 12, paddingHorizontal: 28,
    alignItems: 'center',
  },
  addNoteBtnOverlay: {
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.3)', borderRadius: radius.md,
    paddingVertical: 12, paddingHorizontal: 16, alignItems: 'center',
  },

  rail: { alignSelf: 'stretch', justifyContent: 'center', gap: 8 },
  railChip: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: 10, paddingHorizontal: 10, backgroundColor: colors.surface,
    alignItems: 'center',
  },
  railChipText: { color: colors.muted, fontSize: 11.5, fontFamily: fonts.bold, textAlign: 'center' },
  railDivider: { height: 1, backgroundColor: colors.border, marginVertical: 6 },
  railLabel: { color: colors.muted, fontSize: 11, fontFamily: fonts.bold, textAlign: 'center', marginBottom: 2 },
  railSpeedBtn: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: 9, alignItems: 'center', backgroundColor: colors.surface,
  },

  zoomRow: { paddingHorizontal: 28, marginTop: 16 },
  zoomLabel: { color: colors.muted, fontSize: 12, fontFamily: fonts.bold, marginBottom: 8 },
  zoomTrack: { height: 32, justifyContent: 'center' },
  zoomTrackLine: {
    position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  zoomHandle: {
    position: 'absolute', left: -9, width: 18, height: 18, borderRadius: 9,
    backgroundColor: GOLD, borderWidth: 2, borderColor: colors.surface,
  },

  toolsRow: { flexDirection: 'row', justifyContent: 'center', gap: 10, marginTop: 16, paddingHorizontal: 20 },
  toggleChip: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: 8, paddingHorizontal: 14, backgroundColor: colors.surface,
  },
  toggleChipActive: { borderColor: GOLD, backgroundColor: GOLD },
  toggleChipText: { color: colors.muted, fontSize: 12.5, fontFamily: fonts.bold },
  toggleChipTextActive: { color: colors.ink },

  annotateToolbar: {
    marginTop: 12, marginHorizontal: 20, backgroundColor: colors.surface, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: 12,
  },
  toolBtnRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  toolBtn: {
    flex: 1, alignItems: 'center', borderRadius: radius.sm, paddingVertical: 8,
    backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border,
  },
  toolBtnActive: { borderColor: colors.primary, backgroundColor: colors.primary },
  toolBtnText: { color: colors.muted, fontSize: 12, fontFamily: fonts.bold },
  toolBtnTextActive: { color: colors.white },
  colorRow: { flexDirection: 'row', justifyContent: 'center', gap: 12 },
  colorSwatch: { width: 26, height: 26, borderRadius: 13, borderWidth: 2, borderColor: 'transparent' },
  colorSwatchActive: { borderColor: colors.ink },
  saveAnnotationBtn: {
    marginTop: 12, backgroundColor: colors.primary, borderRadius: radius.sm, paddingVertical: 10, alignItems: 'center',
  },
  saveAnnotationBtnText: { color: colors.white, fontSize: 12.5, fontFamily: fonts.bold },

  annotatorRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap',
    marginTop: 12, marginHorizontal: 20,
  },
  annotatorLabel: { color: colors.muted, fontSize: 12, fontFamily: fonts.bold },
  annotatorChip: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 5,
  },
  annotatorChipText: { color: colors.ink, fontSize: 11.5, fontFamily: fonts.bold },

  tHint: { color: colors.muted, fontSize: 12, textAlign: 'center', marginTop: 14 },

  track: {
    height: 40, marginHorizontal: 28, marginTop: 8, justifyContent: 'center',
  },
  trackLine: {
    position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  phaseMarkTouch: { position: 'absolute', marginLeft: -8, padding: 8, alignItems: 'center', justifyContent: 'center' },
  phaseMark: { width: 2, height: 16, backgroundColor: GOLD },
  phaseMarkContact: { backgroundColor: colors.coral, width: 2.5, height: 20 },
  phaseLegend: { color: colors.muted, fontSize: 10.5, textAlign: 'center', marginTop: 4 },
  handle: {
    position: 'absolute', left: -11, width: 22, height: 22, borderRadius: 11,
    backgroundColor: colors.primary, borderWidth: 2, borderColor: colors.surface,
  },

  speedRow: { flexDirection: 'row', justifyContent: 'center', gap: 10, marginTop: 18 },
  speedBtn: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingVertical: 6, paddingHorizontal: 16, backgroundColor: colors.surface,
  },
  speedBtnActive: { borderColor: colors.primary, backgroundColor: colors.primary },
  speedBtnText: { color: colors.muted, fontSize: 13, fontFamily: fonts.bold },
  speedBtnTextActive: { color: colors.white },

  playBtn: {
    backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 14,
    alignItems: 'center', marginHorizontal: 20, marginTop: 20,
  },
  playBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },
  playNote: { color: colors.muted, fontSize: 11.5, lineHeight: 16, textAlign: 'center', paddingHorizontal: 28, marginTop: 12 },

  noteMark: { position: 'absolute', top: -14, marginLeft: -5 },
  noteMarkDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.primary, borderWidth: 2, borderColor: colors.surface },

  addNoteBtn: { alignItems: 'center', marginTop: 16 },
  addNoteBtnText: { color: GOLD, fontSize: 13, fontFamily: fonts.bold },
  noteComposer: { marginHorizontal: 20, marginTop: 16 },
  noteInput: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    padding: 12, color: colors.ink, fontSize: 13.5, minHeight: 60, textAlignVertical: 'top',
  },
  noteComposerBtns: { flexDirection: 'row', justifyContent: 'flex-end', gap: 20, marginTop: 8 },
  noteCancelText: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold },
  noteSaveText: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },
});
