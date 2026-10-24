import { filterStories, excerpt } from './search.mjs';
import { selectIllustration } from './featured.mjs';

const $ = (selector) => document.querySelector(selector);
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const readStore = (key, fallback) => { try { return JSON.parse(localStorage.getItem('sadrobo-' + key)) ?? fallback; } catch { return fallback; } };
const writeStore = (key, value) => { try { localStorage.setItem('sadrobo-' + key, JSON.stringify(value)); } catch {} };
const saved = new Set(readStore('saved', []));
let lastRead = readStore('progress', null);
let fontSize = Math.min(26, Math.max(16, Number(readStore('font', 20)) || 20));
let archive, route, featured, lang = 'ru', visibleLimit = 24, lastScroll = 0;
const phrases = {
  ru: {home:'Главная',catalog:'Все диалоги',arcs:'Арки и подборки',saved:'Закладки',about:'Об архиве',title:'Робот, которому грустно',subtitle:'Архив диалогов',search:'Найти слова, мысли, собеседника…',find:'Найти',start:'Читать с начала',continue:'Продолжить чтение',random:'Случайный диалог',all:'Все',oldest:'Сначала старые',newest:'Сначала новые',az:'По названию',tags:'Темы',year:'Все годы',kinds:'Все записи',dialogue:'Диалоги',canon:'Канон',extra:'Дополнения',illustrated:'С иллюстрациями',reset:'Сбросить фильтры',more:'Показать ещё',nothing:'Здесь пока тихо.',noResults:'По этим условиям ничего не нашлось. Попробуйте другие слова или сбросьте фильтры.',noSaved:'Сохраняйте диалоги значком закладки. Они останутся в этом браузере.',read:'Читать',back:'К каталогу',previous:'Предыдущий',next:'Следующий',bookmark:'В закладки',bookmarked:'В закладках',source:'Публикации',draft:'Черновик перевода · AI',note:'Примечание к переводу',adaptation:'Адаптация',copy:'Скопировать ссылку',copied:'Ссылка скопирована',light:'Светлая тема',dark:'Тёмная тема',menu:'Открыть меню',close:'Закрыть',count:'записей',curated:'Редакторская подборка',date:'Дата публикации в зеркале',onlyEnglish:'Русский текст пока не восстановлен. Ниже — сохранившаяся английская версия.',onlyRussian:'Английский перевод ещё готовится. Ниже — русский оригинал.',emptyText:'Этот диалог сохранился в виде иллюстрации.',saveHint:'Хранится только в вашем браузере.',foot:'А роботу всё ещё грустно.',rights:'Тексты и авторские иллюстрации',latest:'Последние встречи',browse:'Весь каталог',number:'Диалог',edition:'Литературный архив · 2017—2026',updated:'Архив обновлён 24 октября 2026',intro:'Скитаюсь по миру в поисках ответа на вопрос, который даже не знаю.',short:'Короткие разговоры о мире, людях и том, что остаётся внутри.',paths:'Куда пойти?',pathsText:'Можно идти следом за роботом. Можно свернуть на знакомую тему.',recovery:'О полноте архива',recoveryText:'Собраны доступные авторские зеркала. Часть иллюстраций и публикаций из VK ещё предстоит сверить.',image:'Иллюстрация к диалогу',imageFull:'Открыть иллюстрацию целиком',results:'Найдено',readTime:'мин чтения',homeLink:'На главную',reader:'Читалка',display:'Размер текста',total:'в архиве',english:'English',illustrations:'иллюстраций'},
  en: {home:'Home',catalog:'All dialogues',arcs:'Arcs & collections',saved:'Bookmarks',about:'About the archive',title:'The Robot Who Is Sad',subtitle:'An archive of dialogues',search:'Find words, thoughts, someone to talk to…',find:'Search',start:'Read from the beginning',continue:'Continue reading',random:'A random dialogue',all:'All',oldest:'Oldest first',newest:'Newest first',az:'By title',tags:'Themes',year:'All years',kinds:'All works',dialogue:'Dialogues',canon:'Canon',extra:'Extras',illustrated:'Illustrated',reset:'Clear filters',more:'Show more',nothing:'It is quiet here.',noResults:'Nothing matched these filters. Try different words or clear the filters.',noSaved:'Save a dialogue with its bookmark button. Your collection stays in this browser.',read:'Read',back:'Back to the catalogue',previous:'Previous',next:'Next',bookmark:'Bookmark',bookmarked:'Bookmarked',source:'Publications',draft:'Translation draft · AI',note:'Translator note',adaptation:'Adaptation',copy:'Copy link',copied:'Link copied',light:'Light theme',dark:'Dark theme',menu:'Open menu',close:'Close',count:'works',curated:'Editorial collection',date:'Mirror publication date',onlyEnglish:'The Russian original has not yet been recovered. The surviving English version follows.',onlyRussian:'The English translation is still being prepared. The Russian original follows.',emptyText:'The surviving edition of this dialogue is an illustration.',saveHint:'Stored only in your browser.',foot:'And the robot is still sad.',rights:'Texts and original illustrations',latest:'Recent encounters',browse:'Full catalogue',number:'Dialogue',edition:'A literary archive · 2017—2026',updated:'Archive updated 24 October 2026',intro:'I wander the world in search of an answer to a question I do not even know.',short:'Short conversations about the world, people, and what stays inside.',paths:'Where next?',pathsText:'Follow the robot. Or turn towards a familiar thought.',recovery:'About archive coverage',recoveryText:'The accessible author mirrors are collected here. Some VK illustrations and publications still need to be checked.',image:'Illustration for',imageFull:'Open the full illustration',results:'Found',readTime:'min read',homeLink:'Go home',reader:'Reader',display:'Text size',total:'in the archive',english:'English',illustrations:'illustrations'}
};
const activeTheme = () => document.documentElement.dataset.theme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
const t = (key) => phrases[lang][key] ?? key;
const label = (item) => item[lang] ?? item.en ?? item.ru ?? '';
const authorLinks = () => archive.meta.authors.map(author => `<a href="${escape(author.url)}" target="_blank" rel="noopener noreferrer">${escape(author.name)}</a>`).join(lang === 'ru' ? ' и ' : ' and ');
const titleOf = (story) => label(story.title);
const shortTitle = (story) => titleOf(story).replace(/^Робот, которому грустно,? и /, '').replace(/^The Robot Who Is Sad and /, '');
const dateOf = (date) => new Intl.DateTimeFormat(lang === 'ru' ? 'ru-RU' : 'en-GB', {day:'numeric', month:'short', year:'numeric', timeZone:'UTC'}).format(new Date(date));
const icons = {bookmark:'<path d="M6 3h12v18l-6-4-6 4z"/>',arrow:'<path d="M5 12h14m-6-6 6 6-6 6"/>',search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',grid:'<rect x="3" y="3" width="6" height="6"/><rect x="15" y="3" width="6" height="6"/><rect x="3" y="15" width="6" height="6"/><rect x="15" y="15" width="6" height="6"/>',paths:'<path d="M12 21V10m0 3L5 6m7 7 7-7M2 6h3V3m14 0v3h3"/>',home:'<path d="m3 10 9-7 9 7v11H3zM9 21v-8h6v8"/>',info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',moon:'<path d="M20 15A9 9 0 0 1 9 4a9 9 0 1 0 11 11z"/>',shuffle:'<path d="m3 5 3 0 12 14h3m-5-4 5 4-5 3M3 19h3l4-5m4-4 4-5h3m-5-3 5 3-5 4"/>',menu:'<path d="M4 6h16M4 12h16M4 18h16"/>'};
const icon = (name) => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || ''}</svg>`;
const robotMark = `<svg class="robot-mark" width="44" height="52" viewBox="0 0 44 52" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M21 12V5l4-3M7 20l5-8h21l5 8v22H7zM15 24v4m15-4v4M16 37q6-7 12 0M13 44v5m18-5v5"/></svg>`;

