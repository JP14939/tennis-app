// Shared geometry for the coaching-tip diagrams (TipDiagram.js). One
// reusable front-facing player silhouette, viewBox 200x300 -- landmark
// names match the keys used in data/08_coaching_ai/coaching_tips_database.json
// and scripts/09_coaching_ai/tip_selector.py, so a tip's `landmark` field
// maps straight to a point here.
export const VIEWBOX = '0 0 200 300';

export const TORSO_CENTER = { x: 100, y: 120 };

export const LANDMARK_POINTS = {
  nose:           { x: 100, y: 30 },
  left_shoulder:  { x: 65,  y: 65 },
  right_shoulder: { x: 135, y: 65 },
  left_elbow:     { x: 35,  y: 105 },
  right_elbow:    { x: 165, y: 100 },
  left_wrist:     { x: 20,  y: 150 },
  right_wrist:    { x: 180, y: 145 },
  left_hip:       { x: 80,  y: 175 },
  right_hip:      { x: 120, y: 175 },
};

export const SHOULDER_LINE = { from: LANDMARK_POINTS.left_shoulder, to: LANDMARK_POINTS.right_shoulder };
export const HIP_LINE = { from: LANDMARK_POINTS.left_hip, to: LANDMARK_POINTS.right_hip };

// Racket head position -- an extension of the right wrist, not a tracked
// pose landmark, used for the two "racket_distance" tips (fh/bh/sv all
// share the same issue id shape for this one).
export const RACKET_TIP = { x: 200, y: 118 };
