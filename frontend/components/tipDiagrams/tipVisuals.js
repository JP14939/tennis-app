// Manual tip-id -> diagram mapping. Deliberately hand-authored rather than
// derived from each tip's axis/direction fields in
// data/08_coaching_ai/coaching_tips_database.json -- those encode a sign
// convention (user_value vs pro_value on a raw pose axis) that doesn't
// reliably translate into "which way should the arrow point" without
// re-deriving the pose coordinate system's up/down and mirroring
// convention. Reading each tip's own `description` text and picking the
// visually-obvious direction is simpler and less error-prone for what's a
// supplementary illustration, not a data-accurate chart.
//
// type: 'point' (highlight a single landmark + directional arrow),
//       'rotate' (small curved arrow at a single landmark -- rotation/snap
//       issues, e.g. pronation, insufficient shoulder turn),
//       'separation' (the two rotation_range tips -- arc between the
//       shoulder line and hip line), or
//       'extension' (the two racket_distance tips -- dashed line from
//       torso center to the racket tip).
// direction (type 'point' only): 'up' | 'down' | 'in' | 'out'.
export const TIP_VISUALS = {
  // forehand
  fh_elbow_flare:         { type: 'point', landmark: 'right_elbow', direction: 'out' },
  fh_shoulder_drop:       { type: 'point', landmark: 'right_shoulder', direction: 'down' },
  fh_wrist_collapse:      { type: 'point', landmark: 'right_wrist', direction: 'down' },
  fh_hip_rotation:        { type: 'rotate', landmark: 'left_hip' },
  fh_short_backswing:     { type: 'point', landmark: 'right_wrist', direction: 'in' },
  fh_big_loop:            { type: 'point', landmark: 'right_wrist', direction: 'up' },
  fh_followthrough_short: { type: 'point', landmark: 'right_wrist', direction: 'in' },
  fh_head_drop:           { type: 'point', landmark: 'nose', direction: 'down' },
  fh_rotation_range:      { type: 'separation' },
  fh_racket_distance:     { type: 'extension' },

  // backhand
  bh_shoulder_turn:       { type: 'rotate', landmark: 'left_shoulder' },
  bh_wrist_collapse:      { type: 'point', landmark: 'left_wrist', direction: 'down' },
  bh_elbow_high:          { type: 'point', landmark: 'right_elbow', direction: 'up' },
  bh_lead_hand:           { type: 'point', landmark: 'left_wrist', direction: 'out' },
  bh_late_prep:           { type: 'point', landmark: 'left_wrist', direction: 'in' },
  bh_weight_transfer:     { type: 'point', landmark: 'left_hip', direction: 'out' },
  bh_short_followthrough: { type: 'point', landmark: 'left_wrist', direction: 'in' },
  bh_head_movement:       { type: 'point', landmark: 'nose', direction: 'out' },
  bh_rotation_range:      { type: 'separation' },
  bh_racket_distance:     { type: 'extension' },

  // serve
  sv_toss_low:            { type: 'point', landmark: 'right_wrist', direction: 'down' },
  sv_toss_position:       { type: 'point', landmark: 'right_wrist', direction: 'out' },
  sv_elbow_drop:          { type: 'point', landmark: 'right_elbow', direction: 'down' },
  sv_low_contact:         { type: 'point', landmark: 'right_wrist', direction: 'down' },
  sv_pronation:           { type: 'rotate', landmark: 'right_wrist' },
  sv_head_drop:           { type: 'point', landmark: 'nose', direction: 'down' },
  sv_trophy_position:     { type: 'point', landmark: 'right_elbow', direction: 'up' },
  sv_followthrough_across: { type: 'point', landmark: 'right_wrist', direction: 'out' },
  sv_rotation_range:      { type: 'separation' },
  sv_racket_distance:     { type: 'extension' },
};
