/* Source for the inline Viewer.html script. Run scripts/build_viewer.py after edits. */
'use strict';
function element(tag, text, parent, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = String(text);
  if (className) node.className = className;
  if (parent) parent.appendChild(node);
  return node;
}
// Hosting boundary for the three reader operations.
function viewerRequest(method, args, success, failure) {
  google.script.run.withSuccessHandler(success).withFailureHandler(failure)[method](...args);
}
const state = { number: document.body.dataset.number || '', query: document.body.dataset.query || '', mode: document.body.dataset.mode || 'collector',
  collector: document.body.dataset.collector || '', set: document.body.dataset.set || '',
  group: document.body.dataset.group || '', sort: document.body.dataset.sort || 'number' };
let expanded = {};
const indexed = document.body.dataset.indexed === 'yes';
if (indexed) {
  state.p = document.body.dataset.p || '1';
  state.page = document.body.dataset.page || '1';
}
function indexedUrl(changes) {
  const values = { collector: state.collector, set: state.set, number: state.query, p: state.p, ...changes };
  const query = Object.entries(values).filter(([k, v]) => v && !(['p', 'page'].includes(k) && Number(v) === 1))
    .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
  return document.body.dataset.url + (query ? '?' + query : '');
}
try { expanded = JSON.parse(sessionStorage.getItem('fieldnotes-folders') || '{}'); } catch (error) { expanded = {}; }
function urlFor(id, group) {
  if (indexed) return indexedUrl({ note: id });
  const values = { ...state, group: group === undefined ? state.group : group };
  if (values.number) delete values.query;
  if (id) values.note = id;
  return document.body.dataset.url + '?' + Object.entries(values).filter(([, v]) => v).map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
}
function linkTo(id, label, parent, group) {
  const a = element('a', label, parent); a.href = urlFor(id, group); return a;
}
function renderShareLink(parent, id, page = 1) {
  const url = document.body.dataset.url + '?note=' + encodeURIComponent(id) + (page > 1 ? '&page=' + page : '');
  const share = element('div', null, parent, 'letter-share');
  const button = element('button', 'Copy note link', share); button.type = 'button';
  const status = element('span', '', share, 'letter-share-status muted');
  status.setAttribute('role', 'status');
  const field = element('input', null, share);
  field.type = 'url'; field.value = url; field.readOnly = true; field.hidden = true;
  field.setAttribute('aria-label', 'Note link');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(url);
      field.hidden = true; status.textContent = 'Link copied.';
    } catch (error) {
      field.hidden = false; field.focus(); field.select();
      status.textContent = 'Copy the selected link.';
    }
  });
}
function defaultFolderExpanded(folder) { return state.mode === 'collector' && folder.name === 'Carriker'; }
function expansionKey(folder) {
  const key = [state.mode, state.collector, state.query, folder.key];
  if (state.set) key.push(state.set);
  if (state.number) key.push('number=' + state.number);
  return JSON.stringify(key);
}
function countLabel(count, noun) { return count + ' ' + noun + (count === 1 ? '' : 's'); }
function collectorOptions(names) {
  const select = document.getElementById('collector-filter');
  select.replaceChildren();
  element('option', 'All collectors', select).value = '';
  for (const name of names) element('option', name, select).value = name;
  select.value = state.collector;
}
function pageLinks(parent, current, total, param, note) {
  if (total <= 1) return;
  const nav = element('nav', null, parent, 'letter-nav');
  const noun = param === 'page' ? 'Scan' : 'Page';
  nav.setAttribute('aria-label', noun + ' navigation');
  const steps = element('div', null, nav, 'nav-steps');
  for (const [number, label] of [[current - 1, 'Previous'], [current + 1, 'Next']]) {
    if (number < 1 || number > total) continue;
    element('a', label + ' ' + noun.toLowerCase(), steps, 'button').href = indexedUrl({ note, [param]: number });
  }
  element('span', noun + ' ' + current + ' of ' + total, nav, 'nav-position');
}
function renderIndex(result) {
  const root = document.getElementById('results'); root.replaceChildren();
  collectorOptions(result.collectors.map(c => c.name));
  const home = result.kind === 'home', search = result.kind === 'search';
  document.getElementById('browse-title').textContent = home ? 'Collectors' : search ? 'Search results' : state.set;
  document.getElementById('browse-intro').textContent = home ? 'Select a scan set to browse its cards in scan order.' : '';
  document.getElementById('message').textContent = countLabel(result.total, 'card') +
    (home ? ' · ' + countLabel(result.scans, 'scan') : search ? ' matching “' + state.query + '”' : '');
  if (home) {
    for (const c of result.collectors.filter(c => !state.collector || c.name === state.collector)) {
      const details = element('details', null, root, 'folder');
      details.open = c.name === state.collector || result.collectors.length === 1;
      const heading = element('summary', c.name, details);
      element('span', countLabel(c.count, 'card'), heading, 'folder-count');
      const list = element('ul', null, details, 'set-list');
      for (const set of c.sets) {
        const item = element('li', null, list);
        const label = set.name === c.name ? 'Loose cards' : set.name === '.' ? 'Collection root' :
          set.name.startsWith(c.name + '/') ? set.name.slice(c.name.length + 1) : set.name;
        element('a', label, item).href = indexedUrl({ collector: c.name, set: set.name, number: '', p: 1 });
        element('span', countLabel(set.count, 'card') + ' · ' + countLabel(set.scans, 'scan'), item, 'folder-count');
      }
    }
    return;
  }
  if (!result.rows.length) { element('p', 'No records on this page. Check the identifier or collector.', root); return; }
  const table = element('table', null, element('div', null, root, 'table-wrap'));
  const head = element('tr', null, element('thead', null, table));
  for (const title of ['Collection numbers', 'Species', 'Collector / set', 'Reading']) element('th', title, head).scope = 'col';
  const body = element('tbody', null, table);
  for (const row of result.rows) {
    const tr = element('tr', null, body);
    element('td', row.number_label, tr); element('td', row.species, tr);
    const location = element('td', row.collector, tr);
    element('span', row.sets.join(', '), location, 'field-note');
    const cell = element('td', null, tr);
    linkTo(row.note_id, 'Read note →', cell).setAttribute('aria-label', 'Read note: ' + row.number_label + ', ' + row.note_id);
    element('span', countLabel(row.pages, 'page') + ' · ' + row.execution, cell, 'field-note');
  }
  pageLinks(root, result.p, Math.ceil(result.total / result.pageSize), 'p');
}
function renderFolders(result) {
  if (indexed) return renderIndex(result);
  const root = document.getElementById('results'); root.replaceChildren();
  document.getElementById('message').textContent = countLabel(result.total, 'note') + ' in ' +
    countLabel(result.folders.length, state.mode === 'collector' ? 'collector folder' : 'species group');
  document.getElementById('browse-title').textContent = state.mode === 'collector' ? 'Collector folders' : 'Species groups';
  document.getElementById('browse-intro').textContent = state.mode === 'collector' ?
    'Expand a folder to browse notes by species and collection number. The most recently processed collector appears first. Number order is not chronological.' :
    'Browse source names and reviewed aliases across collectors. Alternative identifications stay uncertain. A note may appear under more than one name.';
  const filter = document.getElementById('collector-filter'); filter.replaceChildren();
  element('option', 'All collectors', filter).value = '';
  for (const collector of result.collectors) element('option', collector, filter).value = collector;
  filter.value = state.collector;
  const setFilter = document.getElementById('set-filter'); setFilter.replaceChildren();
  element('option', 'All sets', setFilter).value = '';
  const sets = result.sets;
  for (const set of sets) element('option', set, setFilter).value = set;
  if (state.set && !sets.includes(state.set)) element('option', state.set, setFilter).value = state.set;
  setFilter.value = state.set;
  document.getElementById('set-label').hidden = !sets.length && !state.set;
  if (!result.folders.length) element('p', state.query || state.set || state.collector ? 'No notes match this selection.' : 'No notes are available in this export.', root);
  for (const folder of result.folders) {
    const details = element('details', null, root, 'folder'), key = expansionKey(folder);
    details.open = Object.prototype.hasOwnProperty.call(expanded, key) ? expanded[key] : Boolean(state.query || state.group === folder.key || defaultFolderExpanded(folder));
    details.addEventListener('toggle', () => {
      expanded[key] = details.open;
      try { sessionStorage.setItem('fieldnotes-folders', JSON.stringify(expanded)); } catch (error) { /* Optional session persistence. */ }
    });
    const heading = element('summary', folder.name, details);
    element('span', countLabel(folder.notes.length, 'note') + (state.mode === 'species' ?
      ' · ' + (folder.rank || 'unknown rank') + ' · ' + folder.uncertain + ' uncertain' : ''), heading, 'folder-count');
    const wrap = element('div', null, details, 'table-wrap'), table = element('table', null, wrap);
    table.setAttribute('aria-label', 'Notes in ' + folder.name);
    const header = element('tr', null, element('thead', null, table));
    for (const label of ['Species', 'Collection numbers', 'Collector', 'Reading']) element('th', label, header).scope = 'col';
    const body = element('tbody', null, table);
    for (const note of folder.notes) {
      const row = element('tr', null, body), cat = note.catalogue;
      element('td', cat.species, row); element('td', cat.number_label, row);
      const collector = element('td', cat.collector, row);
      if (cat.scan_sets.length) element('span', cat.scan_sets.join(', '), collector, 'field-note');
      const reading = element('td', null, row), a = linkTo(note.note_id, 'Read note →', reading, folder.key);
      a.setAttribute('aria-label', 'Read note: ' + cat.title + ', ' + cat.collector + ', ' + note.note_id);
      element('span', countLabel(note.page_count, 'page') + ' · ' + note.execution, reading, 'field-note');
      if (note.summary_snippet) {
        const summaryRow = element('tr', null, body, 'catalogue-summary-row'), cell = element('td', null, summaryRow); cell.colSpan = 4;
        element('p', note.summary_snippet, cell, 'catalogue-summary');
      }
    }
    if (!state.query && folder.is_latest && result.folders.length > 1) element('hr', null, root, 'folder-divider');
  }
}
let catalogueRequest = 0;
function loadFolders() {
  const request = ++catalogueRequest;
  document.getElementById('catalogue').hidden = false; document.getElementById('record').hidden = true;
  document.getElementById('message').textContent = 'Loading field notes…';
  viewerRequest('listFolders', [{ ...state }], result => { if (request === catalogueRequest) renderFolders(result); },
    error => { if (request === catalogueRequest) document.getElementById('message').textContent = error.message; });
}
function renderNavigation(root, navigation, position) {
  const nav = element('nav', null, root, 'letter-nav'); nav.setAttribute('aria-label', 'Note navigation ' + position);
  const backLabel = indexed ? (state.query ? '← Search results' : state.set ? '← Scan set' : '← Collectors') : '← All notes';
  const back = element('a', backLabel, nav, 'button'); back.href = urlFor(null);
  if (!navigation) return;
  element('span', navigation.position ? 'Note ' + navigation.position + ' of ' + navigation.total : 'Outside current browse selection', nav, 'nav-position');
  const steps = element('div', null, nav, 'nav-steps');
  for (const [key, label] of [['previous', '← Previous note'], ['next', 'Next note →']]) {
    if (navigation[key]) {
      const a = linkTo(navigation[key].note_id, label, steps); a.className = 'button'; a.rel = key === 'previous' ? 'prev' : 'next';
    } else element('span', label, steps, 'button disabled').setAttribute('aria-disabled', 'true');
  }
}

