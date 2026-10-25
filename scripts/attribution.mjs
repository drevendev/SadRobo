// Attribution is maintained separately from imported source editions. Project
// founders are never used as implicit authors of individual contributions.
const statuses = new Set(['unverified', 'partial', 'verified']);
function publicURL(value, context) {
  try { if (!['http:', 'https:'].includes(new URL(value).protocol)) throw new Error(); }
  catch { throw new Error(`Invalid attribution URL: ${context}`); }
}

export function applyAttribution(stories, registry) {
  if (registry.schemaVersion !== 1) throw new Error('Unsupported attribution schema');
  const people = registry.creators || {};
  for (const [id, person] of Object.entries(people)) {
    if (!person.name?.trim()) throw new Error(`Missing creator name: ${id}`);
    if (person.url) publicURL(person.url, id);
  }
  const workIds = new Set(stories.map(s => s.id));
  for (const id of Object.keys(registry.works || {})) {
    if (!workIds.has(id)) throw new Error(`Unknown attribution work: ${id}`);
  }
  function credit(input = {}) {
    const status = input.status || 'unverified';
    if (!statuses.has(status)) throw new Error(`Invalid attribution status: ${status}`);
    const creatorIds = [...new Set(input.creatorIds || [])];
    const authors = creatorIds.map(id => {
      if (!people[id]) throw new Error(`Unknown creator: ${id}`);
      return { id, ...people[id] };
    });
    const sources = input.sources || [];
    for (const url of sources) publicURL(url, 'evidence');
    if (status === 'verified' && (!authors.length || (!sources.length && !input.note?.trim()))) {
      throw new Error('Verified attribution needs an author and evidence');
    }
    const license = { status: 'unverified', ...input.license };
    if (!statuses.has(license.status)) throw new Error('Invalid license verification status');
    if (license.url) publicURL(license.url, 'license');
    if (license.status === 'verified' && (!license.id || !license.url)) {
      throw new Error('Verified license needs an identifier and URL');
    }
    return { status, creatorIds, authors, sources, note: input.note || '', license };
  }
  // Validate even records for presently unselected image variants.
  const imageCredits = new Map(Object.entries(registry.images || {}).map(([hash, entry]) => {
    if (!/^[a-f0-9]{64}$/.test(hash)) throw new Error(`Invalid attribution image SHA256: ${hash}`);
    return [hash, credit(entry)];
  }));
  for (const story of stories) {
    const entry = registry.works?.[story.id] || {};
    story.credits = { text: credit(entry.text), translations: {} };
    for (const [language, translation] of Object.entries(entry.translations || {})) {
      story.credits.translations[language] = credit(translation);
    }
    for (const image of [...story.images, ...(story.imageVariants || [])]) {
      // A new hash from a different edition is not proof of the same author.
      image.credits = imageCredits.get(image.sha256) || credit();
    }
  }
  return {
    textsVerified: stories.filter(s => s.credits.text.status === 'verified').length,
    textsTotal: stories.length,
    illustrationsVerified: stories.filter(s => s.images[0]?.credits.status === 'verified').length,
    illustrationsTotal: stories.filter(s => s.images.length).length
  };
}