function href(view = 'home', params = {}) {
  const query = new URLSearchParams({lang, ...params});
  for (const [key, value] of [...query]) if (!value) query.delete(key);
  return `#/${view === 'home' ? '' : view}?${query}`;
}
function parseRoute() {
  const [pathname, query = ''] = location.hash.slice(1).split('?');
  const parts = (pathname || '/').split('/').filter(Boolean);
  route = { view: parts[0] || 'home', id: parts[1], params: new URLSearchParams(query) };
  lang = route.params.get('lang') === 'en' ? 'en' : route.params.get('lang') === 'ru' ? 'ru' : readStore('language','ru');
  if (!['ru','en'].includes(lang)) lang = 'ru';
  writeStore('language', lang);
}
function linkToStory(story, arc = '') { return href('read/' + story.id, {arc}); }
function options(values, selected) { return values.map(([id, text]) => `<option value="${escape(id)}" ${selected === id ? 'selected' : ''}>${escape(text)}</option>`).join(''); }
function bookmarkButton(story, compact = false) { return `<button class="bookmark ${saved.has(story.id) ? 'is-saved' : ''} ${compact ? 'compact' : ''}" data-action="bookmark" data-id="${story.id}" aria-pressed="${saved.has(story.id)}" aria-label="${t(saved.has(story.id) ? 'bookmarked' : 'bookmark')}: ${escape(shortTitle(story))}">${icon('bookmark')}${compact ? '' : `<span>${t(saved.has(story.id) ? 'bookmarked' : 'bookmark')}</span>`}</button>`; }
function tagLinks(story) { return story.tags.slice(0,3).map(id => {const tag=archive.tags.find(x=>x.id===id); return `<a class="tag" href="${href('catalog',{tag:id})}">${escape(label(tag))}</a>`;}).join(''); }
function card(story, arc = '') {
  const image = story.images[0];
  return `<article class="story-card"><div class="card-number">${String(story.order).padStart(3,'0')}</div><div class="card-copy"><div class="eyebrow card-date"><time datetime="${story.date}">${escape(dateOf(story.date))}</time>${story.kind !== 'dialogue' ? `<span> · ${t(story.kind)}</span>` : ''}</div><h3><a href="${linkToStory(story,arc)}">${escape(shortTitle(story))}</a></h3><p>${escape(excerpt(story,lang,route.params.get('q') || ''))}</p><div class="card-bottom"><div class="tags">${tagLinks(story)}</div>${bookmarkButton(story,true)}</div></div>${image ? `<a class="card-art" href="${linkToStory(story,arc)}" tabindex="-1" aria-hidden="true"><img src="./${escape(image.path)}" alt="" loading="lazy" width="140" height="140"></a>` : ''}</article>`;
}