function needsWiderTranscription(note) {
  const hasLongLine = ({ text }) => (text || '').split(/\r?\n/).some(line => line.trimEnd().length >= 72);
  return note.pages.some(page => hasLongLine(page) || (page.annotations || []).some(hasLongLine)) ||
    (note.translations || []).some(hasLongLine);
}

function renderSourceText(parent, text, tokens) {
  const pre = element('pre', null, parent);
  if (!tokens.size) { pre.textContent = text; return; }
  const numbers = /(?<![\p{L}\p{N}_])([0-9]+)(?:[ \t]*[-–—−][ \t]*([0-9]+))?(?![\p{L}\p{N}_])/gu;
  let cursor = 0;
  for (const match of text.matchAll(numbers)) {
    const [written, first, last] = match;
    if (!tokens.has(last ? first + '-' + last : first)) continue;
    let start = match.index, end = start + written.length;
    if (first === state.query) end = start + first.length;
    else if (last === state.query) start = end - last.length;
    pre.appendChild(document.createTextNode(text.slice(cursor, start)));
    const mark = element('mark', text.slice(start, end), pre, 'number-match');
    mark.title = 'Catalogue number ' + state.query;
    cursor = end;
  }
  pre.appendChild(document.createTextNode(text.slice(cursor)));
}

    function renderPage(root, scan, page, note, number, jobs, hits) {
      const pair = element('section', null, root, 'page-pair');
      pair.dataset.imageId = scan ? scan.image_id : page.image_id;
      element('h3', 'Page ' + number + (scan && scan.side ? ' · ' + scan.side : ''), pair);
      const columns = element('div', null, pair, 'page-columns');
      const figure = element('figure', null, columns, 'page-column');
      element('p', 'Original scan', figure, 'column-label');
      const sheet = element('div', null, figure, 'page-sheet scan-sheet');
      const canLoad = scan && ['mapped', 'folder_lookup'].includes(scan.mapping_status);
      const scanMessage = !scan ? 'No source scan is listed for this transcription.' :
        scan.status === 'missing' ? 'Scan missing from local inventory.' :
        scan.status !== 'ready' ? 'Inventory scan state: ' + scan.status :
        !canLoad ? 'No Google Drive mapping supplied. Configure the collection scan folder or an image mapping.' : 'Loading scan…';
      const message = element('p', scanMessage, sheet, 'scan-message');
      const caption = element('figcaption', scan ? scan.order + '. ' + scan.path : page.image_id, figure);
      if (canLoad && scan.status === 'ready') jobs.push({ scan, pair, sheet, caption, message });
      const text = element('section', null, columns, 'page-column');
      element('p', 'Source-language transcription', text, 'column-label');
      const transcript = element('div', null, text, 'page-sheet transcript-sheet');
      transcript.setAttribute('role', 'region');
      transcript.setAttribute('aria-label', 'Transcription, page ' + number);
      if (!page) element('p', 'No complete transcription is available for this page.', transcript);
      else {
        if (page.status !== 'text') element('p', 'Page status: ' + page.status, transcript, 'page-status');
        const tokens = new Set();
        for (const hit of hits) {
          const evidence = (note.identifiers || []).filter(field => field.value === hit.value).flatMap(field => field.evidence || []);
          if (!evidence.length || evidence.some(e => e.image_id === page.image_id)) tokens.add(hit.token);
        }
        renderSourceText(transcript, page.text, tokens);
        for (const annotation of page.annotations || []) {
          element('h4', 'Annotation (' + annotation.kind + ')', transcript);
          renderSourceText(transcript, annotation.text, tokens);
        }
      }
      for (const translation of note.translations || []) {
        if (translation.image_id !== pair.dataset.imageId) continue;
        element('h4', 'Optional translation · ' + translation.language, transcript);
        element('pre', translation.text, transcript);
      }
    }
    function loadScans(jobs, result) {
      // Sequential downloads preserve positions and bound simultaneous image memory.
      const job = jobs.shift();
      if (!job) return;
      viewerRequest('loadImage', [{ token: result.token, note_id: result.note.note_id, image_id: job.scan.image_id }], answer => {
        job.message.textContent = answer.message || '';
        if (answer.status === 'ready') {
          const image = element('img', null, job.sheet);
          image.alt = job.scan.filename;
          image.onload = () => {
            if (image.naturalWidth && image.naturalHeight) job.pair.style.setProperty('--page-ratio', image.naturalWidth + ' / ' + image.naturalHeight);
          };
          image.onerror = () => { image.hidden = true; job.message.textContent = 'Image bytes could not be displayed.'; };
          image.src = answer.data;
          const enlarge = element('button', 'Enlarge scan', job.caption);
          enlarge.addEventListener('click', () => enlargeScan(answer.data, job.scan.filename));
          if (answer.url) {
            const a = element('a', 'Open original in Drive ↗', job.caption);
            a.href = answer.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
          }
        }
        loadScans(jobs, result);
      }, error => { job.message.textContent = error.message; loadScans(jobs, result); });
    }


