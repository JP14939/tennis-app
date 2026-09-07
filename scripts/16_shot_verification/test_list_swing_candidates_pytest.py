"""Regression coverage for merge_duplicate_swings(): find_swing_peaks()
(shared with detect_rallies.py etc.) sometimes splits one real swing into
two candidates when its velocity curve dips without fully bottoming out
mid-swing and re-crosses the threshold just past MIN_SWING_GAP_SEC --
confirmed on real data (job 7 rally 1's two peaks, 1.87s apart, were the
same swing per Jack's own review). Jack described the symptom directly:
"I get the video before the swing and I get the video after the same
swing, so I'm recording the same contact frame."

merge_duplicate_swings() merges primarily on peak_frame proximity (the
reliable signal, directly tied to the MIN_SWING_GAP_SEC floor) with
contact_frame_guess as a secondary trigger -- testing against the real
rally 1 case showed contact_frame_guess ALONE isn't reliable here, since
the spurious first peak's guess is itself low-confidence/noisy."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from list_swing_candidates import merge_duplicate_swings, MERGE_WINDOW_SEC, _partition_job_files  # noqa: E402

FPS = 30.0


def _swing(peak_frame, contact_frame_guess=None, contact_confidence=0.5):
    return {
        'peak_frame': peak_frame,
        'contact_frame_guess': contact_frame_guess,
        'contact_confidence': contact_confidence,
    }


def test_close_peak_frames_merge_keeping_higher_confidence():
    # ~1.87s apart at 30fps -- the real rally 1 case that prompted this fix.
    # contact_frame_guess is deliberately just as far apart as peak_frame,
    # matching the real data where the automated guess wasn't reliable here.
    low = _swing(peak_frame=7, contact_frame_guess=7, contact_confidence=0.3)
    high = _swing(peak_frame=63, contact_frame_guess=63, contact_confidence=0.6)
    merged = merge_duplicate_swings([low, high], FPS)
    assert merged == [high]


def test_far_apart_swings_both_survive():
    gap_frames = int((MERGE_WINDOW_SEC + 1.0) * FPS)
    first = _swing(peak_frame=10, contact_frame_guess=15, contact_confidence=0.5)
    second = _swing(peak_frame=10 + gap_frames, contact_frame_guess=15 + gap_frames, contact_confidence=0.5)
    merged = merge_duplicate_swings([first, second], FPS)
    assert merged == [first, second]


def test_missing_contact_frame_guess_still_merges_on_peak_frame():
    # No contact_frame_guess at all (no racket/ball evidence) -- must still
    # merge on peak_frame proximity instead of crashing on None arithmetic.
    close_frames = int(0.5 * FPS)
    a = _swing(peak_frame=100, contact_frame_guess=None, contact_confidence=0.2)
    b = _swing(peak_frame=100 + close_frames, contact_frame_guess=None, contact_confidence=0.6)
    merged = merge_duplicate_swings([a, b], FPS)
    assert merged == [b]


def test_contact_frame_guess_alone_can_trigger_a_merge():
    # peak_frame gap is large, but contact evidence agrees they're the same
    # contact -- the secondary trigger should still catch this.
    far_peak_gap = int((MERGE_WINDOW_SEC + 2.0) * FPS)
    a = _swing(peak_frame=0, contact_frame_guess=50, contact_confidence=0.4)
    b = _swing(peak_frame=far_peak_gap, contact_frame_guess=55, contact_confidence=0.7)
    merged = merge_duplicate_swings([a, b], FPS)
    assert merged == [b]


def test_tie_confidence_keeps_earlier_swing():
    first = _swing(peak_frame=10, contact_frame_guess=15, contact_confidence=0.5)
    second = _swing(peak_frame=25, contact_frame_guess=25, contact_confidence=0.5)
    merged = merge_duplicate_swings([first, second], FPS)
    assert merged == [first]


def test_unordered_input_is_sorted_before_merging():
    early = _swing(peak_frame=10, contact_frame_guess=15, contact_confidence=0.4)
    late = _swing(peak_frame=1000, contact_frame_guess=1005, contact_confidence=0.9)
    merged = merge_duplicate_swings([late, early], FPS)
    assert merged == [early, late]


# _partition_job_files(): a job's raw source video can be hardlinked in
# under the 'full_video' prefix to make it browsable in Swing Review for
# context, without ever going through pose extraction/swing detection --
# job 9 hung for 10+ minutes and timed out when a 2.18GB full match video
# was instead placed as 'rally_007.mp4', where it got treated identically
# to a real (short) rally clip. These tests cover the directory split that
# keeps the two kinds of file from ever being confused with each other.

def test_partitions_rally_clips_and_full_video_separately(tmp_path):
    (tmp_path / 'rally_001.mp4').write_bytes(b'')
    (tmp_path / 'rally_002.mp4').write_bytes(b'')
    (tmp_path / 'full_video.mp4').write_bytes(b'')

    clips, full_videos = _partition_job_files(str(tmp_path))
    assert clips == ['rally_001.mp4', 'rally_002.mp4']
    assert full_videos == ['full_video.mp4']


def test_no_full_video_file_returns_empty_list(tmp_path):
    (tmp_path / 'rally_001.mp4').write_bytes(b'')

    clips, full_videos = _partition_job_files(str(tmp_path))
    assert clips == ['rally_001.mp4']
    assert full_videos == []


def test_unrelated_files_are_excluded_from_both(tmp_path):
    (tmp_path / 'rally_001.mp4').write_bytes(b'')
    (tmp_path / 'full_video.mp4').write_bytes(b'')
    (tmp_path / '.DS_Store').write_bytes(b'')
    (tmp_path / 'notes.json').write_bytes(b'')

    clips, full_videos = _partition_job_files(str(tmp_path))
    assert clips == ['rally_001.mp4']
    assert full_videos == ['full_video.mp4']
