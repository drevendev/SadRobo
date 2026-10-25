"""Offline import regression tests: stable IDs, bytes, provenance and reruns."""
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.import_vk import import_export, write, read


class VKImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.export = self.root / 'export'
        (self.root / 'public/images').mkdir(parents=True)
        (self.export / 'images').mkdir(parents=True)
        self.identifier = 'proza-2023-06-26-571'
        write(self.root / 'content/vk-mapping.json', {'-62019209_414': self.identifier})
        write(self.root / 'content/mirror-stories.json', [{
            'id':self.identifier,'kind':'extra','date':'2023-06-26',
            'title':{'ru':'Собранная версия'},'text':{'ru':'Другая редакция'},
            'sources':[{'platform':'proza','url':'https://proza.ru/test','date':'2023-06-26'}],
            'images':[]}])
        write(self.root / 'content/tumblr.json', [])
        write(self.root / 'content/import-report.json', {})
        data = b'\xff\xd8\xffimage fixture'
        (self.export / 'images/fixture.jpg').write_bytes(data)
        self.state = {'posts':{'-62019209_414':{
            'id':'-62019209_414','post_id':414,'date':1385603700,'text':'Первоисточник!',
            'url':'https://vk.com/wall-62019209_414','photos':[{'id':'-62019209_1'}]}},
            'photos':{'-62019209_1':{'id':'-62019209_1','url':'https://vk.com/photo-62019209_1',
                'image':{'url':'https://example.invalid/secret-signed-url','width':20,'height':10},
                'file':'images/fixture.jpg','sha256':hashlib.sha256(data).hexdigest()}},
            'last_scan':{'reported_count':1,'seen_posts':1},'errors':[]}

    def run_import(self):
        write(self.export / 'export.json',self.state)
        with contextlib.redirect_stdout(io.StringIO()):
            return import_export(self.export,self.root)

    def test_idempotent_import_keeps_id_primary_text_and_does_not_publish_signed_urls(self):
        first = self.run_import()
        before = (self.root / 'content/stories.json').read_bytes()
        self.run_import()
        self.assertEqual((self.root / 'content/stories.json').read_bytes(),before)
        self.assertEqual(len(first),1)
        self.assertEqual(first[0]['id'],self.identifier)
        self.assertEqual(first[0]['text']['ru'],'Первоисточник!')
        self.assertEqual(first[0]['sources'][0]['role'],'primary')
        self.assertEqual(len(list((self.root / 'public/images').iterdir())),1)
        self.assertNotIn('secret-signed-url',(self.root / 'content/vk.json').read_text(encoding='utf-8'))
        self.assertEqual(read(self.root / 'content/mirror-stories.json')[0]['text']['ru'],'Другая редакция')

    def test_missing_or_corrupt_download_is_reported_without_losing_text(self):
        (self.export / 'images/fixture.jpg').write_bytes(b'corrupt')
        stories = self.run_import()
        self.assertEqual(stories[0]['text']['ru'],'Первоисточник!')
        self.assertEqual(stories[0]['images'],[])
        self.assertEqual(stories[0]['missingPhotoIds'],['-62019209_1'])
        report = read(self.root / 'content/vk-missing-photos.json')
        self.assertEqual(report[0]['works'][0]['id'],self.identifier)
        self.assertFalse(report[0]['works'][0]['mirrorIllustrationAvailable'])
        self.assertEqual(read(self.root / 'content/import-report.json')['vk']['missingPhotos'],1)

    def test_unknown_post_requires_review_before_modifying_reader(self):
        self.state['posts']['-62019209_414']['id'] = '-62019209_999'
        self.state['posts'] = {'-62019209_999':self.state['posts']['-62019209_414']}
        with self.assertRaisesRegex(ValueError,'Review new VK posts'):
            self.run_import()
        self.assertFalse((self.root / 'content/stories.json').exists())

    def test_smaller_vk_download_does_not_replace_higher_resolution_mirror(self):
        mirror = self.root / 'public/images/mirror.jpg'
        mirror.write_bytes(b'mirror fixture')
        digest = hashlib.sha256(mirror.read_bytes()).hexdigest()
        stories = read(self.root / 'content/mirror-stories.json')
        stories[0]['images'] = [{'path':'images/mirror.jpg','sha256':digest}]
        write(self.root / 'content/mirror-stories.json',stories)
        write(self.root / 'content/image-dimensions.json',{digest:{'width':600,'height':800}})
        result = self.run_import()[0]
        self.assertEqual(len(result['images']),1)
        self.assertEqual(result['images'][0]['path'],'images/mirror.jpg')
        self.assertEqual(len(result['imageVariants']),2)
        self.assertEqual(result['sources'][0]['platform'],'vk')
        self.assertEqual(result['missingPhotoIds'],[])


if __name__ == '__main__':
    unittest.main()
