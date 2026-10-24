import { cp, mkdir, writeFile, stat, readFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { loadArchive, root } from './archive.mjs';

const archive = await loadArchive({ requireTranslations: !process.argv.includes('--preview') });
const ids = new Set();
for (const story of archive.stories) {
  if (ids.has(story.id)) throw new Error(`Duplicate story id ${story.id}`);
  ids.add(story.id);
  for (const image of story.images) await stat(path.join(root, 'public', image.path));
}
await mkdir(path.join(root, 'dist'), { recursive: true });
await cp(path.join(root, 'public'), path.join(root, 'dist'), { recursive: true });
const serialized = JSON.stringify(archive);
const fingerprint = (text) => createHash('sha256').update(text).digest('hex').slice(0,12);
const archiveFile = `archive-${fingerprint(serialized)}.json`;
await writeFile(path.join(root, 'dist/archive.json'), serialized);
await writeFile(path.join(root, 'dist', archiveFile), serialized);
// Content-addressed assets prevent a returning reader's cached edition from
// mixing an old application/stylesheet with an updated archive on GitHub Pages.
const search = await readFile(path.join(root, 'public/search.mjs'), 'utf8');
const searchFile = `search-${fingerprint(search)}.mjs`;
await writeFile(path.join(root, 'dist', searchFile), search);
const app = (await readFile(path.join(root, 'public/app.mjs'), 'utf8'))
  .replace('./search.mjs', './' + searchFile).replace('./archive.json', './' + archiveFile);
const appFile = `app-${fingerprint(app)}.mjs`;
await writeFile(path.join(root, 'dist', appFile), app);
const css = await readFile(path.join(root, 'public/styles.css'), 'utf8');
const cssFile = `styles-${fingerprint(css)}.css`;
await writeFile(path.join(root, 'dist', cssFile), css);
const html = (await readFile(path.join(root, 'public/index.html'), 'utf8'))
  .replace('./app.mjs', './' + appFile).replace('./styles.css', './' + cssFile);
await writeFile(path.join(root, 'dist/index.html'), html);
await writeFile(path.join(root, 'dist/.nojekyll'), '');
await mkdir(path.join(root, 'dist/downloads'), { recursive: true });
await cp(path.join(root, 'content'), path.join(root, 'dist/downloads/content'), { recursive: true });
for (const file of ['LICENSE', 'LICENSE-CODE', 'ATTRIBUTION.md']) {
  try { await cp(path.join(root, file), path.join(root, 'dist/downloads', file)); }
  catch (error) { if (!process.argv.includes('--preview')) throw error; }
}
await writeFile(path.join(root, 'dist/downloads/stories.json'), JSON.stringify(archive.stories, null, 2) + '\n');
console.log(`Built ${archive.stories.length} works, ${archive.meta.englishDrafts} English drafts, ${archive.meta.illustrations} unique illustrations.`);
