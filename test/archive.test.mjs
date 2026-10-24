import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { loadArchive, root } from '../scripts/archive.mjs';
import { filterStories, normalize } from '../public/search.mjs';
import { illustratedEntries, selectIllustration } from '../public/featured.mjs';

const archive = await loadArchive();

test('every exported VK post has one work with original text, exact time and source order', async () => {
  const vk = JSON.parse(await readFile(path.join(root,'content/vk.json'),'utf8'));
  const mapping = JSON.parse(await readFile(path.join(root,'content/vk-mapping.json'),'utf8'));
  const primary = archive.stories.filter(s => s.dateSource === 'vk');
  assert.equal(vk.posts.length,322);
  assert.equal(primary.length,322);
  assert.equal(new Set(primary.map(s => s.vkPostId)).size,322);
  for (const [index,post] of vk.posts.entries()) {
    const story = primary[index];
    assert.equal(story.id,mapping[post.id]);
    assert.equal(story.timestamp,post.date);
    assert.equal(Date.parse(story.publishedAt)/1000,post.date);
    const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Moscow',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date(post.date*1000));
    const part = name => parts.find(p=>p.type===name).value;
    assert.equal(story.date,`${part('year')}-${part('month')}-${part('day')}`,post.id);
    assert.equal(story.sources[0].url,post.url);
    assert.equal(story.sources[0].role,'primary');
    const raw = post.text.trim();
    const body = raw.startsWith('Робот, которому грустно') ? raw.split('\n').slice(1).join('\n').trim() : raw;
    assert.equal(story.text.ru,body,post.id);
    if(index) assert.ok(story.timestamp>=primary[index-1].timestamp);
  }
  assert.equal(primary[0].date,'2013-11-28');
  const mirrors = archive.stories.filter(s => s.dateSource === 'mirror');
  assert.equal(mirrors.length,3);
  assert.ok(mirrors.every(s => s.contentNote.ru && !s.sources.some(x => x.role === 'primary')));
  const missing = JSON.parse(await readFile(path.join(root,'content/vk-missing-photos.json'),'utf8'));
  assert.equal(missing.length,archive.meta.vk.missingPhotos);
  assert.equal(Object.keys(vk.photos).length,317);
  assert.equal(Object.values(vk.photos).filter(p=>p.path).length,archive.meta.vk.downloadedPhotos);
  assert.ok(missing.every(p=>p.works.length && p.error));
});

