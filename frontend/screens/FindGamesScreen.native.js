import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet, SafeAreaView,
  Modal, ScrollView, ActivityIndicator, Alert, Animated, PanResponder,
} from 'react-native';
import MapView, { Marker, Circle } from 'react-native-maps';
import { useFocusEffect } from '@react-navigation/native';
import * as Location from 'expo-location';
import { useAuth } from '../context/AuthContext';
import { colors, fonts, radius, spacing } from '../theme';
import {
  getCourts, addCourt, confirmCourt, setCourtCost, watchCourt, unwatchCourt,
  watchClub, unwatchClub, getAvailability, postAvailability, createAreaWatch,
  suggestClubName, confirmClubName,
} from '../api/courts';
import { playTapSound, playAchievementSound } from '../utils/sounds';

// Fallback region if location permission is denied or unavailable -- keeps
// the map usable (if not locally relevant) rather than blank/crashed.
const DEFAULT_REGION = { latitude: 51.5074, longitude: -0.1278, latitudeDelta: 0.2, longitudeDelta: 0.2 };

// Mirrors backend/src/routes/courts.js's CONFIRMATION_THRESHOLD -- display
// only, the real gate is server-side.
const CONFIRMATION_THRESHOLD = 2;

// Mirrors backend/src/domain/invariants.js's MIN/MAX_AREA_WATCH_RADIUS_KM --
// display only, the real bound is server-side (isRadiusKm).
const MIN_AREA_RADIUS_KM = 0.1;
const MAX_AREA_RADIUS_KM = 20;
const DEFAULT_AREA_RADIUS_KM = 3;

const DAY_OPTIONS = [
  { label: 'Today', offset: 0 },
  { label: 'Tomorrow', offset: 1 },
  { label: 'In 2 days', offset: 2 },
];

function buildStartTime(dayOffset, hhmm) {
  const [h, m] = hhmm.split(':').map((n) => parseInt(n, 10));
  if (Number.isNaN(h) || Number.isNaN(m)) return null;
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
}

function formatWhen(isoString) {
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;
  return d.toLocaleString(undefined, { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

// A continuous drag-a-handle-along-a-track slider, same PanResponder
// track+handle mechanics as CourtSheet's day-offset slider below, but for a
// continuous range (0.1-20km) instead of 3 discrete steps. Standalone
// (rather than another copy inside a bigger component) since the area-watch
// sheet is its only user and doesn't share CourtSheet's other state.
function RadiusSlider({ valueKm, onChange }) {
  const trackWidth = useRef(0);
  const handleX = useRef(new Animated.Value(0)).current;

  const kmToFrac = (km) => (km - MIN_AREA_RADIUS_KM) / (MAX_AREA_RADIUS_KM - MIN_AREA_RADIUS_KM);
  const setHandleFromKm = (km) => handleX.setValue(kmToFrac(km) * trackWidth.current);

  // Keep the handle in sync if valueKm changes from outside a drag (e.g. the
  // sheet re-opening with a previous value) -- mirrors the intent of
  // CourtSheet's setDayHandleFromOffset, generalized to a continuous value.
  useEffect(() => { if (trackWidth.current) setHandleFromKm(valueKm); }, [valueKm]);

  const handleTouch = (localX) => {
    if (!trackWidth.current) return;
    const clamped = Math.max(0, Math.min(trackWidth.current, localX));
    const frac = clamped / trackWidth.current;
    const km = Math.round((MIN_AREA_RADIUS_KM + frac * (MAX_AREA_RADIUS_KM - MIN_AREA_RADIUS_KM)) * 10) / 10;
    onChange(km);
    handleX.setValue(clamped);
  };
  const touchStartX = useRef(0);
  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        touchStartX.current = evt.nativeEvent.locationX;
        handleTouch(touchStartX.current);
      },
      onPanResponderMove: (evt, gesture) => handleTouch(touchStartX.current + gesture.dx),
    })
  ).current;

  return (
    <View
      style={s.radiusTrack}
      onLayout={(e) => { trackWidth.current = e.nativeEvent.layout.width; setHandleFromKm(valueKm); }}
      {...responder.panHandlers}
    >
      <View style={s.radiusTrackFill} />
      <Animated.View style={[s.radiusHandle, { transform: [{ translateX: handleX }] }]} />
    </View>
  );
}

