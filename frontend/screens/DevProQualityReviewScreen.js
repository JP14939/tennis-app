import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator, Platform } from 'react-native';
import PlatformVideo from '../components/PlatformVideo';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { useWindowSize } from '../utils/responsive';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius } from '../theme';

// Pro-database TECHNIQUE quality tiering (roadmap 1b B1.6) -- orthogonal to
// Pro Clip Review's label-accuracy verdicts (is the shot type/contact time
// right) and stored in a completely separate log for that reason (see
// clip_review_log.py). Same free, one-at-a-time review pattern as Amateur
// Clip Review, adapted: no "current label" to confirm here, just three
// buttons. Tagged clips never resurface (server-side filtering, built in
// from day one this time -- Amateur Clip Review only got this after a real
// "why did my progress not register" gap).
const TIERS = [
  { key: 'gold', label: '⭐ Gold — textbook', hotkey: 'g', style: 'gold' },
  { key: 'ok', label: 'OK — normal', hotkey: 'o', style: 'ok' },
  { key: 'exclude', label: '✕ Exclude — bad clip', hotkey: 'x', style: 'exclude' },
];

function TappableVideo({ uri, width, height }) {
  const videoRef = useRef(null);
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
    <TouchableOpacity activeOpacity={1} style={[s.videoWrap, { width, height }]} onPress={toggle}>
      <PlatformVideo
        ref={videoRef}
        uri={uri}
        width={width}
        height={height}
        onStatusUpdate={(status) => setPlaying(!!status.isPlaying)}
      />
      {!playing && (
        <View pointerEvents="none" style={StyleSheet.absoluteFill}>
          <View style={s.playHint}><Text style={s.playHintText}>▶</Text></View>
        </View>
      )}
    </TouchableOpacity>
  );
}

