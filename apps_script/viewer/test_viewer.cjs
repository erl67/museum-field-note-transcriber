const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { context, fixture, frontend, nodes, id, bytes, server, html, seal, sha } = require('./test_support.cjs');
const text = root => nodes(root).map(n => n.textContent).join('\n');
const request = token => ({ token, note_id: id('note',1), image_id: id('img',2) });
test('notepad opens a card in one request, silently, and leaves a bookmark to it', () => {
  assert.match(html, /href="<\?= appUrl \?>\?note=random" aria-label="Open a random card">\s*<svg[^>]*>[\s\S]*?<\/svg>\s*<\/a>/);
  const f = frontend({ indexed: 'yes', note: 'random', collector: 'Old filter', page: '2' });
  assert.equal(f.ids.message.textContent, '');
  assert.equal(f.catalogueCalls.length, 0);
  assert.deepEqual(f.noteCalls.map(call => call.id), ['random']);
  assert.deepEqual({ ...f.noteCalls[0].context }, {});
  assert.equal(f.calls.length, 0);
  const chosen = context().sandbox.loadNote('random', {});
  let bookmark;
  f.sandbox.google.script.history = { replace: (_, params) => { bookmark = { ...params }; } };
  f.noteCalls[0].success({ ...chosen, collectors: ['Carriker'], context: { collector: 'Carriker', page: 1 } });
  assert.deepEqual(bookmark, { note: chosen.note.note_id });
  assert.equal(nodes(f.ids.record).find(n => n.tag === 'h2').textContent, chosen.note.catalogue.title);
  assert.equal(f.ids.message.textContent, '');
  assert.doesNotMatch(text(f.ids.record), /loading|choosing|opening a random/i);
  assert.equal(f.calls[0].req.note_id, chosen.note.note_id);
  const empty = frontend({ indexed: 'yes', note: 'random' });
  empty.noteCalls[0].failure(new Error('There are no cards in this catalogue.'));
  assert.match(empty.ids.message.textContent, /no cards/i);
});
function many() {
  const b=fixture(), n=b.notes[0];
  b.notes.push({ ...structuredClone(n), note_id:id('note',2),number_order:1,catalogue:{...n.catalogue,collector:'Avery',collector_folder:'Avery'} });
  return seal(b);
}
test('opening a set verifies the stored UTF-8 bytes before decoding its rows', () => {
  const species = 'Café ♂ �';
  const page = JSON.stringify([{ species }]);
  const pageName = sha(page) + '.json';
  const directory = JSON.stringify([sha(page)]);
  const set = { name: 'Example/set1', count: 1, pages: sha(directory) };
  const manifest = { schema_version: 2, export_kind: 'fieldnotes-index', page_size: 40,
    collectors: [{ name: 'Example', sets: [set] }] };
  const files = { 'index.json': JSON.stringify(manifest), [set.pages + '.json']: directory, [pageName]: page };
  const openSet = () => context(fixture(), { indexFile: name => files[name] }).sandbox.listFolders({ set: set.name });
  assert.equal(openSet().rows[0].species, species);

  // An invalid byte and the valid replacement character decode to the same text.
  // Only the published bytes may satisfy the file's hash.
  const [before, after] = page.split('�');
  files[pageName] = Buffer.concat([Buffer.from(before), Buffer.from([0xff]), Buffer.from(after)]);
  assert.equal(files[pageName].toString('utf8'), page);
  assert.throws(openSet, error => error.message.includes('content changed') && error.message.includes(pageName));
});
test('numeric searches include range members and highlight the original text on its evidence page', () => {
  const cases = JSON.parse(fs.readFileSync(path.join(__dirname, '../../test/inputs/catalogue-ranges.json'), 'utf8'));
  const api = context().sandbox;
  for (const [raw, yes, no] of cases) for (const query of [...yes, ...no]) {
    assert.equal(api.numberMatches_([raw], query).length > 0, yes.includes(query), raw + ' / ' + query);
  }
  const bundle = fixture(), note = bundle.notes[0], first = note.pages[0];
  note.catalogue.numbers = ['8419-20', '8429'];
  note.catalogue.number_label = '8419-20, 8429';
  note.identifiers = [{ value: '8419-20', evidence: [{ image_id: first.image_id }] }];
  first.text = 'First (8419 – 20) <source> 8429.';
  note.pages[1].text = 'Another reference (8419 – 20)';
  const publicApi = context(bundle, { publicMode: true, allowlist: [note.note_id] }).sandbox;
  for (const [query, expected] of [['8420', '8419 – 20'], ['8419', '8419']]) {
    const row = publicApi.listFolders({ number: query }).folders[0].notes[0];
    assert.equal(row.catalogue.number_label, '8419-20, 8429');
    const f = frontend(), loaded = publicApi.loadNote(row.note_id, { number: query });
    f.sandbox.renderNote(loaded);
    const marks = nodes(f.ids.record).filter(n => n.tag === 'mark');
    assert.deepEqual(marks.map(n => n.textContent), [expected]);
    const source = nodes(f.ids.record).find(n => n.tag === 'pre');
    assert.equal(source.children.map(n => n.textContent).join(''), first.text);
  }
  first.text += ' Elevation 8421.';
  const updated = context(bundle).sandbox;
  assert.equal(updated.listFolders({ query: '8421' }).total, 1);
  assert.equal(updated.listFolders({ number: '8421' }).total, 0);
  const browser = frontend();
  browser.ids.query.value = '8420'; browser.ids.search.events.submit({preventDefault(){}});
  assert.equal(browser.catalogueCalls.at(-1).context.number, '8420');
});
test('base stylesheet is verbatim and client embedding is current',()=>{
  const css=fs.readFileSync(path.join(__dirname,'reference.css'),'utf8');
  assert.equal(html.match(/<style>([\s\S]*?)<\/style>/)[1],css);
  assert.equal(sha(css),'82ddc4e76fa105bad5668707e73d20d5e33448771567c9b0197aa58185be4804');
  assert.equal(html.replace(/\r\n/g,'\n').match(/<script>\n([\s\S]*?)\n  <\/script>/)[1],
    fs.readFileSync(path.join(__dirname,'client.js'),'utf8').replace(/\r\n/g,'\n'));
  assert.match(css,/--scan-share: 47fr; --text-share: 53fr/);
  assert.match(html,/@media \(max-width: 760px\)/); assert.match(html,/object-fit: contain/);
});
test('exact scan sets work across older exports, listing, navigation and public selection', () => {
  const bundle = many();
  for (const [index, note] of bundle.notes.entries()) {
    const folder = index ? 'Carriker/set10' : 'Carriker/set1';
    Object.assign(note.catalogue, { collector: 'Carriker', collector_folder: 'Carriker' });
    for (const scan of note.scans) {
      scan.image_id = id('img', scan.order + index * 10);
      scan.path = folder + '/' + scan.filename;
      scan.folder = folder;
    }
    note.pages.forEach((page, i) => { page.image_id = note.scans[i].image_id; });
  }
  const api = context(bundle).sandbox, f = frontend({ set: 'Carriker/set1' });
  const result = api.listFolders(f.catalogueCalls[0].context);
  assert.deepEqual([...result.sets], ['Carriker/set1', 'Carriker/set10']);
  assert.equal(result.total, 1);
  f.catalogueCalls[0].success(result);
  assert.equal(f.ids.message.textContent, '1 note in 1 collector folder');
  assert.equal(f.ids['set-filter'].value, 'Carriker/set1');
  const link = nodes(f.ids.results).find(n => n.tag === 'a');
  assert.ok(link.href.includes('set=Carriker%2Fset1'));
  const loaded = api.loadNote(bundle.notes[0].note_id, { set: 'Carriker/set1' });
  assert.equal(loaded.navigation.total, 1);
  assert.equal(loaded.navigation.next, null);
  f.ids['clear-search'].events.click();
  assert.equal(f.catalogueCalls.at(-1).context.set, '');
  const published = context(bundle, { publicMode: true, allowlist: [bundle.notes[0].note_id] }).sandbox;
  assert.deepEqual([...published.listFolders({}).sets], ['Carriker/set1']);
  assert.equal(published.listFolders({ set: 'Carriker/set10' }).total, 0);
});
test('only explicit sides are labelled and 72-character lines widen the whole note', () => {
  const bundle = fixture(), note = bundle.notes[0], f = frontend();
  note.scans[0].side = 'Front'; note.scans[1].side = 'Back';
  function render() { f.sandbox.renderNote(context(bundle).sandbox.loadNote(note.note_id, {})); }
  note.pages[0].text = 'x'.repeat(71) + '  \r\nshort';
  render();
  assert.equal(f.ids.record.dataset.wideTranscription, 'false');
  assert.match(text(f.ids.record), /Page 1 · Front/); assert.match(text(f.ids.record), /Page 2 · Back/);
  for (const field of [note.pages[0], { kind: 'addition' }, { image_id: note.pages[1].image_id, language: 'English' }]) {
    field.text = 'x'.repeat(72);
    if (field.kind) note.pages[1].annotations = [field];
    if (field.language) note.translations = [field];
    render();
    assert.equal(f.ids.record.dataset.wideTranscription, 'true');
    field.text = 'short';
  }
  render();
  assert.equal(f.ids.record.dataset.wideTranscription, 'false');
});
test('public copy link uses this note and deployment, with a manual clipboard fallback', async () => {
  const bundle = fixture(), nid = bundle.notes[0].note_id, f = frontend({ query: 'private search' });
  f.sandbox.renderNote(context(bundle).sandbox.loadNote(nid, {}));
  assert.ok(!nodes(f.ids.record).some(n => n.textContent === 'Copy note link'));
  f.sandbox.renderNote(context(bundle, { publicMode: true, allowlist: [nid] }).sandbox.loadNote(nid, {}));
  const share = nodes(f.ids.record).find(n => n.className === 'letter-share');
  const [button, status, input] = share.children;
  await button.events.click();
  assert.ok(input.focused && input.selected && !input.hidden);
  assert.equal(input.value, 'https://script.google.com/synthetic/exec?note=' + nid);
  let copied;
  f.sandbox.navigator = { clipboard: { writeText: async value => { copied = value; } } };
  await button.events.click();
  assert.equal(copied, input.value); assert.ok(input.hidden); assert.equal(status.textContent, 'Link copied.');
});
test('public installation uses owner read-only access and configures the index by folder',()=>{
  const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'appsscript.json')));
  assert.equal(manifest.webapp.access,'ANYONE_ANONYMOUS');assert.equal(manifest.webapp.executeAs,'USER_DEPLOYING');
  assert.deepEqual(manifest.oauthScopes,['https://www.googleapis.com/auth/drive.readonly']);
  for(const k of ['ACCESS_FILE_ID','EXPORT_FILE_ID','SCAN_ROOT_FOLDER_ID','INDEX_FOLDER_ID','INDEX_PARENT_FOLDER_ID']) assert.match(server,new RegExp(k+": ''"));
  assert.match(server,/PUBLIC_MODE: true/);assert.doesNotMatch(server,/PUBLIC_NOTE_IDS:|note_[0-9a-f]{32}|setSharing|setTrashed|createFile|UrlFetchApp/);
});
test('only intended entry points are callable RPCs',()=>{
  assert.deepEqual([...server.matchAll(/^function (\w+)\(/gm)].map(m=>m[1]).filter(n=>!n.endsWith('_')).sort(),['doGet','listFolders','loadImage','loadNote']);
});
test('Carriker opens by name even when another collector sorts first',()=>{
  const f=frontend();f.catalogueCalls[0].success(context(many()).sandbox.listFolders({}));
  assert.equal(f.ids.results.children[0].children[0].textContent,'Avery');assert.equal(f.ids.results.children[0].open,false);
  assert.equal(f.ids.results.children[1].children[0].textContent,'Carriker');assert.equal(f.ids.results.children[1].open,true);
});
test('user expansion choices survive navigation and reload',()=>{
  const saved={},f=frontend({},saved),result=context(many()).sandbox.listFolders({});f.catalogueCalls[0].success(result);
  f.ids.results.children[0].open=true;f.ids.results.children[0].events.toggle();
  f.ids.results.children[1].open=false;f.ids.results.children[1].events.toggle();
  const g=frontend({},saved);g.catalogueCalls[0].success(result);
  assert.equal(g.ids.results.children[0].open,true);assert.equal(g.ids.results.children[1].open,false);
});
test('processing order and divider preserve the named Carriker expansion rule',()=>{
  const bundle=many();
  bundle.notes[1].processed_at='2026-11-17T13:00:00Z';
  const folders=context(bundle).sandbox.listFolders({});
  const f=frontend(); f.catalogueCalls[0].success(folders);
  assert.equal(folders.folders[0].name,'Avery'); assert.equal(folders.folders[0].is_latest,true);
  assert.equal(f.ids.results.children[0].open,false); assert.equal(f.ids.results.children[1].className,'folder-divider');
  assert.equal(f.ids.results.children[2].open,true);
});
test('catalogue includes all records without fetching images or requiring dates',()=>{
  const b=fixture(),n=b.notes[0];b.notes=Array.from({length:125},(_,i)=>({...structuredClone(n),note_id:id('note',i+1),number_order:i}));
  const c=context(b),r=c.sandbox.listFolders({});assert.equal(r.total,125);assert.equal(r.folders[0].notes.length,125);assert.equal(c.counts().imageReads,0);
  assert.equal(r.folders[0].notes[0].pages,undefined);
});
test('search all numbers names aliases collector and saved Unicode text',()=>{
  const c=context();for(const query of ['0012','9846','Example bird','Reviewed alias','Carriker','café']) assert.equal(c.sandbox.listFolders({query}).total,1);
  assert.equal(c.sandbox.listFolders({query:'absent'}).total,0);assert.throws(()=>c.sandbox.listFolders({query:'x'.repeat(201)}),/Invalid/);
});
test('species mode filters collectors and retains uncertain alternatives',()=>{
  const b=many();b.notes[0].catalogue.species_groups.push({key:'alternative',name:'Another bird?',rank:'species',uncertain:true,role:'principal'});
  const c=context(b),r=c.sandbox.listFolders({mode:'species',collector:'Carriker'});
  assert.equal(r.total,1);assert.equal(r.folders.length,2);assert.equal(r.folders.find(g=>g.key==='alternative').uncertain,1);
  assert.equal(c.sandbox.listFolders({mode:'species'}).total,2);
});
test('unknown and unprocessed notes remain accessible',()=>{
  const b=fixture(),n=b.notes[0];n.execution='unprocessed';n.pages=[];n.catalogue.species='Unknown species';n.catalogue.number_label='Number not recorded';
  n.catalogue.species_groups=[{key:'unknown',name:'Unknown species',uncertain:true}];
  const c=context(b);assert.equal(c.sandbox.listFolders({mode:'species'}).folders[0].name,'Unknown species');
  const f=frontend();f.sandbox.renderNote(c.sandbox.loadNote(n.note_id,{}));assert.match(text(f.ids.record),/No complete transcription/);
});
test('stable links and navigation retain selected search group and mode',()=>{
  const b=many();b.notes[1].catalogue.collector_folder='Carriker';const c=context(b),input={query:'café',mode:'species',group:'name:species:example bird',sort:'number'};
  const r=c.sandbox.loadNote(id('note',1),input);assert.equal(r.navigation.next.note_id,id('note',2));
  const f=frontend();f.sandbox.renderNote(r);const links=nodes(f.ids.record).filter(n=>n.tag==='a');
  assert.ok(links.some(n=>n.href.includes('query=caf%C3%A9')&&n.href.includes('mode=species')&&n.href.includes('note='+id('note',2))));
  assert.equal(f.ids.record.children.filter(n=>n.tag==='nav').length,2);
});
test('previous next exclude search nonmatches retired and other groups',()=>{
  const b=many();b.notes[1].active=false;const c=context(b),r=c.sandbox.loadNote(id('note',1),{group:'Carriker'});
  assert.equal(r.navigation.next,null);assert.equal(r.navigation.previous,null);assert.equal(c.sandbox.listFolders({}).total,1);
  assert.equal(c.sandbox.loadNote(id('note',2),{}).note.active,false);
});
test('rows and summary snippets preserve template table structure',()=>{
  const b=fixture();b.notes[0].summary='Unicode é '.repeat(100);const c=context(b),f=frontend();f.catalogueCalls[0].success(c.sandbox.listFolders({}));
  const row=nodes(f.ids.results).find(n=>n.className==='catalogue-summary-row');assert.equal(row.children[0].colSpan,4);
  assert.equal(row.children[0].children[0].className,'catalogue-summary');assert.ok(Array.from(row.children[0].children[0].textContent).length<=360);
  assert.equal(c.sandbox.loadNote(id('note',1),{}).note.summary,b.notes[0].summary);
});
test('ordered left scans and right transcription retain complete Unicode source',()=>{
  const f=frontend();f.sandbox.renderNote(context().sandbox.loadNote(id('note',1),{}));
  const pairs=f.ids.record.children.filter(n=>n.className==='page-pair');assert.equal(pairs[0].dataset.imageId,id('img',2));assert.equal(pairs[1].dataset.imageId,id('img',1));
  for(const pair of pairs){const columns=pair.children.find(n=>n.className==='page-columns');assert.equal(columns.children[0].tag,'figure');assert.equal(columns.children[1].tag,'section');}
  assert.match(text(pairs[0]),/0012 ♂ ♀/);assert.match(text(pairs[1]),/\[blank\]/);
  const children=f.ids.record.children;assert.ok(children.findIndex(n=>n.className==='letter-summary')<children.indexOf(pairs[0]));assert.ok(children.findIndex(n=>n.className==='panel')>children.indexOf(pairs[1]));
});
test('source HTML is literal text and never executable markup',()=>{
  const f=frontend();f.sandbox.renderNote(context().sandbox.loadNote(id('note',1),{}));
  assert.match(text(f.ids.record),/<img src=x onerror=bad\(\)>/);assert.equal(nodes(f.ids.record).filter(n=>n.tag==='img'||n.tag==='script').length,0);
  assert.doesNotMatch(html,/innerHTML|document\.write|<\?!/);
});
test('sequential image errors leave text visible and continue all pages',()=>{
  const f = frontend({ indexed: 'yes' });
  const result = context().sandbox.loadNote(id('note',1),{});
  result.collectors = ['Carriker'];
  f.sandbox.renderNote(result);
  const pairs = f.ids.record.children.filter(n => n.className === 'page-pair');
  assert.equal(pairs.length, 2);
  assert.match(text(pairs[0]), /0012/);
  assert.match(text(pairs[1]), /\[blank\]/);
  assert.equal(f.calls.length, 1);
  assert.equal(f.calls[0].req.image_id, pairs[0].dataset.imageId);
  f.calls[0].failure({ message: 'Synthetic inaccessible image' });
  assert.equal(f.calls[1].req.image_id, pairs[1].dataset.imageId);
  f.calls[1].success({ status: 'ready', data: 'data:image/jpeg;base64,AA', url: '' });
  assert.match(text(pairs[0]), /inaccessible/);
  assert.ok(nodes(pairs[1]).some(n => n.textContent === 'Enlarge scan'));
});
test('loaded image dimensions preserve proportions and offer enlargement',()=>{
  const f=frontend();f.sandbox.renderNote(context().sandbox.loadNote(id('note',1),{}));f.calls[0].success({status:'ready',data:'data:image/jpeg;base64,AA',url:''});
  const pair=f.ids.record.children.find(n=>n.className==='page-pair'),img=nodes(pair).find(n=>n.tag==='img');img.naturalWidth=1600;img.naturalHeight=900;img.onload();
  assert.equal(pair.style['--page-ratio'],'1600 / 900');assert.ok(nodes(pair).some(n=>n.textContent==='Enlarge scan'));
  img.onerror();assert.equal(img.hidden,true);assert.match(text(pair),/could not be displayed/);assert.match(text(pair),/0012/);
});
test('new search response cannot be overwritten by older response',()=>{
  const f=frontend();f.ids.query.value='new';f.ids.search.events.submit({preventDefault(){}});const c=context();
  f.catalogueCalls[1].success(c.sandbox.listFolders({query:'absent'}));f.catalogueCalls[0].success(c.sandbox.listFolders({}));
  assert.match(f.ids.message.textContent,/0 note/);
});
test('access gate applies to every restricted RPC',()=>{
  const c=context(fixture(),{deny:true});for(const call of [()=>c.sandbox.listFolders({}),()=>c.sandbox.loadNote(id('note',1),{}),()=>c.sandbox.loadImage(request('x'))]) assert.throws(call,/Access denied/);
  assert.equal(c.counts().exportReads,0);
});
test('authenticated mapped image checks bytes hash and returned Drive link',()=>{
  const c=context(),token=c.sandbox.loadNote(id('note',1),{}).token,r=c.sandbox.loadImage(request(token));
  assert.equal(r.status,'ready');assert.match(r.url,/drive.google.com/);assert.equal(Buffer.from(r.data.split(',')[1],'base64').toString(),bytes.toString());
});
test('missing mapping missing scan and inaccessible scan differ',()=>{
  const b=fixture();b.notes[0].scans[0].drive_file_id=null;let c=context(b),token=c.sandbox.loadNote(id('note',1),{}).token;
  assert.equal(c.sandbox.loadImage(request(token)).status,'missing_mapping');b.notes[0].scans[0].status='missing';token=c.sandbox.loadNote(id('note',1),{}).token;
  assert.equal(c.sandbox.loadImage(request(token)).status,'missing_scan');c=context(fixture(),{imageError:true});token=c.sandbox.loadNote(id('note',1),{}).token;
  assert.equal(c.sandbox.loadImage(request(token)).status,'inaccessible');
});
test('changed exports and changed scans never substitute evidence',()=>{
  const c=context(),token=c.sandbox.loadNote(id('note',1),{}).token;assert.equal(c.sandbox.loadImage(request('old')).status,'stale_export');
  const b=fixture();b.notes[0].scans[0].sha256='0'.repeat(64);const changed=context(b),t=changed.sandbox.loadNote(id('note',1),{}).token;
  assert.equal(changed.sandbox.loadImage(request(t)).status,'changed_scan');
  assert.equal(c.sandbox.loadImage(request(token)).status,'ready');
});
test('exact nested Drive paths only no global filename selection',()=>{
  const b=fixture();for(const s of b.notes[0].scans)s.drive_file_id=null;
  const c=context(b,{scanRoot:'synthetic_root'}),t=c.sandbox.loadNote(id('note',1),{}).token;assert.equal(c.sandbox.loadImage(request(t)).status,'ready');
  assert.deepEqual(c.lookups,['folder:Carriker','file:card2.jpg']);assert.doesNotMatch(server,/DriveApp.getFilesByName/);
});
test('duplicate and unavailable Drive paths are not guessed',()=>{
  for(const [tree,status]of [[{},'path_unavailable'],[{folders:{Carriker:[{},{}]}},'ambiguous_path'],[{folders:{Carriker:[{files:{'card2.jpg':['one','two']}}]}},'ambiguous_path']]){
    const b=fixture();b.notes[0].scans[0].drive_file_id=null;const c=context(b,{scanRoot:'synthetic_root',folderTree:tree}),t=c.sandbox.loadNote(id('note',1),{}).token;
    assert.equal(c.sandbox.loadImage(request(t)).status,status);assert.equal(c.counts().imageReads,0);
  }
});
test('unsafe paths rejected before Drive folder reads',()=>{
  for(const p of ['../card.jpg','/card.jpg','C:/card.jpg','C:\\card.jpg','x//card.jpg','x/./card.jpg','x/../card.jpg','x/\u0000card.jpg']){
    const b=fixture();Object.assign(b.notes[0].scans[0],{path:p,drive_file_id:null});const c=context(b,{scanRoot:'synthetic_root'}),t=c.sandbox.loadNote(id('note',1),{}).token;
    assert.equal(c.sandbox.loadImage(request(t)).status,'invalid_path');assert.equal(c.counts().folderReads,0);
  }
});
test('explicit mapping failure does not fall back to folder search',()=>{
  const c=context(fixture(),{scanRoot:'synthetic_root',imageError:true}),t=c.sandbox.loadNote(id('note',1),{}).token;
  assert.equal(c.sandbox.loadImage(request(t)).status,'inaccessible');assert.equal(c.counts().folderReads,0);
});
test('browser cannot supply arbitrary paths IDs or other note images',()=>{
  const c=context(),t=c.sandbox.loadNote(id('note',1),{}).token;
  assert.throws(()=>c.sandbox.loadNote('../private',{}),/Invalid note/);assert.throws(()=>c.sandbox.loadImage({...request(t),image_id:id('img',99)}),/not part/);
  assert.equal(c.sandbox.loadImage({...request(t),path:'../private',drive_file_id:'arbitrary'}).status,'ready');
});
test('size MIME and trash limits before image transfer',()=>{
  for(const [options,status]of [[{getSize:()=>13*1024*1024},'unavailable'],[{getMimeType:()=> 'text/html'},'unavailable'],[{isTrashed:()=>true},'missing_scan']]){
    const c=context(fixture(),{image:options}),t=c.sandbox.loadNote(id('note',1),{}).token;assert.equal(c.sandbox.loadImage(request(t)).status,status);assert.equal(c.counts().imageReads,0);
  }
  const b=fixture();b.notes[0].scans[0].size=25*1024*1024;const c=context(b),t=c.sandbox.loadNote(id('note',1),{}).token;
  assert.equal(c.sandbox.loadImage(request(t)).status,'too_large');assert.equal(c.counts().imageReads,0);
});
test('duplicate paths IDs pages and inconsistent exports fail closed',()=>{
  for(const mutate of [b=>b.notes.push(b.notes[0]),b=>b.notes[0].scans[1].path=b.notes[0].scans[0].path,b=>b.notes[0].pages[1].image_id=b.notes[0].pages[0].image_id,b=>b.notes[0].pages.pop()]){
    const b=fixture();mutate(b);assert.throws(()=>context(b).sandbox.listFolders({}),/Duplicate|duplicate|coverage/);
  }
  const b=fixture();b.content_sha256='0'.repeat(64);assert.throws(()=>context(b,{noSeal:true}).sandbox.listFolders({}),/hash is inconsistent/);
});
test('legacy public bundle still limits browsing, bookmarks and random picks to its active selection',()=>{
  const b = many(), first = id('note',1);
  assert.equal(context(b, { publicMode: true }).sandbox.listFolders({}).total, 0);
  const api = context(b, { publicMode: true, allowlist: [first] }).sandbox;
  assert.equal(api.listFolders({}).total, 1);
  assert.equal(api.loadNote('random', { query: 'old search' }).note.note_id, first);
  assert.throws(() => api.loadNote(id('note',2), {}), /absent/);
  b.notes[0].active = false;
  assert.equal(api.listFolders({}).total, 0);
  assert.throws(() => api.loadNote('random', {}), /no cards/i);
});
test('public responses search and evidence omit all internal fields',()=>{
  const b=fixture(),n=b.notes[0],secret='PRIVATE_SENTINEL';n.provenance={prompt:secret};n.partial_response=secret;n.review_reasons=[secret];n.future_field=secret;n.catalogue.search_text=secret;n.catalogue.conflicts=[secret];n.scans[0].previous_paths=[secret];
  n.metadata.collector={value:'A',normalized:'A',certainty:'inferred',authority_id:secret,evidence:[{image_id:id('img',2),quote:'A',reviewer:secret}]};
  const c=context(b,{publicMode:true,allowlist:[n.note_id]}),r=c.sandbox.loadNote(n.note_id,{});
  assert.doesNotMatch(JSON.stringify(r),/PRIVATE_SENTINEL|synthetic_drive_|previous_paths|prompt/);
  assert.equal(c.sandbox.listFolders({query:secret}).total,0);assert.equal(r.note.pages[0].text,n.pages[0].text);
});
test('public images omit Drive links but keep byte verification',()=>{
  const c=context(fixture(),{publicMode:true,allowlist:[id('note',1)]}),t=c.sandbox.loadNote(id('note',1),{}).token,r=c.sandbox.loadImage(request(t));assert.equal(r.status,'ready');assert.equal(r.url,'');
});
test('public shared budgets stop reads and reset in a new minute',()=>{
  const cache=new Map(),c=context(fixture(),{publicMode:true,cache,now:100000});for(let i=0;i<120;i++)c.sandbox.listFolders({});
  const blocked=context(fixture(),{publicMode:true,cache,now:100000});assert.throws(()=>blocked.sandbox.listFolders({}),/busy/);assert.equal(blocked.counts().exportReads,0);
  assert.equal(context(fixture(),{publicMode:true,allowlist:[id('note',1)],cache,now:120000}).sandbox.listFolders({}).total,1);
});
test('public image budget limits repeated images while text remains available',()=>{
  const c=context(fixture(),{publicMode:true,allowlist:[id('note',1)]}),t=c.sandbox.loadNote(id('note',1),{}).token;
  for(let i=0;i<60;i++)c.sandbox.loadImage(request(t));assert.throws(()=>c.sandbox.loadImage(request(t)),/busy/);assert.equal(c.sandbox.listFolders({}).total,1);
});
test('public lock or cache failure refuses access before Drive reads',()=>{
  for(const options of [{lockBusy:true},{cacheError:true}]){const c=context(fixture(),{publicMode:true,...options});assert.throws(()=>c.sandbox.listFolders({}),/busy/);assert.equal(c.counts().exportReads,0);}
});
test('export errors return no private parser or Drive details',()=>{
  for(const options of [{exportError:true},{exportText:'{"PRIVATE"'},{exportSize:11*1024*1024}])assert.throws(()=>context(fixture(),options).sandbox.listFolders({}),e=>/export is unavailable/.test(e.message)&&!/PRIVATE/.test(e.message));
});
