"""Merge source records conservatively; retain raw imports as the audit trail."""
import hashlib
import json
import re
from functools import cmp_to_key
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Proza limits its title field to 50 characters. These full names occur in the
# same work's body; the source's truncated title remains in sources[].title.
TITLE_FROM_BODY = {
    'proza-2021-09-10-466': 'Робот, которому грустно, и Актуальность моей работы',
    'proza-2021-09-15-625': 'Робот, которому грустно, и Робот, которому хочется убивать',
    'proza-2022-09-20-670': 'Робот, которому грустно, и Председатель земного шара',
    'proza-2024-02-02-724': 'Робот, которому грустно, и Робот, который ест загрязнения',
    'proza-2024-03-04-854': 'Робот, которому грустно, и Робот, который возвращает былое величие',
    'proza-2024-03-14-704': 'Робот, которому грустно, и Джордж Даос Мартин Какаос',
}


def clean(text):
    text = text.replace('\xa0', ' ')
    text = '\n'.join(line.strip() for line in text.splitlines())
    text = re.split(r'(?:^|\n)(?:Следующий диалог|Предыдущий диалог|Следующая часть|Предыдущая часть)\s*:', text, maxsplit=1)[0]
    return re.sub(r'\n{3,}', '\n\n', text).strip()


def normalized(text):
    return re.sub(r'[\W_]+', '', text.casefold().replace('ё', 'е'))


def main():
    proza = json.loads((ROOT / 'content/proza.json').read_text(encoding='utf-8'))
    telegram = json.loads((ROOT / 'content/telegram.json').read_text(encoding='utf-8'))
    stories, seen, excluded = [], {}, []
    for source, posts in [('proza', proza['posts']), ('telegram', telegram['posts'])]:
        for post in posts:
            if source == 'telegram' and post['id'] in {1, 2, 7, 9, 10}:
                excluded.append({'source': post['url'], 'reason': 'service message, pin or archive announcement'})
                continue
            text = clean(post['text'])
            if source == 'telegram':
                text = text.split('\n', 1)[1].strip()
                text = re.sub(r'\n+#диалоги.*$', '', text).strip()
            title = post['title']
            source_title = title
            if source == 'proza' and len(title) >= 44 and title.startswith('Робот, которому грустно, и '):
                partner = title.removeprefix('Робот, которому грустно, и ')
                for greeting in re.findall(r'Привет[,!]\s*([^\n]+)', text):
                    greeting = greeting.rstrip('.! ')
                    if greeting.startswith(partner) and len(greeting) > len(partner):
                        title = 'Робот, которому грустно, и ' + greeting
                        break
            key = normalized(text)
            if key in seen:
                seen[key]['sources'].append({'platform': source, 'url': post['url'], 'date': post['date']})
                for image in post['images']:
                    if image['sha256'] not in {i['sha256'] for i in seen[key]['images']}:
                        seen[key]['images'].append(image)
                continue
            kind = 'canon' if 'канон' in title.casefold() else 'extra' if (not title.startswith('Робот, которому грустно') or 'Мета.' in title) else 'dialogue'
            sid = post['id'] if source == 'proza' else f'tg-{post["id"]:03d}'
            title = TITLE_FROM_BODY.get(sid, title)
            story = {'id': sid, 'date': post['date'][:10], 'kind': kind, 'title': {'ru': title},
                     'text': {'ru': text}, 'sources': [{'platform': source, 'url': post['url'], 'date': post['date'], 'title': source_title}],
                     'images': post['images'], 'tags': [], 'arcs': [], 'translation': {'status': 'pending'}}
            stories.append(story)
            seen[key] = story
    next_links = {}
    for post in proza['posts']:
        match = re.search(r'Следующий диалог:\s*https?://(?:www\.)?proza.ru/(\d+/\d+/\d+/\d+)', post['text'])
        if match:
            next_links[post['id']] = 'proza-' + match[1].replace('/', '-')
    def compare(a, b):
        if a['date'] != b['date']:
            return -1 if a['date'] < b['date'] else 1
        def follows(first, last):
            visited = set()
            while first in next_links and first not in visited:
                visited.add(first)
                first = next_links[first]
                if first == last:
                    return True
            return False
        if follows(a['id'], b['id']):
            return -1
        if follows(b['id'], a['id']):
            return 1
        return int(a['id'].split('-')[-1]) - int(b['id'].split('-')[-1])
    stories.sort(key=cmp_to_key(compare))
    (ROOT / 'content/stories.json').write_text(json.dumps(stories, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'content/import-report.json').write_text(json.dumps({'prozaWorks': len(proza['posts']), 'telegramMessages': telegram['messageCount'],
        'uniqueWorks': len(stories), 'excluded': excluded, 'duplicatePolicy': 'Identical normalized bodies only; title similarity never merges distinct stories.',
        'vk': {'status': 'blocked', 'reason': 'Public endpoint returned access restriction; browser safety policy also blocks vk.ru. No VK completeness claim.'},
        'limitations': ['Proza dates are mirror publication dates, not verified original VK dates.', 'VK-only texts and illustrations may be missing.', 'Proza contains no story illustrations.']}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(stories)} works; {sum(p["kind"] == "dialogue" for p in stories)} dialogues')


if __name__ == '__main__':
    main()
