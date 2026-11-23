/** Indexed Drive adapter. Only Code.gs exposes RPCs. All client keys resolve via the manifest. */
function indexReader_(imageRequest) {
  const gate = gate_(imageRequest);
  let folder = gate || DriveApp.getFolderById(SETTINGS.INDEX_FOLDER_ID || SETTINGS.INDEX_PARENT_FOLDER_ID);
  if (!SETTINGS.INDEX_FOLDER_ID) {
    const children = folder.getFoldersByName('Field_notes_index');
    if (!children.hasNext()) throw new Error('Field_notes_index is missing. Publish the index and wait for Drive sync.');
    folder = children.next();
    if (children.hasNext()) throw new Error('Multiple Field_notes_index folders. Configure the intended index folder ID.');
  }
  if (folder.isTrashed()) throw new Error('Viewer index folder is unavailable.');
  const memo = new Map();
  function read(name, ref) {
    if (memo.has(name)) return memo.get(name);
    const matches = folder.getFilesByName(name);
    if (!matches.hasNext()) throw new Error('Index file unavailable. Check Drive sync and access.');
    const file = matches.next();
    if (matches.hasNext() || file.isTrashed() || file.getSize() > SETTINGS.MAX_EXPORT_BYTES)
      throw new Error('Ambiguous, removed or oversized index file. Check the publication.');
    // Recheck access before any cache hit. Only small immutable JSON is cached per user.
    const cache = ref && file.getSize() <= 80000 ? CacheService.getUserCache() : null;
    let raw;
    if (cache) {
      try { raw = cache.get(ref); } catch (error) { /* Cache is optional. */ }
    }
    if (!raw) {
      raw = file.getBlob().getDataAsString('UTF-8');
      if (ref && sha_(raw) !== ref) throw new Error('Index content changed. Check Drive sync and retry.');
      if (cache) {
        try { cache.put(ref, raw, 300); } catch (error) { /* Continue without caching. */ }
      }
    }
    const value = JSON.parse(raw);
    memo.set(name, value);
    return value;
  }
  const master = read('index.json');
  if (master.schema_version !== 2 || master.export_kind !== 'fieldnotes-index' ||
      !Array.isArray(master.collectors) || !(master.page_size > 0))
    throw new Error('Unsupported field notes index.');
  if (SETTINGS.PUBLIC_MODE &&
      master.members_sha256 !== sha_([...new Set(SETTINGS.PUBLIC_NOTE_IDS)].sort().join('\n')))
    throw new Error('Public index and configured note selection differ.');
  function object(ref) {
    if (typeof ref !== 'string' || !/^[a-f0-9]{64}$/.test(ref)) throw new Error('Invalid index reference.');
    return read(ref + '.json', ref);
  }
  return { master, object };
}

function indexContext_(input) {
  input = input || {};
  const query = String(input.number || input.query || '').trim();
  const collector = String(input.collector || ''), set = String(input.set || '');
  if (query.length > 200 || collector.length > 500 || set.length > 4096) throw new Error('Invalid selection.');
  return { query, number: query, collector, set, p: positivePage_(input.p), page: positivePage_(input.page) };
}

function positivePage_(value) {
  if (value == null || value === '') return 1;
  if (!/^[1-9][0-9]{0,8}$/.test(String(value))) throw new Error('Invalid page number.');
  return Number(value);
}

function homeCollectors_(master) {
  return master.collectors.map(c => ({ name: c.name, count: c.count,
    sets: c.sets.map(s => ({ name: s.name, count: s.count, scans: s.scans })) }));
}

function setInfo_(master, collector, name) {
  const candidates = master.collectors.filter(c => !collector || c.name === collector)
    .flatMap(c => c.sets.filter(s => s.name === name));
  if (candidates.length !== 1) throw new Error('Scan set is absent or ambiguous. Select a collector and set.');
  return candidates[0];
}

function setRows_(reader, set, p) {
  const ref = reader.object(set.pages)[p - 1];
  if (!ref) throw new Error('Page is outside this set.');
  return reader.object(ref);
}

function noteRoute_(reader, id) {
  if (!validId_(id, 'note')) throw new Error('Invalid note ID.');
  if (SETTINGS.PUBLIC_MODE && !SETTINGS.PUBLIC_NOTE_IDS.includes(id)) return null;
  const bucket = reader.object(reader.master.routes)[id.slice(5, 7)];
  return bucket ? reader.object(bucket)[id] || null : null;
}

