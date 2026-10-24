"""Export a VK wall directly using a user or application service access key.

Python 3.10+, stdlib only. Community tokens are not supported by wall.get.

The token is entered privately at runtime; it is never included in URLs, saved
responses, command-line arguments, or diagnostic output. See docs/vk-export.md.
"""
import argparse
import getpass
import hashlib
import json
import re
import sys
import time
import warnings
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
API_VERSION = '5.199'
USER_AGENT = 'SadRoboArchive/1.0 (+https://github.com/drevendev/SadRobo)'
MAX_IMAGE_BYTES = 60 * 1024 * 1024


class ExportError(Exception):
    """An intentionally safe diagnostic, without request bodies or server echoes."""


class VKClient:
    def __init__(self, token, interval=0.5, opener=urlopen, sleep=time.sleep,
                 monotonic=time.monotonic):
        self._token = token
        self._interval = max(interval, 0.4)
        self._opener, self._sleep, self._clock = opener, sleep, monotonic
        self._last_request = None
        self._cooldown = 0

    def _request(self, request, image=False):
        for attempt in range(5):
            if self._last_request is not None:
                self._sleep(max(0, max(self._interval, self._cooldown) - (self._clock() - self._last_request)))
            self._last_request = self._clock()
            try:
                with self._opener(request, timeout=40) as response:
                    limit = MAX_IMAGE_BYTES if image else 16 * 1024 * 1024
                    data = response.read(limit + 1)
                    if len(data) > limit:
                        raise ExportError('Response exceeded the size limit.')
                    return data
            except HTTPError as error:
                status = error.code
                if status == 429 or 500 <= status < 600:
                    if status == 429:
                        self._cooldown = min(30, max(2, self._cooldown * 2))
                    if attempt < 4:
                        self._sleep(max(2 ** (attempt + 1), retry_after(error.headers)))
                        continue
                raise ExportError(f'HTTP {status}; export can be resumed.') from None
            except (URLError, TimeoutError, OSError):
                if attempt < 4:
                    self._sleep(2 ** (attempt + 1))
                    continue
                raise ExportError('Network request failed; export can be resumed.') from None

    def wall_page(self, domain, offset):
        # POST prevents a token from appearing in URLs, history, or URL error logs.
        body = urlencode({'domain': domain, 'offset': offset, 'count': 100,
                          'filter': 'owner', 'extended': 0, 'v': API_VERSION,
                          'access_token': self._token}).encode('ascii')
        request = Request('https://api.vk.com/method/wall.get', data=body,
                          headers={'User-Agent': USER_AGENT,
                                   'Content-Type': 'application/x-www-form-urlencoded'})
        for attempt in range(3):
            try:
                payload = json.loads(self._request(request))
            except (ValueError, UnicodeError):
                raise ExportError('VK returned invalid JSON.') from None
            if not isinstance(payload, dict):
                raise ExportError('VK returned an unexpected response.')
            if 'error' not in payload:
                return validate_page(payload.get('response'))
            error = payload['error']
            code = error.get('error_code') if isinstance(error, dict) else None
            code = code if isinstance(code, int) else None
            if code in (6, 10) and attempt < 2:
                self._sleep(2 ** (attempt + 1))
                continue
            hints = {5: 'Token is invalid or expired.', 6: 'Rate limit reached.',
                     9: 'Flood control; stop and try again later.',
                     14: 'VK requires a CAPTCHA; automated export stopped.',
                     15: 'This token does not have access to the wall.',
                     27: 'wall.get does not support community tokens, even with wall permission. '
                         'Use a VK API user or service access key; see docs/vk-export.md.',
                     28: 'Application authorization failed. Check your VK API user or service access key.',
                     1051: 'This token profile type cannot call wall.get. Use a VK API user or service access key.'}
            # Do not print error_msg / request_params: VK may echo credentials.
            safe_code = code if isinstance(code, int) else 'unknown'
            raise ExportError(f'VK API error {safe_code}. '
                              + hints.get(code, 'Check token permissions and API access.'))

    def photo_bytes(self, url):
        if not valid_image_url(url):
            raise ExportError('The image does not have a valid HTTPS URL.')
        return self._request(Request(url, headers={'User-Agent': USER_AGENT}), image=True)