function shell(content) {
  const nav = [['home','home'],['catalog','grid'],['arcs','paths'],['saved','bookmark'],['about','info']];
  return `<div class="app-shell">
    <header class="site-header">
      <div class="instrument-strip"><span>SR—01 <span class="strip-separator">/</span> ${t('subtitle')}</span><span class="instrument-state"><i aria-hidden="true"></i>${lang==='ru'?'Мне всё ещё грустно.':"I'm still sad."}</span></div>
      <div class="masthead-bar"><a class="brand" href="${href()}" aria-label="${t('homeLink')}">${robotMark}<span>SadRobo<span class="brand-caption">${lang==='ru'?'Робот, которому грустно':'The Robot Who Is Sad'}</span></span></a><div class="header-vent" aria-hidden="true"></div><div class="topbar-actions"><div class="language-control" role="group" aria-label="Language / Язык"><button data-action="language" data-lang="ru" aria-pressed="${lang==='ru'}" lang="ru">РУ</button><span>/</span><button data-action="language" data-lang="en" aria-pressed="${lang==='en'}" lang="en">EN</button></div><button class="icon-button theme-button" data-action="theme" aria-label="${t(activeTheme()==='dark'?'light':'dark')}">${icon('moon')}</button><button class="icon-button mobile-menu" data-action="menu" aria-label="${t('menu')}" aria-controls="sidebar" aria-expanded="false">${icon('menu')}</button></div></div>
      <nav class="site-nav" id="sidebar" aria-label="${lang === 'ru' ? 'Основная навигация' : 'Main navigation'}">${nav.map(([view,ico])=>`<a class="nav-link ${route.view === view ? 'active' : ''}" href="${href(view)}" ${route.view===view?'aria-current="page"':''}>${icon(ico)}<span>${t(view)}</span>${view==='saved'?`<span class="nav-count" id="saved-count">${saved.size||''}</span>`:''}</a>`).join('')}<span class="nav-edition">2017 — 2026</span></nav>
    </header>
    <div class="page"><main id="main" tabindex="-1">${content}</main></div>
    <footer class="footer"><div class="footer-signature">${robotMark}<span>${t('foot')}<small>© ${authorLinks()} · <a href="${href('about')}">CC BY 4.0</a></small></span></div><div class="footer-links"><a href="https://t.me/sadrobo" target="_blank" rel="noopener noreferrer">Telegram ↗</a><a href="https://vk.ru/sadrobo" target="_blank" rel="noopener noreferrer">ВКонтакте ↗</a><a href="https://github.com/drevendev/SadRobo" target="_blank" rel="noopener noreferrer">GitHub ↗</a></div></footer>
  </div><div class="toast" role="status" id="toast"></div>`;
}

function home() {
  const first = archive.stories.find(x=>x.kind==='dialogue');
  const recent = archive.stories.filter(x=>x.kind==='dialogue').slice(-3).reverse();
  const resume = archive.stories.find(x=>x.id===lastRead?.id);
  const item = featured;
  const story = item?.story;
  return `<section class="archive-cover">
    <div class="cover-title"><span class="eyebrow">${lang==='ru'?'Сохранившиеся разговоры / 2017—2026':'Surviving conversations / 2017—2026'}</span><h1>${lang==='ru'?'Робот, которому<br><em>грустно.</em>':'The Robot<br>Who Is <em>Sad.</em>'}</h1><p>${t('intro')}</p></div>
    <div class="cover-drawing" aria-hidden="true"><img src="./robot-blueprint.svg" width="220" height="290" alt=""><span>${lang==='ru'?'Такова моя природа.':"It's my nature."}</span></div>
  </section>
  ${story?`<section class="memory-station" aria-label="${lang==='ru'?'Случайная иллюстрация из архива':'A random illustration from the archive'}">
    <div class="station-top"><span><i class="status-dot" aria-hidden="true"></i>${lang==='ru'?'Случайная встреча':'A chance encounter'}</span><span class="station-number">№ ${String(story.order).padStart(3,'0')}</span><button class="text-button" data-action="shuffle-picture">${icon('shuffle')}${lang==='ru'?'Другая иллюстрация':'Another illustration'}</button></div>
    <div class="station-content"><figure class="memory-screen"><a class="featured-image-link" href="${linkToStory(story)}" data-feature-id="${story.id}" aria-label="${t('read')}: ${escape(titleOf(story))}"><img class="featured-image" src="./${escape(item.image.path)}" alt="${escape(t('image')+' «'+shortTitle(story)+'»')}"></a><figcaption>${lang==='ru'?'Нажмите на рисунок, чтобы открыть диалог.':'Select the illustration to open its dialogue.'}<span aria-hidden="true">↗</span></figcaption></figure>
    <div class="field-notes"><span class="eyebrow">${t('subtitle')}</span><div class="feature-caption" aria-live="polite" aria-atomic="true"><h2><a href="${linkToStory(story)}">${escape(shortTitle(story))}</a></h2><time datetime="${story.date}">${escape(dateOf(story.date))}</time></div><p class="field-excerpt">${escape(excerpt(story,lang))}</p><a class="button primary" href="${linkToStory(story)}">${t('read')} ${icon('arrow')}</a><div class="field-stamp" aria-hidden="true">${lang==='ru'?'Память<br>сохранилась':'Memory<br>remains'}</div></div></div>
    <div class="station-bottom"><span>${archive.stories.length} ${t('count')} <span class="strip-separator">/</span> ${archive.meta.illustrations} ${t('illustrations')}</span><span>${lang==='ru'?'А роботу всё ещё грустно.':'And the robot is still sad.'}</span></div>
  </section>`:''}
  <section class="reading-entry" aria-label="${t('reader')}"><a class="button start-reading" href="${linkToStory(first)}">|← ${t('start')}</a>${resume?`<a class="resume-panel" href="${linkToStory(resume)}"><span class="eyebrow">${t('continue')}</span><strong>${escape(shortTitle(resume))}</strong><span>${Math.round(lastRead.progress||0)}% →</span></a>`:`<p>${t('short')}</p>`}<button class="text-button" data-action="random">${icon('shuffle')}${t('random')}</button></section>
  <section class="home-search"><form class="search-field" data-form="search">${icon('search')}<input name="q" type="search" aria-label="${t('search')}" placeholder="${t('search')}" autocomplete="off"><button type="submit">${t('find')} ↗</button></form></section>
  <section class="home-paths"><div class="section-heading"><div><span class="eyebrow">${lang==='ru'?'В памяти остались дороги':'The roads remain in memory'}</span><h2>${t('arcs')}</h2></div><a class="text-link" href="${href('arcs')}">${lang==='ru'?'Все маршруты':'All reading paths'} ↗</a></div><div class="path-list">${archive.arcs.slice(0,3).map((arc,i)=>`<a class="path-row" href="${href('catalog',{arc:arc.id})}"><span class="path-index">0${i+1}</span><span><strong>${escape(label(arc))}</strong><small>${escape(label(arc.description))}</small></span><span class="path-count">${archive.stories.filter(x=>x.arcs.includes(arc.id)).length} <span aria-hidden="true">↗</span></span></a>`).join('')}</div></section>
  <section class="recent"><div class="section-heading"><div><span class="eyebrow">${lang==='ru'?'Время идёт':'Time goes on'}</span><h2>${t('latest')}</h2></div><a class="text-link" href="${href('catalog')}">${t('browse')} ↗</a></div><div class="story-list">${recent.map(s=>card(s)).join('')}</div></section>`;
}

