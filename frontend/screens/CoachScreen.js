import { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, TextInput, StyleSheet,
  SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native';
import Alert from '../utils/alert';
import { useFocusEffect } from '@react-navigation/native';
import { useAuth } from '../context/AuthContext';
import { getInviteCode, linkCoach, listStudents, getStudentHistory } from '../api/coach';
import { colors, fonts, radius, spacing, scoreColor } from '../theme';
import { playTapSound, playAchievementSound } from '../utils/sounds';
import { TennisBallIcon, BackChevronIcon } from '../components/icons';

function formatProId(proId, playerName) {
  if (!proId) return 'Analysis';
  const [shot, num] = proId.split('_');
  if (!shot || !num) return proId;
  const label = shot.charAt(0).toUpperCase() + shot.slice(1);
  if (playerName) return `${playerName}'s ${label}`;
  return `${label} Technique #${parseInt(num, 10)}`;
}

function formatDate(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString.includes('Z') ? isoString : `${isoString.replace(' ', 'T')}Z`);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function Section({ title, children }) {
  return (
    <View style={sec.wrap}>
      <Text style={sec.title}>{title}</Text>
      {children}
    </View>
  );
}
const sec = StyleSheet.create({
  wrap: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: 16, marginBottom: spacing.lg },
  title: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.bold, marginBottom: 12 },
});

