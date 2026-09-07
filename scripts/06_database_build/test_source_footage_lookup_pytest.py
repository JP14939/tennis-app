"""
Regression coverage for source_footage_lookup.py's swing_id -> source video
bucket math -- confirmed directly against every real swings_validated.json
file on disk (forehand: 1-399/1001-1133/2001-2114, backhand:
1-441/1001-1080/2001-2100/3001-3052, serve: 1-230/1001-1107) before writing
this, so these boundary values are real, not guessed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import source_footage_lookup as sfl  # noqa: E402


def test_first_job_range_maps_to_compilation_1():
    assert sfl.source_video_for('forehand', 1).endswith('forehand_compilation_1.mp4')
    assert sfl.source_video_for('forehand', 399).endswith('forehand_compilation_1.mp4')


def test_second_job_range_maps_to_compilation_2():
    assert sfl.source_video_for('forehand', 1001).endswith('forehand_compilation_2.mp4')
    assert sfl.source_video_for('forehand', 1133).endswith('forehand_compilation_2.mp4')


def test_third_job_range_maps_to_compilation_3():
    assert sfl.source_video_for('forehand', 2001).endswith('forehand_compilation_3.mp4')
    assert sfl.source_video_for('forehand', 2114).endswith('forehand_compilation_3.mp4')


def test_backhand_has_four_job_ranges():
    assert sfl.source_video_for('backhand', 1).endswith('backhand_compilation_1.mp4')
    assert sfl.source_video_for('backhand', 1080).endswith('backhand_compilation_2.mp4')
    assert sfl.source_video_for('backhand', 2100).endswith('backhand_compilation_3.mp4')
    assert sfl.source_video_for('backhand', 3052).endswith('backhand_compilation_4.mp4')


def test_serve_has_two_job_ranges():
    assert sfl.source_video_for('serve', 230).endswith('serve_compilation_1.mp4')
    assert sfl.source_video_for('serve', 1107).endswith('serve_compilation_2.mp4')


def test_out_of_range_swing_id_returns_none_instead_of_a_wrong_guess():
    assert sfl.source_video_for('forehand', 3001) is None


def test_unknown_shot_type_returns_none():
    assert sfl.source_video_for('volley', 1) is None


def test_paths_are_absolute_and_use_the_real_data_dir():
    path = sfl.source_video_for('serve', 1)
    assert os.path.isabs(path)
    assert sfl.SOURCE_VIDEOS_DIR in path


def test_poses_path_first_job_range_maps_to_poses_1():
    assert sfl.poses_path_for('forehand', 1).endswith('forehand_poses.json')
    assert sfl.poses_path_for('forehand', 399).endswith('forehand_poses.json')


def test_poses_path_second_job_range_maps_to_poses_2():
    assert sfl.poses_path_for('forehand', 1001).endswith('forehand_poses_2.json')


def test_poses_path_third_job_range_maps_to_poses_3():
    assert sfl.poses_path_for('forehand', 2001).endswith('forehand_poses_3.json')


def test_poses_path_backhand_has_four_job_ranges():
    assert sfl.poses_path_for('backhand', 1).endswith('backhand_poses.json')
    assert sfl.poses_path_for('backhand', 1080).endswith('backhand_poses_2.json')
    assert sfl.poses_path_for('backhand', 2100).endswith('backhand_poses_3.json')
    assert sfl.poses_path_for('backhand', 3052).endswith('backhand_poses_4.json')


def test_poses_path_out_of_range_swing_id_returns_none():
    assert sfl.poses_path_for('forehand', 3001) is None


def test_poses_path_unknown_shot_type_returns_none():
    assert sfl.poses_path_for('volley', 1) is None


def test_poses_path_is_absolute_and_uses_real_data_dir():
    path = sfl.poses_path_for('serve', 1)
    assert os.path.isabs(path)
    assert sfl.POSES_DIR in path