function catalog(isSaved = false) {
  const params = Object.fromEntries(route.params);
  const arc = archive.arcs.find(x=>x.id===params.arc);
  return `<section class="catalog-page"><div class="page-heading"><span class="eyebrow">${isSaved?t('saveHint'):t('subtitle')}</span><h1>${isSaved?t('saved'):arc?escape(label(arc)):t('catalog')}<span class="heading-dot">.</span></h1>${arc?`<p>${escape(label(arc.description))}</p><span class="collection-label">${t('curated')}</span>`:`<p>${lang==='ru'?'Любая встреча с чего-нибудь начинается.':'Every encounter begins somewhere.'}</p>`}</div><form class="search-field catalog-search" data-form="search">${icon('search')}<input id="catalog-query" name="q" type="search" value="${escape(params.q||'')}" placeholder="${t('search')}" aria-label="${t('search')}" autocomplete="off"><button type="submit">${t('find')}</button></form><div class="filters"><label><span class="sr-only">${t('year')}</span><select data-filter="year">${options([['',t('year')],...[...new Set(archive.stories.map(s=>s.date.slice(0,4)))].map(y=>[y,y])],params.year||'')}</select></label><label><span class="sr-only">${t('kinds')}</span><select data-filter="kind">${options([['',t('kinds')],...['dialogue','canon','extra','illustrated'].map(k=>[k,t(k)])],params.kind||'')}</select></label><label><span class="sr-only">${t('arcs')}</span><select data-filter="arc">${options([['',t('arcs')],...archive.arcs.map(a=>[a.id,label(a)])],params.arc||'')}</select></label><label class="sort-filter"><span class="sr-only">${t('oldest')}</span><select data-filter="sort">${options(['oldest','newest','title'].map(x=>[x,t(x==='title'?'az':x)]),params.sort||'oldest')}</select></label></div><div class="tag-filter" role="group" aria-label="${t('tags')}"><button data-tag="" class="tag-chip ${!params.tag?'selected':''}" aria-pressed="${!params.tag}">${t('all')}</button>${archive.tags.map(tag=>`<button class="tag-chip ${params.tag===tag.id?'selected':''}" data-tag="${tag.id}" aria-pressed="${params.tag===tag.id}">${escape(label(tag))}</button>`).join('')}</div><div id="catalog-results" aria-live="polite"></div></section>`;
}
function renderResults() {
  const holder = $('#catalog-results');
  if (!holder) return;
  const p = Object.fromEntries(route.params);
  const stories = filterStories(archive.stories,{query:p.q,tag:p.tag,arc:p.arc,year:p.year,kind:p.kind,sort:p.sort,saved:route.view==='saved'?saved:null});
  const active = ['q','tag','arc','year','kind'].some(k=>p[k]);
  holder.innerHTML = `<div class="results-bar"><span>${t('results')}: <b>${stories.length}</b></span>${active?`<a href="${href(route.view)}">${t('reset')} ×</a>`:''}</div>${stories.length?`<div class="story-list">${stories.slice(0,visibleLimit).map(s=>card(s,p.arc)).join('')}</div>${stories.length>visibleLimit?`<button class="button load-more" data-action="more">${t('more')} <span>${Math.min(24,stories.length-visibleLimit)}</span> ↓</button>`:''}`:`<div class="empty-state">${robotMark}<h2>${t('nothing')}</h2><p>${t(route.view==='saved'&&!active?'noSaved':'noResults')}</p>${active?`<a class="button" href="${href(route.view)}">${t('reset')}</a>`:''}</div>`}`;
}
function arcs() {
  return `<section class="arcs-page"><div class="page-heading"><span class="eyebrow">${lang==='ru'?'Несколько дорог через один мир':'Several paths through one world'}</span><h1>${t('arcs')}<span class="heading-dot">.</span></h1><p>${lang==='ru'?'Редакторские маршруты по связанным диалогам. Они помогают ориентироваться и не заменяют авторскую хронологию.':'Editorial reading paths through connected dialogues. They help you find your way and preserve publication order.'}</p></div><div class="arc-grid">${archive.arcs.map((arc,i)=>`<a class="arc-card" href="${href('catalog',{arc:arc.id})}"><div class="arc-card-top"><span>0${i+1}</span>${icon('arrow')}</div><span class="eyebrow">${t('curated')}</span><h2>${escape(label(arc))}</h2><p>${escape(label(arc.description))}</p><div class="arc-card-foot">${archive.stories.filter(s=>s.arcs.includes(arc.id)).length} ${t('count')} <span>→</span></div></a>`).join('')}</div></section>`;
}

