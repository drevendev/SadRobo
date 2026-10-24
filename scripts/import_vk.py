"""Offline import of a locally exported VK wall. No network or credentials.

The reviewed post-to-work mapping preserves existing reader links. Unmapped
posts stop the import, so a later scan cannot silently merge unrelated works.
"""
import argparse
import copy
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[1]


def source_date(timestamp):
    try:
        zone = ZoneInfo('Europe/Moscow')
    except ZoneInfoNotFoundError:
        # Windows may lack the IANA database. This archive starts in 2013;
        # Moscow used UTC+4 until 2014-10-25 22:00 UTC, then UTC+3.
        # Reject earlier dates rather than silently applying today's offset.
        if timestamp < 1301180400:
            raise ValueError('Install IANA timezone data for VK dates before March 2011.')
        zone = timezone(timedelta(hours=4 if timestamp < 1414274400 else 3))
    return datetime.fromtimestamp(timestamp, zone).date().isoformat()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def import_export(export_root, root=ROOT):
    # The exporter writes atomically; one manifest read is a consistent snapshot.
    state = read(export_root / 'export.json')
    mapping = read(root / 'content/vk-mapping.json')
    posts = sorted(state['posts'].values(), key=lambda p: (p['date'], p['post_id']))
    unknown = set(state['posts']) - set(mapping)
    if unknown:
        raise ValueError('Review new VK posts in content/vk-mapping.json: ' + ', '.join(sorted(unknown)))
    if len({mapping[p['id']] for p in posts}) != len(posts):
        raise ValueError('Two VK posts map to the same reader record.')
    mirrors = read(root / 'content/mirror-stories.json')
    old = {s['id']: s for s in mirrors}
    tumblr = read(root / 'content/tumblr.json')
    exact_files = {}
    for file in (root / 'public/images').iterdir():
        if file.is_file():
            exact_files[hashlib.sha256(file.read_bytes()).hexdigest()] = 'images/' + file.name
    photo_records, missing, errors = {}, [], {e['photo_id']: e['message'] for e in state.get('errors', [])}
    for key, photo in state['photos'].items():
        record = {k: photo[k] for k in ('id','owner_id','photo_id','text','url') if k in photo}
        file = (export_root / photo.get('file', '__missing__')).resolve()
        valid = (file.is_relative_to(export_root.resolve()) and file.is_file()
                 and hashlib.sha256(file.read_bytes()).hexdigest() == photo.get('sha256'))
        if valid:
            digest = photo['sha256']
            relative = exact_files.get(digest, f'images/vk-{digest}{file.suffix.lower()}')
            target = root / 'public' / relative
            if not target.exists():
                shutil.copyfile(file, target)
            exact_files[digest] = relative
            record.update(path=relative, sha256=digest)
            record['width'] = photo.get('image', {}).get('width')
            record['height'] = photo.get('image', {}).get('height')
            record['fallbackSize'] = bool(photo.get('used_fallback_size'))
        else:
            record['error'] = errors.get(key, 'Not downloaded or file verification failed.')
            missing.append(key)
        photo_records[key] = record
    visual = read(root / 'content/vk-image-equivalents.json') if (root / 'content/vk-image-equivalents.json').exists() else {}
    stories = []
    editorial = {1:'Робот: первый рисунок',124:'Робот, которому грустно, и Кусок жизни',
                 413:'Джордж Мартин: новый мир',414:'Джордж Мартин: отныне я здесь хозяин',
                 421:'Джордж Мартин: в искусстве нет демократии',437:'Джордж Мартин: я убивал персонажей',
                 440:'Джордж Мартин: если нужно повернуть сюжет',643:'Робот на асфальте'}
    aggregate = old['proza-2023-06-26-571']
    for post in posts:
        identifier = mapping[post['id']]
        story = copy.deepcopy(old.get(identifier, {'id':identifier,'kind':'dialogue','title':{},'text':{},'sources':[],'images':[]}))
        raw = post['text'].strip()
        first, _, rest = raw.partition('\n')
        titled = first.startswith('Робот, которому грустно')
        title = first.strip() if titled else editorial.get(post['post_id'], story['title'].get('ru'))
        if not title:
            raise ValueError('An untitled post needs an editorial title: ' + post['id'])
        story['title']['ru'] = title
        story['text']['ru'] = rest.strip() if titled else raw
        story['date'] = source_date(post['date'])
        story['publishedAt'] = datetime.fromtimestamp(post['date'], timezone.utc).isoformat()
        story['dateSource'] = 'vk'
        story['vkPostId'] = post['id']
        story['timestamp'] = post['date']
        if not titled:
            story['titleSource'] = 'editorial' if post['post_id'] in editorial else 'mirror'
        source = {'platform':'vk','url':post['url'],'date':story['date'],'timestamp':post['date'],'role':'primary'}
        story['sources'] = [source] + [s for s in story['sources'] if s['platform'] != 'vk']
        if post['post_id'] in (414,421,437,440):
            story['kind'] = 'extra'
            for s in aggregate['sources']:
                if s['url'] not in {x['url'] for x in story['sources']}:
                    story['sources'].append({**s,'note':'Collected mirror edition of four separate VK monologues.'})
        if post['post_id'] in (1,413,643):
            story['kind'] = 'extra'
        if identifier.startswith('tumblr-'):
            original = next(p for p in tumblr if 'tumblr-'+p['id'] == identifier)
            story['title']['en'], story['text']['en'] = original['title'], original['text']
            story['translation'] = {'status':'source-english'}
            story['sources'].append({'platform':'tumblr','url':original['url'],'date':original['date']})
            story['images'] = copy.deepcopy(original['images'])
        vk_images = [{k:p[k] for k in ('path','sha256','width','height','url') if k in p} | {'platform':'vk','photoId':link['id']}
                     for link in post['photos'] if 'path' in (p := photo_records[link['id']])]
        primary_hashes = {i['sha256'] for i in vk_images}
        mirror_images = story['images']
        # Remove only byte-identical or reviewed pixel-equivalent mirror copies.
        story['images'] = vk_images + [i for i in mirror_images if i['sha256'] not in primary_hashes
            and not any(i['sha256'] in visual.get(h, []) for h in primary_hashes)]
        seen = set()
        story['images'] = [i for i in story['images'] if not (i['sha256'] in seen or seen.add(i['sha256']))]
        story['imageVariants'] = copy.deepcopy(story['images'])
        story['images'] = sorted(story['images'], key=lambda i: (
            i.get('platform') == 'vk', (i.get('width') or 0)*(i.get('height') or 0)), reverse=True)[:1]
        story['missingPhotoIds'] = [l['id'] for l in post['photos'] if 'path' not in photo_records[l['id']]]
        notes = []
        if story.get('titleSource') == 'editorial':
            notes.append(('Название добавлено для каталога; в посте VK заголовка нет.', 'The title was added for the catalogue; the VK post has no heading.'))
        if notes:
            story['contentNote'] = {lang:' '.join(n[index] for n in notes) for index,lang in enumerate(('ru','en'))}
        else:
            story.pop('contentNote', None)
        stories.append(story)
    used = {s['id'] for s in stories}
    for mirror in mirrors:
        if mirror['id'] not in used:
            story = copy.deepcopy(mirror)
            story['dateSource'] = 'mirror'
            story['contentNote'] = {'ru':'Публикация из зеркала. Соответствующий пост VK не найден; указана дата зеркала.',
                                    'en':'A mirror publication. No matching VK post was found; the date is from the mirror.'}
            stories.append(story)
    # Primary sequence first; mirror-only supplementary editions follow it.
    write(root / 'content/stories.json', stories)
    write(root / 'content/vk.json', {'source':'https://vk.ru/sadrobo','exportUpdatedAt':state.get('updated_at'),
          'dateTimezone':'Europe/Moscow','posts':posts,'photos':photo_records})
    report = read(root / 'content/import-report.json')
    report.update(uniqueWorks=len(stories), duplicatePolicy='Reviewed body matching; stable IDs retained. Four collected Martin monologues restored as four original VK posts.',
        vk={'status':'imported','posts':len(posts),'reportedPosts':state.get('last_scan',{}).get('reported_count'),
            'photos':len(photo_records),'downloadedPhotos':len(photo_records)-len(missing),'missingPhotos':len(missing),
            'exportUpdatedAt':state.get('updated_at'),'scan':state.get('last_scan'),
            'errorCounts':dict(Counter(photo_records[key]['error'] for key in missing)),
            'firstDate':stories[0]['date'],'lastDate':stories[len(posts)-1]['date']},
        limitations=['Missing VK photo downloads are listed individually in vk-missing-photos.json.',
                     'Three mirror-only supplementary publications retain mirror dates.',
                     'Coverage describes the exported wall; deleted or hidden VK posts cannot be inferred.'])
    write(root / 'content/import-report.json', report)
    missing_report = []
    for key in missing:
        related = [s for s in stories if key in s.get('missingPhotoIds', [])]
        missing_report.append({'photoId':key,'url':photo_records[key]['url'],'error':photo_records[key]['error'],
            'works':[{'id':s['id'],'title':s['title']['ru'],'post':s['sources'][0]['url'],
                      'mirrorIllustrationAvailable':bool(s['images'])} for s in related]})
    write(root / 'content/vk-missing-photos.json', missing_report)
    lines = ['# Недостающие фотографии VK', '',
             f'Сохранено {len(photo_records)-len(missing)} из {len(photo_records)}. Не скачано: {len(missing)}.', '',
             '404 — объект не найден по CDN URL; это не доказательство удаления фото. '
             '403 — отказ в доступе; 429 — ограничение частоты; 5xx — ошибка сервера.', '',
             '| Пост | Фото | Ошибка | Есть иллюстрация из зеркала |',
             '| --- | --- | --- | --- |']
    for item in missing_report:
        for work in item['works']:
            title = work['title'].replace('|','\\|').replace('\n',' ')
            lines.append(f"| [{title}]({work['post']}) | [{item['photoId']}]({item['url']}) | {item['error']} | {'Да' if work['mirrorIllustrationAvailable'] else 'Нет'} |")
    (root / 'content/vk-missing-photos.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print(json.dumps(report['vk'], ensure_ascii=False, indent=2))
    return stories


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / '.cache/vk-export')
    import_export(parser.parse_args().input)
