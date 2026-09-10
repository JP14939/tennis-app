import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet, SafeAreaView,
  ScrollView, ActivityIndicator, Platform, Modal, Animated,
} from 'react-native';
import Alert from '../utils/alert';
import { API_BASE } from '../config/api';
import { SHOT_TYPES } from '../config/shotTypes';
import { useAuth } from '../context/AuthContext';
import { saveHistory, flagNotShot, confirmRealShot, correctShotType, flagMatch } from '../api/history';
import { getNotes, addNote } from '../api/coach';
import { colors, fonts, radius, spacing } from '../theme';
import CourtBackground from '../components/CourtBackground';
import ResultShareCard from '../components/ResultShareCard';
import { captureAndShare } from '../utils/shareCard';
import { playTapSound, playCompleteSound, playAchievementSound } from '../utils/sounds';
import { BackChevronIcon, ShareIcon, CheckIcon, FlagIcon, ChevronDownIcon } from '../components/icons';
import ScoreCard from '../components/ScoreCard';
import StatCard from '../components/StatCard';
import PhaseBreakdown, { PHASE_LABELS, PHASE_ORDER, phaseColor } from '../components/PhaseBreakdown';
import TipsSection, { Collapsible, useRotate } from '../components/TipsSection';
import FriendPickerModal from '../components/FriendPickerModal';
import { shareSwing } from '../api/friends';
import { logDrillPractice } from '../api/drills';
import { useReferenceClip } from '../config/referenceClips';
import { recordHappyEvent, considerReviewPrompt } from '../utils/reviewPrompt';

