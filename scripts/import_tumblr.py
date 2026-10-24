"""Preserve the author's earlier English edition and its illustrations."""
import hashlib
import json
import xml.etree.ElementTree as ET
from import_telegram import DOM, ROOT, CACHE, download

MATCHES = {
    '672384140683984896': 'proza-2017-07-11-545',
    '672525656658231296': 'proza-2017-07-12-553',
    '673524983810686976': 'proza-2017-07-13-449',
    '674882445479477248': 'proza-2017-07-13-469',
    '682582187742265344': 'proza-2017-07-18-1919',
    '683123885634469888': 'proza-2017-07-18-1923',
    '691281740695846912': 'proza-2017-07-18-1931',
    '691369768042872832': 'proza-2021-05-20-644',
}


def main():
    rss = download('https://therobotwhoissad.tumblr.com/rss', CACHE / 'tumblr-rss.html')
    root = ET.fromstring(rss)
    posts = []
    for item in root.findall('./channel/item'):
        url = item.findtext('link')
        sid = url.split('/')[-1]
        html = item.findtext('description') or ''
        dom = DOM(html)
        paragraphs = [p.text().strip() for p in dom.root.find(tag='p')]
        title = item.findtext('title') or ''
        if paragraphs and paragraphs[0] == title:
            paragraphs.pop(0)
        match = MATCHES.get(sid)
        if 'Katara' in title:
            match = 'proza-2017-08-03-187'
        images = []
        for image in dom.root.find(tag='img'):
            candidates = image.attrs.get('srcset', '').split(',')
            src = candidates[-1].strip().split(' ')[0] if candidates[-1].strip() else image.attrs['src']
            data = download(src, CACHE / f'tumblr-{sid}.jpg')
            digest = hashlib.sha256(data).hexdigest()
            relative = f'images/{digest[:20]}.jpg'
            (ROOT / 'public' / relative).write_bytes(data)
            images.append({'path': relative, 'sha256': digest, 'source': src})
        posts.append({'id': sid, 'url': url, 'title': title, 'date': item.findtext('pubDate'),
                      'text': '\n\n'.join(paragraphs), 'images': images, 'matchedStoryId': match})
    (ROOT / 'content/tumblr.json').write_text(json.dumps(posts, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(posts)} English source posts, {sum(len(p["images"]) for p in posts)} illustrations')


if __name__ == '__main__':
    main()