def validate_page(response):
    if (not isinstance(response, dict) or not isinstance(response.get('items'), list)
            or not isinstance(response.get('count'), int) or response['count'] < 0):
        raise ExportError('VK returned an unexpected wall page.')
    return response


def valid_image_url(value):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return (url.scheme == 'https' and bool(url.hostname)
                and url.username is None and url.password is None)
    except ValueError:
        return False


def photo_sizes(photo):
    """Keep all distinct sizes actually exposed by VK, largest first."""
    candidates = []
    for size in list(photo.get('sizes', [])) + list(photo.get('images', [])):
        if not isinstance(size, dict):
            continue
        url = size.get('url') or size.get('src')
        width, height = size.get('width', 0), size.get('height', 0)
        if (valid_image_url(url) and isinstance(width, int) and isinstance(height, int)
                and width >= 0 and height >= 0):
            candidates.append({'url': url, 'width': width, 'height': height})
    candidates.sort(key=lambda size: (size['width'] * size['height'],
                                     max(size['width'], size['height'])), reverse=True)
    unique = {}
    for size in candidates:
        unique.setdefault(size['url'], size)
    return list(unique.values())


def largest_photo(photo):
    candidates = photo_sizes(photo)
    if candidates:
        return candidates[0]
    # A lone legacy URL does not expose enough dimensions to compare sizes.
    # Keep such a photo unresolved instead of inventing its resolution.
    return None