function renderBody(text) {
  const sourceLookup = new Map(archive.stories.flatMap(s=>s.sources.map(source=>[source.url.replace(/^https?:\/\/(?:www\.)?/, '').replace(/\/$/,''),s])));
  return text.split(/\n\s*\n/).map(paragraph=>`<p>${paragraph.split(/(https?:\/\/[^\s<>]+)/g).map(part=>{
    if (!/^https?:\/\//.test(part)) return escape(part);
    const target = sourceLookup.get(part.replace(/^https?:\/\/(?:www\.)?/,'').replace(/\/$/,''));
    return target?`<a href="${linkToStory(target)}">${escape(part)}</a>`:`<a href="${escape(part)}" target="_blank" rel="noopener noreferrer">${escape(part)}</a>`;
  }).join('')}</p>`).join('');
}
function sequenceControls(story, arc, position) {
  const matches = filterStories(archive.stories, arc ? {arc} : {kind:story.kind});
  const list = matches.some(item=>item.id===story.id) ? matches : filterStories(archive.stories,{kind:story.kind});
  const index = list.findIndex(item=>item.id===story.id);
  const ru = lang==='ru';
  const control = (item, text) => item ? `<a href="${linkToStory(item,arc)}">${text}</a>` : `<span aria-disabled="true">${text}</span>`;
  return `<nav class="sequence-controls" aria-label="${ru?'Навигация по диалогам':'Dialogue navigation'} — ${position==='top'?(ru?'перед текстом':'before the text'):(ru?'после текста':'after the text')}">${control(index>0?list[0]:null,ru?'|← Начало':'|← First')}${control(list[index-1],'← '+t('previous'))}<button class="sequence-random" data-action="random" data-arc="${escape(arc)}">${icon('shuffle')}${ru?'Случайный':'Random'}</button>${control(list[index+1],t('next')+' →')}${control(index<list.length-1?list.at(-1):null,ru?'Конец →|':'Last →|')}</nav>`;
}

