"""Diagnostic public downloads; responses are retained outside the published site."""
import concurrent.futures
from import_telegram import CACHE, download

TARGETS = {
    'vk-mobile': 'https://m.vk.com/sadrobo',
    'vk-com': 'https://vk.com/sadrobo',
    'tumblr-rss': 'https://therobotwhoissad.tumblr.com/rss',
    'tumblr-api': 'https://therobotwhoissad.tumblr.com/api/read/json?num=50',
}


def fetch(item):
    name, url = item
    try:
        data = download(url, CACHE / f'{name}.html')
        print(name, len(data), flush=True)
    except Exception as error:
        print(name, str(error), flush=True)


if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, TARGETS.items()))
