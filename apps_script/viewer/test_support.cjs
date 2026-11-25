// Synthetic, offline Apps Script/DOM adapters. No Google credentials or live calls.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const server = ['Code.gs', 'Index.gs'].map(name => fs.readFileSync(path.join(__dirname, name), 'utf8')).join('\n');
const html = fs.readFileSync(path.join(__dirname, 'Viewer.html'), 'utf8');
const bytes = Buffer.from('synthetic JPEG bytes for server validation; browser preview supplies actual JPEGs');
const sha = value => crypto.createHash('sha256').update(value).digest('hex');
const id = (prefix, n) => prefix + '_' + n.toString(16).padStart(32, '0');
function seal(bundle) {
  const { content_sha256, ...payload } = bundle;
  return { content_sha256: sha(JSON.stringify(payload)), ...payload };
}
function fixture() {
  const scans = [2, 1].map((n, i) => ({ image_id: id('img', n), path: 'Carriker/card' + n + '.jpg', filename: 'card' + n + '.jpg',
    folder: 'Carriker', status: 'ready', order: i + 1, size: bytes.length, sha256: sha(bytes), drive_file_id: 'synthetic_drive_' + n, mapping_status: 'mapped' }));
  const note = { note_id: id('note', 1), active: true, execution: 'complete', discovery: 'ready', grouping: 'reviewed',
    metadata_review: 'unreviewed', transcription_review: 'unreviewed', number_order: 0,
    hints: { collector_folder: 'Carriker', filenames: scans.map(s => s.filename) },
    catalogue: { collector: 'Carriker', collector_folder: 'Carriker', collector_basis: 'folder attribution', numbers: ['0012','9846'],
      number_label: '0012, 9846', species: 'Example bird', title: 'Example bird — 0012, 9846', aliases: ['Reviewed alias'],
      species_groups: [{ key: 'name:species:example bird', name: 'Example bird', rank: 'species', uncertain: false, role: 'principal', as_written: 'Example bird' }] },
    metadata: {}, entries: [], identifiers: [], taxa: [], localities: [], dates: [], observations: [],
    summary: 'Synthetic summary only.', notes: [], translations: [], review_reasons: [], partial_response: '',
    pages: [{ image_id: id('img', 2), status: 'text', text: '<img src=x onerror=bad()> & café\n0012 ♂ ♀', annotations: [] },
      { image_id: id('img', 1), status: 'blank', text: '[blank]', annotations: [] }], scans,
    provenance: { model: 'synthetic', prompt: 'INTERNAL_PROMPT' } };
  return seal({ schema_version: 1, export_kind: 'fieldnotes-viewer', exported_at: '2026-11-17T12:00:00Z', notes: [note] });
}
function context(bundle = fixture(), options = {}) {
  let gateReads = 0, imageReads = 0, folderReads = 0, exportReads = 0, lockReleases = 0;
  const cache = options.cache || new Map(), lookups = [];
  const indexReads = [];
  const blob = { getDataAsString: () => options.exportText === undefined ? JSON.stringify(options.noSeal ? bundle : seal(bundle)) : options.exportText,
    getBytes: () => [...bytes] };
  const file = { getName: () => 'synthetic', isTrashed: () => false, getId: () => 'export', getSize: () => options.exportSize || Buffer.byteLength(JSON.stringify(bundle)), getBlob: () => blob };
  const image = { ...file, getSize: () => bytes.length, getMimeType: () => 'image/jpeg', getBlob: () => { imageReads++; return blob; } };
  function iterator(items) { let i = 0; return { hasNext: () => i < items.length, next: () => items[i++] }; }
  function folder(tree) {
    return { isTrashed: () => Boolean(tree.trashed), getFoldersByName(name) { lookups.push('folder:' + name); return iterator(((tree.folders || {})[name] || []).map(folder)); },
      getFilesByName(name) { lookups.push('file:' + name); return iterator(((tree.files || {})[name] || []).map(key =>
        options.imageProvider ? options.imageProvider(key) : { ...image, getId: () => key, ...options.image })); } };
  }
  const tree = options.folderTree || { folders: { Carriker: [{ files: { 'card2.jpg': ['synthetic_resolved_2'], 'card1.jpg': ['synthetic_resolved_1'] } }] } };
  const sandbox = {
    Date: class extends Date { static now() { return options.now === undefined ? 100000 : options.now; } },
    LockService: { getScriptLock: () => ({ tryLock: () => !options.lockBusy, releaseLock: () => { lockReleases++; } }) },
    CacheService: { getUserCache: () => ({ get: k => cache.get(k), put: (k, v) => cache.set(k, v) }),
      getScriptCache: () => ({ get: k => { if (options.cacheError) throw Error('private cache error'); return cache.get(k) || null; }, put: (k, v) => cache.set(k, v) }) },
    DriveApp: { getFileById(key) {
      if (key === 'gate') { gateReads++; if (options.deny) throw Error('denied'); return file; }
      if (key === 'export') { exportReads++; if (options.exportError) throw Error('PRIVATE Drive data'); return file; }
      if (options.imageError) throw Error('hidden existence');
      if (options.imageProvider) return options.imageProvider(key);
      return { ...image, getId: () => key, ...options.image };
    }, getFolderById(key) {
      folderReads++;
      if (key === 'parent' && options.indexParent) {
        if (options.deny) throw Error('inaccessible parent');
        return { isTrashed: () => false, getName: () => 'Transcriptions', getFoldersByName(name) {
          lookups.push('folder:' + name);
          return iterator(Array.from({length: options.indexChildren ?? 1}, () => sandbox.DriveApp.getFolderById('index')));
        }};
      }
      if (key === 'index' && options.indexFile) return { isTrashed: () => false, getName: () => 'Field_notes_index', getFilesByName(name) {
        indexReads.push(name);
        const raw = options.indexFile(name);
        if (raw == null) return iterator([]);
        const data = Buffer.from(raw);
        return iterator([{ isTrashed: () => false, getSize: () => data.length,
          getBlob: () => ({ getBytes: () => Array.from(new Int8Array(data)), getDataAsString: () => data.toString('utf8') }) }]);
      }};
      if (options.folderError || key !== options.scanRoot) throw Error('hidden folder');
      return folder(tree);
    } },
    Utilities: { DigestAlgorithm: { SHA_256: 'sha256' }, Charset: { UTF_8: 'utf8' },
      computeDigest: (algorithm, value, charset) => Array.from(new Int8Array(
        crypto.createHash(algorithm).update(Buffer.from(value, charset)).digest())),
      base64Encode: v => Buffer.from(v).toString('base64') }, console
  };
  vm.createContext(sandbox);
  let code = server.replace(/\bACCESS_FILE_ID:\s*'[^']*'/, "ACCESS_FILE_ID: " + JSON.stringify(options.indexParent ? '' : 'gate'))
    .replace(/\bEXPORT_FILE_ID:\s*'[^']*'/, "EXPORT_FILE_ID: 'export'")
    .replace("INDEX_FOLDER_ID: ''", "INDEX_FOLDER_ID: " + JSON.stringify(options.indexFile && !options.indexParent ? 'index' : ''))
    .replace("INDEX_PARENT_FOLDER_ID: ''", "INDEX_PARENT_FOLDER_ID: " + JSON.stringify(options.indexParent ? 'parent' : ''))
    .replace(/\bPUBLIC_MODE:\s*false/, 'PUBLIC_MODE: ' + Boolean(options.publicMode))
    .replace(/\bPUBLIC_NOTE_IDS:\s*\[\]/, 'PUBLIC_NOTE_IDS: ' + JSON.stringify(options.allowlist || bundle.notes.map(n => n.note_id)))
    .replace(/\bSCAN_ROOT_FOLDER_ID:\s*'[^']*'/, 'SCAN_ROOT_FOLDER_ID: ' + JSON.stringify(options.scanRoot || ''));
  vm.runInContext(code, sandbox);
  return { sandbox, lookups, indexReads, cache, counts: () => ({ gateReads, imageReads, folderReads, exportReads, lockReleases }) };
}
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.textContent = ''; this.dataset = {}; this.attributes = {}; this.events = {}; this.style = { setProperty(n, v) { this[n] = v; } }; }
  appendChild(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  addEventListener(n, fn) { this.events[n] = fn; }
  setAttribute(n, v) { this.attributes[n] = v; }
  showModal() { this.open = true; }
  focus() { this.focused = true; }
  scrollIntoView() { this.scrolledIntoView = true; }
  select() { this.selected = true; }
  close() { this.open = false; }
  remove() { this.removed = true; }
}
function frontend(dataset = {}, saved = {}) {
  const ids = Object.fromEntries(['record','message','results','initial-error','query','search','catalogue','clear-search','browse-title','browse-intro','browse-mode','collector-filter','set-label','set-filter','sort-order'].map(id => [id,new Element(id)]));
  for (const id of ['query-label', 'legacy-controls', 'site-header']) ids[id] = new Element(id);
  const body = new Element('body'); body.dataset = { url: 'https://script.google.com/synthetic/exec', ...dataset };
  const calls = [], catalogueCalls = [], noteCalls = [];
  const runner = { withSuccessHandler(fn) { this.success = fn; return this; }, withFailureHandler(fn) { this.failure = fn; return this; },
    loadImage(req) { calls.push({ req, success: this.success, failure: this.failure }); },
    listFolders(context) { catalogueCalls.push({ context, success: this.success, failure: this.failure }); },
    loadNote(id, context) { noteCalls.push({ id, context, success: this.success, failure: this.failure }); } };
  const sandbox = { document: { body, querySelector: () => ids['site-header'], getElementById: id => ids[id], createElement: tag => new Element(tag),
    createTextNode: text => Object.assign(new Element('#text'), { textContent: text }) },
    google: { script: { run: runner } }, sessionStorage: { getItem: k => saved[k], setItem: (k, v) => { saved[k] = v; } } };
  vm.createContext(sandbox); vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], sandbox);
  return { sandbox, ids, calls, catalogueCalls, noteCalls, saved };
}
function nodes(root) { return [root, ...root.children.flatMap(nodes)]; }
module.exports = { context, fixture, frontend, nodes, id, sha, seal, bytes, server, html };
