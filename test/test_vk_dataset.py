"""Offline checks for supplied VK JSON imports; no live requests."""
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_vk_dataset import import_dataset, normalize_dataset
from scripts.export_vk import ExportError

PNG = b'\x89PNG\r\n\x1a\nfixture bytes'


def row(number=1, photos=None, text='Текст'):
    return {'postId': f'-42_{number}', 'text': text, 'publishedAt': '2017-07-11T12:00:00Z',
            'photoUrls': photos or []}


class VKDatasetTests(unittest.TestCase):
    def test_post_deduplication_keeps_order_and_photo_links(self):
        posts, photos = normalize_dataset([
            row(2, ['https://sun9.userapi.com/a.png']), row(1),
            row(2, ['https://sun9.userapi.com/b.png'])])
        self.assertEqual(list(posts), ['-42_1', '-42_2'])
        self.assertEqual(len(photos), 2)
        self.assertEqual(len(posts['-42_2']['photos']), 2)
        self.assertEqual(posts['-42_1']['text'], 'Текст')

    def test_conflicting_duplicate_is_not_silently_discarded(self):
        with self.assertRaises(ExportError):
            normalize_dataset([row(), row(text='Другой текст')])

    def test_empty_invalid_dates_and_unexpected_hosts_are_rejected(self):
        for rows in ([], {}, [dict(row(), publishedAt='yesterday')],
                     [row(photos=['https://userapi.com.attacker.invalid/a'])],
                     [row(photos=['https://localhost/a'])]):
            with self.subTest(rows=rows), self.assertRaises(ExportError):
                normalize_dataset(rows)

    def test_hash_deduplication_resume_and_corrupted_file_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            def download(url):
                calls.append(url)
                return PNG
            rows = [row(photos=['https://sun9.userapi.com/a.png', 'https://sun9.userapi.com/b.png'])]
            state = import_dataset(rows, root, download)
            self.assertEqual(len(calls), 2)
            self.assertEqual(len(list((root / 'images').iterdir())), 1)
            self.assertTrue(state['download_complete'])
            self.assertEqual(state['coverage'], 'unverified')
            import_dataset(rows, root, download)
            self.assertEqual(len(calls), 2)
            file = root / next(iter(state['photos'].values()))['file']
            file.write_bytes(b'corrupt')
            import_dataset(rows, root, download)
            self.assertEqual(file.read_bytes(), PNG)

    def test_failed_image_keeps_text_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            def fail(url):
                raise ExportError('Image unavailable.')
            rows = [row(photos=['https://sun9.userapi.com/a.png'])]
            state = import_dataset(rows, directory, fail)
            self.assertFalse(state['download_complete'])
            saved = json.loads((Path(directory) / 'dataset-export.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['posts']['-42_1']['text'], 'Текст')
            self.assertTrue(import_dataset(rows, directory, lambda _: PNG)['download_complete'])

    def test_smaller_dataset_cannot_overwrite_a_larger_saved_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            import_dataset([row(1), row(2)], directory, lambda _: PNG)
            with self.assertRaises(ExportError):
                import_dataset([row(1)], directory, lambda _: PNG)
            saved = json.loads((Path(directory) / 'dataset-export.json').read_text(encoding='utf-8'))
            self.assertEqual(len(saved['posts']), 2)


if __name__ == '__main__':
    unittest.main()
