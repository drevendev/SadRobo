"""Archive the public Telegram mirror, without API keys or third-party packages."""
import concurrent.futures
import hashlib
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache'
USER_AGENT = 'SadRoboArchive/1.0 (+https://github.com/drevendev/SadRobo)'


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, cls=None, tag=None):
        for child in self.children:
            if isinstance(child, Node):
                if (not cls or cls in child.attrs.get('class', '').split()) and (not tag or tag == child.tag):
                    yield child
                yield from child.find(cls, tag)

    def text(self):
        if self.tag == 'br':
            return '\n'
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children)


class DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in {'br', 'img', 'input', 'meta', 'link', 'hr', 'source', 'wbr', 'area', 'embed', 'param', 'col', 'base'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def download(url, destination):
    if destination.exists():
        return destination.read_bytes()
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def parse_messages(html):
    dom = DOM(html)
    messages = []
    for node in dom.root.find('tgme_widget_message'):
        post = node.attrs.get('data-post')
        if not post:
            continue
        text_node = next(node.find('tgme_widget_message_text'), None)
        text = text_node.text().strip() if text_node else ''
        photos = []
        for photo in node.find('tgme_widget_message_photo_wrap'):
            match = re.search(r"background-image:url\(['\"]?(.*?)['\"]?\)", photo.attrs.get('style', ''))
            if match:
                photos.append(match[1])
        stamp = next(node.find(tag='time'), None)
        title = text.split('\n')[0] if text else ''
        messages.append({'id': int(post.split('/')[-1]), 'url': f'https://t.me/{post}',
                         'date': stamp.attrs.get('datetime') if stamp else None,
                         'title': title, 'text': text, 'photos': photos})
    return messages


def fingerprint(text):
    # Only exact normalized text is merged. Similar stories/chapters remain separate.
    normalized = re.sub(r'\s+', ' ', text.casefold().replace('ё', 'е')).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def main():
    CACHE.mkdir(exist_ok=True)
    messages = {}
    before = None
    visited = set()
    while True:
        url = 'https://t.me/s/sadrobo' + (f'?before={before}' if before else '')
        html = download(url, CACHE / f'telegram-{before or "latest"}.html').decode()
        page = parse_messages(html)
        if not page:
            raise RuntimeError(f'No messages at {url}; refusing a partial successful import')
        for message in page:
            messages[message['id']] = message
        first = min(m['id'] for m in page)
        print(f'Page {before or "latest"}: {len(page)} messages, earliest {first}', flush=True)
        prev = re.search(r'<link rel="prev" href="/s/sadrobo\?before=(\d+)"', html)
        if not prev:
            break
        before = int(prev[1])
        if before in visited or before > first:
            raise RuntimeError('Pagination did not advance')
        visited.add(before)
        time.sleep(.4)

    merged, by_hash = [], {}
    jobs = []
    for message in sorted(messages.values(), key=lambda m: m['id']):
        key = fingerprint(message['text']) if message['text'] else f'photo-{message["id"]}'
        if key in by_hash:
            canonical = by_hash[key]
            canonical['duplicates'].append(message['url'])
        else:
            canonical = {**message, 'fingerprint': key, 'duplicates': [], 'images': []}
            by_hash[key] = canonical
            merged.append(canonical)
        for index, photo in enumerate(message['photos']):
            extension = '.jpg'  # Telegram public preview serves JPEGs.
            relative = f'images/tg-{message["id"]:03d}-{index + 1}{extension}'
            jobs.append((photo, ROOT / 'public' / relative, canonical, relative))

    def fetch_photo(job):
        url, destination, message, relative = job
        data = download(url, destination)
        if not data.startswith(b'\xff\xd8'):
            raise RuntimeError(f'Expected JPEG at {url}')
        return message, relative, hashlib.sha256(data).hexdigest()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for message, relative, digest in pool.map(fetch_photo, jobs):
            if not any(image['sha256'] == digest for image in message['images']):
                message['images'].append({'path': relative, 'sha256': digest})

    output = {'source': 'https://t.me/sadrobo', 'fetchedAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'paginationComplete': True, 'messageCount': len(messages), 'posts': merged}
    (ROOT / 'content' / 'telegram.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Saved {len(merged)} unique posts, {len(jobs)} pictures', flush=True)


if __name__ == '__main__':
    main()