function CourtSheet({ court, watched, onToggleWatch, onSaveCost, onConfirm, navigation }) {
  const { token, user } = useAuth();
  const [costDraft, setCostDraft] = useState(court.cost_info ?? '');
  const [savingCost, setSavingCost] = useState(false);
  const [posts, setPosts] = useState([]);
  const [loadingPosts, setLoadingPosts] = useState(true);
  const [dayOffset, setDayOffset] = useState(0);
  // Track+handle slider, same pattern as SyncCompareScreen's zoom slider --
  // snapped to the 3 discrete steps DAY_OPTIONS already defines (0-2 days
  // ahead is the real cap, this is just a nicer control than 3 buttons).
  const dayTrackWidth = useRef(0);
  const dayHandleX = useRef(new Animated.Value(0)).current;
  const setDayHandleFromOffset = (offset) => {
    const frac = offset / (DAY_OPTIONS.length - 1);
    dayHandleX.setValue(frac * dayTrackWidth.current);
  };
  const handleDayTouch = (localX) => {
    if (!dayTrackWidth.current) return;
    const clamped = Math.max(0, Math.min(dayTrackWidth.current, localX));
    const frac = clamped / dayTrackWidth.current;
    const offset = Math.round(frac * (DAY_OPTIONS.length - 1));
    setDayOffset(offset);
    setDayHandleFromOffset(offset);
  };
  const dayTouchStartX = useRef(0);
  const dayResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        dayTouchStartX.current = evt.nativeEvent.locationX;
        handleDayTouch(dayTouchStartX.current);
      },
      onPanResponderMove: (evt, gesture) => handleDayTouch(dayTouchStartX.current + gesture.dx),
    })
  ).current;
  const [time, setTime] = useState('18:00');
  const [note, setNote] = useState('');
  const [posting, setPosting] = useState(false);
  const [confirming, setConfirming] = useState(false);
  // Self-contained (not lifted to the parent like per-court `watched`) --
  // club membership never affects the map markers, and GET /courts already
  // annotates each court with an accurate club_already_watched, so there's
  // no need for a separately-tracked Set.
  const [clubWatched, setClubWatched] = useState(!!court.club_already_watched);
  const [togglingClubWatch, setTogglingClubWatch] = useState(false);
  // Local, mutable copy of the club's naming state -- same reasoning as
  // clubWatched above (self-contained, since club identity doesn't affect
  // the map markers), updated in place after a successful suggest/confirm
  // rather than re-fetching the whole court list.
  const [clubName, setClubName] = useState(court.club_name);
  const [clubNameVerified, setClubNameVerified] = useState(!!court.club_name_verified);
  const [clubNameSubmittedBy, setClubNameSubmittedBy] = useState(court.club_name_submitted_by);
  const [nameDraft, setNameDraft] = useState('');
  const [suggestingName, setSuggestingName] = useState(false);
  const [confirmingName, setConfirmingName] = useState(false);

  const handleToggleClubWatch = async () => {
    setTogglingClubWatch(true);
    try {
      if (clubWatched) {
        await unwatchClub(token, court.id);
        setClubWatched(false);
      } else {
        await watchClub(token, court.id);
        setClubWatched(true);
      }
    } catch (err) {
      Alert.alert('Could not update', err.message || 'Something went wrong');
    } finally {
      setTogglingClubWatch(false);
    }
  };

  const handleSuggestName = async () => {
    if (!nameDraft.trim()) return;
    setSuggestingName(true);
    try {
      const data = await suggestClubName(token, court.club_id, nameDraft.trim());
      setClubName(data.club.name);
      setClubNameVerified(!!data.club.name_verified);
      setClubNameSubmittedBy(data.club.name_submitted_by);
      setNameDraft('');
    } catch (err) {
      Alert.alert('Could not suggest a name', err.message || 'Something went wrong');
    } finally {
      setSuggestingName(false);
    }
  };

  const handleConfirmName = async () => {
    setConfirmingName(true);
    try {
      const data = await confirmClubName(token, court.club_id);
      setClubNameVerified(!!data.club.name_verified);
    } catch (err) {
      // The two real rejections here (confirming your own suggestion,
      // confirming before anyone's suggested a real name yet) are both
      // already worded as complete sentences server-side -- surfaced as-is
      // rather than wrapped in extra frontend copy.
      Alert.alert('Could not confirm', err.message || 'Something went wrong');
    } finally {
      setConfirmingName(false);
    }
  };

  const loadPosts = useCallback(() => {
    setLoadingPosts(true);
    getAvailability(token, court.id)
      .then((data) => setPosts(data.posts))
      .catch(() => {})
      .finally(() => setLoadingPosts(false));
  }, [token, court.id]);

  useFocusEffect(useCallback(() => { loadPosts(); }, [loadPosts]));

  const saveCost = async () => {
    setSavingCost(true);
    try {
      await setCourtCost(token, court.id, costDraft.trim() || null);
      onSaveCost(court.id, costDraft.trim() || null);
    } catch (err) {
      Alert.alert('Could not save cost', err.message || 'Something went wrong');
    } finally {
      setSavingCost(false);
    }
  };

  const submitAvailability = async () => {
    const startTime = buildStartTime(dayOffset, time);
    if (!startTime) {
      Alert.alert('Invalid time', 'Enter a time as HH:MM, e.g. 18:00');
      return;
    }
    setPosting(true);
    try {
      await postAvailability(token, court.id, { startTime, note: note.trim() || undefined });
      setNote('');
      loadPosts();
    } catch (err) {
      Alert.alert('Could not post', err.message || 'Something went wrong');
    } finally {
      setPosting(false);
    }
  };

  const handleConfirm = async () => {
    setConfirming(true);
    try {
      await onConfirm(court.id);
    } catch (err) {
      Alert.alert('Could not confirm', err.message || 'Something went wrong');
    } finally {
      setConfirming(false);
    }
  };

  return (
    <ScrollView contentContainerStyle={sh.scroll} showsVerticalScrollIndicator={false}>
      <View style={sh.headerRow}>
        <Text style={sh.name}>{court.name}</Text>
        <TouchableOpacity
          style={[sh.watchBtn, watched && sh.watchBtnActive]}
          onPress={() => onToggleWatch(court.id, watched)}
        >
          <Text style={[sh.watchBtnText, watched && sh.watchBtnTextActive]}>
            {watched ? 'Watching' : 'Notify me'}
          </Text>
        </TouchableOpacity>
      </View>
      <View style={sh.metaRow}>
        {court.distance_km != null && <Text style={sh.distance}>{court.distance_km} km away</Text>}
        {court.postcode && <Text style={sh.distance}>{court.postcode}</Text>}
      </View>

      {court.club_id && (
        <View style={sh.clubRow}>
          <View style={{ flex: 1 }}>
            <Text style={sh.clubText}>Part of {clubName}</Text>
            <Text style={sh.clubSubtext}>{court.club_court_count} courts — get notified for any of them</Text>
            {court.club_postcode && <Text style={sh.clubSubtext}>{court.club_postcode}</Text>}
          </View>
          <TouchableOpacity
            style={[sh.clubWatchBtn, clubWatched && sh.watchBtnActive]}
            onPress={handleToggleClubWatch}
            disabled={togglingClubWatch}
          >
            <Text style={[sh.watchBtnText, clubWatched && sh.watchBtnTextActive]}>
              {clubWatched ? 'Watching' : 'Notify me'}
            </Text>
          </TouchableOpacity>
        </View>
      )}

      {court.club_id && !clubNameVerified && (
        <View style={sh.unverifiedBanner}>
          <Text style={sh.unverifiedText}>Club name not yet confirmed by other players</Text>
          {clubNameSubmittedBy === user?.id ? (
            <Text style={sh.unverifiedSub}>You suggested this name — waiting on other players to confirm it.</Text>
          ) : (
            <TouchableOpacity style={sh.confirmBtn} onPress={handleConfirmName} disabled={confirmingName}>
              <Text style={sh.confirmBtnText}>{confirmingName ? 'Confirming...' : `Confirm "${clubName}" is right`}</Text>
            </TouchableOpacity>
          )}
          <View style={sh.nameSuggestRow}>
            <TextInput
              style={sh.nameSuggestInput}
              value={nameDraft}
              onChangeText={setNameDraft}
              placeholder="Know the real name? Suggest it"
              placeholderTextColor={colors.muted}
            />
            <TouchableOpacity style={sh.nameSuggestBtn} onPress={handleSuggestName} disabled={suggestingName || !nameDraft.trim()}>
              <Text style={sh.nameSuggestBtnText}>{suggestingName ? '...' : 'Suggest'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {!court.verified && (
        <View style={sh.unverifiedBanner}>
          <Text style={sh.unverifiedText}>
            Not yet verified — {court.confirmation_count ?? 0}/{CONFIRMATION_THRESHOLD} confirmations
          </Text>
          {court.submitted_by === user?.id ? (
            <Text style={sh.unverifiedSub}>You submitted this pin — waiting on other players to confirm it.</Text>
          ) : court.already_confirmed ? (
            <Text style={sh.unverifiedSub}>You've confirmed this one — thanks!</Text>
          ) : (
            <TouchableOpacity style={sh.confirmBtn} onPress={handleConfirm} disabled={confirming}>
              <Text style={sh.confirmBtnText}>{confirming ? 'Confirming...' : 'Confirm this court exists'}</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      <View style={sh.costRow}>
        <TextInput
          style={sh.costInput}
          value={costDraft}
          onChangeText={setCostDraft}
          placeholder="e.g. $15/hr, or Free"
          placeholderTextColor={colors.muted}
        />
        <TouchableOpacity style={sh.costSaveBtn} onPress={saveCost} disabled={savingCost}>
          <Text style={sh.costSaveBtnText}>{savingCost ? '...' : 'Save'}</Text>
        </TouchableOpacity>
      </View>

      <Text style={sh.sectionTitle}>Who's free</Text>
      {loadingPosts ? (
        <ActivityIndicator color={colors.primary} style={{ marginVertical: 12 }} />
      ) : posts.length === 0 ? (
        <Text style={sh.emptyText}>Nobody's posted availability here yet.</Text>
      ) : (
        posts.map((post) => (
          <View key={post.id} style={sh.postCard}>
            <View style={{ flex: 1 }}>
              <Text style={sh.postName}>{post.user_username ? `@${post.user_username}` : post.user_name}</Text>
              <Text style={sh.postWhen}>{formatWhen(post.start_time)}</Text>
              {post.note && <Text style={sh.postNote}>{post.note}</Text>}
            </View>
            {post.user_id !== user?.id && (
              <TouchableOpacity
                style={sh.messageBtn}
                onPress={() => navigation.navigate('MessageThread', { otherUserId: post.user_id, otherUserName: post.user_name })}
              >
                <Text style={sh.messageBtnText}>Message</Text>
              </TouchableOpacity>
            )}
          </View>
        ))
      )}

      <Text style={sh.sectionTitle}>I'm free to play here</Text>
      <Text style={sh.dayValue}>{DAY_OPTIONS[dayOffset].label}</Text>
      <View
        style={sh.dayTrack}
        onLayout={(e) => {
          dayTrackWidth.current = e.nativeEvent.layout.width;
          setDayHandleFromOffset(dayOffset);
        }}
        {...dayResponder.panHandlers}
      >
        <View style={sh.dayTrackLine} />
        {DAY_OPTIONS.map((opt, i) => (
          <TouchableOpacity
            key={opt.label}
            style={[sh.dayMarkTouch, { left: `${(i / (DAY_OPTIONS.length - 1)) * 100}%` }]}
            onPress={() => { setDayOffset(i); setDayHandleFromOffset(i); }}
          >
            <View style={sh.dayMark} />
            <Text style={sh.dayMarkLabel}>{opt.label}</Text>
          </TouchableOpacity>
        ))}
        <Animated.View style={[sh.dayHandle, { transform: [{ translateX: dayHandleX }] }]} />
      </View>
      <TextInput
        style={sh.timeInput}
        value={time}
        onChangeText={setTime}
        placeholder="18:00"
        placeholderTextColor={colors.muted}
      />
      <TextInput
        style={sh.noteInput}
        value={note}
        onChangeText={setNote}
        placeholder="Optional note, e.g. 'looking for a hitting partner, intermediate'"
        placeholderTextColor={colors.muted}
        multiline
      />
      <TouchableOpacity style={sh.postBtn} onPress={submitAvailability} disabled={posting}>
        <Text style={sh.postBtnText}>{posting ? 'Posting...' : 'Post availability'}</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

export default function FindGamesScreen({ navigation }) {
  const { token } = useAuth();
  const [region, setRegion] = useState(DEFAULT_REGION);
  const [courts, setCourts] = useState([]);
  const [watchedIds, setWatchedIds] = useState(new Set());
  const [loading, setLoading] = useState(true);
  // Tracks the last lat/lng loadCourts was called with, purely so the retry
  // button can re-issue the same request without re-running the location
  // permission flow.
  const lastLoadArgs = useRef(null);
  const [loadError, setLoadError] = useState(false);
  const [locationDenied, setLocationDenied] = useState(false);
  const [selectedCourt, setSelectedCourt] = useState(null);
  const [draftPin, setDraftPin] = useState(null); // { latitude, longitude } while placing a new court
  const [draftName, setDraftName] = useState('');
  const [submittingPin, setSubmittingPin] = useState(false);
  // Area-watch placement: armed by the header button, then the next plain
  // tap on the map (not a marker, not a long-press -- those are already
  // "open a court" and "add a court" respectively) drops the area pin.
  const [placingArea, setPlacingArea] = useState(false);
  const [areaDraftPin, setAreaDraftPin] = useState(null); // { latitude, longitude } while placing a watched area
  const [areaName, setAreaName] = useState('');
  const [areaRadiusKm, setAreaRadiusKm] = useState(DEFAULT_AREA_RADIUS_KM);
  const [savingArea, setSavingArea] = useState(false);
  // Guards loadCourts' promise callbacks -- the surrounding useFocusEffect
  // already tracks its own `cancelled` flag, but loadCourts can also be
  // called directly from retryLoadCourts(), and its .then/.catch/.finally
  // chain never checked either flag, so a stale/slow request could still
  // overwrite state after a newer one already resolved (e.g. rapidly
  // re-focusing the screen, or mashing retry).
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const loadCourts = useCallback((lat, lng) => {
    lastLoadArgs.current = { lat, lng };
    getCourts(token, { lat, lng, radiusKm: 20 })
      .then((data) => {
        if (!mountedRef.current) return;
        setCourts(data.courts);
        // GET /courts now annotates each court with `watched` (previously
        // absent entirely) -- hydrate the client-tracked Set from it so a
        // court already being watched shows correctly on the very first
        // load, not just after re-opening its sheet mid-session.
        setWatchedIds(new Set(data.courts.filter((c) => c.watched).map((c) => c.id)));
        setLoadError(false);
      })
      // Previously swallowed silently, which looked identical to "no courts
      // nearby" -- a slow/timed-out request (the actual failure mode this
      // was masking) now surfaces a real retry affordance instead.
      .catch(() => { if (mountedRef.current) setLoadError(true); })
      .finally(() => { if (mountedRef.current) setLoading(false); });
  }, [token]);

  const retryLoadCourts = () => {
    if (!lastLoadArgs.current) return;
    setLoading(true);
    loadCourts(lastLoadArgs.current.lat, lastLoadArgs.current.lng);
  };

  useFocusEffect(useCallback(() => {
    let cancelled = false;
    (async () => {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (cancelled) return;
      if (status !== 'granted') {
        setLocationDenied(true);
        loadCourts(DEFAULT_REGION.latitude, DEFAULT_REGION.longitude);
        return;
      }
      try {
        const pos = await Location.getCurrentPositionAsync({});
        if (cancelled) return;
        const next = { latitude: pos.coords.latitude, longitude: pos.coords.longitude, latitudeDelta: 0.15, longitudeDelta: 0.15 };
        setRegion(next);
        loadCourts(next.latitude, next.longitude);
      } catch {
        loadCourts(DEFAULT_REGION.latitude, DEFAULT_REGION.longitude);
      }
    })();
    return () => { cancelled = true; };
  }, [loadCourts]));

  const handleToggleWatch = async (courtId, currentlyWatched) => {
    const next = new Set(watchedIds);
    try {
      if (currentlyWatched) {
        await unwatchCourt(token, courtId);
        next.delete(courtId);
      } else {
        await watchCourt(token, courtId);
        next.add(courtId);
      }
      setWatchedIds(next);
    } catch (err) {
      Alert.alert('Could not update', err.message || 'Something went wrong');
    }
  };

  const handleSaveCost = (courtId, costInfo) => {
    setCourts((prev) => prev.map((c) => (c.id === courtId ? { ...c, cost_info: costInfo } : c)));
    setSelectedCourt((prev) => (prev && prev.id === courtId ? { ...prev, cost_info: costInfo } : prev));
  };

  const handleConfirmCourt = async (courtId) => {
    const wasUnverified = !courts.find((c) => c.id === courtId)?.verified;
    const data = await confirmCourt(token, courtId);
    setCourts((prev) => prev.map((c) => (c.id === courtId ? data.court : c)));
    setSelectedCourt((prev) => (prev && prev.id === courtId ? data.court : prev));
    // Your confirmation was the one that tipped it over the threshold --
    // a real, cheaply-detectable "your action made this happen" moment.
    if (wasUnverified && data.court.verified) {
      playAchievementSound();
    }
  };

  const handleSubmitPin = async () => {
    if (!draftName.trim() || !draftPin) {
      Alert.alert('Missing info', 'Give the court a name first.');
      return;
    }
    setSubmittingPin(true);
    try {
      const data = await addCourt(token, {
        name: draftName.trim(),
        latitude: draftPin.latitude,
        longitude: draftPin.longitude,
      });
      setCourts((prev) => [...prev, data.court]);
      setDraftPin(null);
      setDraftName('');
      Alert.alert('Pin dropped', "Your court is on the map as unverified — it'll show as confirmed once a couple of other players vouch for it.");
    } catch (err) {
      Alert.alert('Could not add court', err.message || 'Something went wrong');
    } finally {
      setSubmittingPin(false);
    }
  };

  const handleSaveAreaWatch = async () => {
    if (!areaDraftPin) return;
    setSavingArea(true);
    try {
      await createAreaWatch(token, {
        name: areaName.trim() || undefined,
        latitude: areaDraftPin.latitude,
        longitude: areaDraftPin.longitude,
        radiusKm: areaRadiusKm,
      });
      setAreaDraftPin(null);
      setAreaName('');
      setAreaRadiusKm(DEFAULT_AREA_RADIUS_KM);
      Alert.alert('Area watched', "You'll be notified when someone posts availability at a court in this area.");
    } catch (err) {
      Alert.alert('Could not save area', err.message || 'Something went wrong');
    } finally {
      setSavingArea(false);
    }
  };

  return (
    <SafeAreaView style={s.safe}>
      <View style={s.header}>
        <View style={s.headerTopRow}>
          <Text style={s.title}>Find Games</Text>
          <View style={s.headerActions}>
            <TouchableOpacity
              style={[s.headerBtn, placingArea && s.headerBtnActive]}
              onPress={() => { playTapSound(); setPlacingArea((v) => !v); }}
            >
              <Text style={[s.headerBtnText, placingArea && s.headerBtnTextActive]}>
                {placingArea ? 'Tap the map...' : 'Watch an area'}
              </Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.headerBtn} onPress={() => { playTapSound(); navigation.navigate('MyWatches'); }}>
              <Text style={s.headerBtnText}>My Watches</Text>
            </TouchableOpacity>
          </View>
        </View>
        {locationDenied && <Text style={s.locationWarning}>Location off — showing a default area</Text>}
        {!locationDenied && !placingArea && <Text style={s.hint}>Missing a court? Long-press the map to drop a pin.</Text>}
        {placingArea && <Text style={s.hint}>Tap anywhere on the map to center the area you want to watch.</Text>}
      </View>

      {loading ? (
        <View style={s.centerFill}><ActivityIndicator size="large" color={colors.primary} /></View>
      ) : loadError ? (
        <View style={s.centerFill}>
          <Text style={s.errorText}>Couldn't load courts — check your connection.</Text>
          <TouchableOpacity style={s.retryBtn} onPress={retryLoadCourts}>
            <Text style={s.retryBtnText}>Try again</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <MapView
          style={s.map}
          initialRegion={region}
          region={region}
          onLongPress={(e) => {
            if (placingArea) return; // long-press while placing an area still means "add a court" elsewhere
            setDraftName('');
            setDraftPin(e.nativeEvent.coordinate);
          }}
          onPress={(e) => {
            if (!placingArea) return; // a plain tap on empty map otherwise does nothing (marker taps have their own onPress)
            setAreaDraftPin(e.nativeEvent.coordinate);
            setPlacingArea(false);
          }}
        >
          {courts.map((court) => (
            <Marker
              key={court.id}
              coordinate={{ latitude: court.latitude, longitude: court.longitude }}
              title={court.name}
              description={court.verified ? (court.cost_info ?? 'Cost unknown') : 'Unverified — needs community confirmation'}
              pinColor={court.verified ? undefined : colors.gold}
              onPress={() => setSelectedCourt(court)}
            />
          ))}
          {draftPin && (
            <Marker
              coordinate={draftPin}
              draggable
              onDragEnd={(e) => setDraftPin(e.nativeEvent.coordinate)}
              pinColor={colors.lime}
            />
          )}
          {areaDraftPin && (
            <>
              <Circle
                center={areaDraftPin}
                radius={areaRadiusKm * 1000}
                fillColor="rgba(90,160,90,0.15)"
                strokeColor={colors.lime}
                strokeWidth={2}
              />
              <Marker
                coordinate={areaDraftPin}
                draggable
                onDragEnd={(e) => setAreaDraftPin(e.nativeEvent.coordinate)}
                pinColor={colors.lime}
              />
            </>
          )}
        </MapView>
      )}

      <Modal
        visible={!!selectedCourt}
        animationType="slide"
        transparent
        onRequestClose={() => setSelectedCourt(null)}
      >
        <View style={s.sheetBackdrop}>
          <View style={s.sheetCard}>
            <View style={s.sheetHandle} />
            <TouchableOpacity style={s.sheetClose} onPress={() => setSelectedCourt(null)} hitSlop={10}>
              <Text style={s.sheetCloseText}>✕</Text>
            </TouchableOpacity>
            {selectedCourt && (
              <CourtSheet
                court={selectedCourt}
                watched={watchedIds.has(selectedCourt.id)}
                onToggleWatch={handleToggleWatch}
                onSaveCost={handleSaveCost}
                onConfirm={handleConfirmCourt}
                navigation={navigation}
              />
            )}
          </View>
        </View>
      </Modal>

      <Modal
        visible={!!draftPin}
        animationType="slide"
        transparent
        onRequestClose={() => setDraftPin(null)}
      >
        <View style={s.sheetBackdrop}>
          <View style={s.sheetCard}>
            <View style={s.sheetHandle} />
            <TouchableOpacity style={s.sheetClose} onPress={() => setDraftPin(null)} hitSlop={10}>
              <Text style={s.sheetCloseText}>✕</Text>
            </TouchableOpacity>
            <Text style={s.draftTitle}>Drop a new court here</Text>
            {draftPin && (
              <Text style={s.draftCoords}>{draftPin.latitude.toFixed(5)}, {draftPin.longitude.toFixed(5)}</Text>
            )}
            <Text style={s.draftHint}>Drag the green pin on the map to nudge the exact spot before submitting.</Text>
            <TextInput
              style={s.draftInput}
              value={draftName}
              onChangeText={setDraftName}
              placeholder="Court name, e.g. Riverside Park Courts"
              placeholderTextColor={colors.muted}
              autoFocus
            />
            <TouchableOpacity style={s.draftSubmitBtn} onPress={() => { playTapSound(); handleSubmitPin(); }} disabled={submittingPin}>
              <Text style={s.draftSubmitBtnText}>{submittingPin ? 'Adding...' : 'Add this court'}</Text>
            </TouchableOpacity>
            <Text style={s.draftFootnote}>
              It'll show as unverified until a couple of other players confirm it's really there.
            </Text>
          </View>
        </View>
      </Modal>

      <Modal
        visible={!!areaDraftPin}
        animationType="slide"
        transparent
        onRequestClose={() => setAreaDraftPin(null)}
      >
        <View style={s.sheetBackdrop}>
          <View style={s.sheetCard}>
            <View style={s.sheetHandle} />
            <TouchableOpacity style={s.sheetClose} onPress={() => setAreaDraftPin(null)} hitSlop={10}>
              <Text style={s.sheetCloseText}>✕</Text>
            </TouchableOpacity>
            <Text style={s.draftTitle}>Watch this area</Text>
            <Text style={s.draftHint}>
              You'll be notified when someone posts availability at a court inside the circle.
              Drag the green pin to move it.
            </Text>
            <TextInput
              style={s.draftInput}
              value={areaName}
              onChangeText={setAreaName}
              placeholder="Name this area, e.g. Near work (optional)"
              placeholderTextColor={colors.muted}
            />
            <View style={s.radiusLabelRow}>
              <Text style={s.radiusLabel}>Radius</Text>
              <Text style={s.radiusValue}>{areaRadiusKm.toFixed(1)} km</Text>
            </View>
            <RadiusSlider valueKm={areaRadiusKm} onChange={setAreaRadiusKm} />
            <TouchableOpacity
              style={s.draftSubmitBtn}
              onPress={() => { playTapSound(); handleSaveAreaWatch(); }}
              disabled={savingArea}
            >
              <Text style={s.draftSubmitBtnText}>{savingArea ? 'Saving...' : 'Watch this area'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: spacing.xl, paddingTop: 16, paddingBottom: 10 },
  headerTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: colors.ink, fontSize: 24, fontFamily: fonts.serifItalic },
  headerActions: { flexDirection: 'row', gap: 8 },
  headerBtn: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7 },
  headerBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  headerBtnText: { color: colors.mutedDark, fontSize: 11.5, fontFamily: fonts.bold },
  headerBtnTextActive: { color: colors.white },
  locationWarning: { color: colors.gold, fontSize: 12, marginTop: 4, fontFamily: fonts.semibold },
  hint: { color: colors.muted, fontSize: 12, marginTop: 4, fontFamily: fonts.regular },
  map: { flex: 1 },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  errorText: { color: colors.muted, fontSize: 13.5, fontFamily: fonts.regular, textAlign: 'center', marginBottom: 14 },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 20, paddingVertical: 11 },
  retryBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheetCard: {
    backgroundColor: colors.bg, borderTopLeftRadius: radius.xxl, borderTopRightRadius: radius.xxl,
    maxHeight: '85%', paddingTop: 10, paddingHorizontal: spacing.xl, paddingBottom: spacing.xl,
  },
  sheetHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, alignSelf: 'center', marginBottom: 8 },
  sheetClose: { position: 'absolute', top: 10, right: 16, padding: 6 },
  sheetCloseText: { color: colors.muted, fontSize: 16, fontFamily: fonts.semibold },

  draftTitle: { color: colors.ink, fontSize: 19, fontFamily: fonts.extrabold, marginTop: 10 },
  draftCoords: { color: colors.muted, fontSize: 12.5, marginTop: 4, fontFamily: fonts.regular },
  draftHint: { color: colors.muted, fontSize: 12.5, marginTop: 10, lineHeight: 18, fontFamily: fonts.regular },
  draftInput: {
    backgroundColor: colors.surface, borderRadius: radius.sm, paddingHorizontal: 14, paddingVertical: 12,
    color: colors.ink, fontSize: 14, fontFamily: fonts.regular, marginTop: 14, marginBottom: 14,
  },
  draftSubmitBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 14, alignItems: 'center' },
  draftSubmitBtnText: { color: colors.white, fontSize: 14, fontFamily: fonts.bold },
  draftFootnote: { color: colors.muted, fontSize: 11.5, marginTop: 12, marginBottom: 8, lineHeight: 16, fontFamily: fonts.regular },

  radiusLabelRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
  radiusLabel: { color: colors.ink, fontSize: 13, fontFamily: fonts.semibold },
  radiusValue: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },
  radiusTrack: {
    height: 32, justifyContent: 'center', marginTop: 10, marginBottom: 18,
  },
  radiusTrackFill: { height: 4, borderRadius: 2, backgroundColor: colors.border },
  radiusHandle: {
    position: 'absolute', top: 6, left: -10, width: 20, height: 20, borderRadius: 10,
    backgroundColor: colors.primary,
  },
});

const sh = StyleSheet.create({
  scroll: { paddingTop: 18, paddingBottom: 24 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  name: { flex: 1, color: colors.ink, fontSize: 19, fontFamily: fonts.extrabold, marginRight: 10 },
  metaRow: { flexDirection: 'row', gap: 10 },
  distance: { color: colors.muted, fontSize: 12.5, marginTop: 2, fontFamily: fonts.regular },
  nameSuggestRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  nameSuggestInput: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    color: colors.ink, fontSize: 12.5, fontFamily: fonts.regular,
  },
  nameSuggestBtn: { backgroundColor: colors.primary, borderRadius: radius.sm, paddingHorizontal: 14, justifyContent: 'center' },
  nameSuggestBtnText: { color: colors.white, fontSize: 12, fontFamily: fonts.bold },

  watchBtn: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7 },
  watchBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  watchBtnText: { color: colors.mutedDark, fontSize: 12, fontFamily: fonts.bold },
  watchBtnTextActive: { color: colors.white },

  clubRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: 12, marginTop: 12,
  },
  clubText: { color: colors.primary, fontSize: 13, fontFamily: fonts.bold },
  clubSubtext: { color: colors.mutedDark, fontSize: 11.5, marginTop: 2, fontFamily: fonts.regular },
  clubWatchBtn: { borderWidth: 1, borderColor: colors.primary, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7, backgroundColor: colors.surface },

  unverifiedBanner: {
    backgroundColor: colors.primarySoft, borderRadius: radius.md, padding: 12, marginTop: 14,
  },
  unverifiedText: { color: colors.gold, fontSize: 12.5, fontFamily: fonts.bold },
  unverifiedSub: { color: colors.muted, fontSize: 12, marginTop: 4, fontFamily: fonts.regular },
  confirmBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 10, alignItems: 'center', marginTop: 8 },
  confirmBtnText: { color: colors.white, fontSize: 12.5, fontFamily: fonts.bold },

  costRow: { flexDirection: 'row', gap: 8, marginTop: 14 },
  costInput: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    color: colors.ink, fontSize: 13.5, fontFamily: fonts.regular,
  },
  costSaveBtn: { backgroundColor: colors.primary, borderRadius: radius.sm, paddingHorizontal: 14, justifyContent: 'center' },
  costSaveBtnText: { color: colors.white, fontSize: 13, fontFamily: fonts.bold },

  sectionTitle: { color: colors.ink, fontSize: 15.5, fontFamily: fonts.bold, marginTop: 22, marginBottom: 10 },
  emptyText: { color: colors.muted, fontSize: 13, fontFamily: fonts.regular },

  postCard: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 13, marginBottom: 8,
  },
  postName: { color: colors.ink, fontSize: 13.5, fontFamily: fonts.bold },
  postWhen: { color: colors.mutedDark, fontSize: 12, marginTop: 2, fontFamily: fonts.semibold },
  postNote: { color: colors.muted, fontSize: 12, marginTop: 3, fontFamily: fonts.regular },
  messageBtn: { backgroundColor: colors.primarySoft, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 8 },
  messageBtnText: { color: colors.primary, fontSize: 12, fontFamily: fonts.bold },

  dayValue: { color: colors.primary, fontSize: 15, fontFamily: fonts.bold, marginBottom: 14 },
  dayTrack: { height: 40, marginHorizontal: 10, marginBottom: 16, justifyContent: 'center' },
  dayTrackLine: {
    position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  dayMarkTouch: { position: 'absolute', marginLeft: -20, width: 40, alignItems: 'center' },
  dayMark: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.borderStrong },
  dayMarkLabel: { color: colors.muted, fontSize: 10, fontFamily: fonts.semibold, marginTop: 16, textAlign: 'center' },
  dayHandle: {
    position: 'absolute', left: -11, width: 22, height: 22, borderRadius: 11,
    backgroundColor: colors.primary, borderWidth: 2, borderColor: colors.surface,
  },

  timeInput: {
    backgroundColor: colors.surface, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    color: colors.ink, fontSize: 13.5, fontFamily: fonts.regular, marginBottom: 8,
  },
  noteInput: {
    backgroundColor: colors.surface, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 10,
    color: colors.ink, fontSize: 13.5, fontFamily: fonts.regular, minHeight: 60, textAlignVertical: 'top', marginBottom: 12,
  },
  postBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 14, alignItems: 'center' },
  postBtnText: { color: colors.white, fontSize: 14, fontFamily: fonts.bold },
});