function reader() {
  const story = archive.stories.find(s=>s.id===route.id);
  if (!story) return `<section class="empty-state"><h1>${lang==='ru'?'Диалог не найден':'Dialogue not found'}</h1><a class="button" href="${href('catalog')}">${t('back')}</a></section>`;
  const arc = route.params.get('arc')||'';
  const list = filterStories(archive.stories, arc ? {arc} : {kind:story.kind});
  const index = list.findIndex(s=>s.id===story.id);
  const previous = list[index-1], next = list[index+1];
  const bodyLang = story.text[lang] != null ? lang : lang==='ru'?'en':'ru';
  const body = story.text[bodyLang] || '';
  const minutes = Math.max(1,Math.ceil(body.split(/\s+/).length/190));
  return `<section class="reader-page"><div class="reader-toolbar"><a class="text-link" href="${href('catalog',{arc})}">← ${t('back')}</a><div class="reading-controls" role="group" aria-label="${t('display')}"><button data-action="font-down" aria-label="${lang==='ru'?'Уменьшить текст':'Decrease text size'}">A−</button><button data-action="font-up" aria-label="${lang==='ru'?'Увеличить текст':'Increase text size'}">A+</button></div></div>${sequenceControls(story,arc,'top')}<article class="reading-article"><header class="reading-header"><div class="eyebrow">${t(story.kind==='dialogue'?'number':story.kind)} ${String(story.order).padStart(3,'0')} <span>·</span> <time datetime="${story.date}" title="${t('date')}">${escape(dateOf(story.date))}</time> <span>·</span> ${minutes} ${t('readTime')}</div><h1>${escape(titleOf(story))}</h1><div class="reading-meta"><div class="tags">${tagLinks(story)}</div>${bookmarkButton(story)}</div>${lang==='en'&&story.translation.status==='ai-draft'?`<div class="draft-notice">${t('draft')} <a href="${href('about')}">${lang==='ru'?'О переводе':'About this edition'} ↗</a></div>`:''}</header>${story.contentNote?`<p class="content-note">${escape(label(story.contentNote))}</p>`:''}${bodyLang!==lang?`<p class="content-note">${t(bodyLang==='en'?'onlyEnglish':'onlyRussian')}</p>`:''}<div class="story-body" lang="${bodyLang}" style="--reading-size:${fontSize}px">${body?renderBody(body):`<p class="content-note">${t('emptyText')}</p>`}</div>${story.images.map((image,i)=>`<figure class="reading-illustration"><a href="./${escape(image.path)}" target="_blank" rel="noopener" aria-label="${t('imageFull')}"><img src="./${escape(image.path)}" alt="${escape(t('image')+' «'+shortTitle(story)+'»'+(story.images.length>1?' '+(i+1):''))}" loading="lazy"></a><figcaption>${t('image')} «${escape(shortTitle(story))}» <span>↗</span></figcaption></figure>`).join('')}${lang==='en'&&(story.translation.adaptationNote||story.translation.translatorNote)?`<aside class="translation-notes">${story.translation.adaptationNote?`<p><strong>${t('adaptation')}.</strong> ${escape(story.translation.adaptationNote)}</p>`:''}${story.translation.translatorNote?`<p><strong>${t('note')}.</strong> ${escape(story.translation.translatorNote)}</p>`:''}</aside>`:''}<div class="reading-sources"><span class="eyebrow">${t('source')}</span><div>${story.sources.map(s=>`<a href="${escape(s.url)}" target="_blank" rel="noopener noreferrer">${({proza:'Проза.ру',telegram:'Telegram',tumblr:'Tumblr · English',vk:'ВКонтакте'})[s.platform]} · ${s.role==='primary'?(lang==='ru'?'первоисточник':'primary source'):(lang==='ru'?'зеркало':'mirror')} ↗</a>`).join('')}</div><p>${lang==='ru'?'Соавторы:':'Coauthors:'} ${authorLinks()}. ${lang==='ru'?'Тексты и авторские иллюстрации — CC BY 4.0.':'Texts and original illustrations: CC BY 4.0.'}</p><button class="text-button" data-action="copy">${t('copy')} ↗</button></div><nav class="reading-pagination" aria-label="${t('reader')}">${previous?`<a href="${linkToStory(previous,arc)}"><span class="eyebrow">← ${t('previous')}</span><strong>${escape(shortTitle(previous))}</strong></a>`:'<span></span>'}${next?`<a href="${linkToStory(next,arc)}"><span class="eyebrow">${t('next')} →</span><strong>${escape(shortTitle(next))}</strong></a>`:`<a href="${href('catalog')}"><span class="eyebrow">${t('browse')} →</span><strong>${t('foot')}</strong></a>`}</nav></article>${sequenceControls(story,arc,'bottom')}<div class="reading-progress" id="reading-progress" aria-hidden="true"></div></section>`;
}

