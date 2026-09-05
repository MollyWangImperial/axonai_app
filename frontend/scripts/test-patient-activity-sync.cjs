/* global __dirname */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/patientActivitySync.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText;

function harness(disk = new Map()) {
  const state = { user: 'patient-a', online: true, writesFail: false, sent: [] };
  const cache = new Map();
  const asyncStorage = {
    getAllKeys: async () => [...disk.keys()],
    multiGet: async (keys) => keys.map((key) => [key, disk.get(key) || null]),
    setItem: async (key, value) => { if (state.writesFail) throw new Error('Disk full'); disk.set(key, value); },
    removeItem: async (key) => { disk.delete(key); },
  };
  const storage = { setItem: async (key, value) => { cache.set(key, value); return true; } };
  const exports = {};
  vm.runInNewContext(source, {
    exports, AbortController, setTimeout, clearTimeout,
    require: (id) => {
      if (id === '@/src/auth') return { getUserId: async () => state.user };
      if (id === '@/src/config') return { API_BASE: 'https://test.invalid' };
      if (id === '@/src/utils/storage') return { storage };
      if (id === '@react-native-async-storage/async-storage') return asyncStorage;
      throw new Error(id);
    },
    fetch: async (url, init) => {
      state.sent.push({ url, user: init.headers['X-User-Id'], body: init.body && JSON.parse(init.body) });
      return { ok: state.online, json: async () => ({ ok: state.online, progress: { ex_grasp: { completed_reps: 3, day: '2026-09-05' } } }) };
    },
  });
  return { api: exports, state, disk, cache };
}
const rep = (n) => ({ id: `attempt:rep:${n}`, path: '/api/users/exercise-repetitions', body: { rep: n, score: 80 } });

test('failed network saves survive reopening and sync for the same account', async () => {
  const first = harness();
  first.state.online = false;
  await first.api.queuePatientActivity('patient-a', rep(1));
  assert.equal(await first.api.flushPatientActivities(), false);
  assert.equal(first.disk.size, 1);
  const reopened = harness(first.disk);
  assert.equal(await reopened.api.flushPatientActivities(), true);
  assert.equal(first.disk.size, 0);
  assert.equal(reopened.state.sent[0].body.rep, 1);
});

test('another account never receives the first account pending activity', async () => {
  const { api, state, disk } = harness();
  await api.queuePatientActivity('patient-a', rep(1));
  state.user = 'patient-b';
  assert.equal(await api.flushPatientActivities(), true);
  assert.equal(state.sent.length, 0);
  assert.equal(disk.size, 1);
  await assert.rejects(api.patientRequest('patient-a', '/anything'));
});

test('duplicate events and concurrent tabs do not lose or double-send repetitions', async () => {
  const first = harness();
  const second = harness(first.disk);
  await Promise.all([
    first.api.queuePatientActivity('patient-a', rep(1)),
    second.api.queuePatientActivity('patient-a', rep(2)),
    first.api.queuePatientActivity('patient-a', rep(1)),
  ]);
  assert.equal(first.disk.size, 2);
  await Promise.all([first.api.flushPatientActivities(), first.api.flushPatientActivities()]);
  assert.equal(first.state.sent.length, 2);
});

test('a storage failure is explicit and cannot erase other pending activity', async () => {
  const { api, state, disk } = harness();
  await api.queuePatientActivity('patient-a', rep(1));
  state.writesFail = true;
  await assert.rejects(api.queuePatientActivity('patient-a', rep(2)), /Disk full/);
  assert.equal(disk.size, 1);
});

test('records save in repetition, completed session, then check-in order', async () => {
  const { api, state } = harness();
  await api.queuePatientActivity('patient-a', { id: 'a', path: '/api/users/daily-checkin/complete', body: {} });
  await api.queuePatientActivity('patient-a', { id: 'b', path: '/api/alira/activities', body: {} });
  await api.queuePatientActivity('patient-a', rep(1));
  await api.flushPatientActivities();
  assert.deepEqual(state.sent.map((item) => item.url.split('/').pop()), ['exercise-repetitions', 'activities', 'complete']);
});

test('confirmed progress is fetched from MongoDB API and cached for that account only', async () => {
  const { api, cache } = harness();
  const result = await api.loadAccountExerciseProgress('plan-1', '2026-09-05');
  assert.equal(result.ex_grasp.completed_reps, 3);
  assert.ok(cache.has('ex_progress_v2:patient-a:plan-1:ex_grasp'));
});

test('failed progress reads are not converted into empty progress', async () => {
  const { api, state, cache } = harness();
  state.online = false;
  await assert.rejects(api.loadAccountExerciseProgress('plan-1', '2026-09-05'), /temporarily unavailable/);
  assert.equal(cache.size, 0);
});