def retry_after(headers):
    value = headers.get('Retry-After', '') if headers else ''
    try:
        return min(300, max(0, float(value)))
    except ValueError:
        try:
            return min(300, max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            return 0


def object_id(obj):
    owner, number = obj.get('owner_id'), obj.get('id')
    if not isinstance(owner, int) or not isinstance(number, int):
        raise ExportError('A VK post or photo is missing its numeric ID.')
    return f'{owner}_{number}'


def normalize_post(post):
    post_key = object_id(post)
    normalized = {'id': post_key, 'owner_id': post['owner_id'], 'post_id': post['id'],
                  'date': post.get('date'), 'text': post.get('text', ''),
                  'url': f'https://vk.com/wall{post_key}', 'photos': [], 'reposts': []}
    photos, seen_links = {}, set()

    def visit(source, depth=0):
        if depth > 8:
            raise ExportError('VK returned an excessively nested repost.')
        source_key = object_id(source)
        if depth:
            normalized['reposts'].append({'id': source_key, 'text': source.get('text', ''),
                                         'url': f'https://vk.com/wall{source_key}'})
        for attachment in source.get('attachments', []):
            if attachment.get('type') != 'photo':
                continue
            photo = attachment.get('photo', {})
            photo_key = object_id(photo)
            candidate = largest_photo(photo)
            record = {'id': photo_key, 'owner_id': photo['owner_id'],
                      'photo_id': photo['id'], 'text': photo.get('text', ''),
                      'url': f'https://vk.com/photo{photo_key}', 'image': candidate,
                      'sizes': photo_sizes(photo)}
            previous = photos.get(photo_key, {}).get('image')
            if (photo_key not in photos or (candidate and
                    (not previous or candidate['width'] * candidate['height'] >
                     previous['width'] * previous['height']))):
                photos[photo_key] = record
            link = (photo_key, source_key)
            if link not in seen_links:
                normalized['photos'].append({'id': photo_key, 'source_post': source_key})
                seen_links.add(link)
        for copied in source.get('copy_history', []):
            visit(copied, depth + 1)

    visit(post)
    return normalized, photos


def image_extension(data):
    if data.startswith(b'\xff\xd8\xff'):
        return '.jpg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return '.gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    if data[4:8] == b'ftyp' and data[8:12] in (b'avif', b'avis'):
        return '.avif'
    raise ExportError('The download is not a recognized image; it may be an HTML challenge.')


def verified_file(root, record):
    """Resume only from files inside the export directory with matching bytes."""
    relative, digest = record.get('file'), record.get('sha256')
    if not relative or not digest:
        return False
    file = (root / relative).resolve()
    if not file.is_relative_to(root.resolve()) or not file.is_file():
        return False
    return hashlib.sha256(file.read_bytes()).hexdigest() == digest


def store_photo(client, root, record, previous):
    candidate, old_image = record['image'], previous.get('image')
    if (verified_file(root, previous) and candidate and old_image and
            candidate['width'] * candidate['height'] <=
            old_image['width'] * old_image['height']):
        return {**record, 'file': previous['file'], 'sha256': previous['sha256']}
    if not candidate:
        if verified_file(root, previous):
            return {**record, 'file': previous['file'], 'sha256': previous['sha256']}
        raise ExportError('VK did not expose a downloadable size for this photo.')
    candidates = record.get('sizes') or [candidate]
    failures = []
    for candidate in candidates:
        try:
            data = client.photo_bytes(candidate['url'])
            extension = image_extension(data)
            break
        except ExportError as error:
            failures.append(str(error))
            # Only a missing CDN object warrants trying another explicitly
            # exposed size. Access denial, throttling and challenges stop here.
            if not str(error).startswith('HTTP 404;'):
                raise
    else:
        raise ExportError(failures[-1])
    digest = hashlib.sha256(data).hexdigest()
    # Different VK photo IDs with identical bytes share the same local file.
    relative = f'images/{digest}{extension}'
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        temporary = target.with_suffix(target.suffix + '.tmp')
        temporary.write_bytes(data)
        replace_file(temporary, target)
    return {**record, 'image': candidate, 'file': relative, 'sha256': digest,
            'used_fallback_size': candidate != record['image']}


def replace_file(temporary, target):
    # Windows indexers / virus scanners may briefly hold the destination open.
    for attempt in range(4):
        try:
            temporary.replace(target)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(0.05 * 2 ** attempt)


def save_state(root, state):
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    temporary = root / 'export.json.tmp'
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    replace_file(temporary, root / 'export.json')


def export_wall(client, destination, domain='sadrobo', progress=print):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / 'export.json'
    if manifest.exists():
        try:
            state = json.loads(manifest.read_text(encoding='utf-8'))
        except (ValueError, OSError):
            raise ExportError('Cannot read the existing export manifest.') from None
        if state.get('schema_version') != 1 or state.get('domain') != domain:
            raise ExportError('The export directory belongs to a different wall or format.')
    else:
        state = {'schema_version': 1, 'domain': domain, 'api_version': API_VERSION,
                 'posts': {}, 'photos': {}}
    state['complete'], state['errors'] = False, []
    save_state(root, state)
    offset, page_signatures, seen_posts = 0, set(), set()
    while True:
        page = validate_page(client.wall_page(domain, offset))
        items = page['items']
        if not items:
            state['last_scan'] = {'seen_posts': len(seen_posts), 'reported_count': page['count'],
                                  'offset': offset}
            save_state(root, state)
            if offset < page['count']:
                raise ExportError('VK returned an empty page before the reported end of the wall; '
                                  'export is incomplete and can be resumed.')
            break
        signature = tuple(object_id(post) for post in items)
        if signature in page_signatures:
            raise ExportError('VK repeated an entire page; stopped to avoid an endless loop.')
        page_signatures.add(signature)
        for post in items:
            normalized, photos = normalize_post(post)
            state['posts'][normalized['id']] = normalized
            seen_posts.add(normalized['id'])
            for photo_key, record in photos.items():
                try:
                    record = store_photo(client, root, record, state['photos'].get(photo_key, {}))
                except ExportError as error:
                    # Keep association and URL for a later retry, but never claim success.
                    state['errors'].append({'photo_id': photo_key, 'message': str(error)})
                    previous = state['photos'].get(photo_key, {})
                    if verified_file(root, previous):
                        record = {**record, 'file': previous['file'], 'sha256': previous['sha256'],
                                  'image': previous.get('image'), 'upgrade_error': str(error)}
                state['photos'][photo_key] = record
            save_state(root, state)
        offset += len(items)
        state['last_scan'] = {'seen_posts': len(seen_posts), 'reported_count': page['count'],
                              'offset': offset}
        save_state(root, state)
        progress(f'Wall scanned: {offset}/{page["count"]}; unique posts: {len(state["posts"])}; '
                 f'photo IDs: {len(state["photos"])}')
        if offset >= page['count']:
            break
    # Include unresolved photos from earlier interrupted scans in the status.
    missing = [key for key, photo in state['photos'].items() if not verified_file(root, photo)]
    state['missing_photo_ids'] = missing
    state['complete'] = not missing and not state['errors']
    save_state(root, state)
    return state


def check_access(client, domain='sadrobo'):
    """Read first/last wall pages and verify one available photo, without saving files.

    This is a live access check, not proof of completeness of the full archive.
    """
    first = validate_page(client.wall_page(domain, 0))
    if not first['count'] or not first['items']:
        raise ExportError('VK exposed no posts; access to this archive has not been verified.')
    last = (validate_page(client.wall_page(domain, max(0, first['count'] - 100)))
            if first['count'] > 100 else first)
    if not last['items']:
        raise ExportError('VK did not expose the final page; access to old posts has not been verified.')
    samples = {object_id(post): post for post in first['items'] + last['items']}
    result = {'reported_count': first['count'], 'sampled_posts': len(samples),
              'count_unchanged': first['count'] == last['count'], 'photo': None}
    for post in samples.values():
        _, photos = normalize_post(post)
        for photo_id, photo in photos.items():
            if not photo['image']:
                continue
            data = client.photo_bytes(photo['image']['url'])
            extension = image_extension(data)
            result['photo'] = {'id': photo_id, 'format': extension[1:], 'bytes': len(data),
                               'sha256': hashlib.sha256(data).hexdigest()}
            return result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--domain', default='sadrobo', help='VK short address (default: sadrobo)')
    parser.add_argument('--output', type=Path, default=ROOT / '.cache' / 'vk-export')
    parser.add_argument('--interval', type=float, default=0.5, help='Request interval; minimum 0.4 seconds')
    parser.add_argument('--check', action='store_true',
                        help='Verify first/last wall pages and one photo without saving an export')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.domain):
        parser.error('--domain must be a short address, not a full URL')
    try:
        # Refuse getpass's echoing fallback (e.g. a redirected, non-interactive shell).
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            token = getpass.getpass('VK API user or service access key (hidden; not saved): ').strip()
        if not token:
            raise ExportError('No token entered.')
        client = VKClient(token, args.interval)
        if args.check:
            result = check_access(client, args.domain)
            print(f'Wall read OK: {result["sampled_posts"]} posts sampled; '
                  f'VK reports {result["reported_count"]} posts.')
            if not result['count_unchanged']:
                print('Wall count changed during the check; repeat the check before exporting.')
            if result['photo']:
                photo = result['photo']
                print(f'Photo download OK: {photo["format"]}, {photo["bytes"]} bytes.')
                print('Access check passed. Full archive coverage still requires a complete export and comparison.')
                return 0 if result['count_unchanged'] else 2
            print('No downloadable photo in the sampled pages; image access is not verified.')
            return 2
        state = export_wall(client, args.output, args.domain)
        print(f'Export saved: {args.output.resolve()}')
        if not state['complete']:
            print('Some photos could not be downloaded. Run the same command to retry.', file=sys.stderr)
            return 1
        return 0
    except getpass.GetPassWarning:
        print('A private interactive terminal is required for token entry.', file=sys.stderr)
    except (ExportError, OSError) as error:
        # OSError diagnostics may include arbitrary server-provided paths/URLs.
        message = str(error) if isinstance(error, ExportError) else 'Cannot read or write export files.'
        print(message, file=sys.stderr)
    except (KeyboardInterrupt, EOFError):
        print('\nExport stopped. Run the same command to resume.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    sys.exit(main())
