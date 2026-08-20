import { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator,
  Image, PanResponder,
} from 'react-native';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius, spacing } from '../theme';

// Manual fallback for the fine-tuned ball detector project's labeling
// pipeline (see the plan): frames where the classical-detector-plus-
// Claude-confirm approach found nothing plausible get queued here
// (needs_manual_review), plus a small spot-check slice of already-
// confirmed labels so Jack can sanity-check the automated pipeline's
// accuracy directly rather than only ever seeing the hard cases.
//
// New interaction pattern for this app's Dev Page -- every other review
// tool is tap-a-button; this is the first draw-a-box-on-a-static-image
// tool, since there's no existing verdict to just agree/disagree with.

function DrawableImage({ uri, size, existingBox, onBoxChange }) {
  const [drag, setDrag] = useState(null); // {startX, startY, curX, curY} in on-screen px, relative to the image
  const containerRef = useRef(null);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        const { locationX, locationY } = evt.nativeEvent;
        setDrag({ startX: locationX, startY: locationY, curX: locationX, curY: locationY });
      },
      onPanResponderMove: (evt) => {
        const { locationX, locationY } = evt.nativeEvent;
        setDrag((d) => d && { ...d, curX: locationX, curY: locationY });
      },
      onPanResponderRelease: () => {
        setDrag((d) => {
          if (!d) return d;
          const x1 = Math.max(0, Math.min(d.startX, d.curX));
          const y1 = Math.max(0, Math.min(d.startY, d.curY));
          const x2 = Math.min(size.width, Math.max(d.startX, d.curX));
          const y2 = Math.min(size.height, Math.max(d.startY, d.curY));
          // Ignore an accidental tap/near-zero drag -- not a real box.
          if (x2 - x1 < 4 || y2 - y1 < 4) {
            onBoxChange(null);
            return null;
          }
          onBoxChange({
            x1: x1 / size.width, y1: y1 / size.height,
            x2: x2 / size.width, y2: y2 / size.height,
          });
          return d;
        });
      },
    })
  ).current;

  // Prefer the live drag rectangle while dragging; otherwise show whatever
  // box is already committed (either just-drawn, or an existing automated
  // label being spot-checked).
  const displayBox = drag
    ? {
        x1: Math.min(drag.startX, drag.curX), y1: Math.min(drag.startY, drag.curY),
        x2: Math.max(drag.startX, drag.curX), y2: Math.max(drag.startY, drag.curY),
      }
    : existingBox
    ? {
        x1: existingBox.x1 * size.width, y1: existingBox.y1 * size.height,
        x2: existingBox.x2 * size.width, y2: existingBox.y2 * size.height,
      }
    : null;

  return (
    <View ref={containerRef} style={{ width: size.width, height: size.height }} {...panResponder.panHandlers}>
      <Image source={{ uri }} style={{ width: size.width, height: size.height }} resizeMode="contain" />
      {displayBox && (
        <View
          pointerEvents="none"
          style={[
            d.box,
            {
              left: displayBox.x1, top: displayBox.y1,
              width: displayBox.x2 - displayBox.x1, height: displayBox.y2 - displayBox.y1,
            },
          ]}
        />
      )}
    </View>
  );
}
const d = StyleSheet.create({
  box: { position: 'absolute', borderWidth: 2, borderColor: colors.coral, backgroundColor: 'rgba(180,71,47,0.15)' },
});

