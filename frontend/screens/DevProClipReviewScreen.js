import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator, Modal, Platform } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius } from '../theme';
import { SHOT_TYPES } from '../config/shotTypes';

// Free, no-Claude-cost manual data-quality review of the pro database
// itself -- direct report: a lot of clips are mismatched, some are
// slow-motion, some contain the tail end of one player's/swing's motion
// butted against the start of a different one. Not a teacher-student ML
// loop like the other Dev Page review tools -- this is data-quality
// curation, logged into clip_review_log.py's flat verdict log so a later
// one-off pass (same shape as filter_by_ball_visibility.py) can rebuild
// pro_database.json excluding flagged entries once enough review data exists.
// Simplified 2026-08-27 to 3 verdicts (Looks good / Edit / Don't use this)
// after Jack found the finer-grained ones (mismatched/slow-motion/spans-two-
// swings) confusing in practice -- clip_review_log.py's own docstring
// already notes they only ever fed a "rebuild excluding flagged entries"
// pass that doesn't exist yet, so they had no functional difference from
// plain 'excluded' today. Those values stay valid in clip_review_log.py's
// VERDICTS tuple for historical log entries -- only this screen stops
// exposing them as separate buttons. "Looks good" submits 'label_confirmed'
// (not 'ok') since that's the verdict the sprint's progress counter
// (list_pro_clip_review_candidates.py's LABEL_REVIEW_VERDICTS) actually
// counts -- this also absorbs what a separate "Contact + shot type OK"
// button used to do, which is why that button is gone too.

// Cut mode needs the trimmed clip to still be long enough to be worth
// keeping -- same floor cut_pro_clip.py enforces server-side, checked here
// too so the Confirm button disables before a doomed request round-trips.
const MIN_CUT_SEC = 0.2;

// Fix Contact Time's fine-offset range (frames either side of the marked
// rough position) -- same bound ContactMarkingScreen.js's own fine-tune
// step uses.
const FINE_RADIUS = 50;
const IS_WEB = Platform.OS === 'web';

// PlatformVideo never autoplays and has no native controls -- same
// tap-to-toggle pattern established across every other Dev Page review tool.
// forwardedRef + onProgress let the parent drive seeking and read
// position/duration for Cut mode's trim controls, without every other
// caller of this pattern elsewhere needing to change.
function TappableVideo({ uri, width, height, onProgress, videoRef: externalRef }) {
  const internalRef = useRef(null);
  const videoRef = externalRef || internalRef;
  const [playing, setPlaying] = useState(false);

  const toggle = () => {
    if (playing) {
      videoRef.current?.pauseAsync();
      setPlaying(false);
    } else {
      videoRef.current?.playAsync();
      setPlaying(true);
    }
  };

  return (
    <TouchableOpacity activeOpacity={1} style={[tv.wrap, { width, height }]} onPress={toggle}>
      <PlatformVideo
        ref={videoRef}
        uri={uri}
        width={width}
        height={height}
        onStatusUpdate={(status) => {
          setPlaying(!!status.isPlaying);
          onProgress?.(status);
        }}
      />
      {!playing && (
        <View pointerEvents="none" style={StyleSheet.absoluteFill}>
          <View style={tv.playHint}>
            <Text style={tv.playHintText}>▶</Text>
          </View>
        </View>
      )}
    </TouchableOpacity>
  );
}
const tv = StyleSheet.create({
  wrap: { backgroundColor: '#000' },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 48 },
});

// Tap-anywhere-to-seek strip showing where the pro database currently
// thinks contact happens (gold marker) against the live playhead (white) --
// lets Jack check that mark against what he actually sees in the clip, the
// same "duration-relative marker + live playhead" idea Cut mode's trimBar
// already uses, just for a single point instead of a range. Single-tap
// seek via TouchableOpacity's own locationX -- no PanResponder needed here,
// unlike SyncCompareScreen's drag-to-scrub scrubber.
function ContactTimeStrip({ markerSec, positionSec, durationSec, onSeekSec }) {
  const trackWidth = useRef(0);
  return (
    <TouchableOpacity
      activeOpacity={1}
      style={s.contactStripTrack}
      onLayout={(e) => { trackWidth.current = e.nativeEvent.layout.width; }}
      onPress={(e) => {
        if (!trackWidth.current || !durationSec) return;
        const x = Math.max(0, Math.min(trackWidth.current, e.nativeEvent.locationX));
        onSeekSec((x / trackWidth.current) * durationSec);
      }}
    >
      {durationSec > 0 && (
        <View style={[s.trimPlayhead, { left: `${(positionSec / durationSec) * 100}%` }]} />
      )}
      {durationSec > 0 && markerSec != null && (
        <View style={[s.contactMarker, { left: `${(markerSec / durationSec) * 100}%` }]} />
      )}
    </TouchableOpacity>
  );
}

