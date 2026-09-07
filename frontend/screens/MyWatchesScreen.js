import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import Alert from '../utils/alert';
import { useAuth } from '../context/AuthContext';
import { colors, fonts, radius, spacing } from '../theme';
import {
  getWatchedCourts, unwatchCourt, unwatchClubById, deleteAreaWatch,
} from '../api/courts';
import { playTapSound } from '../utils/sounds';

// No court/club id is passed into this screen -- it's reached from Find
// Games' header button, not from a specific court, so there's nothing to
// pre-select. Three independent sections (courts, clubs, areas) mirror the
// three watch types GET /courts/watched already returns.
function Section({ title, emptyText, items, renderItem }) {
  return (
    <View style={s.section}>
      <Text style={s.sectionTitle}>{title}</Text>
      {items.length === 0 ? (
        <Text style={s.emptyText}>{emptyText}</Text>
      ) : (
        items.map(renderItem)
      )}
    </View>
  );
}

function WatchRow({ title, subtitle, onRemove, removing }) {
  return (
    <View style={s.row}>
      <View style={s.rowText}>
        <Text style={s.rowTitle}>{title}</Text>
        {subtitle ? <Text style={s.rowSubtitle}>{subtitle}</Text> : null}
      </View>
      <TouchableOpacity style={s.removeBtn} onPress={onRemove} disabled={removing}>
        <Text style={s.removeBtnText}>{removing ? '...' : 'Remove'}</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function MyWatchesScreen() {
  const { token } = useAuth();
  const [courts, setCourts] = useState([]);
  const [clubs, setClubs] = useState([]);
  const [areas, setAreas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  // Tracks which single row is mid-remove, keyed the same way each list's
  // renderItem key is -- disables just that row's button rather than every
  // button on the screen while one delete is in flight.
  const [removingKey, setRemovingKey] = useState(null);
  // Guards against setState after this screen has been navigated away from
  // -- same pattern HighlightArchiveScreen/ResultsScreen already use for the
  // same reason (a slow response landing after unmount).
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const load = useCallback(() => {
    setLoading(true);
    getWatchedCourts(token)
      .then((data) => {
        if (!mountedRef.current) return;
        setCourts(data.courts ?? []);
        setClubs(data.clubs ?? []);
        setAreas(data.areas ?? []);
        setLoadError(false);
      })
      .catch(() => { if (mountedRef.current) setLoadError(true); })
      .finally(() => { if (mountedRef.current) setLoading(false); });
  }, [token]);

  // Reload every time this screen is focused -- a watch can be added from
  // Find Games (a different screen) or removed here, so a cached list from
  // the last visit could easily be stale.
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const handleRemoveCourt = async (courtId) => {
    setRemovingKey(`court-${courtId}`);
    try {
      await unwatchCourt(token, courtId);
      setCourts((prev) => prev.filter((c) => c.id !== courtId));
    } catch (err) {
      Alert.alert('Could not remove', err.message || 'Something went wrong');
    } finally {
      setRemovingKey(null);
    }
  };

  const handleRemoveClub = async (clubId) => {
    setRemovingKey(`club-${clubId}`);
    try {
      await unwatchClubById(token, clubId);
      setClubs((prev) => prev.filter((c) => c.id !== clubId));
    } catch (err) {
      Alert.alert('Could not remove', err.message || 'Something went wrong');
    } finally {
      setRemovingKey(null);
    }
  };

  const handleRemoveArea = async (areaId) => {
    setRemovingKey(`area-${areaId}`);
    try {
      await deleteAreaWatch(token, areaId);
      setAreas((prev) => prev.filter((a) => a.id !== areaId));
    } catch (err) {
      Alert.alert('Could not remove', err.message || 'Something went wrong');
    } finally {
      setRemovingKey(null);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
      </SafeAreaView>
    );
  }

  if (loadError) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.centerFill}>
          <Text style={s.errorText}>Couldn't load your watches — check your connection.</Text>
          <TouchableOpacity style={s.retryBtn} onPress={() => { playTapSound(); load(); }}>
            <Text style={s.retryBtnText}>Try again</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll}>
        <Section
          title="Courts"
          emptyText="You're not watching any specific courts yet — open one on the map and tap Notify me."
          items={courts}
          renderItem={(court) => (
            <WatchRow
              key={court.id}
              title={court.name}
              subtitle={court.postcode}
              removing={removingKey === `court-${court.id}`}
              onRemove={() => { playTapSound(); handleRemoveCourt(court.id); }}
            />
          )}
        />
        <Section
          title="Clubs"
          emptyText="You're not watching any clubs yet — open a court that's part of one to see the club option."
          items={clubs}
          renderItem={(club) => (
            <WatchRow
              key={club.id}
              title={club.name}
              subtitle={club.postcode}
              removing={removingKey === `club-${club.id}`}
              onRemove={() => { playTapSound(); handleRemoveClub(club.id); }}
            />
          )}
        />
        <Section
          title="Areas"
          emptyText={'You\'re not watching any areas yet — use "Watch an area" on the Find Games map.'}
          items={areas}
          renderItem={(area) => (
            <WatchRow
              key={area.id}
              title={area.name || 'Unnamed area'}
              subtitle={area.postcode ? `${area.radius_km} km radius · ${area.postcode}` : `${area.radius_km} km radius`}
              removing={removingKey === `area-${area.id}`}
              onRemove={() => { playTapSound(); handleRemoveArea(area.id); }}
            />
          )}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  errorText: { color: colors.muted, fontSize: 13.5, fontFamily: fonts.regular, textAlign: 'center', marginBottom: 14 },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  section: { marginBottom: spacing.lg },
  sectionTitle: { color: colors.ink, fontSize: 15.5, fontFamily: fonts.bold, marginBottom: 10 },
  emptyText: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular, lineHeight: 18 },

  row: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 13, marginBottom: 8,
  },
  rowText: { flex: 1, marginRight: 10 },
  rowTitle: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold },
  rowSubtitle: { color: colors.muted, fontSize: 12, marginTop: 2, fontFamily: fonts.regular },
  removeBtn: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7 },
  removeBtnText: { color: colors.mutedDark, fontSize: 12, fontFamily: fonts.bold },
});
