// Optional offline comparison. Pass the website dist directory and run the synthetic preview first.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const origin = 'http://127.0.0.1:8783';
const output = path.resolve(__dirname, '../local/visual-check');

async function appearance(page, selectors) {
  return page.evaluate(selectors => Object.fromEntries(selectors.map(selector => {
    const style = getComputedStyle(document.querySelector(selector));
    return [selector, ['fontFamily', 'fontSize', 'lineHeight', 'color', 'backgroundColor', 'padding',
      'borderTop', 'borderRadius', 'columnGap'].map(key => style[key])];
  })), selectors);
}

async function geometry(page) {
  return page.locator('.page-pair').evaluateAll(pairs => pairs.map(pair => {
    const image = pair.querySelector('img'), scan = pair.querySelector('.scan-sheet').getBoundingClientRect();
    const text = pair.querySelector('.transcript-sheet').getBoundingClientRect();
    return { imageId: pair.dataset.imageId, width: scan.width, height: scan.height, textWidth: text.width,
      textLeft: text.x - scan.x, textTop: text.y - scan.y, original: [image.naturalWidth, image.naturalHeight],
      fit: getComputedStyle(image).objectFit };
  }));
}

const site = path.resolve(process.argv[2] || '../ericlaslo-website/dist');
const demo = path.resolve(__dirname, '../local/demo');
const fixture = require('../test/inputs/demo.json').notes[0];

async function check(browser, size) {
  const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1 });
  const notes = await context.newPage(), letters = await context.newPage(), errors = [];
  for (const page of [notes, letters]) page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await notes.goto(origin);
  await notes.locator('#results summary').first().waitFor();
  assert.equal(await notes.locator('#results tr, #results img').count(), 0);
  await notes.locator('summary').filter({hasText:'Carriker'}).click();
  await notes.getByRole('link', {name: 'Loose cards'}).click();
  await notes.getByRole('link', {name: /^Read note:.*12a/}).click();
  await notes.locator('.scan-sheet img').nth(1).waitFor();
  const id = new URL(notes.url()).searchParams.get('note');
  const bundle = JSON.parse(fs.readFileSync(path.join(demo, 'exports/Field_notes_viewer.json')));
  const note = bundle.notes.find(n => n.note_id === id);
  assert.equal(note.provenance.provider, 'offline-fixture');
  const letter = {...note, letter_id:id, catalogue_names:{}, hints:{folder:'Example'}};
  const catalogue = { version:1, folders:[{name:'Example', letters:[letter]}], links:[], unresolved:[] };
  const assets = new Map([
    ['/birds/letter-reader/', 'letter-reader/index.html'], ['/birds/letter-reader/reader.js', 'letter-reader/reader.js'],
    ['/birds/assets/catalogue.js', 'assets/catalogue.js'], ['/birds/assets/birds.css', 'assets/birds.css'],
    ['/birds/assets/favicon.svg', 'assets/favicon.svg']
  ]);
  await letters.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort();
    if (assets.has(url.pathname)) return route.fulfill({path:path.join(site, assets.get(url.pathname))});
    if (url.pathname === '/birds/letter-reader/catalogue.json') return route.fulfill({json:catalogue});
    const scan = fixture.pages.find(p => url.pathname === '/birds/scans/Correspondence/' + p.path);
    if (scan) return route.fulfill({path:path.join(demo, 'cards', scan.path)});
    return route.abort();
  });
  await letters.goto(origin + '/birds/letter-reader/?letter=' + id);
  await letters.locator('.page-pair').nth(1).scrollIntoViewIfNeeded();
  for (const page of [notes, letters]) await page.waitForFunction(() => {
    const images = [...document.querySelectorAll('.scan-sheet img')];
    return images.length === 2 && images.every(img => img.naturalWidth > 0);
  });
  const panels = ['.site-header', 'h1', '.letter-nav', '.letter-heading h2', '.page-columns', '.scan-sheet', '.transcript-sheet pre', '.site-footer'];
  assert.deepEqual(await appearance(notes, panels), await appearance(letters, panels));
  const actual = await geometry(notes), reference = await geometry(letters);
  assert.equal(actual.length, reference.length);
  for (const [i, pair] of actual.entries()) {
    assert.equal(pair.imageId, reference[i].imageId);
    assert.equal(pair.width, reference[i].width);
    assert.equal(pair.textWidth, reference[i].textWidth);
    assert.deepEqual(pair.original, reference[i].original);
    assert.equal(pair.fit, 'contain');
    assert.ok(Math.abs(pair.width / pair.height - pair.original[0] / pair.original[1]) < 0.01);
    if (size.width > 760) assert.ok(pair.textLeft > 0 && pair.textWidth > pair.width);
    else assert.ok(pair.textLeft === 0 && pair.textTop > pair.height);
    assert.equal(await notes.getByRole('region', {name:'Transcription, page ' + (i + 1)}).locator('pre').first().textContent(), note.pages[i].text);
  }
  for (const [label, page] of [['notes', notes], ['website', letters]])
    await page.locator('.page-pair').first().screenshot({path:path.join(output, label + '-page-' + size.width + '.png')});
  await notes.getByRole('button', {name:'Enlarge scan'}).nth(1).click();
  await notes.locator('dialog[open]').waitFor();
  await notes.keyboard.press('Escape');
  await notes.getByRole('link', {name:/^Page 2\b/}).click();
  await notes.getByRole('region', {name:'Transcription, page 2'}).waitFor();
  assert.equal(new URL(notes.url()).searchParams.get('page'), '2');
  assert.equal(await notes.locator('.page-pair').count(), 2);
  await notes.goBack();
  await notes.getByRole('region', {name:'Transcription, page 1'}).waitFor();
  await notes.locator('#query').fill('0012');
  await notes.locator('#collector-filter').selectOption('');
  await notes.getByRole('button', {name:'Search', exact:true}).click();
  await notes.getByText('2 cards matching', {exact:false}).waitFor();
  assert.equal(await notes.locator('#results tbody tr').count(), 2);
  await notes.locator('#collector-filter').selectOption('Carriker');
  await notes.getByRole('button', {name:'Search', exact:true}).click();
  await notes.getByText('1 card matching', {exact:false}).waitFor();
  await notes.goto(origin + '/?number=8420');
  await notes.getByRole('link', {name:/^Read note:/}).click();
  assert.equal(await notes.locator('.transcript-sheet mark').textContent(), '8419-20');
  assert.deepEqual(errors, []);
  await context.close();
  return {viewport:size, firstPage:actual[0], secondPage:actual[1]};
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.FIELDNOTES_BROWSER_CHANNEL || 'msedge', headless: true });
  try {
    const results = [];
    for (const viewport of [{ width: 1365, height: 950 }, { width: 390, height: 844 }]) results.push(await check(browser, viewport));
    fs.writeFileSync(path.join(output, 'comparison.json'), JSON.stringify({ browser: browser.version(), results }, null, 2));
    console.log('Matched reference styles and panel geometry at 1365 and 390 px. Both reading and search flows passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