export default function DevProQualityReviewScreen({ navigation, route }) {
  const { token } = useAuth();
  const { width: videoWidth, height: videoHeight } = useWindowSize();
  const shotTypeFilter = route?.params?.shotType || null;

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [progress, setProgress] = useState(null);
  const [index, setIndex] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [taggedCount, setTaggedCount] = useState(0);

  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const qs = shotTypeFilter ? `?shot_type=${encodeURIComponent(shotTypeFilter)}` : '';
        const res = await fetch(`${API_BASE}/api/dev/pro-quality-review-candidates${qs}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const data = await res.json();
        setCandidates(data.candidates ?? []);
        setProgress(data.progress ?? null);
        setIndex(0);
      } catch {
        setLoadError(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [token, shotTypeFilter]);

  const current = candidates[index];

  const goNext = () => {
    setSubmitError(null);
    setIndex((i) => Math.min(i + 1, candidates.length));
  };
  const goPrev = () => {
    setSubmitError(null);
    setIndex((i) => Math.max(i - 1, 0));
  };

  const tag = async (tier) => {
    if (!current || submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const res = await fetch(`${API_BASE}/api/dev/pro-quality-review/tag`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ id: current.id, tier }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || `Request failed (${res.status})`);
      setTaggedCount((n) => n + 1);
      goNext();
    } catch (e) {
      setSubmitError(e.message || 'Failed to save tag');
    } finally {
      setSubmitting(false);
    }
  };

  // Web-only keyboard shortcuts: G / O / X for the three tiers.
  useEffect(() => {
    if (Platform.OS !== 'web' || !current) return undefined;
    const onKeyDown = (e) => {
      const tier = TIERS.find((t) => t.hotkey === e.key.toLowerCase())?.key;
      if (!tier || submitting) return;
      const target = e.target;
      const typing = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA');
      if (typing) return;
      e.preventDefault();
      tag(tier);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [current, submitting]);

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
            <Text style={s.errorText}>Couldn't load pro quality review candidates.</Text>
            <TouchableOpacity style={s.retryBtn} onPress={() => navigation.replace('DevProQualityReview')}>
              <Text style={s.retryBtnText}>Retry</Text>
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
            <Text style={s.doneHeadline}>All caught up</Text>
            {progress && (
              <>
                <Text style={s.doneCountText}>
                  By shot type: {Object.entries(progress.by_shot_type || {})
                    .map(([k, v]) => `${k} ${v.tagged}/${v.total}`).join(' · ')}
                </Text>
                <Text style={s.doneCountText}>
                  By tier: {Object.entries(progress.by_tier || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || 'none tagged yet'}
                </Text>
              </>
            )}
            <Text style={s.doneCountText}>{taggedCount} tagged this session</Text>
            <Text style={s.doneCountText}>Come back later — tagged clips won't show up again.</Text>
            {index > 0 && (
              <TouchableOpacity style={s.retryBtn} onPress={goPrev}>
                <Text style={s.retryBtnText}>◀ Back through the list</Text>
              </TouchableOpacity>
            )}
          </View>
        </SafeAreaView>
      </RequireAdmin>
    );
  }

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <View style={s.stage}>
          <TappableVideo uri={`${API_BASE}${current.clip_url}`} width={videoWidth} height={videoHeight} />

          <View style={s.progressRow}>
            <Text style={s.progressText}>{index + 1} / {candidates.length} in this queue</Text>
            <Text style={s.progressSub}>
              {current.shot_type} · {current.id}
              {current.camera_angle != null ? ` · ${Math.round(current.camera_angle)}° angle` : ''}
              {current.view_direction ? ` · ${current.view_direction} view` : ''}
            </Text>
          </View>

          <TouchableOpacity style={s.prevBtn} onPress={goPrev} disabled={index === 0}>
            <Text style={[s.prevBtnText, index === 0 && s.prevBtnTextDisabled]}>◀ Back</Text>
          </TouchableOpacity>

          <View style={s.verdictPanel}>
            <Text style={s.doneCountText}>How would you rate this swing's technique?</Text>
            {submitError && <Text style={s.errorTextSmall}>{submitError}</Text>}
            <View style={s.tierBtnCol}>
              {TIERS.map((t) => (
                <TouchableOpacity
                  key={t.key}
                  style={[s.tierBtn, s[`tierBtn_${t.style}`], submitting && s.tierBtnDisabled]}
                  disabled={submitting}
                  onPress={() => tag(t.key)}
                >
                  <Text style={s.tierBtnText}>
                    {t.label}{Platform.OS === 'web' ? `  (${t.hotkey.toUpperCase()})` : ''}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={s.doneCountText}>{taggedCount} tagged this session</Text>
          </View>
        </View>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 24 },
  stage: { flex: 1, position: 'relative' },
  videoWrap: { backgroundColor: '#000' },
  playHint: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  playHintText: { color: 'rgba(255,255,255,0.75)', fontSize: 48 },

  progressRow: {
    position: 'absolute', top: 0, left: 0, right: 0, alignItems: 'center',
    paddingTop: 14, paddingBottom: 10, backgroundColor: 'rgba(0,0,0,0.5)',
  },
  progressText: { color: '#fff', fontSize: 16, fontFamily: fonts.semibold },
  progressSub: { color: 'rgba(255,255,255,0.75)', fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },

  prevBtn: { position: 'absolute', left: 14, top: 12, paddingVertical: 6, paddingHorizontal: 4 },
  prevBtnText: { color: colors.primary, fontSize: 14, fontFamily: fonts.semibold },
  prevBtnTextDisabled: { color: 'rgba(255,255,255,0.3)' },

  verdictPanel: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    backgroundColor: 'rgba(20,20,20,0.9)', borderTopWidth: 1, borderColor: colors.border,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: 12, paddingBottom: 16, gap: 6,
  },
  tierBtnCol: { gap: 8, marginTop: 4 },
  tierBtn: { borderRadius: radius.lg, paddingVertical: 12, alignItems: 'center' },
  tierBtn_gold: { backgroundColor: '#c99a2e' },
  tierBtn_ok: { backgroundColor: colors.primary },
  tierBtn_exclude: { backgroundColor: colors.coral },
  tierBtnDisabled: { opacity: 0.5 },
  tierBtnText: { color: '#fff', fontSize: 15, fontFamily: fonts.semibold },
  doneCountText: { color: 'rgba(255,255,255,0.7)', fontSize: 11.5, textAlign: 'center', marginTop: 2, fontFamily: fonts.regular },
  doneHeadline: { color: '#fff', fontSize: 18, fontFamily: fonts.semibold, textAlign: 'center', marginBottom: 8 },
  errorText: { color: '#fff', fontSize: 15, textAlign: 'center', fontFamily: fonts.regular, marginBottom: 12 },
  errorTextSmall: { color: colors.coral, fontSize: 12.5, textAlign: 'center', fontFamily: fonts.regular },
  retryBtn: { marginTop: 8, paddingVertical: 10, paddingHorizontal: 20, borderRadius: radius.lg, backgroundColor: colors.primary },
  retryBtnText: { color: '#fff', fontSize: 14, fontFamily: fonts.semibold },
});
