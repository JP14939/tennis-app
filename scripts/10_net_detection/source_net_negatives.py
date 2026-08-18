"""
Source a categorized negative ("no tennis net") image set for retraining the
net-keypoint model, which was proven this session to false-positive on 100%
of tested non-tennis images because it has never seen a real negative
example (see net_presence_verifier.py / prepare_net_pose_dataset_v4.py for
the rest of this pipeline). Same Openverse CC-licensed API pattern as
source_net_images.py -- not scraping, license metadata kept per image.

Two categories:
  - generic: broad non-tennis scenes (street, park, building, interior).
  - hard: net-LIKE structures (volleyball/badminton nets, soccer goals,
    chain-link fences, clotheslines, blinds) -- these are what actually
    fooled both the Hough heuristic and the trained model in this session's
    diagnostic (a park bench got mistaken for a net at 0.85 confidence), so
    they're deliberately targeted rather than left to chance.

Deliberately does NOT touch data/10_net_detection/streettest_negatives --
those 12 images are the held-out evaluation set from this session's
diagnostic and must never leak into training data.

Usage:
  python source_net_negatives.py
"""
import json
import os
import time
import urllib.parse
import urllib.request

OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_negatives_v1\raw'
META_PATH = r'C:\Users\jackp\tennis_app\data\10_net_detection\net_negatives_v1\source_metadata.json'

QUERIES = {
    'generic': [
        'suburban street sidewalk', 'city park pathway',
        'residential building facade', 'living room interior',
        'office interior', 'empty parking lot',
    ],
    'hard': [
        'empty volleyball net beach', 'badminton net court',
        'soccer goal net', 'chain link fence',
        'clothesline laundry', 'window blinds',
    ],
}
N_PER_QUERY = 6

HEADERS = {'User-Agent': 'TennisAppResearch/1.0 (educational project; contact via github)'}
VALID_EXT = ('.jpg', '.jpeg', '.png', '.webp')


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))


def openverse_images(query, n):
    results = []
    page = 1
    while len(results) < n:
        url = f'https://api.openverse.org/v1/images/?q={urllib.parse.quote(query)}&page_size=20&page={page}'
        data = fetch_json(url)
        items = data.get('results', [])
        if not items:
            break
        for item in items:
            if item.get('url', '').lower().endswith(VALID_EXT) and not item.get('mature'):
                results.append({
                    'url': item['url'], 'source': 'openverse', 'query': query,
                    'creator': item.get('creator'), 'license': item.get('license'),
                    'foreign_landing_url': item.get('foreign_landing_url'),
                })
        page += 1
        if page > 3:
            break
    return results[:n]


def download(url, out_path):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        with open(out_path, 'wb') as f:
            f.write(resp.read())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    all_candidates = []
    for category, queries in QUERIES.items():
        for q in queries:
            print(f'Querying Openverse ({category}): "{q}"...')
            try:
                for item in openverse_images(q, n=N_PER_QUERY):
                    item['category'] = category
                    all_candidates.append(item)
            except Exception as e:
                print(f'  failed: {e}')
            time.sleep(0.5)

    seen_urls = set()
    unique = []
    for c in all_candidates:
        if c['url'] not in seen_urls:
            seen_urls.add(c['url'])
            unique.append(c)
    print(f'\n{len(unique)} unique candidate images found. Downloading...')

    metadata = []
    for c in unique:
        ext = os.path.splitext(c['url'])[1].split('?')[0].lower()
        if ext not in VALID_EXT:
            ext = '.jpg'
        fname = f'{c["category"]}_{len([m for m in metadata if m["category"] == c["category"]]):04d}{ext}'
        out_path = os.path.join(OUT_DIR, fname)
        try:
            download(c['url'], out_path)
            c['local_file'] = fname
            metadata.append(c)
        except Exception as e:
            print(f'  skip {c["url"]}: {e}')

    with open(META_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)

    by_cat = {}
    for m in metadata:
        by_cat[m['category']] = by_cat.get(m['category'], 0) + 1
    print(f'\nDownloaded {len(metadata)} images to {OUT_DIR}')
    print(f'By category: {by_cat}')
    print(f'Metadata (with license/attribution) saved to {META_PATH}')


if __name__ == '__main__':
    main()
