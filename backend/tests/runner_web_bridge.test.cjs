const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const server = fs.readFileSync(path.join(__dirname, '..', 'server.py'), 'utf8');
const webShim = fs.readFileSync(path.join(__dirname, '..', '..', 'frontend', 'src', 'shims', 'webview-web.tsx'), 'utf8');

function bridgeFor(parameter, nativeBridge, referrer, embedded = true) {
  const source = server.match(new RegExp(`function postRN\\(${parameter}\\)\\{[\\s\\S]*?\\n\\}`));
  assert.ok(source, `Could not find ${parameter} runner bridge`);
  const parentMessages = [];
  const nativeMessages = [];
  const window = { parent: embedded ? { postMessage: (...args) => parentMessages.push(args) } : null };
  if (!embedded) window.parent = window;
  if (nativeBridge) window.ReactNativeWebView = { postMessage: value => nativeMessages.push(value) };
  const context = vm.createContext({ window, document: { referrer }, URL });
  vm.runInContext(`${source[0]}; postRN({ type: 'library_test_complete', task_result: { task_id: 'T1' } });`, context);
  return { parentMessages, nativeMessages };
}

for (const parameter of ['data', 'd']) {
  test(`${parameter} runner sends completion to a cross-origin web parent`, () => {
    const result = bridgeFor(parameter, false, 'https://rehyn.com/assessment?library_test=1');
    assert.equal(result.nativeMessages.length, 0);
    assert.equal(result.parentMessages.length, 1);
    assert.equal(result.parentMessages[0][1], 'https://rehyn.com');
    assert.deepEqual(JSON.parse(result.parentMessages[0][0]), {
      type: 'library_test_complete', task_result: { task_id: 'T1' },
    });
  });

  test(`${parameter} runner keeps native delivery single-path`, () => {
    const result = bridgeFor(parameter, true, 'https://rehyn.com/assessment');
    assert.equal(result.nativeMessages.length, 1);
    assert.equal(result.parentMessages.length, 0);
  });

  test(`${parameter} runner does not post from a top-level page`, () => {
    const result = bridgeFor(parameter, false, '', false);
    assert.equal(result.parentMessages.length, 0);
  });
}

test('web shim accepts messages only from its runner iframe', () => {
  assert.match(webShim, /ev\.source === iframeRef\.current\.contentWindow/);
  assert.match(webShim, /onMessageRef\.current\?\.\(\{ nativeEvent: \{ data \} \}\)/);
});
