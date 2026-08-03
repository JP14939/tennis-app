// Mock data for the Highlight Archive (premium) feature preview. Real
// auto-detection (swing-finding + shot-type classification) isn't built yet
// — see project notes. This lets the UI/UX be built and reviewed now.

export const MOCK_DETECTED_CLIPS = [
  { id: 'd1', timestamp: '0:42', duration: '2.1s' },
  { id: 'd2', timestamp: '1:15', duration: '1.8s' },
  { id: 'd3', timestamp: '2:03', duration: '2.4s' },
  { id: 'd4', timestamp: '3:37', duration: '1.9s' },
  { id: 'd5', timestamp: '4:12', duration: '2.2s' },
  { id: 'd6', timestamp: '5:58', duration: '2.0s' },
];

export const MOCK_ARCHIVE_CLIPS = [
  { id: 'a1', shot_type: 'forehand', timestamp: '0:12', date: '27 Jul' },
  { id: 'a2', shot_type: 'serve',    timestamp: '1:04', date: '27 Jul' },
  { id: 'a3', shot_type: 'backhand', timestamp: '2:41', date: '24 Jul' },
];
