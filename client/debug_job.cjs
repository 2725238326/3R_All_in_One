const puppeteer = require('puppeteer-core');

process.on('unhandledRejection', (e) => { console.log('UnhandledRejection:', e); });
(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: false,
    args: ['--no-sandbox', '--disable-web-security', '--user-data-dir=C:\\Temp\\chrome-debug-profile'],
    defaultViewport: null,
  });
  const page = await browser.newPage();
  const errors = [];

  page.on('pageerror', (err) => errors.push('PAGE ERROR: ' + err.message + '\n' + (err.stack||'').substring(0,1500)));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push('[console.error] ' + msg.text());
  });

  await page.goto('http://127.0.0.1:4173', { waitUntil: 'networkidle2', timeout: 15000 });
  await new Promise(r => setTimeout(r, 2000));

  console.log('Initial root content length:', await page.evaluate(() => document.getElementById('root')?.innerHTML?.length || 0));

  // Find a finished job link
  const jobInfo = await page.evaluate(() => {
    const rows = document.querySelectorAll('.job-row, tr, .job-item, [data-job-id]');
    const result = [];
    for (const r of rows) {
      const id = r.getAttribute('data-job-id') || r.querySelector('[data-job-id]')?.getAttribute('data-job-id') || '';
      const text = r.textContent?.substring(0, 100) || '';
      if (id || /失败|完成|finished|failed/i.test(text)) {
        result.push({ id, text });
      }
    }
    return result.slice(0, 5);
  });
  console.log('Found jobs:', JSON.stringify(jobInfo, null, 2));

  // Click the inspect arrow (→) button on the finished job row
  const clicked = await page.evaluate(() => {
    const rows = document.querySelectorAll('tbody tr');
    for (const r of rows) {
      if (r.textContent && /失败|完成/.test(r.textContent)) {
        const btns = r.querySelectorAll('button');
        for (const b of btns) {
          if (b.textContent && b.textContent.includes('→')) {
            b.click();
            return 'inspect arrow on: ' + r.textContent.substring(0, 80);
          }
        }
        r.click();
        return 'row clicked: ' + r.textContent.substring(0, 80);
      }
    }
    return null;
  });
  console.log('Clicked:', clicked);
  await new Promise(r => setTimeout(r, 3000));

  console.log('\nAfter click, root length:', await page.evaluate(() => document.getElementById('root')?.innerHTML?.length || 0));
  console.log('Body text snapshot:');
  const body = await page.evaluate(() => document.body.innerText.substring(0, 500));
  console.log(body);
  console.log('\nErrors:');
  errors.forEach(e => console.log(' -', e.substring(0, 1500)));

  await new Promise(r => setTimeout(r, 5000));
  await browser.close();
})();
