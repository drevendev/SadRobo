import { readFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const root = fileURLToPath(new URL('../', import.meta.url));
const readJSON = async (file) => JSON.parse(await readFile(path.join(root, file), 'utf8'));

export async function loadArchive({ requireTranslations = true } = {}) {
  const stories = await readJSON('content/stories.json');
  const taxonomy = await readJSON('content/taxonomy.json');
  const tumblr = await readJSON('content/tumblr.json');
  const translations = new Map();
  for (const name of await readdir(path.join(root, 'content/translations'))) {
    if (!name.endsWith('.json')) continue;
    for (const entry of await readJSON(`content/translations/${name}`)) {
      if (translations.has(entry.id)) throw new Error(`Duplicate English translation: ${entry.id}`);
      translations.set(entry.id, entry);
    }
  }
  const markdown = await readFile(path.join(root, 'content/translations/telegram.md'), 'utf8');
  for (const match of markdown.matchAll(/<!-- (tg-\d+) -->\s*# ([^\n]+)\n+([\s\S]*?)(?=<!-- tg-|$)/g)) {
    if (translations.has(match[1])) throw new Error(`Duplicate English translation: ${match[1]}`);
    translations.set(match[1], { id: match[1], title: match[2], text: match[3].trim(), status: 'ai-draft' });
  }
  const missing = [];
  for (const [index, story] of stories.entries()) {
    story.order = index + 1;
    // Proza's Void record is a next-story navigation link; its surviving edition is visual.
    if (story.id === 'proza-2017-07-18-1919') story.text.ru = '';
    const english = translations.get(story.id);
    if (english) {
      story.title.en = english.title;
      story.text.en = english.text;
      story.translation = { status: english.status, adaptationNote: english.adaptationNote || '', translatorNote: english.translatorNote || '' };
    } else missing.push(story.id);
    const partner = story.title.ru.replace(/^Робот, которому грустно,? и /, '');
    story.tags = taxonomy.tags.filter(tag => new RegExp(tag.pattern, 'i').test(partner)).map(tag => tag.id);
    if (!story.tags.length) story.tags = ['inner-world'];
    story.arcs = taxonomy.arcs.filter(arc => arc.ids?.includes(story.id) || (arc.from && story.date >= arc.from && story.date <= arc.to)).map(arc => arc.id);
    for (const oldEnglish of tumblr.filter(post => post.matchedStoryId === story.id)) {
      story.sources.push({ platform: 'tumblr', url: oldEnglish.url, date: oldEnglish.date });
      for (const image of oldEnglish.images) if (!story.images.some(i => i.sha256 === image.sha256)) story.images.push(image);
    }
  }
  if (requireTranslations && missing.length) throw new Error(`Missing English translations (${missing.length}): ${missing.join(', ')}`);
  // The Olympic Flame survives in the old English edition, without a recovered Russian original.
  const flame = tumblr.find(post => post.title.includes('Olympic Flame'));
  stories.push({ id: 'tumblr-' + flame.id, order: stories.length + 1, date: '2022-06-09', kind: 'extra',
    title: { ru: 'Робот, которому грустно, и Олимпийский огонь', en: flame.title }, text: { en: flame.text }, images: flame.images,
    tags: ['culture'], arcs: [], translation: { status: 'source-english' },
    contentNote: { ru: 'Сохранилась английская публикация. Русский оригинал пока не восстановлен.', en: 'Preserved from the original English edition. The Russian original has not yet been recovered.' },
    sources: [{ platform: 'tumblr', url: flame.url, date: flame.date }] });
  const report = await readJSON('content/import-report.json');
  return { stories, tags: taxonomy.tags.map(({ pattern, ...tag }) => tag), arcs: taxonomy.arcs,
    meta: { ...report, uniqueWorks: stories.length, englishDrafts: translations.size,
      illustrations: new Set(stories.flatMap(s => s.images.map(i => i.sha256))).size,
      updated: '2026-10-24', author: 'drevendev / Робот, которому грустно', license: 'CC-BY-4.0' } };
}
