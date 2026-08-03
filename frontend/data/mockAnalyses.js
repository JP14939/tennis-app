// Shared mock analysis history — used by HomeScreen (recent activity preview)
// and HistoryScreen (full list). Will be replaced with real /api/history data
// once the backend persists analyses.

export const SHOT_ICONS = { forehand: '🎾', backhand: '🏓', serve: '🚀' };

export const MOCK_ANALYSES = [
  {
    id: '1',
    shot_type: 'forehand',
    date: 'Today, 14:32',
    pro_id: 'forehand_0142',
    similarity: 74,
    tip: 'Your elbow is too far from your body at contact — tuck it closer for more control.',
    angle_label: 'Diagonal',
  },
  {
    id: '2',
    shot_type: 'serve',
    date: 'Yesterday, 09:15',
    pro_id: 'serve_0031',
    similarity: 61,
    tip: 'Your contact point is too low — toss the ball higher and reach up more.',
    angle_label: 'Semi-side',
  },
  {
    id: '3',
    shot_type: 'backhand',
    date: '28 Jul, 17:08',
    pro_id: 'backhand_0088',
    similarity: 82,
    tip: 'Great technique! Your form closely matches the pro.',
    angle_label: 'Diagonal',
  },
];
