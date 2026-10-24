export function normalize(value) {
  return String(value ?? '').normalize('NFKC').toLocaleLowerCase().replaceAll('ё', 'е').replaceAll('’', "'");
}

export function filterStories(stories, { query = '', tag = '', arc = '', year = '', kind = '', saved = null, sort = 'oldest' } = {}) {
  const words = normalize(query).trim().split(/\s+/).filter(Boolean);
  const filtered = stories.filter(story => {
    if (tag && !story.tags.includes(tag)) return false;
    if (arc && !story.arcs.includes(arc)) return false;
    if (year && !story.date.startsWith(year)) return false;
    if (kind === 'illustrated' ? !story.images.length : kind && story.kind !== kind) return false;
    if (saved && !saved.has(story.id)) return false;
    const haystack = normalize([story.title.ru, story.title.en, story.text.ru, story.text.en].join(' '));
    return words.every(word => haystack.includes(word));
  });
  return filtered.sort((a, b) => sort === 'newest' ? b.date.localeCompare(a.date) || b.order - a.order : sort === 'title' ? (a.title.ru || a.title.en).localeCompare(b.title.ru || b.title.en, 'ru') : a.date.localeCompare(b.date) || a.order - b.order);
}

export function excerpt(story, language = 'ru', query = '') {
  const text = story.text[language] ?? story.text.en ?? story.text.ru ?? '';
  const firstWord = normalize(query).trim().split(/\s+/)[0];
  const index = firstWord ? normalize(text).indexOf(firstWord) : -1;
  const start = Math.max(0, index - 45);
  return (start ? '…' : '') + text.slice(start, start + 170).replaceAll('\n', ' ') + (text.length > start + 170 ? '…' : '');
}