// ── Student's history (viewed by their coach) ────────────────────────────────
function StudentHistory({ student, navigation, onBack }) {
  const { token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [analyses, setAnalyses] = useState([]);

  useFocusEffect(useCallback(() => {
    let cancelled = false;
    setLoading(true);
    getStudentHistory(token, student.id)
      .then((data) => { if (!cancelled) setAnalyses(data.analyses); })
      .catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [token, student.id]));

  return (
    <View>
      <TouchableOpacity style={h.backLink} onPress={onBack}>
        <BackChevronIcon size={13} color={colors.muted} />
        <Text style={h.backLinkText}>Students</Text>
      </TouchableOpacity>
      <Text style={h.studentName}>{student.name}</Text>

      {loading && <ActivityIndicator color={colors.primary} style={{ marginTop: 20 }} />}

      {!loading && analyses.length === 0 && (
        <Text style={h.emptyText}>No analyses saved yet.</Text>
      )}

      {!loading && analyses.map((item) => {
        const score = Math.round(item.similarity ?? 0);
        return (
          <TouchableOpacity
            key={item.id}
            style={h.card}
            activeOpacity={0.8}
            onPress={() => navigation.navigate('Results', {
              savedResult: item.result,
              analysisId: item.id,
              shotType: item.shot_type,
              canAddNotes: true,
            })}
          >
            <View style={h.cardHeader}>
              <View style={h.shotBadge}>
                <TennisBallIcon size={16} color={colors.primary} />
                <Text style={h.shotLabel}>{item.shot_type.charAt(0).toUpperCase() + item.shot_type.slice(1)}</Text>
              </View>
              <Text style={h.date}>{formatDate(item.created_at)}</Text>
            </View>
            <Text style={[h.score, { color: scoreColor(score) }]}>{score}/100</Text>
            <Text style={h.proId}>{formatProId(item.pro_id, item.result?.matches?.[0]?.player_name)}</Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}
const h = StyleSheet.create({
  backLink: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 14 },
  backLinkText: { color: colors.muted, fontSize: 13, fontFamily: fonts.semibold },
  studentName: { color: colors.ink, fontSize: 22, fontFamily: fonts.serifItalic, marginBottom: 16 },
  emptyText: { color: colors.muted, fontSize: 13.5, fontFamily: fonts.regular, textAlign: 'center', paddingVertical: 30 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, padding: 14, marginBottom: 10 },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  shotBadge: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  shotLabel: { color: colors.ink, fontSize: 13.5, fontFamily: fonts.bold },
  date: { color: colors.muted, fontSize: 11.5, fontFamily: fonts.regular },
  score: { fontSize: 18, fontFamily: fonts.extrabold },
  proId: { color: colors.muted, fontSize: 11.5, marginTop: 2, fontFamily: fonts.regular },
});

// ── Main screen ────────────────────────────────────────────────────────────
export default function CoachScreen({ navigation }) {
  const { token } = useAuth();
  const [inviteCode, setInviteCode] = useState(null);
  const [generating, setGenerating] = useState(false);

  const [linkCodeInput, setLinkCodeInput] = useState('');
  const [linking, setLinking] = useState(false);

  const [students, setStudents] = useState([]);
  const [loadingStudents, setLoadingStudents] = useState(true);
  const [selectedStudent, setSelectedStudent] = useState(null);
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  const loadStudents = useCallback(() => {
    setLoadingStudents(true);
    listStudents(token)
      .then((data) => { if (mountedRef.current) setStudents(data.students); })
      .catch(() => {})
      .finally(() => { if (mountedRef.current) setLoadingStudents(false); });
  }, [token]);

  useFocusEffect(useCallback(() => { loadStudents(); }, [loadStudents]));

  const generateCode = async () => {
    setGenerating(true);
    try {
      const data = await getInviteCode(token);
      setInviteCode(data.code);
    } catch (err) {
      Alert.alert('Could not generate code', err.message || 'Something went wrong');
    } finally {
      setGenerating(false);
    }
  };

  const submitLink = async () => {
    if (!linkCodeInput.trim()) return;
    setLinking(true);
    try {
      const data = await linkCoach(token, linkCodeInput.trim().toUpperCase());
      setLinkCodeInput('');
      playAchievementSound();
      Alert.alert('Linked!', `You're now coaching ${data.student.name}.`);
      loadStudents();
    } catch (err) {
      Alert.alert('Could not link', err.message || 'Invalid or already-used code');
    } finally {
      setLinking(false);
    }
  };

  if (selectedStudent) {
    return (
      <SafeAreaView style={s.safe}>
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <StudentHistory
            student={selectedStudent}
            navigation={navigation}
            onBack={() => setSelectedStudent(null)}
          />
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <Text style={s.h1}>Coach mode</Text>
        <Text style={s.sub}>Coach someone else's account, or let a coach follow yours.</Text>

        <Section title="Your invite code">
          <Text style={s.helpText}>Share this with your coach so they can follow your analyses.</Text>
          {inviteCode ? (
            <Text style={s.codeDisplay}>{inviteCode}</Text>
          ) : null}
          <TouchableOpacity style={s.actionBtn} onPress={() => { playTapSound(); generateCode(); }} disabled={generating}>
            <Text style={s.actionBtnText}>
              {generating ? 'Generating...' : inviteCode ? 'Generate new code' : 'Generate invite code'}
            </Text>
          </TouchableOpacity>
        </Section>

        <Section title="Follow a student">
          <Text style={s.helpText}>Enter a student's invite code to start coaching them.</Text>
          <TextInput
            style={s.input}
            value={linkCodeInput}
            onChangeText={setLinkCodeInput}
            placeholder="Invite code"
            placeholderTextColor={colors.muted}
            autoCapitalize="characters"
          />
          <TouchableOpacity
            style={[s.actionBtn, !linkCodeInput.trim() && s.actionBtnDisabled]}
            onPress={() => { playTapSound(); submitLink(); }}
            disabled={linking || !linkCodeInput.trim()}
          >
            <Text style={s.actionBtnText}>{linking ? 'Linking...' : 'Link'}</Text>
          </TouchableOpacity>
        </Section>

        <Section title="Students you coach">
          {loadingStudents && <ActivityIndicator color={colors.primary} />}
          {!loadingStudents && students.length === 0 && (
            <Text style={s.helpText}>No students linked yet.</Text>
          )}
          {!loadingStudents && students.map((student) => (
            <TouchableOpacity
              key={student.id}
              style={s.studentRow}
              onPress={() => setSelectedStudent(student)}
            >
              <Text style={s.studentRowText}>{student.name}</Text>
              <Text style={s.chevron}>›</Text>
            </TouchableOpacity>
          ))}
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xl, paddingTop: 24, paddingBottom: 60 },

  h1: { color: colors.ink, fontSize: 28, fontFamily: fonts.serifItalic, marginBottom: 6 },
  sub: { color: colors.muted, fontSize: 13.5, lineHeight: 19, marginBottom: 24, fontFamily: fonts.regular },

  helpText: { color: colors.muted, fontSize: 12.5, lineHeight: 18, marginBottom: 12, fontFamily: fonts.regular },
  codeDisplay: {
    color: colors.primary, fontSize: 24, fontFamily: fonts.extrabold, letterSpacing: 2,
    textAlign: 'center', backgroundColor: colors.bg, borderRadius: radius.sm,
    paddingVertical: 14, marginBottom: 12,
  },
  input: {
    backgroundColor: colors.bg, borderRadius: radius.sm, paddingHorizontal: 14, paddingVertical: 12,
    color: colors.ink, fontSize: 14, fontFamily: fonts.regular, marginBottom: 10, letterSpacing: 1,
  },
  actionBtn: { backgroundColor: colors.primary, borderRadius: radius.pill, paddingVertical: 12, alignItems: 'center' },
  actionBtnDisabled: { opacity: 0.4 },
  actionBtnText: { color: colors.white, fontSize: 13.5, fontFamily: fonts.bold },

  studentRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  studentRowText: { color: colors.ink, fontSize: 14.5, fontFamily: fonts.semibold },
  chevron: { color: colors.divider, fontSize: 20 },
});
