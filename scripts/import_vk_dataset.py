"""Save VK post JSON and its photo files locally, without a VK API token.

Input: a JSON array exported by axiomworks/vk-posts-scraper (see docs/vk-export.md).
This imports supplied data; it does not call VK's wall API or verify wall coverage.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

try:
    from .export_vk import ExportError, ROOT, VKClient, image_extension, replace_file, verified_file
except ImportError:
    from export_vk import ExportError, ROOT, VKClient, image_extension, replace_file, verified_file


def normalize_dataset(rows):
    if not isinstance(rows, list) or not rows:
        raise ExportError('Expected a non-empty JSON array of VK posts.')
    posts, photos = {}, {}
    owners = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ExportError('Each dataset row must be an object.')
        post_id = row.get('postId') or row.get('id')
        if not isinstance(post_id, str) or not re.fullmatch(r'-?\d+_\d+', post_id):
            raise ExportError('A row has no valid postId (expected ownerId_postId).')
        owners.add(post_id.split('_')[0])
        text = row.get('text')
        if text is not None and not isinstance(text, str):
            raise ExportError('Post text must be a string or null.')
        date = row.get('publishedAt')
        if not isinstance(date, str):
            raise ExportError('A post has no publishedAt date.')
        try:
            parsed = datetime.fromisoformat(date.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            raise ExportError('Post dates must be ISO timestamps with a time zone.') from None
        post = {'id': post_id, 'url': f'https://vk.com/wall{post_id}',
                'date': parsed.astimezone(timezone.utc).isoformat(),
                'text': text or '', 'photos': [], 'is_repost': bool(row.get('isRepost'))}
        urls = row.get('photoUrls') or []
        if not isinstance(urls, list):
            raise ExportError('photoUrls must be an array.')
        for url in urls:
            if not isinstance(url, str):
                raise ExportError('A photo URL is not a string.')
            try:
                parts = urlsplit(url)
                host = (parts.hostname or '').lower()
                valid = (parts.scheme == 'https' and not parts.username and not parts.password
                         and (host == 'userapi.com' or host.endswith('.userapi.com')))
            except ValueError:
                valid = False
            if not valid:
                raise ExportError('Expected an HTTPS userapi.com photo URL; review the dataset.')
            # A dataset gives no VK photo ID or reliable dimensions. Preserve the
            # supplied URL verbatim rather than constructing a higher-resolution URL.
            key = hashlib.sha256(url.encode('utf-8')).hexdigest()
            photos[key] = {'url': url}
            if key not in post['photos']:
                post['photos'].append(key)
        if post_id in posts:
            previous = posts[post_id]
            if any(previous[k] != post[k] for k in ('text', 'date', 'is_repost')):
                raise ExportError('Conflicting copies of the same post; review the dataset.')
            previous['photos'] = list(dict.fromkeys(previous['photos'] + post['photos']))
        else:
            posts[post_id] = post
    if len(owners) != 1:
        raise ExportError('Expected posts from a single wall; export SadRobo separately.')
    ordered = sorted(posts.values(), key=lambda p: (p['date'], p['id']))
    return {p['id']: p for p in ordered}, photos


def import_dataset(rows, destination, download):
    posts, photos = normalize_dataset(rows)
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / 'dataset-export.json'
    previous = {}
    if manifest.exists():
        try:
            previous = json.loads(manifest.read_text(encoding='utf-8'))
            if previous.get('schema') != 'sadrobo-vk-dataset-1':
                raise ValueError
        except (ValueError, OSError, AttributeError):
            raise ExportError('Cannot resume from the existing dataset manifest.') from None
        if not set(previous.get('posts', {})).issubset(posts):
            raise ExportError('This dataset omits previously saved posts. Use a different --output folder.')
    for key, record in photos.items():
        old = previous.get('photos', {}).get(key, {})
        if verified_file(root, old):
            record.update(file=old['file'], sha256=old['sha256'])
    state = {'schema': 'sadrobo-vk-dataset-1', 'coverage': 'unverified',
             'download_complete': False, 'posts': posts, 'photos': photos, 'errors': []}

    def save():
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        temporary = root / 'dataset-export.json.tmp'
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        replace_file(temporary, manifest)

    save()
    for key, record in photos.items():
        if verified_file(root, record):
            continue
        try:
            data = download(record['url'])
            extension = image_extension(data)
            digest = hashlib.sha256(data).hexdigest()
            relative = f'images/{digest}{extension}'
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                temporary = target.with_suffix(extension + '.tmp')
                temporary.write_bytes(data)
                replace_file(temporary, target)
            record.update(file=relative, sha256=digest)
        except ExportError as error:
            state['errors'].append({'photo': key, 'message': str(error)})
        save()
    state['download_complete'] = not state['errors']
    save()
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path, help='Exported JSON array, with postId/text/publishedAt/photoUrls')
    parser.add_argument('--output', type=Path, default=ROOT / '.cache' / 'vk-dataset')
    args = parser.parse_args()
    try:
        rows = json.loads(args.input.read_text(encoding='utf-8-sig'))
        # Only download supplied image URLs. wall_page() is never called.
        client = VKClient(token=None, interval=0.5)
        state = import_dataset(rows, args.output, client.photo_bytes)
        print(f'Saved {len(state["posts"])} posts and {len(state["photos"])} photo references.')
        print(f'Archive: {args.output.resolve()}')
        print('Wall coverage is unverified: compare oldest/newest posts and the source count.')
        if state['download_complete']:
            return 0
        print('Some images failed. Run the same command to retry.', file=sys.stderr)
    except (ValueError, ExportError, OSError) as error:
        print(str(error) if isinstance(error, ExportError) else 'Cannot read/write a valid JSON dataset.', file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. Run the same command to resume.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
