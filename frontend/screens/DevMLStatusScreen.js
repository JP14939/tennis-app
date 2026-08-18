import { useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { colors, fonts, radius, spacing } from '../theme';
import RequireAdmin from '../components/RequireAdmin';

function pct(v) {
  return v == null ? '—' : `${(v * 100).toFixed(1)}%`;
}

function StatusCard({ title, children }) {
  return (
    <View style={s.card}>
      <Text style={s.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

function StatRow({ label, value, trusted }) {
  return (
    <View style={s.statRow}>
      <Text style={s.statLabel}>{label}</Text>
      <View style={s.statValueRow}>
        <Text style={s.statValue}>{value}</Text>
        {trusted !== undefined && (
          <View style={[s.badge, trusted ? s.badgeTrusted : s.badgeUntrusted]}>
            <Text style={[s.badgeText, trusted ? s.badgeTextTrusted : s.badgeTextUntrusted]}>
              {trusted ? 'TRUSTED' : 'NOT TRUSTED'}
            </Text>
          </View>
        )}
      </View>
    </View>
  );
}

export default function DevMLStatusScreen({ navigation }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [data, setData] = useState(null);

  const load = useCallback(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(false);
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/api/dev/ml-status`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`Request failed (${res.status})`);
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch {
        if (!cancelled) setLoadError(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  useFocusEffect(useCallback(() => load(), [load]));

  let content;
  if (loading) {
    content = (
      <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
    );
  } else if (loadError || !data) {
    content = (
      <View style={s.centerFill}>
        <Text style={s.errorText}>Couldn't load ML status.</Text>
        <TouchableOpacity style={s.retryBtn} onPress={load}>
          <Text style={s.retryBtnText}>Try again</Text>
        </TouchableOpacity>
      </View>
    );
  } else {
    const { shot_contact: contact, shot_classifier: classifier, tip_selector: tips, contact_frame: contactFrame } = data;
    content = (
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>ML Reliability</Text>
        <Text style={s.sub}>Live numbers from each teacher-student loop's training log.</Text>

        <StatusCard title={`Shot Contact Verifier (${contact.total_examples} examples)`}>
          {Object.entries(contact.buckets).map(([bucket, b]) => (
            <StatRow
              key={bucket}
              label={`${bucket} (N=${b.n})`}
              value={`${pct(b.agreement_rate)}${b.wilson_lower_bound != null ? ` (lb ${pct(b.wilson_lower_bound)})` : ''}`}
              trusted={b.trusted}
            />
          ))}
          <Text style={s.thresholdNote}>
            Needs {contact.thresholds.min_examples_before_trust}+ examples and {pct(contact.thresholds.agreement_threshold)} agreement (Wilson lower bound) to trust.
          </Text>
        </StatusCard>

        <StatusCard title={`Shot Classifier (${classifier.total_examples} examples)`}>
          <StatRow label="Agreement rate" value={pct(classifier.agreement_rate)} trusted={classifier.trusted} />
          <Text style={s.thresholdNote}>
            Needs {classifier.thresholds.min_examples_before_trust}+ examples and {pct(classifier.thresholds.agreement_threshold)} agreement to trust.
          </Text>
        </StatusCard>

        <StatusCard title={`Tip Selector (${tips.total_examples} examples)`}>
          <StatRow label="Agreement rate" value={pct(tips.agreement_rate)} trusted={tips.trusted} />
          {Object.entries(tips.by_shot_type).map(([shotType, n]) => (
            <StatRow key={shotType} label={shotType} value={`${n} examples`} />
          ))}
          <Text style={s.thresholdNote}>
            Needs {tips.thresholds.min_examples_before_trust}+ examples and {pct(tips.thresholds.agreement_threshold)} agreement to trust.
          </Text>
        </StatusCard>

        <StatusCard title={`Contact Frame Detector (${contactFrame.total_examples} examples)`}>
          <StatRow
            label="Overall"
            value={contactFrame.overall.n === 0 ? 'No data yet' : `±${contactFrame.overall.mean_abs_error}f avg, ${pct(contactFrame.overall.within_tolerance_rate)} within ${contactFrame.thresholds.tolerance_frames}f`}
            trusted={contactFrame.overall.n > 0 ? contactFrame.overall.trusted : undefined}
          />
          {['manual_review', 'user_submitted'].map((src) => {
            const s2 = contactFrame.by_source[src];
            return (
              <StatRow
                key={src}
                label={src === 'manual_review' ? 'Manual (Dev Page)' : 'Real users'}
                value={s2.n === 0 ? `0 examples` : `N=${s2.n}, ±${s2.mean_abs_error}f avg (bias ${s2.mean_signed_error >= 0 ? '+' : ''}${s2.mean_signed_error}f)`}
              />
            );
          })}
          <Text style={s.thresholdNote}>
            Needs {contactFrame.thresholds.min_examples_before_trust}+ examples and {pct(contactFrame.thresholds.within_tolerance_threshold)} within ±{contactFrame.thresholds.tolerance_frames} frames to trust. Signed bias shows systematic early(-)/late(+) error, not just averaged-away noise.
          </Text>
        </StatusCard>
      </ScrollView>
    );
  }

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>{content}</SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center' },

  h1:  { color: colors.ink, fontSize: 24, fontFamily: fonts.bold, letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19, marginBottom: 20, fontFamily: fonts.regular },

  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: 14 },
  cardTitle: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold, marginBottom: 10 },

  statRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 6 },
  statLabel: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.semibold, flex: 1 },
  statValueRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  statValue: { color: colors.ink, fontSize: 12.5, fontFamily: fonts.regular },

  badge: { borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 3 },
  badgeTrusted: { backgroundColor: '#dcf5e3' },
  badgeUntrusted: { backgroundColor: '#f3d4d0' },
  badgeText: { fontSize: 9.5, fontFamily: fonts.bold, letterSpacing: 0.3 },
  badgeTextTrusted: { color: '#1a7a3c' },
  badgeTextUntrusted: { color: colors.coral },

  thresholdNote: { color: colors.muted, fontSize: 11, lineHeight: 15, marginTop: 8, fontFamily: fonts.regular },

  errorText: { color: colors.muted, fontSize: 13.5, textAlign: 'center', marginBottom: 14, paddingHorizontal: 24 },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },
});
