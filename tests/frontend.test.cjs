const assert = require('node:assert/strict');
const { test } = require('node:test');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function harness(fetch) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      innerHTML: 'private data', value: 'private input', textContent: '',
      classList: { add() {}, remove() {}, toggle() {} },
      replaceChildren() { this.innerHTML = ''; },
      appendChild() {}, addEventListener() {}, remove() {},
      insertAdjacentHTML(_, html) { this.innerHTML += html; },
    });
    return elements.get(id);
  }
  const input = element('input');
  const context = vm.createContext({
    fetch, setTimeout: () => 0,
    document: { getElementById: element, querySelectorAll: () => [input],
      addEventListener() {}, createElement: () => element('toast') },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8'), context);
  return { context, element, input, run: (script) => vm.runInContext(script, context) };
}
const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });

test('logout clears sensitive DOM and late profile response cannot repopulate it', async () => {
  let release;
  const h = harness(async (url) => {
    if (url === '/api/profile') return new Promise(resolve => { release = resolve; });
    return response({}, url === '/api/auth/me' ? 401 : 200);
  });
  await new Promise(resolve => setImmediate(resolve));
  h.run('currentUser = { id: 2, username: "alice" }');
  const pending = h.run('loadProfile()');
  await h.run('logout()');
  release(response({ full_name: 'PRIVATE', ssn: 'PRIVATE', username: 'alice' }));
  await pending;
  assert.equal(h.element('profile-info').innerHTML, '');
  assert.equal(h.element('doc-detail').innerHTML, '');
  assert.equal(h.element('admin-users').innerHTML, '');
  assert.equal(h.input.value, '');
  assert.equal(h.run('currentUser'), null);
});

test('failed server logout does not pretend to terminate the session', async () => {
  const h = harness(async url => response({}, url === '/api/auth/logout' ? 500 : 401));
  await new Promise(resolve => setImmediate(resolve));
  h.run('currentUser = { id: 2, username: "alice" }');
  await h.run('logout()');
  assert.equal(h.run('currentUser.id'), 2);
});

test('document pagination requests a bounded page and escapes titles', async () => {
  const requests = [];
  const h = harness(async url => {
    requests.push(url);
    if (url.startsWith('/api/documents')) return response([
      { id: 3, owner_id: 2, title: '<img onerror=alert(1)>', visibility: 'private' },
    ]);
    return response({}, 401);
  });
  await new Promise(resolve => setImmediate(resolve));
  h.run('currentUser = { id: 2, username: "alice" }');
  await h.run('loadDocs(50)');
  assert.ok(requests.includes('/api/documents?limit=50&offset=50'));
  assert.ok(h.element('doc-list').innerHTML.includes('&lt;img'));
  assert.ok(h.element('doc-list').innerHTML.includes('data-offset="0"'));
});
