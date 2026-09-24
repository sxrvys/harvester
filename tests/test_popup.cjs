// Exercise the actual popup script against a small browser/DOM boundary.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const elements = new Map();
function element(selector) {
  if (!elements.has(selector)) elements.set(selector, {
    value: selector === '#video-preset' ? 'h264_all_keyframes' : selector === '#audio-preset' ? 'wav_48k_24' : '',
    disabled: false, hidden: false, textContent: '', listeners: {},
    addEventListener(type, callback) { this.listeners[type] = callback; }
  });
  return elements.get(selector);
}
const sent = [];
const context = vm.createContext({URL, setInterval() {}, window: {close() {}},
  document: {querySelector: element},
  browser: {
    tabs: {query: async () => [{id: 1, url: 'https://www.youtube.com/watch?v=abcdefghijk'}]},
    runtime: {sendMessage: async message => {
      if (message.command === 'get_companion_status') return {ok: true, result: {configured: false, v2_queue: true, v2_public_pages: true}};
      if (message.command === 'get_harvest_state') return {state: 'running', message: 'Old legacy work'};
      sent.push(message);
      return {ok: true, result: {state: 'queued'}};
    }}
  }
});
vm.runInContext(fs.readFileSync('extension/firefox/popup.js', 'utf8'), context);
(async () => {
  await context.initialize();
  assert.equal(element('#harvest').disabled, false, 'v2 submission must ignore legacy busy state');
  assert.equal(element('#queue-controls').hidden, false);
  element('#bundle-name').value = ' Night scene ';
  element('#clip-start').value = '0:10';
  element('#clip-end').value = '0:20';
  await context.submitToQueue(false);
  assert.equal(sent[0].start, false);
  assert.equal(sent[0].name, 'Night scene');
  assert.equal(sent[0].options.start, 10);
  assert.match(element('#status').textContent, /Added to queue/);
  await element('#harvest').listeners.click();
  assert.equal(sent[1].start, true);
  assert.match(element('#status').textContent, /follow progress/);
  element('#clip-end').value = '0:05';
  await context.submitToQueue(true);
  assert.equal(sent.length, 2, 'invalid range must not enqueue anything');
  assert.match(element('#status').textContent, /end after start/);
  context.browser.tabs.query = async () => [{id: 1, url: 'https://archive.org/details/chi_000108'}];
  await context.initialize();
  assert.equal(element('#queue-controls').hidden, false, 'generic public pages get naming and queue controls');
  assert.equal(element('#harvest').disabled, false);
  element('#clip-start').value = '';
  element('#clip-end').value = '';
  await context.submitToQueue(false);
  assert.equal(sent[2].url, 'https://archive.org/details/chi_000108');
  console.log('Firefox naming, queue-only, and immediate-harvest tests passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
