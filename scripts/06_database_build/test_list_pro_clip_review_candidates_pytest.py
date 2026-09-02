"""Coverage for list_pro_clip_review_candidates.py's review-state helpers:
a machine audio contact fill (note ends '(audio)') keeps an entry in the
review queue; a human contact correction or a quality verdict takes it out."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import list_pro_clip_review_candidates as lc  # noqa: E402


def test_is_machine_contact_fill():
    assert lc._is_machine_contact_fill('contact_time_corrected', '1.0 -> 1.31 (audio)')
    assert lc._is_machine_contact_fill('contact_time_corrected', '1.0 -> 1.31 (audio)\n')
    assert not lc._is_machine_contact_fill('contact_time_corrected', '1.0 -> 1.31')  # human
    assert not lc._is_machine_contact_fill('label_confirmed', None)
    assert not lc._is_machine_contact_fill('excluded', None)


def test_still_needs_review():
    vn = {
        'a': ('contact_time_corrected', '1.0 -> 1.31 (audio)'),   # machine fill
        'b': ('contact_time_corrected', '1.0 -> 1.31'),           # human
        'c': ('label_confirmed', None),
        'd': ('excluded', None),
    }
    assert lc._still_needs_review('a', vn) is True
    assert lc._still_needs_review('z', vn) is True   # never logged
    assert lc._still_needs_review('b', vn) is False
    assert lc._still_needs_review('c', vn) is False
    assert lc._still_needs_review('d', vn) is False
