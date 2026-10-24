import { cp, mkdir, writeFile, stat, readFile } from 'node:fs/promises';
import path from 'node:path';
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
await writeFile(path.join(root, 'dist/archive.json'), JSON.stringify(archive));
await writeFile(path.join(root, 'dist/.nojekyll'), '');
await mkdir(path.join(root, 'dist/downloads'), { recursive: true });
await cp(path.join(root, 'content'), path.join(root, 'dist/downloads/content'), { recursive: true });
for (const file of ['LICENSE', 'LICENSE-CODE', 'ATTRIBUTION.md']) {
  try { await cp(path.join(root, file), path.join(root, 'dist/downloads', file)); }
  catch (error) { if (!process.argv.includes('--preview')) throw error; }
}
await writeFile(path.join(root, 'dist/downloads/stories.json'), JSON.stringify(archive.stories, null, 2) + '\n');
console.log(`Built ${archive.stories.length} works, ${archive.meta.englishDrafts} English drafts, ${archive.meta.illustrations} unique illustrations.`);
