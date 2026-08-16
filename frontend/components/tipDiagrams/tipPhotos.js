// Static require map for real tip photos, keyed by the same issue_id used
// in TIP_VISUALS (./tipVisuals.js) and coaching_tips_database.json.
// Metro can't require() an asset path built from a variable, so each photo
// needs one explicit line here once its file exists in
// frontend/assets/tipPhotos/ -- see that folder's README for the naming
// convention and how to add an entry. Any issue_id with no entry here
// falls back to the SVG diagram in TipDiagram.js automatically.
//
// Filled in 2026-08-10 from Jack's 30-image ChatGPT-generated batch --
// 25 of the 30 matched an existing issue_id exactly (verified per-image,
// not assumed from ordering). The remaining 5 generated images described
// serve issues that don't exist in coaching_tips_database.json today
// (sv_wrist_cock, sv_racquet_drop, sv_flat_contact_point,
// sv_follow_through_finish, sv_balance_landing) -- saved under
// assets/tipPhotos/_unmatched_new_serve_tips/ rather than wired in here,
// since there's no matching tip for them to attach to yet. The 5 existing
// ids with no photo (sv_head_drop, sv_trophy_position,
// sv_followthrough_across, sv_rotation_range, sv_racket_distance) fall
// back to their SVG diagrams below.
export const TIP_PHOTOS = {
  fh_elbow_flare: require('../../assets/tipPhotos/fh_elbow_flare.png'),
  fh_shoulder_drop: require('../../assets/tipPhotos/fh_shoulder_drop.png'),
  fh_wrist_collapse: require('../../assets/tipPhotos/fh_wrist_collapse.png'),
  fh_hip_rotation: require('../../assets/tipPhotos/fh_hip_rotation.png'),
  fh_short_backswing: require('../../assets/tipPhotos/fh_short_backswing.png'),
  fh_big_loop: require('../../assets/tipPhotos/fh_big_loop.png'),
  fh_followthrough_short: require('../../assets/tipPhotos/fh_followthrough_short.png'),
  fh_head_drop: require('../../assets/tipPhotos/fh_head_drop.png'),
  fh_rotation_range: require('../../assets/tipPhotos/fh_rotation_range.png'),
  fh_racket_distance: require('../../assets/tipPhotos/fh_racket_distance.png'),

  bh_shoulder_turn: require('../../assets/tipPhotos/bh_shoulder_turn.png'),
  bh_wrist_collapse: require('../../assets/tipPhotos/bh_wrist_collapse.png'),
  bh_elbow_high: require('../../assets/tipPhotos/bh_elbow_high.png'),
  bh_lead_hand: require('../../assets/tipPhotos/bh_lead_hand.png'),
  bh_late_prep: require('../../assets/tipPhotos/bh_late_prep.png'),
  bh_weight_transfer: require('../../assets/tipPhotos/bh_weight_transfer.png'),
  bh_short_followthrough: require('../../assets/tipPhotos/bh_short_followthrough.png'),
  bh_head_movement: require('../../assets/tipPhotos/bh_head_movement.png'),
  bh_rotation_range: require('../../assets/tipPhotos/bh_rotation_range.png'),
  bh_racket_distance: require('../../assets/tipPhotos/bh_racket_distance.png'),

  sv_toss_low: require('../../assets/tipPhotos/sv_toss_low.png'),
  sv_toss_position: require('../../assets/tipPhotos/sv_toss_position.png'),
  sv_elbow_drop: require('../../assets/tipPhotos/sv_elbow_drop.png'),
  sv_low_contact: require('../../assets/tipPhotos/sv_low_contact.png'),
  sv_pronation: require('../../assets/tipPhotos/sv_pronation.png'),
};
