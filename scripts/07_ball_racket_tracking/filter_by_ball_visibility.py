"""
Rebuild pro_database.json, excluding entries whose ball wasn't visible near
the estimated contact point (per audit_ball_visibility.py's report) — those
clips can't be reliably calibrated against a user's manually-marked contact
frame. The pre-filter database is backed up separately; the underlying clip
files and pose data are untouched.
"""
import json

DB_PATH = r'C:\Users\jackp\tennis_app\data\06_pro_database\pro_database.json'
AUDIT_PATH = r'C:\Users\jackp\tennis_app\data\07_audits\ball_visibility_audit.json'

with open(DB_PATH) as f:
    db = json.load(f)
with open(AUDIT_PATH) as f:
    audit = json.load(f)

visible_ids = {r['id'] for r in audit if r['ball_visible']}

kept = [e for e in db['entries'] if e['id'] in visible_ids]
dropped = [e for e in db['entries'] if e['id'] not in visible_ids]

db['entries'] = kept
db['total'] = len(kept)
db['shots'] = {'forehand': 0, 'backhand': 0, 'serve': 0}
for e in kept:
    db['shots'][e['shot_type']] += 1

with open(DB_PATH, 'w') as f:
    json.dump(db, f)

print(f'Kept {len(kept)} entries, dropped {len(dropped)}')
print(f"  Forehand: {db['shots']['forehand']}")
print(f"  Backhand: {db['shots']['backhand']}")
print(f"  Serve:    {db['shots']['serve']}")
