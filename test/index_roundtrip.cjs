// The Python suite supplies the complete synthetic 10,000-card export on stdin.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { context, sha, frontend, nodes } = require('../apps_script/viewer/test_support.cjs');
const { files, subset, empty } = JSON.parse(fs.readFileSync(0, 'utf8'));
const indexFile = key => files[key];
const { sandbox: api, indexReads, counts } = context(undefined, { indexFile });
const home = api.listFolders({});
assert.equal(home.total, 10000);
assert.equal(home.scans, 20000);
assert.deepEqual(indexReads, ['index.json']);
assert.equal(home.rows, undefined);
const byParent = context(undefined, {indexFile, indexParent:true});
assert.equal(byParent.sandbox.listFolders({}).total, home.total);
assert.deepEqual(byParent.lookups, ['folder:Field_notes_index']);
assert.throws(() => context(undefined, {indexFile, indexParent:true, deny:true}).sandbox.listFolders({}), /Access denied/);
assert.throws(() => context(undefined, {indexFile, indexParent:true, indexChildren:0}).sandbox.listFolders({}), /missing/);
assert.throws(() => context(undefined, {indexFile, indexParent:true, indexChildren:2}).sandbox.listFolders({}), /Multiple/);
const browser = frontend({ indexed: 'yes' });
browser.catalogueCalls[0].success(home);
assert.equal(nodes(browser.ids.results).filter(n => n.tag === 'table').length, 0);
assert.equal(nodes(browser.ids.results).filter(n => n.tag === 'details').length, 2);
const rows = api.listFolders({ collector: 'A', set: 'A/set1', p: 2 });
assert.equal(indexReads.length, 4);
assert.equal(rows.rows.length, 40);
assert.equal(rows.rows[0].numbers[0], '40');
const id = 'note_' + sha('39').slice(0, 32);
for (const [number, collector, total] of [[' SHARED ', '', 2], ['shared', 'B', 1], ['0012', '', 1],
  ['12', '', 1], ['12A', 'A', 1], ['12a', 'B', 0], ['8420', '', 2], [id, 'A', 1], [id, 'B', 0], ['absent', '', 0]]) {
  const before = indexReads.length, listing = api.listFolders({ number, collector });
  assert.equal(listing.total, total, number + '/' + collector);
  assert.ok(indexReads.length - before <= 5);
}
const loaded = api.loadNote(id, { page: 2 });
assert.equal(loaded.navigation.position, 40);
assert.equal(loaded.navigation.next.note_id, rows.rows[0].note_id);
assert.equal(loaded.context.set, 'A/set1');
assert.equal(loaded.context.page, 2);
assert.equal(loaded.note.scans[1].image_id, loaded.note.pages[1].image_id);
browser.sandbox.renderNote(loaded);
const pairs = nodes(browser.ids.record).filter(n => n.className === 'page-pair');
assert.deepEqual(pairs.map(pair => pair.dataset.imageId), Array.from(loaded.note.scans, scan => scan.image_id));
assert.equal(pairs.length, 2);
for (const [i, pair] of pairs.entries())
  assert.equal(nodes(pair).find(n => n.tag === 'pre').textContent, loaded.note.pages[i].text);
assert.equal(pairs[0].scrolledIntoView, undefined);
assert.equal(pairs[1].scrolledIntoView, true);
for (const [i, pair] of pairs.entries()) {
  const heading = pair.children.find(n => n.tag === 'h3');
  assert.ok(heading.textContent.startsWith('Page ' + (i + 1)));
  assert.equal(heading.children.length, 0);
}
assert.ok(!nodes(browser.ids.record).some(n => n.attributes['aria-label'] === 'Scan navigation'));
assert.equal(counts().imageReads, 0);
const request = { note_id: id, image_id: loaded.note.scans[1].image_id, token: loaded.token };
assert.equal(api.loadImage(request).status, 'missing_mapping');
assert.equal(api.loadImage({ ...request, token: 'old' }).status, 'stale_export');
assert.throws(() => api.loadImage({ ...request, image_id: 'img_' + '0'.repeat(32) }), /part of this note/);
assert.throws(() => api.loadNote(id, { page: 3 }), /absent/);
assert.throws(() => context(undefined, { indexFile, deny: true }).sandbox.listFolders({}), /Access denied/);
const broken = context(undefined, { indexFile: key => key === 'index.json' ? files[key] : '{}' }).sandbox;
assert.throws(() => broken.listFolders({ set: 'A/set1' }), /content changed/);

// Simulate replacing only the published manifest. Even cached and leftover files
// stay on Drive throughout the test, and the public viewer keeps the same settings.
let published = files;
const live = context(undefined, { publicMode: true,
  indexFile: key => published[key] ?? files[key] ?? subset[key] ?? empty[key] });
const publicApi = live.sandbox;
function randomPick(...draws) {
  publicApi.Math = Object.create(Math);
  publicApi.Math.random = () => {
    assert.ok(draws.length, 'unexpected extra draw');
    return draws.shift();
  };
  const picked = publicApi.loadNote('random', { collector: 'ignored', query: 'ignored', page: 2 });
  assert.equal(draws.length, 0);
  assert.equal(picked.context.page, 1);
  return picked;
}
for (const position of [0, 39, 40, 4999, 5000, 9999]) {
  const before = live.indexReads.length;
  const picked = randomPick((position + 0.5) / 10000);
  assert.equal(picked.note.note_id, 'note_' + sha(String(position)).slice(0, 32));
  const reads = live.indexReads.slice(before);
  assert.equal(reads.filter(name => name === 'index.json').length, 1);
  assert.ok(reads.length <= 7, 'one manifest, set directory, up to two browse pages, ID directory, ID bucket and card');
}
assert.equal(live.counts().imageReads, 0);
assert.equal(publicApi.loadNote(id, {}).token, request.token);
published = subset;
assert.equal(publicApi.listFolders({}).total, 2);
assert.equal(publicApi.listFolders({ query: id }).total, 0);
assert.equal(publicApi.listFolders({ number: '8420' }).total, 0);
assert.throws(() => publicApi.loadNote(id, {}), /absent/);
assert.throws(() => publicApi.loadImage(request), /absent/);
const first = randomPick(0), second = randomPick(0.5);
assert.equal(first.note.note_id, 'note_' + sha('0').slice(0, 32));
assert.equal(second.note.note_id, 'note_' + sha('1').slice(0, 32));
// The third slot is the first card's second set. Either unique card can win the redraw.
assert.equal(randomPick(0.99, 0).note.note_id, first.note.note_id);
assert.equal(randomPick(0.99, 0.99).note.note_id, second.note.note_id);
published = empty;
assert.equal(publicApi.listFolders({}).total, 0);
assert.throws(() => publicApi.loadNote('random', {}), /no cards/i);
assert.throws(() => publicApi.loadNote(first.note.note_id, {}), /absent/);
assert.throws(() => publicApi.loadImage({ note_id: first.note.note_id, image_id: first.note.scans[0].image_id, token: first.token }), /absent/);
published = files;
assert.equal(publicApi.loadNote(id, {}).note.note_id, id);
