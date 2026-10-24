import test from 'node:test';
import assert from 'node:assert/strict';
import { initializeTokenPage } from '../public/vk-token.mjs';

function fixture({ referrer = 'https://vk.com/', response = { access_token: 'TEST_ONLY_TOKEN', scope: 'wall' }, failure } = {}) {
  const ids = ['context', 'authorize', 'status', 'result', 'token', 'copy', 'toggle', 'clear'];
  const ui = Object.fromEntries(ids.map(id => [id, {
    disabled: true, hidden: true, value: '', type: 'password', textContent: '', events: {},
    addEventListener(name, callback) { this.events[name] = callback; },
    setAttribute() {}, focus() {}, select() {}
  }]));
  const events = {}, requests = [], clipboard = [];
  const document = { referrer, getElementById: id => ui[id],
    defaultView: { addEventListener: (name, callback) => { events[name] = callback; } } };
  const bridge = { isWebView: () => false, isIframe: () => true,
    async send(method, params) {
      requests.push({ method, params });
      if (method === 'VKWebAppInit') return {};
      if (failure) throw failure;
      return response;
    } };
  return { ui, events, requests, clipboard, context: { bridge, document,
    location: { search: '?vk_app_id=1234' }, navigator: { clipboard: { writeText: async text => clipboard.push(text) } } } };
}

test('token request is explicit, asks only wall, and clears the result on leaving', async () => {
  const f = fixture();
  await initializeTokenPage(f.context);
  assert.deepEqual(f.requests.map(r => r.method), ['VKWebAppInit']);
  assert.equal(f.ui.token.value, '');
  await f.ui.authorize.events.click();
  assert.deepEqual(f.requests[1], { method: 'VKWebAppGetAuthToken', params: { app_id: 1234, scope: 'wall' } });
  assert.equal(f.ui.token.value, 'TEST_ONLY_TOKEN');
  assert.equal(f.ui.token.type, 'password');
  assert.deepEqual(f.clipboard, []);
  await f.ui.copy.events.click();
  assert.deepEqual(f.clipboard, ['TEST_ONLY_TOKEN']);
  f.events.pagehide();
  assert.equal(f.ui.token.value, '');
  assert.equal(f.ui.result.hidden, true);
});

test('outside VK or without a real app ID, authorization remains disabled', async () => {
  for (const referrer of ['https://example.invalid/', 'https://vk.com.attacker.invalid/', 'http://vk.com/', 'https://vk.com:9999/', '']) {
    const f = fixture({ referrer });
    await initializeTokenPage(f.context);
    assert.equal(f.ui.authorize.disabled, true);
    assert.deepEqual(f.requests, []);
  }
  const f = fixture();
  f.context.location.search = '';
  await initializeTokenPage(f.context);
  assert.deepEqual(f.requests, []);
});

test('missing wall grant and raw error secrets are never exposed as a successful token', async () => {
  const f = fixture({ response: { access_token: 'TEST_ONLY_TOKEN', scope: 'vkid.personal_info' } });
  await initializeTokenPage(f.context);
  await f.ui.authorize.events.click();
  assert.equal(f.ui.token.value, '');
  assert.equal(f.ui.result.hidden, true);
  const failed = fixture({ failure: { error_data: { error_code: 15, error_msg: 'TEST_ONLY_TOKEN',
    request_params: [{ access_token: 'TEST_ONLY_TOKEN' }] } } });
  await initializeTokenPage(failed.context);
  await failed.ui.authorize.events.click();
  assert.match(failed.ui.status.textContent, /15/);
  assert.ok(!failed.ui.status.textContent.includes('TEST_ONLY_TOKEN'));
  assert.equal(failed.ui.token.value, '');
});

test('a late authorization response cannot restore a token after pagehide', async () => {
  let resolve;
  const response = new Promise(done => { resolve = done; });
  const f = fixture({ response });
  await initializeTokenPage(f.context);
  const pending = f.ui.authorize.events.click();
  f.events.pagehide();
  resolve({ access_token: 'TEST_ONLY_TOKEN', scope: 'wall' });
  await pending;
  assert.equal(f.ui.token.value, '');
  assert.equal(f.ui.result.hidden, true);
  assert.equal(f.ui.authorize.disabled, true);
});
