/** Independent read-only Field Notes viewer. No deployment or IDs supplied. */
const SETTINGS = Object.freeze({
  PUBLIC_MODE: false,
  PUBLIC_NOTE_IDS: [], // Explicit reviewed publication allowlist, used only in public mode.
  ACCESS_FILE_ID: '',
  EXPORT_FILE_ID: '',
  SCAN_ROOT_FOLDER_ID: '', // The Field Notes root, containing collector subfolders.
  MAX_EXPORT_BYTES: 10 * 1024 * 1024,
  MAX_IMAGE_BYTES: 12 * 1024 * 1024,
  MAX_NOTE_IMAGE_BYTES: 24 * 1024 * 1024,
  PUBLIC_REQUESTS_PER_MINUTE: 120,
  PUBLIC_IMAGES_PER_MINUTE: 60
});

function sha_(value) {
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, value)
    .map(byte => ('0' + (byte & 255).toString(16)).slice(-2)).join('');
}
function validId_(value, prefix) {
  return typeof value === 'string' && new RegExp('^' + prefix + '_[0-9a-f]{32}$').test(value);
}
function validateImageRequest_(request) {
  if (!request || !validId_(request.note_id, 'note') || !validId_(request.image_id, 'img') ||
      typeof request.token !== 'string' || request.token.length > 200) throw new Error('Invalid image request.');
}
function bundle_(imageRequest) {
  gate_(imageRequest);
  let value, raw;
  try {
    const file = DriveApp.getFileById(SETTINGS.EXPORT_FILE_ID);
    if (file.isTrashed() || file.getSize() > SETTINGS.MAX_EXPORT_BYTES) throw new Error('Unavailable');
    raw = file.getBlob().getDataAsString('UTF-8');
    value = JSON.parse(raw);
  } catch (error) {
    throw new Error('Viewer export is unavailable. Check access, valid JSON and the 10 MiB limit.');
  }
  if (!value || value.schema_version !== 1 || value.export_kind !== 'fieldnotes-viewer' || !Array.isArray(value.notes))
    throw new Error('Unsupported viewer export schema.');
  const header = /^\{"content_sha256":"([0-9a-f]{64})",/.exec(raw);
  if (!header || value.content_sha256 !== header[1] || sha_('{' + raw.slice(header[0].length)) !== header[1])
    throw new Error('Viewer export content hash is inconsistent; regenerate the export.');
  const ids = new Set(), paths = new Map(), images = new Map();
  for (const note of value.notes) {
    if (!note || !validId_(note.note_id, 'note') || ids.has(note.note_id) || !Array.isArray(note.scans) || !Array.isArray(note.pages) || !note.catalogue)
      throw new Error('Invalid or duplicate archival IDs in export.');
    ids.add(note.note_id);
    const pageIds = new Set(), scanIds = new Set();
    for (const page of note.pages) {
      if (!validId_(page.image_id, 'img') || pageIds.has(page.image_id) || typeof page.text !== 'string') throw new Error('Invalid or duplicate page sections.');
      pageIds.add(page.image_id);
    }
    for (const [index, scan] of note.scans.entries()) {
      if (!validId_(scan.image_id, 'img') || scanIds.has(scan.image_id) || scan.order !== index + 1 || typeof scan.path !== 'string')
        throw new Error('Invalid scan manifest order or duplicate image IDs.');
      scanIds.add(scan.image_id);
      const key = scan.path.toLocaleLowerCase();
      if (paths.has(key) && paths.get(key) !== scan.image_id) throw new Error('Duplicate scan paths in export.');
      paths.set(key, scan.image_id);
      if (scan.status === 'ready') {
        if (!Number.isSafeInteger(scan.size) || scan.size < 1 || !/^[0-9a-f]{64}$/.test(scan.sha256 || '')) throw new Error('Invalid image size/hash in export.');
        const manifest = scan.path + ':' + scan.size + ':' + scan.sha256;
        if (images.has(scan.image_id) && images.get(scan.image_id) !== manifest) throw new Error('Inconsistent image identity in export.');
        images.set(scan.image_id, manifest);
      }
    }
    if (note.execution === 'complete' && (note.pages.length !== note.scans.length || note.pages.some((p, i) => p.image_id !== note.scans[i].image_id)))
      throw new Error('Complete note page coverage differs from its scans.');
  }
  if (SETTINGS.PUBLIC_MODE) value.notes = value.notes.filter(n => n.active === true && SETTINGS.PUBLIC_NOTE_IDS.includes(n.note_id));
  return { value, token: sha_(raw) };
}
function scalars_(source, keys) {
  const result = {};
  for (const key of keys) {
    const v = (source || {})[key];
    if (v === null || ['string', 'number', 'boolean'].includes(typeof v)) result[key] = v;
  }
  return result;
}
function strings_(values) { return Array.isArray(values) ? values.filter(v => typeof v === 'string') : []; }
function field_(value) {
  return { ...scalars_(value, ['value', 'normalized', 'certainty', 'entry_id', 'number_type', 'namespace', 'role', 'name_type', 'rank', 'source_uncertain', 'alternative_group', 'precision', 'event', 'kind']),
    evidence: (value.evidence || []).map(e => scalars_(e, ['image_id', 'entry_id', 'quote', 'location'])) };
}
function catalogue_(cat) {
  return { ...scalars_(cat, ['collector', 'collector_folder', 'collector_basis', 'species', 'number_label', 'title']),
    numbers: strings_(cat.numbers), aliases: strings_(cat.aliases),
    species_groups: (cat.species_groups || []).map(g => scalars_(g, ['key', 'name', 'rank', 'uncertain', 'role', 'as_written'])) };
}
function publicNote_(note) {
  const result = scalars_(note, ['note_id', 'active', 'execution', 'discovery', 'grouping', 'metadata_review', 'transcription_review', 'summary']);
  result.hints = { collector_folder: note.hints.collector_folder, filenames: strings_(note.hints.filenames) };
  result.catalogue = catalogue_(note.catalogue);
  result.metadata = {};
  for (const key of ['collector', 'language', 'document_type', 'physical_hand']) if (note.metadata[key]) result.metadata[key] = field_(note.metadata[key]);
  for (const key of ['identifiers', 'taxa', 'localities', 'dates', 'observations']) result[key] = (note[key] || []).map(field_);
  result.entries = (note.entries || []).map(e => ({ ...scalars_(e, ['entry_id', 'image_id', 'label']), evidence: (e.evidence || []).map(v => scalars_(v, ['image_id', 'entry_id', 'quote', 'location'])) }));
  result.pages = note.pages.map(p => ({ ...scalars_(p, ['image_id', 'status', 'text']), annotations: (p.annotations || []).map(a => scalars_(a, ['kind', 'text'])) }));
  result.notes = strings_(note.notes);
  result.translations = (note.translations || []).map(t => scalars_(t, ['image_id', 'language', 'text']));
  result.scans = note.scans.map(s => ({ ...scalars_(s, ['image_id', 'path', 'filename', 'folder', 'status', 'order']),
    mapping_status: s.drive_file_id ? 'mapped' : SETTINGS.SCAN_ROOT_FOLDER_ID ? 'folder_lookup' : 'missing_mapping' }));
  return result;
}
function context_(input) {
  input = input || {};
  const result = { query: String(input.query || '').trim(), mode: String(input.mode || 'collector'), collector: String(input.collector || ''),
    group: String(input.group || ''), sort: String(input.sort || 'number') };
  if (result.query.length > 200 || result.collector.length > 500 || result.group.length > 2000 ||
      !['collector', 'species'].includes(result.mode) || !['number', 'species'].includes(result.sort)) throw new Error('Invalid browse/search options.');
  return result;
}
function searchText_(source) {
  // Search only explicitly publishable reading fields in public mode; no hidden-field oracle.
  const n = publicNote_(source);
  return JSON.stringify(n).toLocaleLowerCase();
}
function matches_(notes, context) {
  return notes.filter(n => n.active !== false && (!context.collector || [n.catalogue.collector, n.catalogue.collector_folder].includes(context.collector)) &&
    (!context.query || searchText_(n).includes(context.query.toLocaleLowerCase()))).sort((a, b) =>
      (context.sort === 'species' ? a.catalogue.species.localeCompare(b.catalogue.species) : 0) || a.number_order - b.number_order || a.note_id.localeCompare(b.note_id));
}
function memberships_(note, mode) {
  return mode === 'collector' ? [{ key: note.catalogue.collector_folder, name: note.catalogue.collector_folder, uncertain: false }] : note.catalogue.species_groups;
}
function row_(note) {
  const snippet = Array.from((note.summary || '').replace(/\s+/g, ' ').trim());
  return { note_id: note.note_id, catalogue: catalogue_(note.catalogue), page_count: note.scans.length,
    execution: note.execution, metadata_review: note.metadata_review, transcription_review: note.transcription_review,
    summary_snippet: snippet.length <= 360 ? snippet.join('') : snippet.slice(0, 359).join('') + '…' };
}
function listFolders(input) {
  const { value } = bundle_(), context = context_(input), matches = matches_(value.notes, context), groups = new Map();
  for (const note of matches) for (const member of memberships_(note, context.mode)) {
    if (!groups.has(member.key)) groups.set(member.key, { key: member.key, name: member.name, rank: member.rank || null, notes: [], confirmed: 0, uncertain: 0 });
    const group = groups.get(member.key);
    if (!group.notes.some(n => n.note_id === note.note_id)) {
      group.notes.push(row_(note)); group[member.uncertain ? 'uncertain' : 'confirmed']++;
    }
  }
  const active = value.notes.filter(n => n.active !== false);
  const folders = [...groups.values()].sort((a, b) => a.name.localeCompare(b.name) || a.key.localeCompare(b.key));
  if (context.mode === 'collector') {
    const activity = new Map();
    for (const note of active) {
      const stamp = Date.parse(note.processed_at), key = note.catalogue.collector_folder;
      if (Number.isFinite(stamp)) activity.set(key, Math.max(activity.get(key) || 0, stamp));
    }
    folders.sort((a, b) => (activity.get(b.key) || 0) - (activity.get(a.key) || 0));
    if (folders.length && activity.has(folders[0].key)) folders[0].is_latest = true;
  }
  return { total: matches.length, context, collectors: [...new Set(active.map(n => n.catalogue.collector_folder))].sort(), folders };
}
function selectNote_(value, id) {
  if (!validId_(id, 'note')) throw new Error('Invalid note ID.');
  const note = value.notes.find(n => n.note_id === id);
  if (!note) throw new Error('Note is absent from this export.');
  return note;
}
function loadNote(id, input) {
  const { value, token } = bundle_(), note = selectNote_(value, id), context = context_(input);
  let siblings = matches_(value.notes, context);
  if (context.group) siblings = siblings.filter(n => memberships_(n, context.mode).some(g => g.key === context.group));
  const index = siblings.findIndex(n => n.note_id === id);
  const display = SETTINGS.PUBLIC_MODE ? publicNote_(note) : { ...note, scans: note.scans.map(s => ({ ...s,
    mapping_status: s.drive_file_id ? 'mapped' : SETTINGS.SCAN_ROOT_FOLDER_ID ? 'folder_lookup' : 'missing_mapping' })) };
  return { note: display, token, context, publicMode: SETTINGS.PUBLIC_MODE,
    navigation: { position: index + 1, total: siblings.length, group: context.group,
      previous: index > 0 ? row_(siblings[index - 1]) : null,
      next: index >= 0 && index + 1 < siblings.length ? row_(siblings[index + 1]) : null } };
}
function doGet(e) {
  const p = (e && e.parameter) || {}, page = HtmlService.createTemplateFromFile('Viewer');
  page.noteId = String(p.note || '').slice(0, 100);
  page.query = String(p.query || p.q || '').slice(0, 200); page.mode = String(p.mode || 'collector').slice(0, 20);
  page.collector = String(p.collector || '').slice(0, 500); page.group = String(p.group || '').slice(0, 2000);
  page.sort = String(p.sort || 'number').slice(0, 20); page.appUrl = ScriptApp.getService().getUrl(); page.error = '';
  try { gate_(); } catch (error) { page.error = error.message; }
  return page.evaluate().setTitle('Museum field notes').addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

function publicBudget_(imageRequest) {
  const busy = 'Viewer is busy. Please wait a minute and reload.';
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(100)) throw new Error(busy);
  try {
    const cache = CacheService.getScriptCache();
    const key = 'public-viewer-v1:' + Math.floor(Date.now() / 60000);
    const counts = JSON.parse(cache.get(key) || '{"requests":0,"images":0}');
    if (counts.requests >= SETTINGS.PUBLIC_REQUESTS_PER_MINUTE ||
        (imageRequest && counts.images >= SETTINGS.PUBLIC_IMAGES_PER_MINUTE)) throw new Error(busy);
    counts.requests++;
    if (imageRequest) counts.images++;
    cache.put(key, JSON.stringify(counts), 70);
  } catch (error) {
    throw new Error(busy);
  } finally {
    lock.releaseLock();
  }
}

function gate_(imageRequest) {
  if (!SETTINGS.EXPORT_FILE_ID || (!SETTINGS.PUBLIC_MODE && !SETTINGS.ACCESS_FILE_ID)) {
    throw new Error('Viewer is not configured. Set the access-gate and export file IDs.');
  }
  if (SETTINGS.PUBLIC_MODE) {
    publicBudget_(imageRequest);
    return; // Owner's Drive access is not visitor authorization; publication is intentional.
  }
  try {
    const file = DriveApp.getFileById(SETTINGS.ACCESS_FILE_ID);
    if (file.isTrashed()) throw new Error('Removed');
    file.getName(); // Recheck under USER_ACCESSING on every page and RPC.
  } catch (error) {
    throw new Error('Access denied. Sign in with an account allowed to read the configured collection access file.');
  }
}

function singleDriveChild_(iterator, path) {
  if (!iterator.hasNext()) return { status: 'path_unavailable',
    message: 'Scan path is not visible to this account in the collection folder: ' + path +
      '. Check the collection folder, exact names and access permissions.' };
  const item = iterator.next();
  if (iterator.hasNext()) return { status: 'ambiguous_path',
    message: 'More than one Drive item matches: ' + path + '. Supply an explicit image mapping to select the original.' };
  if (item.isTrashed()) return { status: 'missing_scan', message: 'An item in the scan path is in Trash: ' + path };
  return { item };
}

function scanByPath_(scan) {
  const path = scan.path;
  if (typeof path !== 'string' || path.length > 4096 || /[\\\u0000-\u001f]/.test(path) || /^[A-Za-z]:/.test(path)) {
    return { status: 'invalid_path', message: 'Exported scan path must be relative to the collection folder.' };
  }
  const parts = path.split('/');
  if (parts.length > 32 || parts.some(part => !part || part === '.' || part === '..')) {
    return { status: 'invalid_path', message: 'Exported scan path must be relative to the collection folder.' };
  }
  let folder = DriveApp.getFolderById(SETTINGS.SCAN_ROOT_FOLDER_ID);
  if (folder.isTrashed()) return { status: 'missing_scan', message: 'Configured collection folder is in Trash.' };
  for (const name of parts.slice(0, -1)) {
    const selected = singleDriveChild_(folder.getFoldersByName(name), path);
    if (!selected.item) return selected;
    folder = selected.item;
  }
  const selected = singleDriveChild_(folder.getFilesByName(parts[parts.length - 1]), path);
  return selected.item ? { file: selected.item } : selected;
}

function loadImage(request) {
  validateImageRequest_(request);
  const { value, token } = bundle_(true);
  if (!request || typeof request !== 'object') throw new Error('Invalid image request.');
  if (token !== request.token) return { status: 'stale_export', message: 'Export changed; reload this note.' };
  const note = selectNote_(value, request.note_id);
  const scan = note.scans.find(image => image.image_id === request.image_id);
  if (!scan) throw new Error('Image is not part of this note.');
  if (scan.status === 'missing') return { status: 'missing_scan', message: 'Scan missing from the local inventory.' };
  if (scan.status !== 'ready') return { status: 'unavailable', message: 'Inventory scan state: ' + scan.status };
  if (!scan.drive_file_id && !SETTINGS.SCAN_ROOT_FOLDER_ID) {
    return { status: 'missing_mapping', message: 'No Google Drive mapping supplied. Set the collection scan folder or provide an image mapping.' };
  }
  if (scan.drive_file_id && !/^[A-Za-z0-9_-]{10,}$/.test(scan.drive_file_id)) throw new Error('Invalid Drive mapping.');
  if (!scan.drive_file_id && !/^[A-Za-z0-9_-]{10,}$/.test(SETTINGS.SCAN_ROOT_FOLDER_ID)) throw new Error('Invalid collection folder ID.');
  const planned = note.scans.reduce((n, item) => n + (item.size || 0), 0);
  if (planned > SETTINGS.MAX_NOTE_IMAGE_BYTES || scan.size > SETTINGS.MAX_IMAGE_BYTES) {
    return { status: 'too_large', message: 'Scan display limit reached; use the original Drive file.' };
  }
  let file;
  try {
    if (scan.drive_file_id) file = DriveApp.getFileById(scan.drive_file_id);
    else {
      const resolved = scanByPath_(scan);
      if (!resolved.file) return resolved;
      file = resolved.file;
    }
    if (file.isTrashed()) return { status: 'missing_scan', message: 'Drive scan is in Trash.' };
    if (file.getSize() > SETTINGS.MAX_IMAGE_BYTES || file.getMimeType() !== 'image/jpeg') {
      return { status: 'unavailable', message: 'Drive file is too large or is not JPEG.' };
    }
    const bytes = file.getBlob().getBytes();
    if (bytes.length !== scan.size) return { status: 'changed_scan', message: 'Drive scan size differs from the export; review the scan path or mapping.' };
    const sha = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, bytes)
      .map(byte => ('0' + (byte & 255).toString(16)).slice(-2)).join('');
    if (sha !== scan.sha256) return { status: 'changed_scan', message: 'Drive scan hash differs from the export; review the scan path or mapping.' };
    return { status: 'ready', data: 'data:image/jpeg;base64,' + Utilities.base64Encode(bytes),
      url: SETTINGS.PUBLIC_MODE ? '' : 'https://drive.google.com/file/d/' + encodeURIComponent(file.getId()) + '/view' };
  } catch (error) {
    // Drive deliberately hides whether an inaccessible ID exists. Do not claim deletion.
    return { status: 'inaccessible', message: 'Drive scan or its collection folder cannot be read by this account. It may have been removed; Drive does not distinguish these cases.' };
  }
}
