// Run against the synthetic report fixture described in CONTRIBUTING.md.
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {chromium} = require(process.env.APPTRAIL_PLAYWRIGHT || 'playwright');
(async () => {
  const browser = await chromium.launch({channel: 'msedge', headless: true});
  try {
    const page = await browser.newPage({viewport: {width: 1100, height: 850}});
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => requests.push(request.url()));
    await page.setContent(fs.readFileSync(process.argv[2], 'utf8'));
    await page.locator('#review-controls').waitFor({state: 'visible'});
    const original = await page.locator('.saved-text').allTextContents();
    assert.equal(await page.locator('details:not([open])').count(), 3);
    await page.locator('#next-change').click();
    assert.equal(await page.locator('#change-status').textContent(), 'Change 1 of 2');
    await page.locator('#next-change').click();
    assert.equal(await page.locator('#change-status').textContent(), 'Change 2 of 2');
    await page.locator('#next-change').click();
    assert.equal(await page.locator('#change-status').textContent(), 'Change 1 of 2');
    await page.keyboard.press('Shift+F7');
    assert.equal(await page.locator('#change-status').textContent(), 'Change 2 of 2');
    const query = page.locator('#find-text');
    async function find(value, expected) {
      await query.fill(value);
      await page.waitForFunction(text => document.getElementById('find-status').textContent.includes(text), expected);
    }
    await page.keyboard.press('Control+f');
    assert.equal(await query.evaluate(node => node === document.activeElement), true);
    await find('café [a.*]', 'Match 1 of 2');
    assert.equal(await page.locator('.live-current').first().isVisible(), true);
    assert.equal(await page.locator('details[open]').count(), 1);
    await page.keyboard.press('F3');
    assert.match(await page.locator('#find-status').textContent(), /Match 2 of 2 · After line 6/);
    await page.keyboard.press('F3');
    assert.match(await page.locator('#find-status').textContent(), /Match 1 of 2/);
    await page.keyboard.press('Shift+Enter');
    assert.match(await page.locator('#find-status').textContent(), /Match 2 of 2/);
    // A literal query crossing token boundaries must remain one occurrence.
    await find(' = "😀 café', 'Match 1 of 2');
    assert.equal((await page.locator('.live-current').allTextContents()).join(''), ' = "😀 café');
    await find('CAFÉ', 'Match 1 of 2');
    await page.locator('#find-case').check();
    assert.equal(await page.locator('#find-status').textContent(), 'No matches in saved text');
    assert.equal(await page.locator('#next-match').isDisabled(), true);
    await page.locator('#find-case').uncheck();
    assert.match(await page.locator('#find-status').textContent(), /Match 1 of 2/);
    await find('[a.*]', 'Match 1 of 2');
    await find('⟦LF⟧', 'No matches in saved text');
    await find('Before', 'No matches in saved text');
    await page.locator('#clear-find').click();
    assert.equal(await page.locator('.live-hit').count(), 0);
    assert.deepEqual(await page.locator('.saved-text').allTextContents(), original);
    assert.ok(await page.locator('.syn-string').count());
    assert.ok(await page.locator('.word').count());
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    if (process.argv[3]) {
      await find('value_020', 'Match 1 of 2');
      await page.screenshot({path: process.argv[3], fullPage: false});
    }
    await page.setContent(fs.readFileSync(process.argv[2].replace(/\.html$/, '.empty.html'), 'utf8'));
    assert.equal(await page.locator('#next-change').isDisabled(), true);
    await page.locator('#find-text').fill('missing');
    await page.waitForFunction(() => document.getElementById('find-status').textContent === 'No matches in saved text');
    assert.equal(await page.locator('#next-match').isDisabled(), true);
    await page.setContent(fs.readFileSync(process.argv[2].replace(/\.html$/, '.limit.html'), 'utf8'));
    await page.locator('#find-text').fill('a');
    await page.waitForFunction(() => document.getElementById('find-status').textContent.includes('10000+'));
    assert.equal(await page.locator('.live-hit').count(), 10000);
    const fallback = await browser.newContext({javaScriptEnabled: false});
    const staticPage = await fallback.newPage();
    await staticPage.setContent(fs.readFileSync(process.argv[2], 'utf8'));
    assert.equal(await staticPage.locator('#review-controls').isVisible(), false);
    assert.equal(await staticPage.locator('noscript').isVisible(), true);
    assert.deepEqual(await staticPage.locator('.saved-text').allTextContents(), original);
    await fallback.close();
    assert.deepEqual(errors, []);
    assert.deepEqual(requests, []);
    console.log('Browser checks passed: navigation, wraparound, keyboard, literal/Unicode search, token boundaries, case, collapsed reveal, content preservation, offline CSP.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
