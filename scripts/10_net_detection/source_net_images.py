"""
Source diverse tennis court/net images from legitimate open-license sources
(Openverse aggregates CC-licensed images from Flickr/Wikimedia/etc with a
real search API; Wikimedia Commons categories directly) for net-end keypoint
labeling. Not scraping — these are proper APIs with license metadata kept
alongside each image for attribution.
"""
import json
import os
import time
import urllib.parse
import urllib.request

OUT_DIR = r'C:\Users\jackp\tennis_app\data\10_net_keypoints\raw_images'
META_PATH = r'C:\Users\jackp\tennis_app\data\10_net_keypoints\source_metadata.json'

OPENVERSE_QUERIES = [
    # Indoor/outdoor variety, still targeting framing that shows the full net + end-post
    'indoor tennis court net', 'indoor tennis club court',
    'indoor tennis academy court', 'indoor tennis hall net',
    'outdoor tennis court net', 'outdoor tennis club court',
    'outdoor public tennis court', 'tennis court net indoor facility',
]
WIKIMEDIA_CATEGORIES = []  # already queried; skip to avoid re-hitting their rate limit

HEADERS = {'User-Agent': 'TennisAppResearch/1.0 (educational project; contact via github)'}
VALID_EXT = ('.jpg', '.jpeg', '.png', '.webp')


def fetch_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode('utf-8'))


def openverse_images(query, n=40):
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
        if page > 5:
            break
    return results[:n]


def wikimedia_images(category, n=40):
    url = (f'https://commons.wikimedia.org/w/api.php?action=query&generator=categorymembers'
           f'&gcmtitle=Category:{urllib.parse.quote(category)}&gcmtype=file&gcmlimit={n}'
           f'&prop=imageinfo&iiprop=url|size&format=json')
    data = fetch_json(url)
    pages = data.get('query', {}).get('pages', {})
    results = []
    for page in pages.values():
        info = page.get('imageinfo', [{}])[0]
        img_url = info.get('url', '')
        if img_url.lower().endswith(VALID_EXT) and info.get('width', 0) >= 400:
            results.append({
                'url': img_url, 'source': 'wikimedia_commons', 'query': category,
                'creator': None, 'license': 'see Wikimedia Commons page',
                'foreign_landing_url': info.get('descriptionurl'),
            })
    return results


def download(url, out_path):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        with open(out_path, 'wb') as f:
            f.write(resp.read())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # Load prior run's metadata so we append rather than overwrite, and skip
    # URLs already downloaded
    existing_metadata = []
    if os.path.exists(META_PATH):
        with open(META_PATH) as f:
            existing_metadata = json.load(f)
    seen_urls = {m['url'] for m in existing_metadata}
    # Filenames have gaps (failed downloads skip an index), so the next free
    # index is the max used so far + 1, NOT len(existing_metadata)
    existing_indices = [int(os.path.splitext(m['local_file'])[0].split('_')[1]) for m in existing_metadata]
    start_idx = (max(existing_indices) + 1) if existing_indices else 0

    all_candidates = []
    for q in OPENVERSE_QUERIES:
        print(f'Querying Openverse: "{q}"...')
        try:
            all_candidates += openverse_images(q, n=35)
        except Exception as e:
            print(f'  failed: {e}')
        time.sleep(0.5)

    for cat in WIKIMEDIA_CATEGORIES:
        print(f'Querying Wikimedia Commons category: "{cat}"...')
        try:
            all_candidates += wikimedia_images(cat, n=50)
        except Exception as e:
            print(f'  failed: {e}')
        time.sleep(0.5)

    # dedupe by URL (against both this run's duplicates and the prior run)
    unique = []
    for c in all_candidates:
        if c['url'] not in seen_urls:
            seen_urls.add(c['url'])
            unique.append(c)
    print(f'\n{len(unique)} new unique candidate images found. Downloading...')

    metadata = list(existing_metadata)
    for i, c in enumerate(unique):
        idx = start_idx + i
        ext = os.path.splitext(c['url'])[1].split('?')[0].lower()
        if ext not in VALID_EXT:
            ext = '.jpg'
        fname = f'net_{idx:04d}{ext}'
        out_path = os.path.join(OUT_DIR, fname)
        try:
            download(c['url'], out_path)
            c['local_file'] = fname
            metadata.append(c)
            if i % 20 == 0:
                print(f'  {i}/{len(unique)} downloaded...')
        except Exception as e:
            print(f'  skip {c["url"]}: {e}')

    with open(META_PATH, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f'\nDownloaded {len(metadata) - len(existing_metadata)} new images to {OUT_DIR}')
    print(f'Total images: {len(metadata)}')
    print(f'Metadata (with license/attribution) saved to {META_PATH}')


if __name__ == '__main__':
    main()
