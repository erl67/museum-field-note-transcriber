// Optional browser QA. Point this at the running synthetic preview with its reference route enabled.
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

async function check(browser, size) {
  const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1 });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const notes = await context.newPage(), letters = await context.newPage(), errors = [];
  for (const page of [notes, letters]) page.on('pageerror', error => errors.push(error.message));
  await Promise.all([notes.goto(origin), letters.goto(origin + '/reference')]);
  for (const page of [notes, letters]) await page.locator('.folder[open] tbody a').first().waitFor();
  assert.match(await notes.locator('.folder[open] summary').textContent(), /Carriker/);
  const common = ['.site-header', 'h1', '.intro', '#query', 'button', '.folder', '.folder summary', 'th', '.catalogue-summary', '.site-footer'];
  assert.deepEqual(await appearance(notes, common), await appearance(letters, common));
  for (const [name, page] of [['notes', notes], ['reference', letters]]) {
    await page.screenshot({ path: path.join(output, name + '-catalogue-' + size.width + '.png') });
  }
  const link = notes.locator('.folder[open] tbody a').first();
  const id = new URL(await link.getAttribute('href'), origin).searchParams.get('note');
  await Promise.all([link.click(), letters.goto(origin + '/reference?letter=' + encodeURIComponent(id))]);
  for (const page of [notes, letters]) {
    await page.waitForFunction(() => document.querySelectorAll('.scan-sheet img').length === 2 &&
      [...document.querySelectorAll('.scan-sheet img')].every(img => img.complete && img.naturalWidth > 0));
  }
  const panels = ['.letter-nav', '.letter-heading h2', '.letter-summary', '.page-columns', '.scan-sheet', '.transcript-sheet pre', '.panel'];
  assert.deepEqual(await appearance(notes, panels), await appearance(letters, panels));
  const actual = await geometry(notes), expected = await geometry(letters);
  // The added enlargement button makes the mobile caption taller. Compare the sheets themselves.
  for (let i = 0; i < actual.length; i++) {
    const { textTop, ...sheet } = actual[i], { textTop: referenceTop, ...referenceSheet } = expected[i];
    assert.deepEqual(sheet, referenceSheet);
    assert.equal(sheet.fit, 'contain');
    assert.ok(Math.abs(sheet.width / sheet.height - sheet.original[0] / sheet.original[1]) < 0.01);
    if (size.width > 760) { assert.equal(textTop, referenceTop); assert.ok(sheet.textLeft > 0); }
    else { assert.equal(sheet.textLeft, 0); assert.ok(textTop > sheet.height && referenceTop > sheet.height); }
  }
  for (const [name, page] of [['notes', notes], ['reference', letters]]) {
    await page.locator('.page-pair').first().screenshot({ path: path.join(output, name + '-page-' + size.width + '.png') });
  }
  await notes.getByRole('button', { name: 'Enlarge scan' }).first().click();
  await notes.locator('dialog[open] img').waitFor();
  await notes.keyboard.press('Escape');
  await notes.getByRole('link', { name: '← Browse notes' }).first().click();
  await notes.locator('#browse-mode').selectOption('species');
  await notes.getByRole('heading', { name: 'Species groups' }).waitFor();
  await notes.locator('#collector-filter').selectOption('Carriker');
  await notes.locator('#query').fill('12a');
  await notes.getByRole('button', { name: 'Search', exact: true }).click();
  await notes.waitForFunction(() => document.querySelector('#message').textContent.startsWith('1 note(s) in 1 species group'));
  await notes.getByRole('button', { name: 'Show all' }).click();
  await notes.waitForFunction(() => document.querySelector('#message').textContent.startsWith('3 note(s)'));
  assert.deepEqual(errors, []);
  await context.close();
  return { viewport: size, pages: actual };
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