function about() {
  const ru = lang==='ru';
  return `<section class="about-page"><div class="page-heading"><span class="eyebrow">${ru?'Всё в одном месте':'Everything in one place'}</span><h1>${t('about')}<span class="heading-dot">.</span></h1><p>${t('short')}</p></div><div class="about-prose"><h2>${ru?'Робот и его мир':'The robot and his world'}</h2><p>${ru?'Робот скитается по миру в поисках ответа на неизвестный вопрос. Он встречает людей, идеи, вещи и других роботов. Ему грустно.':'The robot wanders the world in search of an answer to an unknown question. He meets people, ideas, things and other robots. He is sad.'}</p><p>${ru?'«Робот, которому грустно» создан в соавторстве':'The Robot Who Is Sad was created jointly by'} ${authorLinks()}. ${ru?'Здесь можно читать по порядку, искать сразу на двух языках и собирать собственные закладки.':'Read in order, search both languages and collect your own bookmarks.'}</p><h2>${ru?'Источники и полнота':'Sources and coverage'}</h2><p>${ru?'Первоисточник проекта — ВКонтакте. Telegram, Проза.ру и Tumblr — зеркала. При восстановлении тексты, иллюстрации и первоначальная хронология сверяются с VK.':'VK is the project’s primary source. Telegram, Proza.ru and Tumblr are mirrors. Restored texts, illustrations and original publication order are checked against VK.'}</p><ul><li><a href="https://vk.ru/sadrobo">ВКонтакте</a>: ${ru?'первоисточник. Полнота архива относительно VK ещё не подтверждена; старые иллюстрации и отдельные тексты могут отсутствовать.':'primary source. Coverage against VK is not yet verified; some older illustrations and texts may be missing.'}</li><li><a href="https://t.me/sadrobo">Telegram</a>: ${ru?'зеркало; вся доступная публичная лента до сообщения № 58. Служебные записи сохранены в выгрузке и исключены из читалки.':'mirror; the accessible public feed through message 58. Service messages are retained in the source files and omitted from the reader.'}</li><li><a href="https://proza.ru/avtor/sadrobo">Проза.ру</a>: ${ru?'зеркало; 244 публикации. Даты означают публикацию в зеркале, первоначальные даты VK пока не подтверждены.':'mirror; 244 publications. Dates refer to this mirror; original VK dates have not yet been verified.'}</li><li><a href="https://therobotwhoissad.tumblr.com/">Tumblr</a>: ${ru?'зеркало прежней английской редакции; 10 публикаций и иллюстрации. Совпадающие рассказы объединены с русскими; «Олимпийский огонь» пока доступен только на английском.':'mirror of the earlier English edition; 10 posts and illustrations. Matching works share a record with their Russian edition; The Olympic Flame currently survives here only in English.'}</li></ul><p>${ru?'Точные повторы объединяются с сохранением ссылок. Похожие названия не считаются дублями: например, разные встречи с Создателем или Зеркалом остаются отдельными. Арки и темы — редакторская навигация.':'Exact repeats are merged while retaining their source links. Similar titles are not duplicates: different encounters with Creator or Mirror remain separate. Arcs and themes are editorial navigation.'}</p><h2>${ru?'Английская редакция':'The English edition'}</h2><p>${ru?'Перевод опирается на прежние образцы Tumblr: простые фразы, короткие диалоги, буквальная логика и сухие развязки. В английской адаптации смягчены отдельные грубые или натуралистичные места; существенные изменения отмечены под текстом. Русский оригинал не редактировался.':'The translation follows the earlier Tumblr examples: simple phrases, short exchanges, literal logic and dry endings. Some harsh or graphic passages are softened in the English adaptation; material changes are noted beneath the text. The Russian original is preserved.'}</p><p>${ru?'Все новые английские переводы отмечены как черновики AI. Авторская вычитка ещё требуется. Исходная английская версия Tumblr также сохранена в выгрузке.':'All new English translations are marked as AI drafts and still need author review. The original Tumblr English edition is also preserved in the downloads.'}</p><h2>${ru?'Использование и атрибуция':'Reuse and attribution'}</h2><p>${ru?'Авторские тексты, новые переводы и авторские иллюстрации распространяются по':'Original texts, new translations and original illustrations are available under'} <a href="https://creativecommons.org/licenses/by/4.0/">Creative Commons Attribution 4.0 International (CC BY 4.0)</a>. ${ru?'Можно копировать, менять и использовать коммерчески. Укажите обоих авторов и источник, добавьте ссылку на лицензию и отметьте изменения.':'You may copy, adapt and use them commercially. Credit both authors and the source, link the licence and indicate changes.'}</p><blockquote>${ru?'«Робот, которому грустно» — drevendev и FreeSlave. Источник: github.com/drevendev/SadRobo. CC BY 4.0. Изменения: [описание].':'The Robot Who Is Sad — drevendev and FreeSlave. Source: github.com/drevendev/SadRobo. CC BY 4.0. Changes: [description].'}</blockquote><p>${ru?'Права на упоминаемых чужих персонажей, товарные знаки и возможные сторонние элементы иллюстраций остаются у их правообладателей. Код читалки — MIT.':'Referenced third-party characters, trademarks and any third-party elements in illustrations remain with their respective rightsholders. The reader code is MIT licensed.'}</p><h2>${ru?'Скачать и продолжить':'Download and contribute'}</h2><div class="download-links"><a href="./downloads/stories.json" download>JSON · RU + EN ↓</a><a href="https://github.com/drevendev/SadRobo/tree/master/content">${ru?'Исходный архив':'Source archive'} ↗</a><a href="./downloads/ATTRIBUTION.md">${ru?'Атрибуция':'Attribution'} ↓</a><a href="https://github.com/drevendev/SadRobo/issues">${ru?'Исправить или дополнить':'Corrections & additions'} ↗</a></div><p class="muted">${ru?'Закладки, тема, размер текста и место чтения хранятся локально в браузере. Аналитики и внешних шрифтов нет.':'Bookmarks, theme, text size and reading position stay in your browser. No analytics or external fonts.'}</p><p class="eyebrow">${t('updated')}</p></div></section>`;
}

function render({scroll = true} = {}) {
  const previousView = route?.view;
  parseRoute();
  if (route.view==='home' && (previousView!=='home' || !featured)) {
    featured = selectIllustration(archive.stories, featured?.key);
  }
  const content = route.view==='home'?home():route.view==='catalog'||route.view==='saved'?catalog(route.view==='saved'):route.view==='arcs'?arcs():route.view==='read'?reader():route.view==='about'?about():`<section class="empty-state"><h1>404</h1><a href="${href()}">${t('homeLink')}</a></section>`;
  $('#app').innerHTML = shell(content);
  document.documentElement.lang = lang;
  document.title = (route.view==='read' ? titleOf(archive.stories.find(s=>s.id===route.id)||{title:{ru:'404',en:'404'}}) : route.view==='home'?t('title'):t(route.view)) + ' · SadRobo';
  renderResults();
  if (scroll) {
    window.scrollTo({top:0,behavior:'instant'});
    if (route.view==='read' && lastRead?.id===route.id) requestAnimationFrame(()=>window.scrollTo({top:lastRead.scroll||0,behavior:'instant'}));
  }
  if (route.view==='read' && archive.stories.some(s=>s.id===route.id)) {
    if (lastRead?.id!==route.id) lastRead = {id:route.id,scroll:0,progress:0};
    writeStore('progress',lastRead);
  }
}