test('every canonical work has a stable unique ID, English edition and provenance', () => {
  assert.equal(archive.stories.length, 325);
  assert.equal(new Set(archive.stories.map(s=>s.id)).size, 325);
  for (const story of archive.stories) {
    assert.match(story.id, /^(proza-\d{4}-\d{2}-\d{2}-\d+|tg-\d{3}|tumblr-\d+|vk-\d+-\d+)$/);
    assert.ok(story.title.en, story.id);
    assert.equal(typeof story.text.en, 'string', story.id);
    assert.ok(story.text.en.trim() || !story.text.ru, story.id);
    assert.ok(story.sources.length, story.id);
    for (const source of story.sources) assert.match(source.url, /^https:\/\/(proza.ru|t.me|therobotwhoissad.tumblr.com|vk.com)\//);
    assert.equal(new Set(story.images.map(i => i.sha256)).size, story.images.length);
    assert.ok(['ai-draft','source-english'].includes(story.translation.status));
  }
});

test('service messages are absent; different stories with the same name survive', () => {
  for (const id of ['tg-001','tg-002','tg-007','tg-009','tg-010']) assert.ok(!archive.stories.some(s=>s.id===id));
  const creators = archive.stories.filter(s=>s.title.ru.replace(/\.$/,'')==='Робот, которому грустно, и Создатель');
  assert.equal(creators.length,2);
  assert.notEqual(creators[0].text.ru,creators[1].text.ru);
});

test('all image files match the archived SHA256 and are local', async () => {
  const images = new Map(archive.stories.flatMap(s=>s.images.map(i=>[i.path,i])));
  assert.ok(images.size > 200);
  for (const [file,image] of images) {
    assert.match(file,/^images\/[a-zA-Z0-9-]+\.(jpg|png|webp|gif|avif)$/);
    const data=await readFile(path.join(root,'public',file));
    assert.equal(createHash('sha256').update(data).digest('hex'),image.sha256,file);
  }
});

test('editorial collections have valid IDs and canonical source order', () => {
  for (const arc of archive.arcs) {
    const works=archive.stories.filter(s=>s.arcs.includes(arc.id));
    assert.ok(works.length>1,arc.id);
    for(const id of arc.ids||[])assert.ok(works.some(s=>s.id===id),id);
  }
  const first=filterStories(archive.stories,{arc:'beginnings'});
  assert.equal(first.length,8);
  assert.deepEqual(first.slice(0,4).map(s=>s.id),['proza-2017-07-11-545','proza-2017-07-12-553','proza-2017-07-13-449','proza-2017-07-13-469']);
});

test('bilingual search handles case, ё/е and multiple terms across the full text', () => {
  assert.equal(normalize('Всё ЕЩЁ'),'все еще');
  assert.ok(filterStories(archive.stories,{query:'ПЕЛЬМЕХАМИ'}).some(s=>s.id==='tg-015'));
  assert.ok(filterStories(archive.stories,{query:'dumplings'}).some(s=>s.id==='tg-015'));
  assert.ok(filterStories(archive.stories,{query:'Theseus parts'}).some(s=>s.id==='tg-018'));
  assert.equal(filterStories(archive.stories,{query:'nonexistentunicorn 123xyz'}).length,0);
});

test('filters combine, bookmarks constrain results, and sort does not mutate the archive', () => {
  const snapshot=archive.stories.map(s=>s.id);
  const result=filterStories(archive.stories,{year:'2026',kind:'dialogue',tag:'people',sort:'newest'});
  assert.ok(result.length>0);
  assert.ok(result.every(s=>s.date.startsWith('2026')&&s.kind==='dialogue'&&s.tags.includes('people')));
  assert.ok(result.every((s,i)=>!i||s.date<=result[i-1].date));
  assert.deepEqual(filterStories(archive.stories,{saved:new Set(['tg-015'])}).map(s=>s.id),['tg-015']);
  assert.deepEqual(archive.stories.map(s=>s.id),snapshot);
});

test('recovered Russian and image-only records are explicitly represented', () => {
  const flame=archive.stories.find(s=>s.id.startsWith('tumblr-'));
  assert.ok(flame.text.ru.includes('Олимпийский'));
  assert.equal(flame.translation.status,'source-english');
  assert.equal(flame.dateSource,'vk');
  const voidStory=archive.stories.find(s=>s.id==='proza-2017-07-18-1919');
  assert.equal(voidStory.text.ru,'');
  assert.equal(voidStory.text.en,'');
  assert.ok(voidStory.images.length>=1);
  assert.equal(archive.meta.vk.status,'imported');
});

test('new translations and original editions are stored separately', async () => {
  const oldEnglish=JSON.parse(await readFile(path.join(root,'content/tumblr.json'),'utf8'));
  assert.equal(oldEnglish.length,10);
  const vikings=archive.stories.find(s=>s.id==='proza-2017-07-12-553');
  assert.ok(vikings.translation.adaptationNote);
  assert.notEqual(vikings.text.en,oldEnglish.find(s=>s.matchedStoryId===vikings.id).text);
});

test('each random homepage illustration opens the dialogue that owns it', () => {
  const entries = illustratedEntries(archive.stories);
  assert.equal(entries.length, archive.meta.illustrations);
  for (let i = 0; i < entries.length; i++) {
    const selected = selectIllustration(archive.stories, '', () => (i + .5) / entries.length);
    assert.ok(selected.story.images.some(image => image.path === selected.image.path));
    assert.equal(selected.key, entries[i].key);
    const another = selectIllustration(archive.stories, selected.key, () => 0);
    assert.notEqual(another.key, selected.key);
  }
  assert.equal(selectIllustration([]), null);
  const only = [archive.stories.find(story => story.images.length === 1)];
  assert.equal(selectIllustration(only, illustratedEntries(only)[0].key).story.id, only[0].id);
});
