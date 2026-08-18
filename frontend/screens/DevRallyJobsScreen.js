import { useCallback, useRef, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator } from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { API_BASE } from '../config/api';
import { playTapSound } from '../utils/sounds';
import RequireAdmin from '../components/RequireAdmin';
import { colors, fonts, radius, spacing } from '../theme';

// Generic dev-only job picker, reused by both review tools (boundary review
// and free manual swing review) via route.params -- reuses GET
// /highlights/jobs as-is (already scoped to the logged-in user, no separate
// admin-only backend route needed since it's your own data either way).
export default function DevRallyJobsScreen({ navigation, route }) {
  const {
    targetScreen = 'DevRallyBoundaryReview',
    title = 'Rally Boundary Review',
    subtitle = 'Pick a match to review its detected rally boundaries against.',
  } = route.params ?? {};

  const { token } = useAuth();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/highlights/jobs`, { headers: { Authorization: `Bearer ${token}` } });
      const data = await res.json();
      if (mountedRef.current) setJobs(data.jobs ?? []);
    } catch {
      // Leave whatever was previously loaded rather than blanking the screen.
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, [token]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const doneJobs = jobs.filter((j) => j.status === 'done');

  return (
    <RequireAdmin navigation={navigation}>
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <Text style={s.h1}>{title}</Text>
          <Text style={s.sub}>{subtitle}</Text>

          {loading && jobs.length === 0 ? (
            <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 40 }} />
          ) : doneJobs.length === 0 ? (
            <View style={s.empty}>
              <Text style={s.emptyTitle}>No processed matches yet</Text>
              <Text style={s.emptySub}>Upload a match from the regular app first.</Text>
            </View>
          ) : (
            doneJobs.map((job) => (
              <TouchableOpacity
                key={job.id}
                style={s.card}
                activeOpacity={0.8}
                onPress={() => { playTapSound(); navigation.navigate(targetScreen, { jobId: job.id }); }}
              >
                <Text style={s.cardTitle}>Job #{job.id}</Text>
                {targetScreen === 'DevRallyBoundaryReview' && (
                  <Text style={s.cardSub}>
                    {job.pending_boundary_review > 0
                      ? `${job.pending_boundary_review} rall${job.pending_boundary_review === 1 ? 'y' : 'ies'} left to review`
                      : 'All rallies reviewed'}
                  </Text>
                )}
              </TouchableOpacity>
            ))
          )}
        </ScrollView>
      </SafeAreaView>
    </RequireAdmin>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 48 },

  h1:  { color: colors.ink, fontSize: 24, fontFamily: fonts.bold, letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 13, lineHeight: 19, marginBottom: 20, fontFamily: fonts.regular },

  card: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: 16, marginBottom: 12,
  },
  cardTitle: { color: colors.ink, fontSize: 15, fontFamily: fonts.bold, marginBottom: 4 },
  cardSub: { color: colors.muted, fontSize: 12.5, fontFamily: fonts.regular },

  empty: { alignItems: 'center', marginTop: 60 },
  emptyTitle: { color: colors.ink, fontSize: 16, fontFamily: fonts.bold, marginBottom: 6 },
  emptySub: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },
});
