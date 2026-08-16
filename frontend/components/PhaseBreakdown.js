import { View, Text, StyleSheet } from 'react-native';
import { colors, fonts, radius } from '../theme';

export const PHASE_LABELS = {
  backswing: 'Backswing',
  contact: 'Contact',
  follow_through: 'Follow-through',
  body_rotation: 'Body Rotation',
};
export const PHASE_ORDER = ['backswing', 'contact', 'follow_through', 'body_rotation'];

export function phaseColor(score) {
  if (score == null) return colors.muted;
  if (score >= 18.75) return colors.primary;  // 75% of 25
  if (score >= 13.75) return colors.gold;      // 55% of 25
  return colors.coral;
}

// NotesBlock is optional -- ResultsScreen (tied to a saved analysisId) passes
// it so coaches can leave per-phase notes; VersusResultsScreen (no
// analysisId for an ephemeral 1v1 comparison) omits it entirely.
export default function PhaseBreakdown({ phases, analysisId, notes, canAddNotes, onAddNote, NotesBlock }) {
  if (!phases) return null;
  return (
    <>
      <Text style={s.sectionTitle}>Phase breakdown</Text>
      {PHASE_ORDER.map((key) => {
        const phase = phases[key];
        if (!phase) return null;
        const pScore = phase.score;
        return (
          <View key={key} style={s.phaseCard}>
            <View style={s.phaseHeader}>
              <Text style={s.phaseName}>{PHASE_LABELS[key]}</Text>
              <Text style={[s.phaseScore, { color: phaseColor(pScore) }]}>
                {pScore != null ? `${pScore}/25` : '—'}
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
            {key === 'body_rotation' && phase.has_racket_data === false && (
              <Text style={s.phaseNote}>Racket not clearly visible — scored on body rotation only.</Text>
            )}
            {phase.tips?.[0] && <Text style={s.phaseTip}>{phase.tips[0]}</Text>}
            {NotesBlock && analysisId && (
              <NotesBlock notes={notes} phaseKey={key} canAddNotes={!!canAddNotes} onAdd={onAddNote} />
            )}
          </View>
        );
      })}
    </>
  );
}

const s = StyleSheet.create({
  sectionTitle: { color: colors.ink, fontSize: 19, fontFamily: fonts.serif, marginBottom: 12 },
  phaseCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.md, padding: 14, marginBottom: 9,
  },
  phaseHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  phaseName: { color: colors.ink, fontSize: 14, fontFamily: fonts.bold },
  phaseScore: { fontSize: 14, fontFamily: fonts.bold },
  phaseTrack: { height: 5, backgroundColor: colors.border, borderRadius: 3, overflow: 'hidden' },
  phaseFill: { height: 5, borderRadius: 3 },
  phaseTip: { color: colors.mutedDark, fontSize: 12.5, lineHeight: 18, marginTop: 9, fontFamily: fonts.regular },
  phaseNote: { color: colors.muted, fontSize: 12, marginTop: 8, fontStyle: 'italic', fontFamily: fonts.regular },
});