// Coach notes attached to one phase (or general, phaseKey=null) -- shown
// inline wherever they're relevant, with an "Add note" composer when the
// viewer is allowed to write one (canAddNotes, passed from CoachScreen).
function NotesBlock({ notes, phaseKey, canAddNotes, onAdd }) {
  const [composing, setComposing] = useState(false);
  const [text, setText] = useState('');
  const relevant = notes.filter((n) => (n.phase_key ?? null) === (phaseKey ?? null) && n.timestamp_sec == null);

  const submit = async () => {
    if (!text.trim()) return;
    await onAdd({ noteText: text.trim(), phaseKey: phaseKey ?? undefined });
    setText('');
    setComposing(false);
  };

  return (
    <View style={n.wrap}>
      {relevant.map((note) => (
        <View key={note.id} style={n.note}>
          <Text style={n.noteAuthor}>{note.coach_name}</Text>
          <Text style={n.noteText}>{note.note_text}</Text>
        </View>
      ))}
      {canAddNotes && (
        composing ? (
          <View style={n.composer}>
            <TextInput
              style={n.input}
              value={text}
              onChangeText={setText}
              placeholder="Write a note..."
              placeholderTextColor={colors.muted}
              multiline
            />
            <View style={n.composerBtns}>
              <TouchableOpacity onPress={() => { setComposing(false); setText(''); }}>
                <Text style={n.cancelText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={submit}>
                <Text style={n.saveText}>Save note</Text>
              </TouchableOpacity>
            </View>
          </View>
        ) : (
          <TouchableOpacity onPress={() => setComposing(true)}>
            <Text style={n.addLink}>+ Add note</Text>
          </TouchableOpacity>
        )
      )}
    </View>
  );
}
const n = StyleSheet.create({
  wrap: { marginTop: 8 },
  note: { backgroundColor: colors.primarySoft, borderRadius: radius.sm, padding: 10, marginBottom: 6 },
  noteAuthor: { color: colors.primary, fontSize: 11, fontFamily: fonts.bold, marginBottom: 2 },
  noteText: { color: colors.limeText, fontSize: 12.5, lineHeight: 18, fontFamily: fonts.regular },
  addLink: { color: colors.primary, fontSize: 12, fontFamily: fonts.semibold },
  composer: { marginTop: 4 },
  input: {
    backgroundColor: colors.bg, borderRadius: radius.sm, padding: 10,
    color: colors.ink, fontSize: 13, fontFamily: fonts.regular, minHeight: 60, textAlignVertical: 'top',
  },
  composerBtns: { flexDirection: 'row', justifyContent: 'flex-end', gap: 16, marginTop: 6 },
  cancelText: { color: colors.muted, fontSize: 12.5, fontFamily: fonts.semibold },
  saveText: { color: colors.primary, fontSize: 12.5, fontFamily: fonts.bold },
});

// The result is graded against the pro-swing database as a whole, not shown as
// a match to one named player -- most database clips aren't identified, and a
// "matched to Forehand Technique #142" caption read as broken. The score card
// / share card caption describes the number; the compared clip is still a real
// pro swing, just labelled generically ("Pro swing") in Sync Compare.
const proMatchCaption = (shotType) =>
  `How closely your ${shotType || 'swing'} matches pro technique`;

async function buildFormData(videoUri, shotType, contactTimeSec, viewDirectionHint) {
  const formData = new FormData();
  if (Platform.OS === 'web') {
    const response = await fetch(videoUri);
    const blob = await response.blob();
    formData.append('video', blob, 'swing.mp4');
  } else {
    formData.append('video', { uri: videoUri, name: 'swing.mp4', type: 'video/mp4' });
  }
  formData.append('shotType', shotType);
  if (contactTimeSec !== undefined && contactTimeSec !== null) {
    formData.append('contactTime', String(contactTimeSec));
  }
  if (viewDirectionHint === 'front' || viewDirectionHint === 'back') {
    formData.append('viewDirectionHint', viewDirectionHint);
  }
  return formData;
}

export default function ResultsScreen({ navigation, route }) {
  const {
    videoUri, shotType, contactTimeSec, viewDirectionHint,
    savedResult, analysisId: routeAnalysisId, canAddNotes,
    flaggedNotShot = false, confirmedRealShot = false, matchFlagged: matchFlaggedInitial = false,
    practiceStepId,
  } = route.params ?? {};
  const { token, isAuthenticated } = useAuth();

  const [status, setStatus] = useState(savedResult ? 'done' : 'loading'); // loading | error | done
  const [errorMsg, setErrorMsg] = useState('');
  const [errorCode, setErrorCode] = useState(null);
  const [result, setResult] = useState(savedResult ?? null);
  // idle | saving | saved | limit | error — purely informational, never blocks
  // the result from displaying. ('guest' is also set transiently by
  // saveToHistory for a logged-out caller, but that caller is held at the
  // reveal gate and never renders the body, so it has no banner.)
  const [saveStatus, setSaveStatus] = useState('idle');
  const shareCardRef = useRef(null);
  const [shareModalVisible, setShareModalVisible] = useState(false);
  // Bumped every time the share popup opens so ResultShareCard/ScoreRing
  // remount and the fill-up animation replays instead of only running once.
  const [shareModalKey, setShareModalKey] = useState(0);
  const [friendPickerVisible, setFriendPickerVisible] = useState(false);

  // Guards runAnalysis()'s post-fetch state updates -- without it, backing
  // out of this screen mid-analysis still let the eventual response's
  // setResult/setStatus/etc. land on the unmounted screen.
  const mountedRef = useRef(true);
  // Delayed "rate the app?" prompt (see maybePromptForReview below) -- held in
  // a ref so leaving the screen before it fires cancels it.
  const reviewTimerRef = useRef(null);
  useEffect(() => () => {
    mountedRef.current = false;
    if (reviewTimerRef.current) clearTimeout(reviewTimerRef.current);
  }, []);

  // A fresh analysis (route params has no analysisId yet) only gets one
  // once saveToHistory() below actually saves it -- captured here so the
  // verify buttons, notes, and Compare button all work for a just-analyzed
  // result, not only when viewing an already-saved one from History.
  const [savedAnalysisId, setSavedAnalysisId] = useState(routeAnalysisId ?? null);
  const analysisId = savedAnalysisId;

  const [flagged, setFlagged] = useState(flaggedNotShot);
  const [confirmed, setConfirmed] = useState(confirmedRealShot);
  const [matchFlagged, setMatchFlagged] = useState(matchFlaggedInitial);
  const [displayShotType, setDisplayShotType] = useState(shotType);
  const [showTypePicker, setShowTypePicker] = useState(false);

  // Bundled clean-swing clip for this shot type -- null until the asset is
  // added and wired in config/referenceClips.js, which keeps the "Watch the
  // ideal swing" button and per-tip "See this done right" links hidden.
  const referenceClip = useReferenceClip(displayShotType);

  // Closed by default -- unlike TipsSection's tips (valuable, actionable),
  // the phase breakdown is a deep-dive most users don't need on first look;
  // the hero score is the payoff, this is opt-in detail below it.
  const [phasesOpen, setPhasesOpen] = useState(false);
  const phasesRotate = useRotate(phasesOpen);

  const [notes, setNotes] = useState([]);
  const loadNotes = () => {
    if (!analysisId) return;
    getNotes(token, analysisId).then((data) => setNotes(data.notes)).catch(() => {});
  };
  useEffect(() => { loadNotes(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [analysisId]);
  const handleAddNote = async ({ noteText, phaseKey }) => {
    await addNote(token, { analysisId, noteText, phaseKey });
    loadNotes();
  };

  const handleSendToFriend = async (friend) => {
    setFriendPickerVisible(false);
    try {
      await shareSwing(token, friend.id, analysisId);
      Alert.alert('Sent!', `${friend.name} can now see this swing on Friends.`);
    } catch (err) {
      Alert.alert('Could not send', err.message || 'Something went wrong');
    }
  };

  const handleToggleFlag = async () => {
    const nextFlagged = !flagged;
    setFlagged(nextFlagged);
    if (nextFlagged) setConfirmed(false);
    try {
      await flagNotShot(token, analysisId, nextFlagged);
    } catch (err) {
      setFlagged(!nextFlagged); // revert on failure
    }
  };

  const handleToggleConfirm = async () => {
    const nextConfirmed = !confirmed;
    setConfirmed(nextConfirmed);
    if (nextConfirmed) setFlagged(false);
    try {
      await confirmRealShot(token, analysisId, nextConfirmed);
    } catch (err) {
      setConfirmed(!nextConfirmed); // revert on failure
    }
  };

  const handleToggleMatchFlag = async () => {
    const next = !matchFlagged;
    setMatchFlagged(next);
    try {
      await flagMatch(token, analysisId, next);
    } catch (err) {
      setMatchFlagged(!next); // revert on failure
    }
  };

  const handleCorrectType = async (newShotType) => {
    if (newShotType === displayShotType) { setShowTypePicker(false); return; }
    const prevShotType = displayShotType;
    setDisplayShotType(newShotType);
    setShowTypePicker(false);
    try {
      await correctShotType(token, analysisId, newShotType);
    } catch (err) {
      setDisplayShotType(prevShotType);
      Alert.alert('Could not update shot type', err.message || 'Something went wrong');
    }
  };

  const runAnalysis = async () => {
    setStatus('loading');
    setErrorMsg('');
    setErrorCode(null);
    try {
      const formData = await buildFormData(videoUri, shotType, contactTimeSec, viewDirectionHint);
      // Send the token when we have one so the analysis counts against the
      // user's own free-tier allowance and saves to their history. A guest
      // (onboarding flow, pre-signup) sends no header and the backend runs it
      // on the strict guest per-IP allowance instead -- see
      // docs/plans/onboarding_plan.md.
      const response = await fetch(`${API_BASE}/api/analyse`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body: formData,
      });
      const data = await response.json();
      if (!mountedRef.current) return;
      if (!response.ok) {
        setErrorCode(data.code ?? null);
        throw new Error(data.error || 'Analysis failed');
      }
      setResult(data);
      setStatus('done');
      // Great swing (>=75) gets the special achievement chime; anything
      // else still gets a neutral "you're done" completion sound. Only
      // reachable from a fresh analysis (see the savedResult guard below,
      // which skips runAnalysis entirely for an already-saved result) --
      // browsing back to an old result never replays either sound.
      // Must read the same field the screen actually DISPLAYS (see `score`
      // below, line ~324) -- this used to read .similarity alone, so a
      // swing whose overall_score and similarity disagreed could play the
      // wrong sound relative to what the user sees on screen.
      const topMatch = data.matches?.[0];
      const topScore = topMatch?.overall_score ?? topMatch?.similarity ?? 0;
      if (topScore >= 75) {
        playAchievementSound();
      } else {
        playCompleteSound();
      }
      await saveToHistory(data);
      maybePromptForReview(topScore);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMsg(err.message || 'Something went wrong');
      setStatus('error');
    }
  };

  // The "happy moment" for an ASO rating ask: a fresh analysis just finished
  // and saved. Gated hard inside considerReviewPrompt() (not first-ever, not
  // more than every 60 days, max 3 lifetime, OS has the final say). Here:
  //   - authenticated only -- a guest hasn't committed to the app yet.
  //   - recordHappyEvent() fires IMMEDIATELY so the count tracks completed
  //     analyses even for a user who leaves the screen before the delay.
  //   - the prompt itself waits ~2.2s (score count-up finishes; the native
  //     sheet doesn't fight it for attention) and only fires for score >= 50,
  //     since a disappointing result isn't a happy moment to ask on.
  const maybePromptForReview = (topScore) => {
    if (!isAuthenticated) return;
    recordHappyEvent();
    if (topScore < 50) return;
    if (reviewTimerRef.current) clearTimeout(reviewTimerRef.current);
    reviewTimerRef.current = setTimeout(() => {
      if (mountedRef.current) considerReviewPrompt();
    }, 2200);
  };

  const saveToHistory = async (data) => {
    if (!isAuthenticated) {
      setSaveStatus('guest');
      return;
    }
    setSaveStatus('saving');
    try {
      const saved = await saveHistory(token, data, shotType);
      if (!mountedRef.current) return;
      setSavedAnalysisId(saved.id);
      setSaveStatus('saved');
      // Best-effort -- a practice attempt failing to link back to its
      // lesson step should never block the analysis result itself from
      // showing (the analysis is already saved to History regardless).
      if (practiceStepId) {
        logDrillPractice(token, practiceStepId, saved.id).catch(() => {});
      }
    } catch (err) {
      if (!mountedRef.current) return;
      setSaveStatus(err.code === 'HISTORY_LIMIT' ? 'limit' : 'error');
    }
  };

  // Guest → signup handoff: a logged-out user analysed a swing (held behind
  // the reveal gate below), then created an account and popped back here.
  // Now authenticated with an unsaved fresh result -> save it to their new
  // history so it's not lost. No-op on every normal path (authed users hit
  // saveToHistory inside runAnalysis; an already-saved result has an id).
  const didGuestSaveRef = useRef(false);
  useEffect(() => {
    // Only the guest→signup case: a fresh analysis (no savedResult param, no
    // analysisId) that this screen ran while logged out. The savedResult
    // effect below owns every other "save an unsaved result" path.
    if (isAuthenticated && result && !savedResult && !routeAnalysisId
        && !savedAnalysisId && !didGuestSaveRef.current) {
      didGuestSaveRef.current = true;
      saveToHistory(result);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, result]);

  useEffect(() => {
    if (savedResult) {
      // A savedResult with no analysisId (e.g. a shot analyzed straight out
      // of a rally, via HighlightArchiveScreen's RallyBrowser) was never
      // actually saved to History yet -- only opening an *already-saved*
      // analysis (HistoryScreen, which always has an analysisId) means
      // there's nothing left to do here.
      if (!routeAnalysisId) saveToHistory(savedResult);
      return; // already have the full result — nothing to fetch
    }
    if (videoUri && shotType) {
      runAnalysis();
    } else {
      setErrorMsg('Missing video or shot type — go back and try again.');
      setStatus('error');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Loading ───────────────────────────────────────────────────────────────
  if (status === 'loading') {
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={s.loadingTitle}>Analysing your swing...</Text>
          <Text style={s.loadingSub}>Comparing your technique against our pro database</Text>
        </View>
      </SafeAreaView>
    );
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (status === 'error') {
    const isDailyLimit = errorCode === 'DAILY_LIMIT';
    // A guest used up the 2 free analyses the onboarding flow allows before
    // signup -- retrying can't help, an account can.
    const isGuestLimit = errorCode === 'GUEST_LIMIT';
    // View gate: the video isn't a usable behind-the-baseline shot. Re-running
    // the same clip can't help -- send them back to re-record instead.
    const isViewReject = errorCode === 'VIEW_NOT_USABLE';
    // Any other failure for a logged-out user: still surface the account path
    // (their history isn't being saved either way), alongside "try again".
    const showGuestSignup = !isAuthenticated && (isGuestLimit || !isViewReject);
    const title = isDailyLimit ? 'Daily limit reached'
      : isGuestLimit ? 'Create a free account'
      : isViewReject ? 'Check your camera setup'
      : 'Analysis failed';
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <View style={s.centerFill}>
          <Text style={s.loadingTitle}>{title}</Text>
          <Text style={s.loadingSub}>{errorMsg}</Text>
          {isDailyLimit ? (
            <TouchableOpacity
              style={s.retryBtn}
              onPress={() => navigation.navigate('Premium')}
            >
              <Text style={s.retryBtnText}>Upgrade to Premium</Text>
            </TouchableOpacity>
          ) : isGuestLimit ? (
            <TouchableOpacity
              style={s.retryBtn}
              onPress={() => navigation.navigate('Signup', { returnTo: { screen: 'Upload', params: { shotType } } })}
            >
              <Text style={s.retryBtnText}>Create free account</Text>
            </TouchableOpacity>
          ) : isViewReject ? (
            <TouchableOpacity style={s.retryBtn} onPress={() => navigation.popToTop()}>
              <Text style={s.retryBtnText}>Record another swing</Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity style={s.retryBtn} onPress={runAnalysis}>
              <Text style={s.retryBtnText}>Try again</Text>
            </TouchableOpacity>
          )}
          {showGuestSignup && !isGuestLimit && (
            <TouchableOpacity
              style={s.secondaryBtn}
              onPress={() => navigation.navigate('Signup', { returnTo: { screen: 'Upload', params: { shotType } } })}
            >
              <Text style={s.secondaryBtnText}>Create a free account</Text>
            </TouchableOpacity>
          )}
          {!isViewReject && !isGuestLimit && (
            <TouchableOpacity style={s.secondaryBtn} onPress={() => navigation.popToTop()}>
              <Text style={s.secondaryBtnText}>Back to home</Text>
            </TouchableOpacity>
          )}
        </View>
      </SafeAreaView>
    );
  }

  // ── Guest reveal gate ─────────────────────────────────────────────────────
  // The onboarding flow lets a logged-out user run their first analysis; the
  // backend has already produced the real result, but we hold it here behind
  // a free-account signup (docs/plans/onboarding_plan.md, "gate at the
  // reveal"). `returnTo` has no params: Signup/Login just pop back to THIS
  // still-mounted Results instance, which kept `result` in state. Becoming
  // authenticated then (a) skips this branch and (b) fires the
  // [isAuthenticated, result] effect above, which saves the held result to
  // the new account's history.
  if (!isAuthenticated && result) {
    const returnTo = { screen: 'Results' };
    return (
      <SafeAreaView style={s.safe}>
        <CourtBackground />
        <View style={s.centerFill}>
          <Text style={s.loadingTitle}>Your score's ready</Text>
          <Text style={s.loadingSub}>
            Create a free account to see your result and keep your swing history.
          </Text>
          <TouchableOpacity style={s.retryBtn} onPress={() => navigation.navigate('Signup', { returnTo })}>
            <Text style={s.retryBtnText}>Create free account</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.secondaryBtn} onPress={() => navigation.navigate('Login', { returnTo })}>
            <Text style={s.secondaryBtnText}>I already have an account</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Results ───────────────────────────────────────────────────────────────
  const top = result.matches?.[0];
  const score = top?.overall_score ?? top?.similarity ?? 0;
  const phases = top?.phases;

  return (
    <SafeAreaView style={s.safe}>
      <CourtBackground />
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity style={s.backLink} onPress={() => navigation.goBack()}>
          <BackChevronIcon size={13} color={colors.muted} />
          <Text style={s.backLinkText}>Back</Text>
        </TouchableOpacity>

        <View style={s.headerRow}>
          <View>
            <Text style={s.header}>Your results</Text>
            <Text style={s.headerSub}>{displayShotType?.charAt(0).toUpperCase() + displayShotType?.slice(1)}</Text>
          </View>
          {top && Platform.OS !== 'web' && (
            <TouchableOpacity
              style={s.shareBtn}
              onPress={() => { setShareModalKey((k) => k + 1); setShareModalVisible(true); }}
            >
              <ShareIcon size={17} color={colors.ink} />
            </TouchableOpacity>
          )}
        </View>

        {result.view_gate && !result.view_gate.usable && (
          <View style={s.viewGateBanner}>
            <Text style={s.viewGateBannerText}>
              ⚠ {result.view_gate.message}
              {'\n'}Your score may be less accurate — film from behind the baseline for the best match.
            </Text>
          </View>
        )}

        {top ? (
          <>
            {/* Score */}
            <ScoreCard score={score} caption={proMatchCaption(displayShotType)} />

            {top.pro_clip_url && result.user_clip_url && (
              <TouchableOpacity
                style={s.compareBtn}
                onPress={() => navigation.navigate('SyncCompare', {
                  videoAUrl: `${API_BASE}${top.pro_clip_url}`,
                  videoBUrl: `${API_BASE}${result.user_clip_url}`,
                  contactASec: top.pro_contact_time_sec ?? 0,
                  contactBSec: result.contact_time_sec ?? 0,
                  overlayA: top.pro_overlay_trajectory ?? null,
                  overlayB: result.user_overlay_trajectory ?? null,
                  racketPathA: top.pro_racket_overlay_trajectory ?? null,
                  racketPathB: result.racket_overlay_trajectory ?? null,
                  ballPathA: top.pro_ball_overlay_trajectory ?? null,
                  ballPathB: result.ball_overlay_trajectory ?? null,
                  labelA: 'Pro swing',
                  labelB: 'You',
                  analysisId,
                  canAddNotes,
                  phaseMarkers: top.phase_markers ?? undefined,
                })}
              >
                <Text style={s.compareBtnText}>Compare side-by-side →</Text>
              </TouchableOpacity>
            )}

            {/* Display-only: the user's clip next to a clean reference swing
                for this shot type -- for watching the difference, not scoring
                (that's the pro-match button above). Hidden until a reference
                clip is wired in config/referenceClips.js. */}
            {referenceClip && result.user_clip_url && (
              <TouchableOpacity
                style={s.compareBtn}
                onPress={() => navigation.navigate('SyncCompare', {
                  videoAUrl: referenceClip.uri,
                  videoBUrl: `${API_BASE}${result.user_clip_url}`,
                  contactASec: referenceClip.contactSec,
                  contactBSec: result.contact_time_sec ?? 0,
                  labelA: 'Ideal swing',
                  labelB: 'You',
                  analysisId,
                  canAddNotes,
                })}
              >
                <Text style={s.compareBtnText}>Watch the ideal swing ▸</Text>
              </TouchableOpacity>
            )}

            {/* Match-quality signal for the DTW comparison -- one tap, no
                prompt. Only offered on a saved analysis (needs an id to
                flag against). See backend history.js logMatchQualityFlag. */}
            {analysisId && (
              <TouchableOpacity
                style={s.matchFlagLink}
                onPress={handleToggleMatchFlag}
                activeOpacity={0.7}
              >
                <FlagIcon size={11} color={matchFlagged ? colors.coral : colors.muted} />
                <Text style={[s.matchFlagText, matchFlagged && s.matchFlagTextOn]}>
                  {matchFlagged ? "Flagged — thanks, we'll review this match" : "This doesn't look like my swing"}
                </Text>
              </TouchableOpacity>
            )}

            {analysisId && (
              <TouchableOpacity style={s.sendBtn} onPress={() => setFriendPickerVisible(true)}>
                <Text style={s.sendBtnText}>Send to a friend</Text>
              </TouchableOpacity>
            )}

            {/* Save-to-history status */}
            {saveStatus === 'saved' && (
              <View style={s.saveBanner}>
                <Text style={s.saveBannerText}>✓ Saved to your history</Text>
              </View>
            )}
            {/* No saveStatus === 'guest' banner: a guest is intercepted by the
                reveal gate above and never reaches this results body. */}
            {saveStatus === 'limit' && (
              <TouchableOpacity
                style={s.saveBannerAction}
                onPress={() => navigation.navigate('Premium')}
              >
                <Text style={s.saveBannerActionText}>Free plan limit reached (3/3) — upgrade to save unlimited →</Text>
              </TouchableOpacity>
            )}

            {/* Real human ground truth for scripts/16_shot_verification/'s
                teacher-student loop -- same verify row as HistoryScreen's
                cards, available here too since this is the first place a
                user actually watches their swing back. */}
            {analysisId && (
              <View style={s.verifyWrap}>
                {flagged && (
                  <View style={s.flaggedBanner}>
                    <FlagIcon size={11} color={colors.coral} />
                    <Text style={s.flaggedBannerText}>Flagged: not a real shot</Text>
                  </View>
                )}
                {confirmed && (
                  <View style={s.confirmedBanner}>
                    <CheckIcon size={11} color={colors.primary} />
                    <Text style={s.confirmedBannerText}>Confirmed: real shot</Text>
                  </View>
                )}
                <Text style={s.verifyLabel}>Is this actually a shot?</Text>
                <View style={s.verifyRow}>
                  <TouchableOpacity
                    style={[s.verifyBtn, confirmed && s.verifyBtnConfirmed]}
                    onPress={handleToggleConfirm}
                    activeOpacity={0.8}
                  >
                    <CheckIcon size={12} color={confirmed ? colors.white : colors.primary} />
                    <Text style={[s.verifyBtnText, confirmed && s.verifyBtnTextOn]}>Yes, real shot</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[s.verifyBtn, flagged && s.verifyBtnFlagged]}
                    onPress={handleToggleFlag}
                    activeOpacity={0.8}
                  >
                    <FlagIcon size={12} color={flagged ? colors.white : colors.coral} />
                    <Text style={[s.verifyBtnText, flagged && s.verifyBtnTextOn]}>No, not a shot</Text>
                  </TouchableOpacity>
                </View>

                {/* Same idea, but for shot TYPE -- teaches
                    scripts/14_shot_classifier/'s teacher-student loop. */}
                <TouchableOpacity style={s.wrongTypeBtn} onPress={() => setShowTypePicker((v) => !v)} activeOpacity={0.7}>
                  <Text style={s.wrongTypeText}>{showTypePicker ? 'Cancel' : 'Wrong shot type?'}</Text>
                </TouchableOpacity>
                {showTypePicker && (
                  <View style={s.typePickerRow}>
                    {SHOT_TYPES.map((st) => (
                      <TouchableOpacity
                        key={st}
                        style={[s.typePickerBtn, st === displayShotType && s.typePickerBtnActive]}
                        onPress={() => handleCorrectType(st)}
                        activeOpacity={0.8}
                      >
                        <Text style={[s.typePickerBtnText, st === displayShotType && s.typePickerBtnTextActive]}>
                          {st.charAt(0).toUpperCase() + st.slice(1)}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
              </View>
            )}

            {/* General coach notes (not tied to a phase) */}
            {analysisId && (canAddNotes || notes.some((nt) => !nt.phase_key && nt.timestamp_sec == null)) && (
              <View style={s.generalNotesWrap}>
                <Text style={s.sectionTitle}>Coach notes</Text>
                <NotesBlock notes={notes} phaseKey={null} canAddNotes={!!canAddNotes} onAdd={handleAddNote} />
              </View>
            )}

            {/* Ball speed at the net crossing -- absent (not dashed) when
                unavailable, e.g. close-up framing or the net wasn't visible;
                see scripts/07_ball_racket_tracking/ball_speed.py. */}
            {result.ball_speed_kmh != null && (
              <StatCard label="Ball speed at net" value={`${result.ball_speed_kmh} km/h`} />
            )}

            {/* Phase breakdown -- collapsed by default, same accordion
                primitives TipsSection already uses below */}
            {phases && (
              <>
                <TouchableOpacity style={s.phaseToggle} onPress={() => setPhasesOpen((o) => !o)} activeOpacity={0.85}>
                  <Text style={s.phaseToggleText}>See phase breakdown</Text>
                  <Animated.View style={{ transform: [{ rotate: phasesRotate }] }}>
                    <ChevronDownIcon size={14} color={colors.mutedDark} />
                  </Animated.View>
                </TouchableOpacity>
                <Collapsible open={phasesOpen}>
                  <View style={s.phaseReveal}>
                    <PhaseBreakdown
                      phases={phases}
                      analysisId={analysisId}
                      notes={notes}
                      canAddNotes={canAddNotes}
                      onAddNote={handleAddNote}
                      NotesBlock={NotesBlock}
                    />
                  </View>
                </Collapsible>
              </>
            )}

            {/* Coaching tips */}
            {top.tips?.length > 0 && (
              <TipsSection
                tips={top.tips}
                referenceClip={referenceClip}
                userClipUrl={result.user_clip_url}
                userContactSec={result.contact_time_sec ?? 0}
                analysisId={analysisId}
                canAddNotes={canAddNotes}
              />
            )}
          </>
        ) : (
          <Text style={s.loadingSub}>No matches found for this swing.</Text>
        )}

        <TouchableOpacity
          style={s.primaryBtn}
          onPress={() => { playTapSound(); navigation.navigate('MainTabs', { screen: 'History' }); }}
        >
          <Text style={s.primaryBtnText}>Try another shot</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.secondaryBtn} onPress={() => navigation.popToTop()}>
          <Text style={s.secondaryBtnText}>Back to home</Text>
        </TouchableOpacity>
      </ScrollView>

      {top && (
        <View style={s.offscreen}>
          <ResultShareCard
            ref={shareCardRef}
            score={score}
            shotType={displayShotType}
            caption="Pro technique match"
          />
        </View>
      )}

      {top && (
        <Modal
          visible={shareModalVisible}
          animationType="fade"
          transparent
          onRequestClose={() => setShareModalVisible(false)}
        >
          <View style={s.shareModalBackdrop}>
            <View style={s.shareModalCard}>
              <View style={s.shareModalHeader}>
                <Text style={s.shareModalTitle}>Share your result</Text>
                <TouchableOpacity onPress={() => setShareModalVisible(false)} hitSlop={10}>
                  <Text style={s.shareModalClose}>✕</Text>
                </TouchableOpacity>
              </View>

              <ScrollView contentContainerStyle={s.shareModalScroll} showsVerticalScrollIndicator={false}>
                <View style={s.shareModalPreviewWrap}>
                  <ResultShareCard
                    key={shareModalKey}
                    score={score}
                    shotType={displayShotType}
                    caption="Pro technique match"
                    animate
                  />
                </View>

                {phases && (
                  <View style={s.shareModalBreakdown}>
                    <Text style={s.shareModalBreakdownTitle}>Swing breakdown</Text>
                    {PHASE_ORDER.map((key) => {
                      const phase = phases[key];
                      if (!phase) return null;
                      const pScore = phase.score;
                      return (
                        <View key={key} style={s.shareModalPhaseRow}>
                          <View style={s.shareModalPhaseHead}>
                            <Text style={s.shareModalPhaseName}>{PHASE_LABELS[key]}</Text>
                            <Text style={[s.shareModalPhaseScore, { color: phaseColor(pScore) }]}>
                              {pScore ?? '—'}/25
                            </Text>
                          </View>
                          <View style={s.phaseTrack}>
                            <View
                              style={[
                                s.phaseFill,
                                { width: `${((pScore ?? 0) / 25) * 100}%`, backgroundColor: phaseColor(pScore) },
                              ]}
                            />
                          </View>
                        </View>
                      );
                    })}
                  </View>
                )}
              </ScrollView>

              <View style={s.shareModalFooter}>
                <TouchableOpacity
                  style={[s.secondaryBtn, s.shareModalFooterBtn]}
                  onPress={() => setShareModalVisible(false)}
                >
                  <Text style={s.secondaryBtnText}>Close</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[s.primaryBtn, s.shareModalFooterBtn]}
                  onPress={async () => {
                    await captureAndShare(shareCardRef, 'Share your RallyMax result');
                    setShareModalVisible(false);
                  }}
                >
                  <Text style={s.primaryBtnText}>Share image</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      )}

      <FriendPickerModal
        visible={friendPickerVisible}
        onClose={() => setFriendPickerVisible(false)}
        onSelect={handleSendToFriend}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 60, paddingBottom: 48 },

  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 18, alignSelf: 'flex-start' },
  backLinkText: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold },

  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  loadingTitle: { color: colors.ink, fontSize: 18, fontFamily: fonts.bold, marginTop: 20, textAlign: 'center' },
  loadingSub: { color: colors.muted, fontSize: 14, marginTop: 8, textAlign: 'center', lineHeight: 20, fontFamily: fonts.regular },
  retryBtn: { backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: 12, paddingHorizontal: 28, marginTop: 24 },
  retryBtnText: { color: colors.white, fontSize: 15, fontFamily: fonts.bold },

  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  header: { color: colors.ink, fontSize: 30, fontFamily: fonts.serifItalic },
  headerSub: { color: colors.muted, fontSize: 14, marginTop: 2, marginBottom: 22, fontFamily: fonts.regular },
  shareBtn: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: colors.surface,
    alignItems: 'center', justifyContent: 'center',
  },
  offscreen: { position: 'absolute', left: -9999, top: -9999 },

  compareBtn: {
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: 'center', marginBottom: 14,
  },
  compareBtnText: { color: colors.primary, fontSize: 13.5, fontFamily: fonts.bold },
  sendBtn: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingVertical: 12, alignItems: 'center', marginBottom: 14,
  },
  sendBtnText: { color: colors.mutedDark, fontSize: 13.5, fontFamily: fonts.bold },
  matchFlagLink: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 8, marginTop: -6, marginBottom: 14,
  },
  matchFlagText: { color: colors.muted, fontSize: 12, fontFamily: fonts.semibold },
  matchFlagTextOn: { color: colors.coral },
  generalNotesWrap: { marginBottom: 26 },

  saveBanner: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.sm, padding: 11, marginBottom: 22, alignItems: 'center',
  },
  saveBannerText: { color: colors.primary, fontSize: 12.5, fontFamily: fonts.bold },
  saveBannerAction: {
    backgroundColor: colors.amberBg,
    borderRadius: radius.sm, padding: 12, marginBottom: 22, alignItems: 'center',
  },
  saveBannerActionText: { color: colors.amberText, fontSize: 12.5, fontFamily: fonts.bold, textAlign: 'center' },

  verifyWrap: { marginBottom: 26 },
  viewGateBanner: {
    backgroundColor: colors.amberBg,
    borderRadius: radius.sm, padding: 12, marginBottom: 18,
  },
  viewGateBannerText: { color: colors.amberText, fontSize: 12.5, fontFamily: fonts.bold, lineHeight: 18 },
  flaggedBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    backgroundColor: colors.coralSoft ?? '#fbe2df', borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 4, marginBottom: 10,
  },
  flaggedBannerText: { color: colors.coral, fontSize: 11, fontFamily: fonts.bold },
  confirmedBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    backgroundColor: colors.primarySoft, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 4, marginBottom: 10,
  },
  confirmedBannerText: { color: colors.primary, fontSize: 11, fontFamily: fonts.bold },
  verifyLabel: { color: colors.muted, fontSize: 11, fontFamily: fonts.semibold, marginBottom: 6 },
  verifyRow: { flexDirection: 'row', gap: 8 },
  verifyBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 10,
  },
  verifyBtnConfirmed: { backgroundColor: colors.primary },
  verifyBtnFlagged: { backgroundColor: colors.coral },
  verifyBtnText: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.bold },
  verifyBtnTextOn: { color: colors.white },
  wrongTypeBtn: {
    alignSelf: 'flex-start', marginTop: 12, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 7,
  },
  wrongTypeText: { color: colors.mutedDark, fontSize: 12, fontFamily: fonts.bold },
  typePickerRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  typePickerBtn: {
    flex: 1, alignItems: 'center', backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingHorizontal: 10, paddingVertical: 10,
  },
  typePickerBtnActive: { backgroundColor: colors.primary },
  typePickerBtnText: { color: colors.mutedDark, fontSize: 12.5, fontFamily: fonts.bold },
  typePickerBtnTextActive: { color: colors.white },

  sectionTitle: { color: colors.ink, fontSize: 19, fontFamily: fonts.serif, marginBottom: 12 },
  phaseToggle: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: colors.surface, borderRadius: radius.md, padding: 15, marginBottom: 22,
  },
  phaseToggleText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold },
  phaseReveal: { marginTop: -12, paddingTop: 10 },
  // phaseTrack/phaseFill are still used directly by the share modal's own
  // mini breakdown replay below -- the main phase-breakdown section itself
  // now lives in components/PhaseBreakdown.js with its own copies.
  phaseTrack: { height: 5, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden' },
  phaseFill: { height: 5, borderRadius: 3 },

  primaryBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 15, alignItems: 'center', marginTop: 16 },
  primaryBtnText: { color: colors.white, fontSize: 14.5, fontFamily: fonts.bold },
  secondaryBtn: {
    backgroundColor: colors.surface, borderRadius: radius.pill,
    paddingVertical: 14, alignItems: 'center', marginTop: 10,
  },
  secondaryBtnText: { color: colors.mutedDark, fontSize: 14.5, fontFamily: fonts.bold },

  shareModalBackdrop: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center', justifyContent: 'center', padding: spacing.xl,
  },
  shareModalCard: {
    width: '100%', maxWidth: 400, maxHeight: '85%',
    backgroundColor: colors.bg, borderRadius: radius.xxl, padding: spacing.lg,
  },
  shareModalHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.md,
  },
  shareModalTitle: { color: colors.ink, fontSize: 17, fontFamily: fonts.bold },
  shareModalClose: { color: colors.muted, fontSize: 18, fontFamily: fonts.semibold, padding: 4 },
  shareModalScroll: { alignItems: 'center', paddingBottom: spacing.sm },
  shareModalPreviewWrap: { marginBottom: spacing.lg },
  shareModalBreakdown: { width: '100%' },
  shareModalBreakdownTitle: {
    color: colors.ink, fontSize: 15, fontFamily: fonts.bold, marginBottom: spacing.sm,
  },
  shareModalPhaseRow: { marginBottom: spacing.sm },
  shareModalPhaseHead: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5,
  },
  shareModalPhaseName: { color: colors.ink, fontSize: 13.5, fontFamily: fonts.semibold },
  shareModalPhaseScore: { fontSize: 13.5, fontFamily: fonts.bold },
  shareModalFooter: { flexDirection: 'row', gap: 10, marginTop: spacing.md },
  shareModalFooterBtn: { flex: 1, marginTop: 0 },
});
