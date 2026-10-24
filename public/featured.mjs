// Pick a picture, retaining its dialogue. One picture gets one chance even if
// multiple source records share it; a manual shuffle avoids the current picture.
export function illustratedEntries(stories) {
  const seen = new Set();
  return stories.flatMap(story => (story.images || []).flatMap(image => {
    const key = image.sha256 || image.path;
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ story, image, key }];
  }));
}

export function selectIllustration(stories, previousKey = '', random = Math.random) {
  const entries = illustratedEntries(stories);
  const choices = entries.length > 1 ? entries.filter(entry => entry.key !== previousKey) : entries;
  return choices[Math.floor(random() * choices.length)] || null;
}
