"""One-off: compare the clean retrained history against the old pre-retrain
backup, to sanity-check the verified-shot gate actually changed anything.
Run once analyze_rallies_parallel.py 3 4 finishes.
"""
import json
import sqlite3
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / 'backend' / 'data' / 'app.db'
BACKUP_PATH = ROOT / 'data' / 'backups' / 'analyses_backup_1786367755834.json'
USER_ID = 13


def summarize(rows):
    n = len(rows)
    if n == 0:
        return {'count': 0}
    scores = [r['similarity'] for r in rows]
    great = sum(1 for s in scores if s >= 75)
    by_type = Counter(r['shot_type'] for r in rows)
    return {
        'count': n,
        'avg_score': round(sum(scores) / n, 1),
        'great_swings (>=75)': great,
        'by_shot_type': dict(by_type),
    }


def main():
    old_rows = json.loads(BACKUP_PATH.read_text())
    old_rows = [r for r in old_rows if r['user_id'] == USER_ID]

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    new_rows = [dict(r) for r in conn.execute(
        'SELECT shot_type, similarity, flagged_not_shot, confirmed_real_shot '
        'FROM analyses WHERE user_id = ?', (USER_ID,)
    ).fetchall()]
    conn.close()

    print('=== OLD (pre-retrain, unverified) ===')
    print(json.dumps(summarize(old_rows), indent=2))
    print()
    print('=== NEW (post-retrain, verified-shot gate) ===')
    print(json.dumps(summarize(new_rows), indent=2))
    print()
    print(f"Reduction: {len(old_rows)} -> {len(new_rows)} "
          f"({len(old_rows) - len(new_rows)} fake candidates filtered out)")


if __name__ == '__main__':
    main()