function setFilter(key,value) {
  const p = Object.fromEntries(route.params);
  p[key] = value;
  location.hash = href(route.view,p);
}
let queryTimer;
document.addEventListener('input', event => {
  if (event.target.id!=='catalog-query') return;
  clearTimeout(queryTimer);
  const query = event.target.value;
  queryTimer = setTimeout(()=>{
    route.params.set('q',query);
    const p = Object.fromEntries(route.params);
    history.replaceState(null,'',href(route.view,p));
    visibleLimit=24;
    renderResults();
  },180);
});
document.addEventListener('change',event=>{ if(event.target.dataset.filter)setFilter(event.target.dataset.filter,event.target.value); });
document.addEventListener('submit',event=>{
  if(event.target.dataset.form!=='search')return;
  event.preventDefault();
  clearTimeout(queryTimer);
  const query = new FormData(event.target).get('q').trim();
  if(route.view==='catalog'||route.view==='saved') {route.params.set('q',query);history.replaceState(null,'',href(route.view,Object.fromEntries(route.params)));renderResults();}
  else location.hash=href('catalog',{q:query});
});
document.addEventListener('click',async event=>{
  if (event.target.closest('.skip-link')) { event.preventDefault(); $('#main')?.focus(); $('#main')?.scrollIntoView(); return; }
  const tag = event.target.closest('[data-tag]');
  if(tag){setFilter('tag',tag.dataset.tag);return;}
  const button = event.target.closest('[data-action]');
  if(!button)return;
  const action = button.dataset.action;
  if(action==='menu') {const opened=$('#sidebar').classList.toggle('is-open');button.setAttribute('aria-expanded',String(opened));}
  if(action==='language') {const p=Object.fromEntries(route.params);p.lang=button.dataset.lang;location.hash=href(route.view==='read'?'read/'+route.id:route.view,p);}
  if(action==='theme') {
    const current=document.documentElement.dataset.theme|| (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
    const theme=current==='dark'?'light':'dark';document.documentElement.dataset.theme=theme;
    try {localStorage.setItem('sadrobo-theme',theme);}catch{}
    button.setAttribute('aria-label',t(theme==='dark'?'light':'dark'));
  }
  if(action==='bookmark') {
    const id=button.dataset.id;saved.has(id)?saved.delete(id):saved.add(id);writeStore('saved',[...saved]);
    if(route.view==='saved')renderResults();
    else {button.classList.toggle('is-saved',saved.has(id));button.setAttribute('aria-pressed',String(saved.has(id)));button.setAttribute('aria-label',t(saved.has(id)?'bookmarked':'bookmark'));if(button.querySelector('span'))button.querySelector('span').textContent=t(saved.has(id)?'bookmarked':'bookmark');}
    $('#saved-count').textContent=saved.size||'';
  }
  if(action==='shuffle-picture'){featured=selectIllustration(archive.stories,featured?.key);render({scroll:false});$('[data-action=\"shuffle-picture\"]')?.focus({preventScroll:true});}
  if(action==='random'){const candidates=filterStories(archive.stories,button.dataset.arc?{arc:button.dataset.arc}:{kind:'dialogue'});const choices=candidates.length?candidates:archive.stories.filter(s=>s.kind==='dialogue');location.hash=linkToStory(choices[Math.floor(Math.random()*choices.length)],button.dataset.arc||'');}
  if(action==='more'){visibleLimit+=24;renderResults();}
  if(action==='font-up'||action==='font-down'){fontSize=Math.min(26,Math.max(16,fontSize+(action==='font-up'?2:-2)));writeStore('font',fontSize);$('.story-body')?.style.setProperty('--reading-size',fontSize+'px');}
  if(action==='copy') {try {await navigator.clipboard.writeText(location.href);$('#toast').textContent=t('copied');$('#toast').classList.add('visible');setTimeout(()=>$('#toast')?.classList.remove('visible'),2500);}catch {button.textContent=location.href;}}
});
document.addEventListener('keydown',event=>{if(event.key==='Escape'){$('#sidebar')?.classList.remove('is-open');$('.mobile-menu')?.setAttribute('aria-expanded','false');}});
window.addEventListener('hashchange',()=>{clearTimeout(queryTimer);visibleLimit=24;render();});
window.addEventListener('scroll',()=>{
  if(route?.view!=='read')return;
  const total=document.documentElement.scrollHeight-innerHeight;
  const progress=total>0?Math.min(100,Math.round(scrollY/total*100)):100;
  $('#reading-progress')?.style.setProperty('width',progress+'%');
  if(Date.now()-lastScroll>350){lastRead={id:route.id,scroll:scrollY,progress};writeStore('progress',lastRead);lastScroll=Date.now();}
},{passive:true});

try {
  const response=await fetch(new URL('./archive.json',import.meta.url));
  if(!response.ok)throw new Error('Archive HTTP '+response.status);
  archive=await response.json();
  for(const id of saved)if(!archive.stories.some(s=>s.id===id))saved.delete(id);
  render();
} catch(error) {
  $('#app').innerHTML='<main class="empty-state"><h1>Не удалось открыть архив / Could not open the archive</h1><p>Попробуйте обновить страницу. / Try reloading the page.</p><a href="https://github.com/drevendev/SadRobo">GitHub ↗</a></main>';
  console.error(error);
}