function rowAt_(reader, set, index) {
  if (index < 0 || index >= set.count) return null;
  const size = reader.master.page_size;
  return setRows_(reader, set, 1 + Math.floor(index / size))[index % size];
}

function identifierRows_(reader, ctx) {
  const term = ctx.query.replace(/[A-Z]/g, c => c.toLowerCase());
  let rows = [];
  if (validId_(term, 'note')) {
    const route = noteRoute_(reader, term);
    if (route) {
      const [set, index] = route.positions[0];
      rows.push(rowAt_(reader, setInfo_(reader.master, route.collector, set), index));
    }
  } else {
    const keys = ['x' + sha_(term).slice(0, 2)];
    if (/^[0-9]+$/.test(term)) keys.push('r' + term.length + '-' + term[0]);
    const lookup = reader.object(reader.master.lookup), seen = new Set();
    for (const key of keys) {
      if (!lookup[key]) continue;
      for (const row of reader.object(lookup[key])) {
        if (seen.has(row.note_id)) continue;
        const exact = row.numbers.some(value => value.trim().replace(/[A-Z]/g, c => c.toLowerCase()) === term);
        if (exact || numberMatches_(row.numbers, term).length) {
          rows.push(row); seen.add(row.note_id);
        }
      }
    }
  }
  return rows.filter(r => (!ctx.collector || r.collector === ctx.collector) && (!ctx.set || r.sets.includes(ctx.set)));
}

function indexedListing_(input) {
  const reader = indexReader_(false), master = reader.master, ctx = indexContext_(input);
  const result = { collectors: homeCollectors_(master), pageSize: master.page_size, p: ctx.p };
  if (ctx.query) {
    const rows = identifierRows_(reader, ctx), start = (ctx.p - 1) * master.page_size;
    return { ...result, kind: 'search', total: rows.length, rows: rows.slice(start, start + master.page_size) };
  }
  if (ctx.set) {
    const set = setInfo_(master, ctx.collector, ctx.set);
    return { ...result, kind: 'set', total: set.count, rows: setRows_(reader, set, ctx.p) };
  }
  if (ctx.collector) {
    const group = master.collectors.find(c => c.name === ctx.collector);
    if (!group) throw new Error('Collector is absent from this export.');
    return { ...result, kind: 'home', total: group.count, scans: group.scans };
  }
  return { ...result, kind: 'home', total: master.count, scans: master.scans };
}

function indexedNote_(id, input) {
  const reader = indexReader_(false), ctx = indexContext_(input), route = noteRoute_(reader, id);
  if (!route) throw new Error('Note is absent from this export.');
  const note = reader.object(route.ref);
  if (note.note_id !== id || ctx.page > note.scans.length) throw new Error('Note or page is absent from this export.');
  let previous, next, total, index;
  if (ctx.query) {
    const rows = identifierRows_(reader, ctx);
    index = rows.findIndex(r => r.note_id === id);
    total = rows.length;
    if (index >= 0) { previous = rows[index - 1]; next = rows[index + 1]; }
  } else {
    ctx.collector = ctx.collector || route.collector;
    ctx.set = ctx.set || route.positions[0][0];
    const set = setInfo_(reader.master, ctx.collector, ctx.set);
    const location = route.positions.find(([name]) => name === ctx.set);
    index = ctx.collector === route.collector && location ? location[1] : -1;
    total = set.count;
    if (index >= 0) { previous = rowAt_(reader, set, index - 1); next = rowAt_(reader, set, index + 1); }
  }
  if (index >= 0) ctx.p = Math.floor(index / reader.master.page_size) + 1;
  return { indexed: true, note: publicNote_(note), context: ctx, token: route.ref, publicMode: SETTINGS.PUBLIC_MODE,
    collectors: reader.master.collectors.map(c => c.name), numberMatches: numberMatches_(note.catalogue.numbers, ctx.query),
    navigation: { position: index + 1, total, previous: previous || null, next: next || null } };
}

function indexedImage_(request) {
  const reader = indexReader_(true), route = noteRoute_(reader, request.note_id);
  if (!route) throw new Error('Note is absent from this export.');
  if (request.token !== route.ref) return { status: 'stale_export', message: 'Reading updated. Reload this note.' };
  const note = reader.object(route.ref);
  if (note.note_id !== request.note_id) throw new Error('Inconsistent note reference.');
  return verifiedImage_(note, request.image_id);
}