export default function DevBallLabelScreen({ navigation }) {
  const { token } = useAuth();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [index, setIndex] = useState(0);
  const [drawnBox, setDrawnBox] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [doneCount, setDoneCount] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);

  const { width: windowWidth, height: windowHeight } = useWindowSize();
  // Images are all 1920x1080 (16:9) source frames -- size to fit within
  // the screen leaving room for the bottom action bar, rather than
  // guessing a fixed box.
  const ACTION_BAR_HEIGHT = 140;
  const availableHeight = Math.max(200, windowHeight - ACTION_BAR_HEIGHT - 80);
  const availableWidth = windowWidth - 32;
  let imgWidth = availableWidth;
  let imgHeight = imgWidth * 9 / 16;
  if (imgHeight > availableHeight) {
    imgHeight = availableHeight;
    imgWidth = imgHeight * 16 / 9;
  }
  const imgSize = { width: Math.round(imgWidth), height: Math.round(imgHeight) };

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/ball-label-candidates`, {
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
  }, [token, reloadKey]);

  const current = candidates[index];

  useEffect(() => {
    setDrawnBox(null);
  }, [current]);

  const advance = () => {
    setDoneCount((c) => c + 1);
    setIndex((i) => i + 1);
  };

  const submit = async (ballVisible) => {
    if (!current || submitting) return;
    if (ballVisible && !drawnBox) return; // must draw a box first
    playTapSound();
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/dev/ball-label/label`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          file: current.file, bucket: current.bucket,
          ball_visible: ballVisible,
          box_norm: ballVisible ? drawnBox : null,
        }),
      });
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      advance();
    } catch {
      // Leave the candidate in place so Jack can just try again.
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
            <Text style={s.errorText}>Couldn't load ball label candidates — check your connection.</Text>
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
                ? 'No frames need manual review right now.'
                : `You reviewed all ${candidates.length} frames this batch. Reopen to load more.`}
            </Text>
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <View style={s.progressRow}>
          <Text style={s.progressText}>Frame {index + 1} of {candidates.length}</Text>
          <Text style={s.progressSub}>
            {current.purpose === 'spotcheck' ? 'Spot-check an auto-confirmed label' : 'Needs manual review'}
            {current.note ? ` · ${current.note}` : ''}
          </Text>
        </View>

        <View style={s.imageWrap}>
          <DrawableImage
            uri={`${API_BASE}${current.image_url}`}
            size={imgSize}
            existingBox={current.purpose === 'spotcheck' ? current.existing_box_norm : null}
            onBoxChange={setDrawnBox}
          />
        </View>
        <Text style={s.hint}>
          {drawnBox ? 'Box drawn — tap "Confirm box" or redraw' : 'Drag on the image to draw a box around the ball'}
        </Text>

        <View style={s.actionBar}>
          <TouchableOpacity
            style={[s.actionBtn, s.noBallBtn]}
            onPress={() => submit(false)}
            disabled={submitting}
          >
            <Text style={s.noBallBtnText}>No ball in this frame</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.actionBtn, s.confirmBtn, !drawnBox && s.actionBtnDisabled]}
            onPress={() => submit(true)}
            disabled={submitting || !drawnBox}
          >
            <Text style={s.confirmBtnText}>{submitting ? 'Saving...' : 'Confirm box'}</Text>
          </TouchableOpacity>
        </View>
        <Text style={s.doneCountText}>{doneCount} labeled this session</Text>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },

  progressRow: { alignItems: 'center', paddingTop: 14, paddingBottom: 10 },
  progressText: { color: colors.ink, fontSize: 16, fontFamily: fonts.extrabold },
  progressSub: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular, textAlign: 'center', paddingHorizontal: 20 },

  imageWrap: { alignItems: 'center', justifyContent: 'center', marginTop: 6 },
  hint: { color: colors.muted, fontSize: 12, textAlign: 'center', marginTop: 8, fontFamily: fonts.regular },

  actionBar: { flexDirection: 'row', gap: 10, paddingHorizontal: spacing.xl, marginTop: 16 },
  actionBtn: { flex: 1, borderRadius: radius.lg, paddingVertical: 15, alignItems: 'center' },
  actionBtnDisabled: { opacity: 0.4 },
  noBallBtn: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  confirmBtn: { backgroundColor: colors.primary },
  noBallBtnText: { color: colors.ink, fontSize: 14, fontFamily: fonts.extrabold },
  confirmBtnText: { color: colors.white, fontSize: 14, fontFamily: fonts.extrabold },
  doneCountText: { color: colors.muted, fontSize: 11.5, textAlign: 'center', marginTop: 12, fontFamily: fonts.regular },

  doneTitle: { color: colors.primary, fontSize: 22, fontFamily: fonts.extrabold, marginBottom: 10 },
  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', lineHeight: 19, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11, marginTop: 14 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