function enlargeScan(data, filename) {
  const dialog = element('dialog', null, document.body, 'scan-dialog');
  const close = element('button', 'Close enlarged scan', dialog);
  close.addEventListener('click', () => { dialog.close(); dialog.remove(); });
  dialog.addEventListener('cancel', () => dialog.remove());
  const image = element('img', null, dialog); image.src = data; image.alt = filename;
  dialog.showModal();
}
function renderMetadata(root, note) {
  const section = element('section', null, root, 'panel'); element('h3', 'Note details', section);
  const grid = element('dl', null, section, 'metadata-grid');
  const values = [['Collector', note.catalogue.collector + ' (' + note.catalogue.collector_basis + ')'],
    ['Collection numbers', note.catalogue.number_label], ['Species', note.catalogue.species],
    ['Archival ID', note.note_id], ['Transcription', note.execution], ['Grouping', note.grouping],
    ['Metadata review', note.metadata_review], ['Transcription review', note.transcription_review]];
  if (note.catalogue.scan_sets.length) values.push(['Scan set', note.catalogue.scan_sets.join(', ')]);
  for (const [label, text] of values) {
    const item = element('div', null, grid); element('dt', label, item); element('dd', text, item);
  }
  for (const [key, label] of [['collector','Collector as written'], ['language','Language'], ['document_type','Document type'], ['physical_hand','Physical hand']]) {
    const field = (note.metadata || {})[key];
    if (!field || !field.value) continue;
    const item = element('div', null, grid); element('dt', label, item); element('dd', field.value + ' (' + field.certainty + ')', item);
  }
  for (const key of ['identifiers', 'taxa', 'localities', 'dates', 'observations']) {
    if (!(note[key] || []).length) continue;
    element('h3', key[0].toUpperCase() + key.slice(1), section);
    for (const field of note[key]) element('p', (field.entry_id ? field.entry_id + ' · ' : '') + (field.value || 'Unknown') +
      ' (' + field.certainty + ')' + [field.number_type, field.namespace, field.rank, field.role, field.event, field.kind,
        field.source_uncertain || field.alternative_group ? 'uncertain identification' : ''].filter(Boolean).map(v => ' · ' + v).join(''), section, 'preserve');
  }
  if ((note.notes || []).length) { element('h3', 'Separate notes', section); element('p', note.notes.join('\n'), section, 'preserve'); }
  if (note.active === false) element('p', 'Retired grouping retained for history.', section, 'notice');
  return section;
}
function renderNote(result) {
  Object.assign(state, result.context || {});
  const root = document.getElementById('record'); root.replaceChildren(); root.hidden = false;
  document.getElementById('catalogue').hidden = true;
  const note = result.note;
  if (indexed) collectorOptions(result.collectors);
  root.dataset.wideTranscription = String(needsWiderTranscription(note));
  renderNavigation(root, result.navigation, 'top');
  const heading = element('header', null, root, 'letter-heading');
  element('p', note.catalogue.collector, heading, 'eyebrow'); element('h2', note.catalogue.title, heading);
  element('p', countLabel(note.scans.length, 'page') + ' · ' + note.execution, heading, 'muted');
  const hits = result.numberMatches || [];
  if (hits.length) element('p', 'Matched catalogue number ' + state.query, heading, 'field-note');
  if (note.summary) {
    const summary = element('section', null, root, 'letter-summary');
    element('p', 'Interpretive summary', summary, 'eyebrow'); element('p', note.summary, summary);
  }
  const jobs = [], pages = new Map(note.pages.map(p => [p.image_id, p]));
  if (indexed) pageLinks(root, state.page, note.scans.length, 'page', note.note_id);
  note.scans.forEach((scan, index) => {
    if (!indexed || index + 1 === state.page) renderPage(root, scan, pages.get(scan.image_id), note, index + 1, jobs, hits);
  });
  const scans = new Set(note.scans.map(s => s.image_id)); let number = note.scans.length;
  for (const page of note.pages) if (!scans.has(page.image_id)) renderPage(root, null, page, note, ++number, jobs, hits);
  if (!number) element('p', 'No source pages or complete transcription are available.', root, 'notice');
  const metadata = renderMetadata(root, note);
  if ((indexed || result.publicMode) && /^note_[0-9a-f]{32}$/.test(note.note_id)) renderShareLink(metadata, note.note_id, indexed ? state.page : 1);
  const details = element('details', null, root, 'provenance');
  element('summary', indexed || result.publicMode ? 'Metadata evidence' : 'Metadata evidence and provenance', details);
  const evidence = { metadata: note.metadata, entries: note.entries, identifiers: note.identifiers, taxa: note.taxa,
    localities: note.localities, dates: note.dates, observations: note.observations };
  if (!indexed && !result.publicMode) Object.assign(evidence, { review_reasons: note.review_reasons, provenance: note.provenance, partial_response: note.partial_response });
  element('pre', JSON.stringify(evidence, null, 2), details);
  renderNavigation(root, result.navigation, 'bottom'); loadScans(jobs, result);
}
function openNote(id) {
  document.getElementById('message').textContent = 'Loading note…';
  viewerRequest('loadNote', [id, { ...state }], result => { document.getElementById('message').textContent = ''; renderNote(result); },
    error => { document.getElementById('message').textContent = error.message;
      const root = document.getElementById('record'); root.hidden = false; renderNavigation(root, null, 'error'); });
}
document.getElementById('query').value = state.query;
document.getElementById('browse-mode').value = state.mode;
document.getElementById('sort-order').value = state.sort;
if (indexed) {
  const form = document.getElementById('search');
  document.querySelector('.site-header').appendChild(form);
  document.getElementById('legacy-controls').hidden = true;
  document.getElementById('clear-search').addEventListener('click', () => {
    document.getElementById('query').value = '';
    document.getElementById('collector-filter').value = '';
    form.submit();
  });
} else {
  document.getElementById('query-label').textContent = 'Search collectors, collection numbers, species, localities, or saved text';
  document.getElementById('search').addEventListener('submit', event => {
    event.preventDefault(); state.query = document.getElementById('query').value.trim();
    state.number = /^[0-9]+$/.test(state.query) ? state.query : '';
    state.group = ''; loadFolders();
  });
  document.getElementById('clear-search').addEventListener('click', () => {
    document.getElementById('query').value = ''; state.query = ''; state.number = ''; state.collector = ''; state.set = ''; state.group = ''; loadFolders();
  });
  for (const [id, key] of [['browse-mode', 'mode'], ['collector-filter', 'collector'], ['set-filter', 'set'], ['sort-order', 'sort']]) {
    document.getElementById(id).addEventListener('change', () => {
      state[key] = document.getElementById(id).value; state.group = '';
      if (key === 'collector') state.set = '';
      loadFolders();
    });
  }
}
if (!document.getElementById('initial-error').textContent.trim()) {
  if (document.body.dataset.note) openNote(document.body.dataset.note); else loadFolders();
}
