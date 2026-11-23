// Serve only the invented cards produced by make_demo.py. All RPCs stay on loopback.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { context, html, sha } = require('../apps_script/viewer/test_support.cjs');
const demo = path.resolve(__dirname, '../local/demo');

function fixtureServer(indexed = true) {
  if (!fs.existsSync(path.join(demo, 'synthetic-fixture.txt'))) throw Error('Run python scripts/make_demo.py first.');
  const raw = fs.readFileSync(path.join(demo, 'exports/Field_notes_viewer.json'), 'utf8');
  const bundle = JSON.parse(raw);
  const specs = require('../test/inputs/demo.json').notes;
  const allowed = new Set(specs.flatMap(spec => spec.pages.map(page => page.path)));
  const pending = new Set(specs.filter(spec => spec.pending).flatMap(spec => spec.pages.map(page => page.path)));
  const tree = { folders: {} }, scans = new Map();
  for (const note of bundle.notes) {
    if (note.provenance?.provider !== 'offline-fixture' &&
        !(note.execution === 'unprocessed' && note.scans.every(scan => pending.has(scan.path))))
      throw Error('The preview accepts synthetic notes only.');
    for (const scan of note.scans) {
      if (!allowed.has(scan.path)) throw Error('Unexpected synthetic fixture path.');
      const parts = scan.path.split('/'), name = parts.pop();
      const data = fs.readFileSync(path.join(demo, 'cards', ...parts, name));
      scans.set(scan.image_id, { isTrashed: () => false, getId: () => scan.image_id, getSize: () => data.length,
        getMimeType: () => 'image/jpeg', getBlob: () => ({ getBytes: () => [...data] }) });
      let parent = tree;
      for (const folder of parts) {
        parent.folders[folder] ||= [{ folders: {}, files: {} }];
        parent = parent.folders[folder][0];
      }
      parent.files[name] = [scan.image_id];
    }
  }
  const indexFile = indexed && (name => fs.readFileSync(path.join(demo, 'exports/Field_notes_index', name), 'utf8'));
  if (indexed && JSON.parse(indexFile('index.json')).members_sha256 !==
      sha(bundle.notes.filter(n => n.active).map(n => n.note_id).sort().join('\n')))
    throw Error('The preview index does not match the synthetic fixture. Run scripts/make_demo.py.');
  const apps = context(bundle, { exportText: raw, indexFile, scanRoot: 'synthetic_root', folderTree: tree, imageProvider: key => scans.get(key) }).sandbox;
  return { listFolders: input => apps.listFolders(input), loadNote: (id, input) => apps.loadNote(id, input),
    loadImage: request => ({ ...apps.loadImage(request), url: '' }) };
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

// Optional rendering comparison uses a local copy of the reference HTML and invented records.
function referenceCalls(api) {
  function letter(note, pageCount) {
    return { ...note, letter_id: note.note_id, page_count: pageCount, metadata: { sender: { value: 'Example writer', certainty: 'explicit' },
      recipient: { value: 'Example reader', certainty: 'explicit' } }, relationship_review: 'unreviewed',
      sort_basis: 'unknown', hints: { folder: note.catalogue.collector_folder } };
  }
  return {
    listFolders(query) {
      const listing = api.listFolders({ query });
      return { total: listing.total, folders: listing.folders.map(g => ({ name: g.name,
        letters: g.notes.map(n => letter(n, n.page_count)) })) };
    },
    loadLetter(id) {
      const result = api.loadNote(id, {});
      return { ...result, letter: letter(result.note, result.note.scans.length), links: [], unresolved: [], warnings: [],
        navigation: { ...result.navigation, folder: result.note.catalogue.collector_folder, previous: null, next: null } };
    },
    loadImage: r => api.loadImage({ ...r, note_id: r.letter_id })
  };
}

function renderPage(template, url, reference) {
  const values = { ...Object.fromEntries(url.searchParams), noteId: url.searchParams.get('note'), letterId: url.searchParams.get('letter'), scanSet: url.searchParams.get('set'),
      number: url.searchParams.get('number') || (/^\?[0-9]+$/.test(url.search) ? url.search.slice(1) : ''),
      query: url.searchParams.get('number') || url.searchParams.get('query') || url.searchParams.get('q') ||
        (/^\?[0-9]+$/.test(url.search) ? url.search.slice(1) : ''),
      indexed: reference ? '' : 'yes', pageNumber: url.searchParams.get('page') || '1',
      listPage: url.searchParams.get('p') || '1', appUrl: reference ? '/reference' : '/', error: '' };
  const bridge = `<meta name="viewport" content="width=device-width, initial-scale=1">
<script>
function runner(success, failure) {
  const call = method => (...args) => fetch('/rpc${reference ? '/reference' : ''}', { method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify({method,args}) })
    .then(r => r.json()).then(r => { if (r.error) throw Error(r.error); success(r.result); }).catch(failure);
  return { withSuccessHandler:fn=>runner(fn,failure), withFailureHandler:fn=>runner(success,fn),
    listFolders:call('listFolders'),loadNote:call('loadNote'),loadLetter:call('loadLetter'),loadImage:call('loadImage') };
}
window.google={script:{run:runner(()=>{},console.error)}};
</script>`;
  return template.replace(/<\?=\s*(\w+)\s*\?>/g, (_, key) => escapeHtml(values[key])).replace('</head>', bridge + '</head>');
}

function createPreview(referenceFile) {
  const api = fixtureServer();
  const reference = referenceFile ? fs.readFileSync(referenceFile, 'utf8') : null;
  const referenceApi = reference ? referenceCalls(fixtureServer(false)) : null;
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src data:; connect-src 'self'; base-uri 'none'");
    if (req.method === 'GET' && (url.pathname === '/' || (url.pathname === '/reference' && reference))) {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      return res.end(renderPage(url.pathname === '/' ? html : reference, url, url.pathname === '/reference'));
    }
    if (req.method !== 'POST' || !(url.pathname === '/rpc' || (url.pathname === '/rpc/reference' && reference))) {
      res.writeHead(404); return res.end();
    }
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    try {
      let body = '';
      for await (const part of req) {
        body += part;
        if (body.length > 32000) throw Error('Request too large');
      }
      const { method, args } = JSON.parse(body);
      const handlers = url.pathname === '/rpc' ? api : referenceApi;
      if (!Object.hasOwn(handlers, method) || !Array.isArray(args)) throw Error('Unknown preview request');
      res.end(JSON.stringify({ result: handlers[method](...args) }));
    } catch (error) {
      res.writeHead(400); res.end(JSON.stringify({ error: error.message }));
    }
  });
}

if (require.main === module) {
  const server = createPreview(process.argv[2]);
  server.listen(8783, '127.0.0.1', () => console.log('Synthetic field notes: http://127.0.0.1:8783/'));
}
module.exports = { createPreview };
