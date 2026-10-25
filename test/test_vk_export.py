"""Offline tests for VK archival semantics; no live VK requests or credentials."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs

from scripts import export_vk as vk

PNG = b'\x89PNG\r\n\x1a\nfixture bytes'


def photo(number=1, sizes=None):
    return {'type': 'photo', 'photo': {
        'owner_id': -42, 'id': number, 'text': 'Подпись',
        'sizes': sizes if sizes is not None else [
            {'url': f'https://example.invalid/{number}.png', 'width': 1024, 'height': 800}]}}


def post(number=1, attachments=None):
    return {'owner_id': -42, 'id': number, 'date': 1234567890,
            'text': f'Текст {number}', 'attachments': attachments or []}


class FixtureClient:
    def __init__(self, posts, images=None):
        self.posts, self.images = posts, images or {}
        self.offsets, self.downloads = [], []

    def wall_page(self, domain, offset):
        self.offsets.append(offset)
        return {'count': len(self.posts), 'items': self.posts[offset:offset + 100]}

    def photo_bytes(self, url):
        self.downloads.append(url)
        result = self.images.get(url, PNG)
        if isinstance(result, Exception):
            raise result
        return result


class FakeResponse:
    def __init__(self, payload):
        self.data = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.data[:limit]


class VKExportTests(unittest.TestCase):
    def test_existing_fallback_is_not_downloaded_again_without_upgrade_option(self):
        sizes = [{'url':'https://example.invalid/big','width':2400,'height':1800},
                 {'url':'https://example.invalid/small','width':1200,'height':900}]
        client = FixtureClient([post(1,[photo(7,sizes)])], {
            sizes[0]['url']:vk.ExportError('HTTP 404; export can be resumed.')})
        first = self.export(client)
        client.downloads.clear()
        second = self.export(client)
        self.assertEqual(client.downloads,[])
        self.assertTrue(second['complete'])
        self.assertEqual(second['photos']['-42_7']['image'],sizes[1])
        self.assertTrue(second['photos']['-42_7']['used_fallback_size'])
        self.assertEqual(second['run_stats']['photos_reused'],1)
        self.assertEqual(first['photos']['-42_7']['sha256'],second['photos']['-42_7']['sha256'])

    def test_known_404_skips_same_urls_but_fresh_url_gets_a_chance(self):
        url = 'https://example.invalid/7.png'
        client = FixtureClient([post(1,[photo(7)])],{url:vk.ExportError('HTTP 404; export can be resumed.')})
        self.export(client)
        client.downloads.clear()
        state = self.export(client)
        self.assertEqual(client.downloads,[])
        self.assertFalse(state['complete'])
        self.assertEqual(state['missing_photo_ids'],['-42_7'])
        self.assertEqual(state['run_stats']['urls_skipped_unavailable'],1)
        fresh = 'https://example.invalid/7.png?fresh=1'
        client.posts = [post(1,[photo(7,[{'url':fresh,'width':1024,'height':800}])])]
        state = self.export(client)
        self.assertEqual(client.downloads,[fresh])
        self.assertTrue(state['complete'])

    def test_migrates_old_errors_and_forced_retry_checks_them_again(self):
        sizes = [{'url':'https://example.invalid/big','width':2400,'height':1800},
                 {'url':'https://example.invalid/small','width':1200,'height':900}]
        client = FixtureClient([post(1,[photo(7,sizes)])], {
            s['url']:vk.ExportError('HTTP 404; export can be resumed.') for s in sizes})
        state = self.export(client)
        del state['photos']['-42_7']['unavailable_urls']
        vk.save_state(self.root,state)
        client.downloads.clear()
        state = self.export(client)
        self.assertEqual(client.downloads,[])
        self.assertEqual(state['run_stats']['urls_skipped_unavailable'],2)
        client.images.clear()
        state = self.export(client,retry_unavailable=True)
        self.assertEqual(client.downloads,[sizes[0]['url']])
        self.assertTrue(state['complete'])

    def test_temporary_failures_are_not_cached_as_unavailable(self):
        url = 'https://example.invalid/7.png'
        client = FixtureClient([post(1,[photo(7)])],{url:vk.ExportError('HTTP 500; export can be resumed.')})
        self.export(client)
        client.downloads.clear()
        client.images.clear()
        state = self.export(client)
        self.assertEqual(client.downloads,[url])
        self.assertTrue(state['complete'])

    def test_legacy_403_does_not_invent_which_of_several_sizes_failed(self):
        record = {'sizes':[{'url':'https://example.invalid/big'},
                           {'url':'https://example.invalid/small'}]}
        vk.seed_unavailable(record,'HTTP 403; export can be resumed.')
        self.assertNotIn('unavailable_urls',record)

    def test_request_attempt_budget_and_final_retry_after_apply_to_next_request(self):
        from urllib.error import HTTPError
        from urllib.request import Request
        calls, sleeps = [], []
        now = [0.0]
        def sleep(seconds):
            sleeps.append(seconds)
            now[0] += seconds
        def opener(request,timeout):
            calls.append(request.full_url)
            if len(calls)<=2:
                raise HTTPError(request.full_url,429,'limited',{'Retry-After':'45'},None)
            return FakeResponse({'response':{'count':0,'items':[]}})
        client = vk.VKClient('TEST_ONLY_SECRET',opener=opener,sleep=sleep,monotonic=lambda:now[0])
        with self.assertRaisesRegex(vk.ExportError,'HTTP 429'):
            client.photo_bytes('https://example.invalid/one')
        self.assertEqual(len(calls),2)
        client.photo_bytes('https://example.invalid/two')
        self.assertGreaterEqual(sleeps.count(45),2)

    def test_falls_back_only_to_exposed_size_after_404(self):
        sizes = [{'url': 'https://example.invalid/big', 'width': 2400, 'height': 1800},
                 {'url': 'https://example.invalid/small', 'width': 1200, 'height': 900}]
        client = FixtureClient([post(1, [photo(7, sizes)])], {
            sizes[0]['url']: vk.ExportError('HTTP 404; export can be resumed.')})
        state = self.export(client)
        record = state['photos']['-42_7']
        self.assertTrue(state['complete'])
        self.assertTrue(record['used_fallback_size'])
        self.assertEqual(record['image']['width'], 1200)
        self.assertEqual(len(record['sizes']), 2)
        self.assertEqual(client.downloads, [size['url'] for size in sizes])
        client.images[sizes[0]['url']] = vk.ExportError('HTTP 403; export can be resumed.')
        client.downloads.clear()
        state = self.export(client, upgrade_existing=True, retry_unavailable=True)
        self.assertEqual(client.downloads, [sizes[0]['url']])
        self.assertTrue(vk.verified_file(self.root, state['photos']['-42_7']))
        self.assertIn('upgrade_error', state['photos']['-42_7'])

    def test_retry_after_and_persistent_rate_cooldown(self):
        from urllib.error import HTTPError
        calls, sleeps = [], []
        def opener(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise HTTPError(request.full_url, 429, 'limited', {'Retry-After': '45'}, None)
            return FakeResponse({'response': {'count': 0, 'items': []}})
        client = vk.VKClient('TEST_ONLY_SECRET', opener=opener, sleep=sleeps.append)
        client.wall_page('sadrobo', 0)
        self.assertIn(45, sleeps)
        self.assertGreaterEqual(client._cooldown, 2)
        self.assertEqual(vk.retry_after({'Retry-After': 'bad'}), 0)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def export(self, client, **options):
        return vk.export_wall(client, self.root, progress=lambda _: None, **options)

    def test_chooses_largest_area_not_last_or_type_name(self):
        sizes = [{'url': 'https://example.invalid/big', 'width': 2400, 'height': 1800, 'type': 'z'},
                 {'src': 'https://example.invalid/small', 'width': 100, 'height': 100, 'type': 'w'},
                 {'url': 'http://example.invalid/unsafe', 'width': 5000, 'height': 5000}]
        candidate = vk.largest_photo({'sizes': sizes})
        self.assertEqual(candidate['url'], 'https://example.invalid/big')
        self.assertEqual(candidate['width'], 2400)

    def test_legacy_url_does_not_invent_image_dimensions(self):
        self.assertIsNone(vk.largest_photo({'photo_256': 'https://example.invalid/legacy'}))
        self.assertIsNone(vk.largest_photo({'photo_2560': 'https://example.invalid/legacy'}))

    def test_repost_keeps_text_and_attachment_source(self):
        original = post(2, [photo(7), photo(7)])
        original['text'] = 'Исходный текст'
        shared = post(3, [photo(8)])
        shared['copy_history'] = [original]
        normalized, photos = vk.normalize_post(shared)
        self.assertEqual(normalized['text'], 'Текст 3')
        self.assertEqual(normalized['reposts'][0]['text'], 'Исходный текст')
        self.assertEqual(normalized['photos'], [
            {'id': '-42_8', 'source_post': '-42_3'},
            {'id': '-42_7', 'source_post': '-42_2'}])
        self.assertEqual(set(photos), {'-42_7', '-42_8'})

    def test_pagination_at_100_and_overlapping_posts_do_not_duplicate(self):
        client = FixtureClient([post(number) for number in range(204)] + [post(0)])
        state = self.export(client)
        self.assertEqual(client.offsets, [0, 100, 200])
        self.assertEqual(len(state['posts']), 204)
        self.assertTrue(state['complete'])

    def test_repeated_photo_id_downloads_once_and_hash_deduplicates_other_ids(self):
        client = FixtureClient([post(1, [photo(7)]), post(2, [photo(7), photo(8)])])
        state = self.export(client)
        self.assertEqual(len(client.downloads), 2)
        self.assertEqual(len(state['photos']), 2)
        self.assertEqual(len(list((self.root / 'images').iterdir())), 1)
        self.assertEqual(state['photos']['-42_7']['file'], state['photos']['-42_8']['file'])
        self.assertEqual(state['photos']['-42_7']['sha256'], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(state['posts']['-42_2']['photos'][0]['id'], '-42_7')

    def test_resume_rescans_from_start_skips_valid_file_and_adds_new_post(self):
        self.export(FixtureClient([post(1, [photo(7)])]))
        client = FixtureClient([post(2, [photo(8)]), post(1, [photo(7)])])
        state = self.export(client)
        self.assertEqual(client.offsets, [0])
        self.assertEqual(client.downloads, ['https://example.invalid/8.png'])
        self.assertEqual(len(state['posts']), 2)

    def test_resume_replaces_corrupt_image(self):
        state = self.export(FixtureClient([post(1, [photo(7)])]))
        file = self.root / state['photos']['-42_7']['file']
        file.write_bytes(b'corrupted')
        client = FixtureClient([post(1, [photo(7)])])
        state = self.export(client)
        self.assertEqual(len(client.downloads), 1)
        self.assertTrue(vk.verified_file(self.root, state['photos']['-42_7']))

    def test_image_failure_retains_association_and_retries_on_next_run(self):
        failed = FixtureClient([post(1, [photo(7)])], {
            'https://example.invalid/7.png': vk.ExportError('HTTP 403; export can be resumed.')})
        state = self.export(failed)
        self.assertFalse(state['complete'])
        self.assertEqual(state['missing_photo_ids'], ['-42_7'])
        self.assertEqual(state['posts']['-42_1']['photos'][0]['id'], '-42_7')
        state = self.export(FixtureClient([post(1, [photo(7)])]), retry_unavailable=True)
        self.assertTrue(state['complete'])
        self.assertEqual(state['errors'], [])

    def test_html_challenge_is_not_stored_as_an_image(self):
        client = FixtureClient([post(1, [photo(7)])], {
            'https://example.invalid/7.png': b'<html>captcha</html>'})
        state = self.export(client)
        self.assertFalse(state['complete'])
        self.assertFalse((self.root / 'images').exists())

    def test_api_uses_post_and_never_echoes_token_from_error_response(self):
        requests = []
        secret = 'TEST_ONLY_SECRET'

        def opener(request, timeout):
            requests.append(request)
            return FakeResponse({'error': {'error_code': 5, 'error_msg': secret,
                                          'request_params': [{'key': 'access_token', 'value': secret}]}})

        client = vk.VKClient(secret, opener=opener, sleep=lambda _: None)
        with self.assertRaises(vk.ExportError) as raised:
            client.wall_page('sadrobo', 0)
        self.assertNotIn(secret, str(raised.exception))
        self.assertEqual(len(requests), 1)
        self.assertNotIn(secret, requests[0].full_url)
        self.assertEqual(requests[0].get_method(), 'POST')
        parameters = parse_qs(requests[0].data.decode())
        self.assertEqual(parameters['access_token'], [secret])
        self.assertEqual(parameters['count'], ['100'])

    def test_api_retries_rate_error_with_backoff(self):
        responses = iter([{'error': {'error_code': 6}}, {'response': {'count': 0, 'items': []}}])
        sleeps = []
        client = vk.VKClient('TEST_ONLY_SECRET', opener=lambda *args, **kwargs: FakeResponse(next(responses)),
                             sleep=sleeps.append)
        self.assertEqual(client.wall_page('sadrobo', 0), {'count': 0, 'items': []})
        self.assertIn(2, sleeps)

    def test_resume_rejects_different_wall_and_unsafe_existing_path(self):
        self.export(FixtureClient([post(1)]))
        with self.assertRaises(vk.ExportError):
            vk.export_wall(FixtureClient([]), self.root, domain='another')
        outside = self.root.parent / 'not-part-of-export.png'
        self.assertFalse(vk.verified_file(self.root, {
            'file': str(outside), 'sha256': hashlib.sha256(PNG).hexdigest()}))

    def test_repeated_full_page_stops_instead_of_looping(self):
        class RepeatingClient(FixtureClient):
            def wall_page(self, domain, offset):
                return {'count': 1000, 'items': [post(1)]}

        with self.assertRaisesRegex(vk.ExportError, 'repeated an entire page'):
            self.export(RepeatingClient([]))
        checkpoint = json.loads((self.root / 'export.json').read_text(encoding='utf-8'))
        self.assertFalse(checkpoint['complete'])
        self.assertEqual(len(checkpoint['posts']), 1)

    def test_empty_page_before_reported_end_keeps_export_incomplete(self):
        class TruncatedClient(FixtureClient):
            def wall_page(self, domain, offset):
                self.offsets.append(offset)
                return {'count': 205, 'items': self.posts[offset:offset + 100]}

        client = TruncatedClient([post(number) for number in range(100)])
        with self.assertRaisesRegex(vk.ExportError, 'empty page before the reported end'):
            self.export(client)
        checkpoint = json.loads((self.root / 'export.json').read_text(encoding='utf-8'))
        self.assertFalse(checkpoint['complete'])
        self.assertEqual(checkpoint['last_scan']['offset'], 100)
        self.assertEqual(checkpoint['last_scan']['reported_count'], 205)
        self.assertEqual(len(checkpoint['posts']), 100)
        self.assertEqual(client.offsets, [0, 100])

    def test_empty_wall_can_complete(self):
        state = self.export(FixtureClient([]))
        self.assertTrue(state['complete'])
        self.assertEqual(state['posts'], {})
        self.assertEqual(state['last_scan']['reported_count'], 0)

    def test_access_check_reads_first_last_pages_and_a_real_image(self):
        posts = [post(number) for number in range(250)]
        posts[-1]['attachments'] = [photo(7)]
        client = FixtureClient(posts)
        result = vk.check_access(client)
        self.assertEqual(client.offsets, [0, 150])
        self.assertEqual(result['sampled_posts'], 200)
        self.assertEqual(result['photo']['sha256'], hashlib.sha256(PNG).hexdigest())
        self.assertEqual(result['photo']['format'], 'png')
        self.assertEqual(len(client.downloads), 1)
        self.assertFalse((self.root / 'export.json').exists())

    def test_access_check_cannot_report_success_for_empty_wall_or_html_photo(self):
        with self.assertRaises(vk.ExportError):
            vk.check_access(FixtureClient([]))
        client = FixtureClient([post(1, [photo(7)])], {'https://example.invalid/7.png': b'<html>login</html>'})
        with self.assertRaises(vk.ExportError):
            vk.check_access(client)
        self.assertIsNone(vk.check_access(FixtureClient([post(1)]))['photo'])

    def test_community_token_error_stops_without_retry_or_secret_echo(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            return FakeResponse({'error': {'error_code': 27, 'error_msg': 'TEST_ONLY_SECRET'}})
        client = vk.VKClient('TEST_ONLY_SECRET', opener=opener, sleep=lambda _: None)
        with self.assertRaisesRegex(vk.ExportError, 'user or service access key') as raised:
            vk.check_access(client)
        self.assertNotIn('TEST_ONLY_SECRET', str(raised.exception))
        self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