export default function DevProClipReviewScreen({ navigation }) {
  const { token } = useAuth();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [index, setIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  // Cut mode: cutStart/cutEnd are captured from the video's own playback
  // position (seconds), not typed in -- matches this screen's tap-driven
  // style rather than adding a numeric input. positionSec/durationSec track
  // the live video for rendering the trim bar and "Set start/end" captures.
  const [cutMode, setCutMode] = useState(false);
  const [cutStart, setCutStart] = useState(null);
  const [cutEnd, setCutEnd] = useState(null);
  const [positionSec, setPositionSec] = useState(0);
  const [durationSec, setDurationSec] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [cutError, setCutError] = useState(null);
  const videoRef = useRef(null);
  // Measured width of Fix Contact Time's rough-scrub track (native only --
  // web uses a real <input type="range"> which needs no manual width math).
  const scrubTrackWidthRef = useRef(0);

  // Split point (2026-08-27): a third mark within Cut mode for clips that
  // actually contain two swings -- submitting "Split into 2 shots" keeps the
  // half containing the entry's already-known contact time as this entry
  // (re-trimmed), and turns the OTHER half into a brand-new database entry
  // instead of discarding it like a normal cut would.
  const [splitPoint, setSplitPoint] = useState(null);
  const [splitError, setSplitError] = useState(null);

  // Wrong-shot-type mode: same reveal-a-sub-panel pattern as cutMode above,
  // not a 4th top-level button, to keep the panel compact.
  const [shotTypeMode, setShotTypeMode] = useState(false);
  const [shotTypeError, setShotTypeError] = useState(null);

  // Contact-time correction mode. "Fix contact time" jumps straight to the
  // 'fine' frame-stepper, anchored on wherever the video is currently paused
  // (roughSec, float seconds -- mirrors ContactMarkingScreen.js's roughTime).
  // 'rough' is still reachable via the "Scrub" button for repositioning when
  // +/-FINE_RADIUS frames isn't enough. The 'fine' pinning effect is a plain
  // synchronous pauseAsync()+setPositionAsync() -- the exact shape
  // ContactMarkingScreen.js / DevSwingReviewScreen.js use, which repaints the
  // frame live on Android; an earlier async/nudge version did not.
  const [ctStep, setCtStep] = useState(null);
  const [contactTimeError, setContactTimeError] = useState(null);
  const [roughSec, setRoughSec] = useState(null);
  const [fineOffset, setFineOffset] = useState(0);
  const [scrubFraction, setScrubFraction] = useState(null);
  // Set after a Cut/Split so the default panel shows an explicit "Next ->"
  // button (cut/split no longer auto-advance -- Jack stays on the re-trimmed
  // clip to also fix its contact time / shot type first).
  const [justEdited, setJustEdited] = useState(false);
  // expo-av's setPositionAsync() silently no-ops before the player is loaded
  // (same trap SyncCompareScreen.js guards against). Track readiness and defer
  // the last requested seek until the first loaded status update lands.
  const videoReadyRef = useRef(false);
  const pendingSeekRef = useRef(null);

  // Lifetime "verified for label accuracy" counts across every past
  // session, from list_pro_clip_review_candidates.py's progress block --
  // separate from doneCount, which only tracks this session.
  const [progress, setProgress] = useState(null);

  // "View in source footage" (hybrid Sprint 0 approach, 2026-08-27): the
  // fast per-clip review above stays the main pass, but a flagged entry can
  // be double-checked against the full, uncut compilation video it came
  // from -- catches cutting mistakes (wrong shot grabbed, missing context)
  // the isolated ~3s clip alone can't reveal. Lazy-rendered (uri only set
  // once the modal opens) since these source files can be 100MB-1.3GB.
  const [sourceFootageOpen, setSourceFootageOpen] = useState(false);
  const [sourceSeeked, setSourceSeeked] = useState(false);
  const sourceVideoRef = useRef(null);

  // "Edit" expander (2026-08-27, renamed from a generic "More"): everything
  // that isn't a one-tap verdict -- cut/split, wrong shot type, fix contact
  // time, view source footage -- lives behind this single toggle now,
  // matching Jack's own mental model of "Looks good / edit it / don't use
  // this" instead of a flat grid of verdict buttons.
  const [editOpen, setEditOpen] = useState(false);

  // Custom clip names, keyed by candidate id, kept client-side only --
  // going back to re-visit a candidate should still show what was typed
  // without a re-fetch. Sent along with every verdict/cut submission.
  const [names, setNames] = useState({});

  // Full-screen video, floating overlays -- same pattern established
  // across the other single-video Dev Page tools this session.
  const { width: videoWidth, height: videoHeight } = useWindowSize();

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/pro-clip-review-candidates`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        setCandidates(data.candidates ?? []);
        setProgress(data.progress ?? null);
        setIndex(0);
        setDoneCount(0);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [token, reloadKey]);

  const current = candidates[index];

  // Clear every per-clip sub-panel / anchor. Called both when `index` changes
  // (new clip) and, without an index change, right after a Cut/Split so the
  // screen returns to the default panel while staying on the same clip.
  const resetClipSubState = useCallback(() => {
    setCutMode(false);
    setCutStart(null);
    setCutEnd(null);
    setCutError(null);
    setSplitPoint(null);
    setSplitError(null);
    setShotTypeMode(false);
    setShotTypeError(null);
    setCtStep(null);
    setContactTimeError(null);
    setRoughSec(null);
    setFineOffset(0);
    setScrubFraction(null);
  }, []);

  useEffect(() => {
    resetClipSubState();
    setJustEdited(false);
    videoReadyRef.current = false;
    pendingSeekRef.current = null;
    setSourceFootageOpen(false);
    setSourceSeeked(false);
    setEditOpen(false);
  }, [index, resetClipSubState]);

  // Server clip URLs carry no query string, so a bare ?v= cache-buster forces
  // <PlatformVideo> to reload the re-encoded bytes after a cut/split without
  // the clip id (and thus the candidate) changing.
  const withNonce = (url) => `${url.split('?')[0]}?v=${Date.now()}`;

  // Update the current candidate in place (used when a cut/split/correction
  // must stay on the same clip instead of advancing the index).
  const patchCurrent = useCallback((partial) => {
    setCandidates((cs) => cs.map((c, i) => (i === index ? { ...c, ...partial } : c)));
  }, [index]);

  const seekTo = (sec) => {
    const ms = Math.round(Math.max(0, sec) * 1000);
    if (!videoReadyRef.current) { pendingSeekRef.current = ms; return; }
    videoRef.current?.setPositionAsync(ms);
  };

  // Single stable status handler. The main video is now a plain
  // <PlatformVideo> (not the TappableVideo wrapper, which is kept only for the
  // source-footage modal) -- an inline handler recreated every render churned
  // and fought in-flight seeks on native.
  const handleStatus = useCallback((status) => {
    const wasReady = videoReadyRef.current;
    videoReadyRef.current = !!status.isLoaded;
    setIsPlaying(!!status.isPlaying);
    if (status.positionMillis != null) setPositionSec(status.positionMillis / 1000);
    if (status.durationMillis != null) setDurationSec(status.durationMillis / 1000);
    if (!wasReady && videoReadyRef.current && pendingSeekRef.current != null) {
      videoRef.current?.setPositionAsync(pendingSeekRef.current);
      pendingSeekRef.current = null;
    }
  }, []);

  const togglePlay = () => {
    if (isPlaying) videoRef.current?.pauseAsync();
    else videoRef.current?.playAsync();
  };

  // Load + play each clip when it opens (or when its URL is cache-busted after
  // a cut/split) so the decoder is warm -- DevSwingReviewScreen.js relies on
  // the same warm start for its synchronous fine-step effect to repaint.
  useEffect(() => {
    if (!current || !videoRef.current) return;
    videoRef.current.setPositionAsync(0);
    videoRef.current.playAsync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.id, current?.clip_url]);

  // Fine phase only: keep the video paused on exactly roughSec + fineOffset
  // frames whenever the offset (or the anchor) changes. Plain synchronous
  // fire-and-forget, identical to ContactMarkingScreen.js:87-93 /
  // DevSwingReviewScreen.js:128-133 -- do NOT make this async or add an
  // Android play/pause nudge; that races and stops repainting the frame.
  useEffect(() => {
    if (ctStep !== 'fine' || roughSec === null) return;
    const fps = current?.fps || 30;
    videoRef.current?.pauseAsync();
    videoRef.current?.setPositionAsync(
      Math.round(Math.max(0, roughSec + fineOffset / fps) * 1000)
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fineOffset, roughSec, ctStep]);

  const submit = async (verdict) => {
    if (!current || submitting) return;
    playTapSound();
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, verdict, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      setDoneCount((c) => c + 1);
      setIndex((i) => i + 1);
    } catch {
      // Leave the candidate in place so Jack can just try again -- same
      // recovery pattern as the other review screens' submit failure.
    } finally {
      setSubmitting(false);
    }
  };

  const submitCut = async () => {
    if (!current || submitting || cutStart == null || cutEnd == null) return;
    if (cutEnd - cutStart < MIN_CUT_SEC) {
      setCutError(`Trimmed clip must be at least ${MIN_CUT_SEC}s`);
      return;
    }
    playTapSound();
    setSubmitting(true);
    setCutError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/cut`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, start_sec: cutStart, end_sec: cutEnd, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      // Stay on the re-trimmed clip: reload its bytes, keep the shifted contact
      // time, and let Jack also fix contact time / shot type before "Next ->".
      patchCurrent({
        clip_contact_time_sec: data.new_contact_time_sec ?? current.clip_contact_time_sec,
        clip_url: withNonce(current.clip_url),
      });
      resetClipSubState();
      videoReadyRef.current = false;
      setJustEdited(true);
      setEditOpen(true);
    } catch {
      setCutError("Couldn't cut this clip — try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const submitSplit = async () => {
    if (!current || submitting || cutStart == null || splitPoint == null || cutEnd == null) return;
    if (!(cutStart < splitPoint && splitPoint < cutEnd)) {
      setSplitError('Mark start, then the swing boundary, then end, in order.');
      return;
    }
    if (splitPoint - cutStart < MIN_CUT_SEC || cutEnd - splitPoint < MIN_CUT_SEC) {
      setSplitError(`Both halves must be at least ${MIN_CUT_SEC}s`);
      return;
    }
    playTapSound();
    setSubmitting(true);
    setSplitError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/split`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          id: current.id, start_sec: cutStart, split_sec: splitPoint, end_sec: cutEnd,
          name: names[current.id] || null,
        }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      // Stay on the re-trimmed first half, and insert the brand-new second
      // half right after it so it gets reviewed next.
      setCandidates((cs) => {
        const next = cs.map((c, i) => (i === index ? {
          ...c,
          clip_contact_time_sec: data.original_new_contact_time_sec ?? c.clip_contact_time_sec,
          clip_url: withNonce(c.clip_url),
        } : c));
        if (data.new_entry) {
          next.splice(index + 1, 0, {
            ...data.new_entry,
            source_video_url: null,
            source_peak_time_sec: null,
          });
        }
        return next;
      });
      resetClipSubState();
      videoReadyRef.current = false;
      setJustEdited(true);
      setEditOpen(true);
    } catch {
      setSplitError("Couldn't split this clip — try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const submitShotType = async (newShotType) => {
    if (!current || submitting) return;
    playTapSound();
    setSubmitting(true);
    setShotTypeError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/correct-shot-type`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, new_shot_type: newShotType, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      const data = await res.json();
      if (justEdited) {
        // Chained edit after a cut/split -- the clip file moved folders, so
        // reload it from the new path; "Next ->" advances.
        patchCurrent({
          shot_type: newShotType,
          clip_url: withNonce(data.clip_path ? `/pro-clips/${data.clip_path}` : current.clip_url),
        });
        setShotTypeMode(false);
      } else {
        setDoneCount((c) => c + 1);
        setIndex((i) => i + 1);
      }
    } catch {
      setShotTypeError("Couldn't correct the shot type — try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const submitContactTime = async (fineT) => {
    if (!current || submitting || fineT == null) return;
    playTapSound();
    setSubmitting(true);
    setContactTimeError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-clip-review/correct-contact-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, new_contact_time_sec: fineT, name: names[current.id] || null }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      if (justEdited) {
        // Chained edit after a cut/split -- stay on the clip so shot type can
        // also be fixed; "Next ->" advances.
        patchCurrent({ clip_contact_time_sec: fineT });
        setCtStep(null); setRoughSec(null); setFineOffset(0); setScrubFraction(null);
      } else {
        setDoneCount((c) => c + 1);
        setIndex((i) => i + 1);
      }
    } catch {
      setContactTimeError("Couldn't correct the contact time — try again.");
    } finally {
      setSubmitting(false);
    }
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
            <Text style={s.errorText}>Couldn't load pro clip review candidates — check your connection.</Text>
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
                ? 'No reviewable pro clips found.'
                : `You reviewed all ${candidates.length} clips this batch.`}
            </Text>
            <TouchableOpacity style={s.retryBtn} onPress={() => setReloadKey((k) => k + 1)}>
              <Text style={s.retryBtnText}>Load more clips</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <View style={s.stage}>
          <TouchableOpacity
            activeOpacity={1}
            style={[tv.wrap, { width: videoWidth, height: videoHeight }]}
            onPress={togglePlay}
          >
            <PlatformVideo
              ref={videoRef}
              uri={`${API_BASE}${current.clip_url}`}
              width={videoWidth}
              height={videoHeight}
              onStatusUpdate={handleStatus}
            />
            {!isPlaying && (
              <View pointerEvents="none" style={StyleSheet.absoluteFill}>
                <View style={tv.playHint}>
                  <Text style={tv.playHintText}>▶</Text>
                </View>
              </View>
            )}
          </TouchableOpacity>

          <View style={s.progressRow} pointerEvents="box-none">
            {index > 0 && (
              <TouchableOpacity
                style={s.prevBtn}
                onPress={() => { playTapSound(); setIndex((i) => Math.max(0, i - 1)); }}
                disabled={submitting}
              >
                <Text style={s.prevBtnText}>‹ Previous</Text>
              </TouchableOpacity>
            )}
            <Text style={s.progressText}>Clip {index + 1} of {candidates.length}</Text>
            <Text style={s.progressSub}>
              {current.id} · {current.shot_type}
              {current.camera_angle != null ? ` · ${current.camera_angle}°` : ''}
            </Text>
            <TextInput
              style={s.nameInput}
              value={names[current.id] || ''}
              onChangeText={(text) => setNames((n) => ({ ...n, [current.id]: text }))}
              placeholder="Name this clip (optional)"
              placeholderTextColor="rgba(255,255,255,0.4)"
            />
          </View>

          {cutMode ? (
            <View style={s.verdictPanel}>
              <View style={s.trimBar}>
                {durationSec > 0 && cutStart != null && (
                  <View style={[s.trimRange, {
                    left: `${(cutStart / durationSec) * 100}%`,
                    width: `${(((cutEnd ?? durationSec) - cutStart) / durationSec) * 100}%`,
                  }]} />
                )}
                {durationSec > 0 && (
                  <View style={[s.trimPlayhead, { left: `${(positionSec / durationSec) * 100}%` }]} />
                )}
                {durationSec > 0 && splitPoint != null && (
                  <View style={[s.contactMarker, { left: `${(splitPoint / durationSec) * 100}%` }]} />
                )}
              </View>
              <Text style={s.trimTimeText}>
                {positionSec.toFixed(2)}s / {durationSec.toFixed(2)}s
                {'  ·  '}start {cutStart != null ? `${cutStart.toFixed(2)}s` : '—'}
                {'  '}end {cutEnd != null ? `${cutEnd.toFixed(2)}s` : '—'}
                {'  '}split {splitPoint != null ? `${splitPoint.toFixed(2)}s` : '—'}
              </Text>
              {cutError && <Text style={s.trimErrorText}>{cutError}</Text>}
              {splitError && <Text style={s.trimErrorText}>{splitError}</Text>}

              <View style={s.trimBtnRow}>
                <TouchableOpacity style={s.trimSetBtn} onPress={() => { setCutStart(positionSec); setCutError(null); }} disabled={submitting}>
                  <Text style={s.verdictBtnText}>Set start</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.trimSetBtn} onPress={() => { setCutEnd(positionSec); setCutError(null); }} disabled={submitting}>
                  <Text style={s.verdictBtnText}>Set end</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.trimSetBtn} onPress={() => { setSplitPoint(positionSec); setSplitError(null); }} disabled={submitting}>
                  <Text style={s.verdictBtnText}>Mark 2nd swing here</Text>
                </TouchableOpacity>
              </View>

              <View style={s.trimBtnRow}>
                <TouchableOpacity
                  style={s.trimCancelBtn}
                  onPress={() => {
                    setCutMode(false); setCutStart(null); setCutEnd(null); setCutError(null);
                    setSplitPoint(null); setSplitError(null);
                  }}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.trimConfirmBtn, (cutStart == null || cutEnd == null) && s.trimBtnDisabled]}
                  onPress={submitCut}
                  disabled={submitting || cutStart == null || cutEnd == null}
                >
                  <Text style={s.verdictBtnText}>Confirm cut</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    s.trimConfirmBtn,
                    (cutStart == null || splitPoint == null || cutEnd == null || !(cutStart < splitPoint && splitPoint < cutEnd)) && s.trimBtnDisabled,
                  ]}
                  onPress={submitSplit}
                  disabled={submitting || cutStart == null || splitPoint == null || cutEnd == null || !(cutStart < splitPoint && splitPoint < cutEnd)}
                >
                  <Text style={s.verdictBtnText}>Split into 2 shots</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : ctStep ? (
            (() => {
              const fps = current.fps || 30;
              const contactSec = Math.max(0, (roughSec ?? 0) + fineOffset / fps);
              const contactFrame = Math.round(contactSec * fps);
              // Reads the real player position/duration whenever there's no
              // active drag -- keeps the bar in sync during ordinary playback
              // instead of freezing at a stale value.
              const progressFraction = scrubFraction ?? (durationSec > 0 ? Math.min(1, positionSec / durationSec) : 0);
              const setOffset = (n) => setFineOffset(Math.min(FINE_RADIUS, Math.max(-FINE_RADIUS, n)));
              const onScrubMove = (e) => {
                if (!durationSec || !scrubTrackWidthRef.current) return;
                const frac = Math.min(1, Math.max(0, e.nativeEvent.locationX / scrubTrackWidthRef.current));
                setScrubFraction(frac);
                seekTo(frac * durationSec);
              };
              const markWindow = async () => {
                await videoRef.current?.pauseAsync();
                setRoughSec(positionSec);
                setFineOffset(0);
                setScrubFraction(null);
                setCtStep('fine');
              };
              const currentContact = current.clip_contact_time_sec;
              const unchanged = currentContact != null && Math.abs(contactSec - currentContact) < 0.5 / fps;
              return (
                <View style={[s.verdictPanel, s.ctPanel]}>
                  {ctStep === 'rough' ? (
                    <>
                      <Text style={s.doneCountText}>Tap video to play/pause, drag bar to scrub near contact, then "Mark"</Text>

                      {IS_WEB
                        ? React.createElement('input', {
                            type: 'range', min: '0', max: '1', step: '0.001',
                            value: String(progressFraction),
                            onChange: (e) => seekTo(parseFloat(e.target.value) * durationSec),
                            style: {
                              width: '100%', accentColor: colors.primary,
                              marginBottom: 6, cursor: 'pointer', height: 20,
                            },
                          })
                        : (
                          <View
                            style={s.ctScrubTrack}
                            onLayout={(e) => { scrubTrackWidthRef.current = e.nativeEvent.layout.width; }}
                            onStartShouldSetResponder={() => true}
                            onMoveShouldSetResponder={() => true}
                            onResponderGrant={onScrubMove}
                            onResponderMove={onScrubMove}
                            onResponderRelease={() => setScrubFraction(null)}
                            onResponderTerminate={() => setScrubFraction(null)}
                          >
                            <View style={[s.ctScrubFill, { width: `${progressFraction * 100}%` }]} />
                            <View style={[s.ctScrubThumb, { left: `${progressFraction * 100}%` }]} />
                          </View>
                        )}
                      <Text style={s.trimTimeText}>{positionSec.toFixed(2)}s / {durationSec.toFixed(2)}s</Text>

                      <View style={s.trimBtnRow}>
                        <TouchableOpacity style={s.trimSetBtn} onPress={markWindow} disabled={submitting}>
                          <Text style={s.verdictBtnText}>Mark contact window →</Text>
                        </TouchableOpacity>
                      </View>
                    </>
                  ) : (
                    <>
                      <Text style={s.doneCountText}>Step ◀ ▶ to the exact contact frame · "Scrub" to move further</Text>
                      <View style={s.ctFrameRow}>
                        <TouchableOpacity style={s.ctFrameBtn} onPress={() => setOffset(fineOffset - 5)} disabled={submitting || fineOffset <= -FINE_RADIUS}>
                          <Text style={[s.ctFrameBtnTextSm, fineOffset <= -FINE_RADIUS && s.ctFrameBtnDisabled]}>◀◀</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={s.ctFrameBtn} onPress={() => setOffset(fineOffset - 1)} disabled={submitting || fineOffset <= -FINE_RADIUS}>
                          <Text style={[s.ctFrameBtnText, fineOffset <= -FINE_RADIUS && s.ctFrameBtnDisabled]}>◀</Text>
                        </TouchableOpacity>
                        <View style={s.ctFrameCenter}>
                          <Text style={s.ctFrameNumber}>Frame {contactFrame}</Text>
                          <Text style={s.ctFrameOffset}>{fineOffset >= 0 ? '+' : ''}{fineOffset} · {contactSec.toFixed(2)}s</Text>
                        </View>
                        <TouchableOpacity style={s.ctFrameBtn} onPress={() => setOffset(fineOffset + 1)} disabled={submitting || fineOffset >= FINE_RADIUS}>
                          <Text style={[s.ctFrameBtnText, fineOffset >= FINE_RADIUS && s.ctFrameBtnDisabled]}>▶</Text>
                        </TouchableOpacity>
                        <TouchableOpacity style={s.ctFrameBtn} onPress={() => setOffset(fineOffset + 5)} disabled={submitting || fineOffset >= FINE_RADIUS}>
                          <Text style={[s.ctFrameBtnTextSm, fineOffset >= FINE_RADIUS && s.ctFrameBtnDisabled]}>▶▶</Text>
                        </TouchableOpacity>
                      </View>
                    </>
                  )}

                  {contactTimeError && <Text style={s.trimErrorText}>{contactTimeError}</Text>}

                  <View style={s.trimBtnRow}>
                    {ctStep === 'fine' && (
                      <TouchableOpacity
                        style={s.trimCancelBtn}
                        onPress={() => { setCtStep('rough'); setScrubFraction(null); videoRef.current?.playAsync(); }}
                        disabled={submitting}
                      >
                        <Text style={s.verdictBtnText}>← Scrub</Text>
                      </TouchableOpacity>
                    )}
                    <TouchableOpacity
                      style={s.trimCancelBtn}
                      onPress={() => {
                        setCtStep(null); setRoughSec(null);
                        setFineOffset(0); setContactTimeError(null); setScrubFraction(null);
                      }}
                      disabled={submitting}
                    >
                      <Text style={s.verdictBtnText}>Cancel</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      style={[s.trimConfirmBtn, (ctStep !== 'fine' || roughSec === null || unchanged) && s.trimBtnDisabled]}
                      onPress={() => submitContactTime(contactSec)}
                      disabled={submitting || ctStep !== 'fine' || roughSec === null || unchanged}
                    >
                      <Text style={s.verdictBtnText}>
                        {submitting ? 'Saving…' : unchanged ? 'No change' : 'Confirm'}
                      </Text>
                    </TouchableOpacity>
                  </View>
                </View>
              );
            })()
          ) : shotTypeMode ? (
            <View style={s.verdictPanel}>
              <Text style={s.doneCountText}>Currently labeled {current.shot_type}. What should it be?</Text>
              {shotTypeError && <Text style={s.trimErrorText}>{shotTypeError}</Text>}
              <View style={s.verdictBtnRow}>
                {SHOT_TYPES.filter((st) => st !== current.shot_type).map((st) => (
                  <TouchableOpacity
                    key={st}
                    style={[s.verdictBtn, s.verdictBtnHalf]}
                    onPress={() => submitShotType(st)}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>{st.charAt(0).toUpperCase() + st.slice(1)}</Text>
                  </TouchableOpacity>
                ))}
                <TouchableOpacity
                  style={[s.cutModeBtn, s.verdictBtnHalf]}
                  onPress={() => { setShotTypeMode(false); setShotTypeError(null); }}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Cancel</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <View style={s.verdictPanel}>
              <ContactTimeStrip
                markerSec={current.clip_contact_time_sec}
                positionSec={positionSec}
                durationSec={durationSec}
                onSeekSec={seekTo}
              />
              <Text style={s.contactStripLabel}>
                Contact: {current.clip_contact_time_sec != null ? `${current.clip_contact_time_sec.toFixed(2)}s` : '—'}
              </Text>
              {justEdited && (
                <Text style={s.doneCountText}>Edited — fix contact time / shot type below, then Next</Text>
              )}
              <View style={s.verdictBtnRow}>
                {justEdited ? (
                  <TouchableOpacity
                    style={[s.verdictBtn, s.verdictBtnFull, s.verdictBtnOk]}
                    onPress={() => { playTapSound(); setDoneCount((c) => c + 1); setIndex((i) => i + 1); }}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>Next →</Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    style={[s.verdictBtn, s.verdictBtnFull, s.verdictBtnOk]}
                    onPress={() => submit('label_confirmed')}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>Looks good</Text>
                  </TouchableOpacity>
                )}
              </View>
              <View style={s.verdictBtnRow}>
                <TouchableOpacity
                  style={[s.cutModeBtn, s.verdictBtnHalf]}
                  onPress={() => setEditOpen((v) => !v)}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>{editOpen ? 'Close ▴' : 'Edit ▾'}</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.verdictBtn, s.verdictBtnHalf]}
                  onPress={() => submit('excluded')}
                  disabled={submitting}
                >
                  <Text style={s.verdictBtnText}>Don't use this</Text>
                </TouchableOpacity>
              </View>
              {editOpen && (
                <View style={s.verdictBtnRow}>
                  <TouchableOpacity
                    style={[s.cutModeBtn, s.verdictBtnHalf]}
                    onPress={() => { videoRef.current?.pauseAsync(); setCutMode(true); }}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>Cut/Split...</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.cutModeBtn, s.verdictBtnHalf]}
                    onPress={() => setShotTypeMode(true)}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>Wrong shot type?</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.cutModeBtn, s.verdictBtnHalf]}
                    onPress={async () => {
                      // Straight into the fine frame-stepper, anchored on
                      // wherever the video is paused right now (Jack lines it
                      // up on the ContactTimeStrip / tap-to-play first). Falls
                      // back to the stored contact time if the clip is sitting
                      // at 0 or ran to the end via autoplay.
                      await videoRef.current?.pauseAsync();
                      const dur = durationSec || 0;
                      const positioned = positionSec > 0.03 && (dur === 0 || positionSec < dur - 0.03);
                      const anchor = positioned
                        ? positionSec
                        : current.clip_contact_time_sec != null
                          ? current.clip_contact_time_sec
                          : (dur > 0 ? dur / 2 : 0);
                      seekTo(anchor);
                      setRoughSec(anchor);
                      setFineOffset(0);
                      setScrubFraction(null);
                      setCtStep('fine');
                    }}
                    disabled={submitting}
                  >
                    <Text style={s.verdictBtnText}>Fix contact time</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.cutModeBtn, s.verdictBtnHalf, !current.source_video_url && s.trimBtnDisabled]}
                    onPress={() => { videoRef.current?.pauseAsync(); setSourceFootageOpen(true); }}
                    disabled={submitting || !current.source_video_url}
                  >
                    <Text style={s.verdictBtnText}>View in source footage</Text>
                  </TouchableOpacity>
                </View>
              )}
              <Text style={s.doneCountText}>{doneCount} reviewed this session</Text>
              {progress && (
                <Text style={s.doneCountText}>
                  {progress.label_reviewed} of {progress.live_total} verified for label accuracy
                </Text>
              )}
              {progress?.contact_fill_pending > 0 && (
                <Text style={s.doneCountText}>
                  {progress.contact_fill_pending} with an audio-guessed contact time to check
                </Text>
              )}
            </View>
          )}
        </View>

        <Modal
          visible={sourceFootageOpen}
          animationType="slide"
          onRequestClose={() => setSourceFootageOpen(false)}
        >
          <SafeAreaView style={s.sourceModalSafe}>
            <View style={s.sourceModalHeader}>
              <Text style={s.sourceModalTitle} numberOfLines={1}>
                {current.id} · contact at {current.source_peak_time_sec != null ? `${current.source_peak_time_sec.toFixed(1)}s` : '—'} in source
              </Text>
              <TouchableOpacity onPress={() => setSourceFootageOpen(false)}>
                <Text style={s.sourceModalClose}>✕ Close</Text>
              </TouchableOpacity>
            </View>
            {sourceFootageOpen && current.source_video_url ? (
              <TappableVideo
                uri={`${API_BASE}${current.source_video_url}`}
                width={videoWidth}
                height={videoHeight - 90}
                videoRef={sourceVideoRef}
                onProgress={(status) => {
                  if (!sourceSeeked && status.durationMillis > 0 && current.source_peak_time_sec != null) {
                    sourceVideoRef.current?.setPositionAsync(current.source_peak_time_sec * 1000);
                    setSourceSeeked(true);
                  }
                }}
              />
            ) : (
              <View style={s.centerFill}>
                <Text style={s.errorText}>No source footage mapped for this clip.</Text>
              </View>
            )}
            <Text style={s.sourceModalHint}>
              Full compilation video, seeked to this shot's contact moment — scrub to see
              the shots before/after for context. These files are large; give it a moment
              to buffer on first open.
            </Text>
          </SafeAreaView>
        </Modal>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },

  stage: { flex: 1, position: 'relative' },

  progressRow: {
    position: 'absolute', top: 0, left: 0, right: 0, alignItems: 'center',
    paddingTop: 14, paddingBottom: 10, backgroundColor: 'rgba(0,0,0,0.5)',
  },
  progressText: { color: '#fff', fontSize: 16, fontFamily: fonts.extrabold },
  progressSub: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  prevBtn: { position: 'absolute', left: 14, top: 12, paddingVertical: 6, paddingHorizontal: 4 },
  prevBtnText: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },

  nameInput: {
    marginTop: 10, width: '80%', color: '#fff', fontSize: 13.5, fontFamily: fonts.regular,
    backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: radius.md,
    paddingHorizontal: 12, paddingVertical: 8, textAlign: 'center',
  },

  verdictPanel: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(20,20,20,0.9)', borderTopWidth: 1, borderColor: colors.border,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    // Tightened further 2026-08-27 (on top of the original ~50% cut) once a
    // "More" expander took most buttons out of the always-visible panel --
    // less padding needed since the panel itself is shorter most of the time.
    padding: 8, paddingBottom: 10, gap: 4,
  },
  verdictBtnRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  verdictBtn: {
    borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: colors.coral,
  },
  // Two per row instead of one full-width button per row -- halves the
  // panel's height since it no longer stacks every verdict vertically.
  verdictBtnHalf: { width: '47%' },
  verdictBtnFull: { width: '100%' },
  verdictBtnOk: { backgroundColor: colors.primary },
  verdictBtnText: { color: colors.white, fontSize: 14.5, fontFamily: fonts.extrabold },
  doneCountText: { color: 'rgba(255,255,255,0.7)', fontSize: 11.5, textAlign: 'center', marginTop: 2, fontFamily: fonts.regular },

  cutModeBtn: {
    borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border,
  },

  trimBar: {
    height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.15)',
    position: 'relative', overflow: 'visible', marginBottom: 4,
  },
  trimRange: {
    position: 'absolute', top: 0, bottom: 0, backgroundColor: colors.primary,
    borderRadius: 4, minWidth: 2,
  },
  trimPlayhead: {
    position: 'absolute', top: -3, width: 2, height: 14,
    backgroundColor: '#fff', marginLeft: -1,
  },

  // Same track look as trimBar, but this one's directly tappable (see
  // ContactTimeStrip) since it has no separate "Set start/end" buttons.
  contactStripTrack: {
    height: 8, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.15)',
    position: 'relative', overflow: 'visible', marginBottom: 4,
  },
  contactMarker: {
    position: 'absolute', top: -4, width: 3, height: 16, borderRadius: 1.5,
    backgroundColor: colors.gold, marginLeft: -1.5,
  },
  contactStripLabel: {
    color: 'rgba(255,255,255,0.75)', fontSize: 11.5, fontFamily: fonts.regular,
    textAlign: 'center', marginBottom: 6,
  },
  // Fix Contact Time's rough-scrub track (native only -- web uses a real
  // <input type="range">), ported directly from ContactMarkingScreen.js's
  // progressTrack/progressFill/progressThumb (its "rough" phase).
  ctScrubTrack: {
    height: 8, backgroundColor: 'rgba(255,255,255,0.25)', borderRadius: 4,
    marginBottom: 8, position: 'relative',
  },
  ctScrubFill: { height: 8, backgroundColor: colors.primary, borderRadius: 4 },
  ctScrubThumb: {
    position: 'absolute', top: -4, width: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.primary, marginLeft: -8,
  },
  // Fine-offset frame stepper, ported from ContactMarkingScreen.js's
  // frameRow/frameBtn/frameCenter (its "fine" phase).
  ctFrameRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: radius.lg,
    paddingVertical: 8, paddingHorizontal: 12, marginBottom: 8,
  },
  ctFrameBtn: { padding: 6 },
  ctFrameBtnText: { color: colors.primary, fontSize: 22, fontFamily: fonts.bold },
  ctFrameBtnTextSm: { color: colors.primary, fontSize: 15, fontFamily: fonts.bold },
  // Fine/rough contact panel: extra bottom room so the action row clears the
  // Android gesture/nav bar (this screen has no SafeAreaProvider), and it
  // stays compact enough to fit above the fold on a phone.
  ctPanel: { paddingBottom: Platform.OS === 'android' ? 30 : 14, gap: 6 },
  ctFrameBtnDisabled: { color: 'rgba(255,255,255,0.3)' },
  ctFrameCenter: { alignItems: 'center' },
  ctFrameNumber: { color: '#fff', fontSize: 17, fontFamily: fonts.extrabold },
  ctFrameOffset: { color: 'rgba(255,255,255,0.7)', fontSize: 11, marginTop: 1, fontFamily: fonts.regular },
  trimTimeText: { color: 'rgba(255,255,255,0.85)', fontSize: 12.5, fontFamily: fonts.regular, marginBottom: 4 },
  trimErrorText: { color: colors.coral, fontSize: 12.5, fontFamily: fonts.bold, marginBottom: 4 },
  trimBtnRow: { flexDirection: 'row', gap: 10 },
  trimSetBtn: {
    flex: 1, borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.12)',
  },
  trimCancelBtn: {
    flex: 1, borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.border,
  },
  trimConfirmBtn: {
    flex: 1, borderRadius: radius.lg, paddingVertical: 6, alignItems: 'center',
    backgroundColor: colors.primary,
  },
  trimBtnDisabled: { opacity: 0.4 },

  sourceModalSafe: { flex: 1, backgroundColor: '#000' },
  sourceModalHeader: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: 10, paddingBottom: 10,
  },
  sourceModalTitle: { flex: 1, color: '#fff', fontSize: 13.5, fontFamily: fonts.bold, marginRight: 12 },
  sourceModalClose: { color: colors.primary, fontSize: 14, fontFamily: fonts.bold },
  sourceModalHint: {
    color: 'rgba(255,255,255,0.6)', fontSize: 11.5, fontFamily: fonts.regular,
    textAlign: 'center', lineHeight: 16, paddingHorizontal: 20, paddingVertical: 10,
  },

  doneTitle: { color: colors.primary, fontSize: 22, fontFamily: fonts.extrabold, marginBottom: 10 },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', lineHeight: 19, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11, marginTop: 14 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
