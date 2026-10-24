"""Import the author's earlier mirror linked by https://t.me/sadrobo/9."""
import concurrent.futures
import hashlib
import json
import re
import time
from urllib.parse import urljoin
from import_telegram import ROOT, CACHE, DOM, download, fingerprint


def fetch_story(item):
    path, listed_title = item
    url = 'https://proza.ru' + path
    html = download(url, CACHE / ('proza' + path.replace('/', '-') + '.html')).decode('cp1251')
    dom = DOM(html.replace('\r', '').replace('\n', ''))
    body = next(dom.root.find('text'), None)
    if not body:
        raise RuntimeError(f'Missing story body at {url}')
    title_node = next(dom.root.find(tag='h1'), None)
    title = title_node.text().strip() if title_node else listed_title
    text = body.text().strip()
    images = []
    # Only the work's illustration; author portraits, counters and adverts are excluded.
    for image in dom.root.find(tag='img'):
        src = image.attrs.get('src', '')
        if '/pics/' in src:
            image_url = urljoin(url, src)
            data = download(image_url, CACHE / PathName(src))
            digest = hashlib.sha256(data).hexdigest()
            extension = '.jpg' if data.startswith(b'\xff\xd8') else '.png' if data.startswith(b'\x89PNG') else None
            if extension is None:
                raise RuntimeError(f'Unrecognized image: {image_url}')
            relative = 'images/' + digest[:20] + extension
            (ROOT / 'public' / relative).write_bytes(data)
            images.append({'path': relative, 'sha256': digest, 'source': image_url})
    date = '-'.join(path.strip('/').split('/')[:3])
    return {'id': 'proza-' + path.strip('/').replace('/', '-'), 'url': url, 'date': date,
            'title': title, 'text': text, 'fingerprint': fingerprint(title + '\n' + text), 'images': images}


def PathName(src):
    return 'proza-image-' + hashlib.sha256(src.encode()).hexdigest()[:20]


def main():
    works = {}
    for offset in range(0, 250, 50):
        url = 'https://proza.ru/avtor/sadrobo' + (f'&s={offset}' if offset else '')
        html = download(url, CACHE / f'proza-index-{offset}.html').decode('cp1251')
        dom = DOM(html)
        found = list(dom.root.find('poemlink'))
        if not found:
            raise RuntimeError(f'Empty author index: {url}')
        works.update({a.attrs['href']: a.text() for a in found})
        print(f'Index {offset}: {len(found)} works', flush=True)
    if len(works) != 244:
        raise RuntimeError(f'Expected 244 works, got {len(works)}; inspect index before accepting')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        posts = []
        for post in pool.map(fetch_story, works.items()):
            posts.append(post)
            if len(posts) % 25 == 0:
                print(f'Fetched {len(posts)}/{len(works)}', flush=True)
    output = {'source': 'https://proza.ru/avtor/sadrobo', 'discoveredVia': 'https://t.me/sadrobo/9',
              'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'paginationComplete': True,
              'posts': sorted(posts, key=lambda p: (p['date'], p['url']))}
    (ROOT / 'content' / 'proza.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Saved {len(posts)} works and {sum(len(p["images"]) for p in posts)} illustrations', flush=True)


if __name__ == '__main__':
    main()
