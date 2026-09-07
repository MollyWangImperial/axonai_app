const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const records = new Map();
const storage = {
  getItem: async (key, fallback) => records.has(key) ? JSON.parse(records.get(key)) : fallback,
  setItem: async (key, value) => { records.set(key, JSON.stringify(value)); return true; },
  removeItem: async key => { records.delete(key); return true; },
};
const asyncStorage = {
  getAllKeys: async () => [...records.keys()],
  multiRemove: async keys => keys.forEach(key => records.delete(key)),
  getItem: async key => records.get(key) || null,
  setItem: async (key, value) => records.set(key, value),
};
let fetchImpl;
const modules = {
  '@/src/utils/storage': { storage },
  '@/src/screenCache': { clearScreenCache() {} },
  '@/src/config': { API_BASE: 'http://qa.invalid' },
  '@react-native-async-storage/async-storage': { default: asyncStorage, __esModule: true },
};
function load(relativePath, name) {
  const source = fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const exports = {};
  vm.runInNewContext(output, { exports, require: key => {
    assert.ok(modules[key], key); return modules[key];
  }, setTimeout, clearTimeout, Headers, Response, AbortController,
  fetch: (...args) => fetchImpl(...args) }, { filename: relativePath });
  modules[name] = exports;
  return exports;
}
const cache = load('src/accountResetStorage.ts', '@/src/accountResetStorage');
const auth = load('src/auth.ts', '@/src/auth');
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

(async () => {
  const user = { id: 'qa-one', name: 'QA', email: 'qa@example.invalid', role: 'patient', trial_access_granted: true, credits: 100 };
  await storage.setItem(auth.USER_KEY, user.id);
  await storage.setItem(auth.USER_OBJ, JSON.stringify(user));
  await storage.setItem('trial_access_code_v1:http://qa.invalid', 'keep-access');
  await storage.setItem(auth.onboardingCompleteKey(user.id), '1');
  await storage.setItem('patient_activity_v1:qa-one', 'old');
  await storage.setItem('pending_patient_activity_v1:http://qa.invalid:qa-one:rep-1', 'old');
  await storage.setItem('patient_activity_v1:qa-other', 'other progress');
  await storage.setItem('persona_session_legacy', 'not-owned-by-this-account');
  await storage.setItem('rehyn_text_size_v1', 'Large');
  await storage.setItem('rehyn_voice_guidance_v1', false);
  const preferences = load('src/userPreferences.ts', '@/src/userPreferences');
  assert.equal((await preferences.loadUserPreferences()).voiceGuidance, false, 'an existing account keeps its saved voice setting');
  assert.equal(cache.belongsToResetAccount('patient_activity_v1:qa-one-more', 'qa-one'), false);
  assert.equal(cache.belongsToResetAccount('pending_patient_activity_v1:http://qa.invalid:qa-one:rep', 'qa-one'), true);

  let firstRequestId;
  fetchImpl = async (url, init) => {
    assert.ok(url.endsWith('/api/users/account/reset'));
    firstRequestId = JSON.parse(init.body).request_id;
    return response({ detail: 'Synthetic failure' }, 503);
  };
  await assert.rejects(auth.resetAccount, /Synthetic failure/);
  assert.equal(await storage.getItem(auth.onboardingCompleteKey(user.id)), '1');
  assert.equal(await storage.getItem('patient_activity_v1:qa-one'), 'old');

  const fresh = { ...user, account_generation: 1, account_reset_at: '2026-09-07', profile: null, onboarding_complete: false,
    consent_accepted: false, consent_required: true, daily_checkins: {} };
  fetchImpl = async (_url, init) => {
    assert.equal(JSON.parse(init.body).request_id, firstRequestId, 'retry must reuse the request ID');
    return response({ ok: true, user: fresh });
  };
  await auth.resetAccount();
  assert.equal(await storage.getItem(auth.onboardingCompleteKey(user.id), ''), '');
  assert.equal(records.has('pending_patient_activity_v1:http://qa.invalid:qa-one:rep-1'), false);
  assert.equal(await storage.getItem('patient_activity_v1:qa-other'), 'other progress');
  assert.equal(await storage.getItem('persona_session_legacy'), 'not-owned-by-this-account');
  assert.equal(await storage.getItem('rehyn_text_size_v1'), 'Large');
  assert.equal(await storage.getItem('trial_access_code_v1:http://qa.invalid'), 'keep-access');
  assert.equal((await auth.getCachedUser()).id, 'qa-one');
  assert.equal(await auth.getAccountGeneration('qa-one'), 1);
  assert.equal((await preferences.loadUserPreferences()).voiceGuidance, true, 'a reset generation must start with voice guidance on');
  await preferences.saveUserPreference('voiceGuidance', false);
  assert.equal(await storage.getItem(preferences.voiceGuidanceKey('qa-one', 1), true), false);
  assert.equal((await preferences.loadUserPreferences()).voiceGuidance, false, 'the reset account may still turn voice guidance off');

  // New progress survives later hydrations of the same generation.
  await storage.setItem(auth.onboardingCompleteKey(user.id), '1');
  await auth.hydrateAccountStateFromServer(fresh);
  assert.equal(await storage.getItem(auth.onboardingCompleteKey(user.id)), '1');
  // A reset account must never inherit another locally completed survey.
  await storage.removeItem(auth.onboardingCompleteKey(user.id));
  await storage.setItem(auth.onboardingCompleteKey('qa-other'), '1');
  await auth.recoverSingleAccountCache('qa-one');
  assert.equal(await storage.getItem(auth.onboardingCompleteKey(user.id), ''), '');
  fetchImpl = async (_url, init) => {
    assert.equal(init.headers.get('X-Account-Generation'), '1');
    assert.equal(init.headers.get('X-User-Id'), 'qa-one');
    return response({ ok: true });
  };
  await auth.authedFetch('/api/users/onboarding', { method: 'POST' });
  console.log('PASS: scoped cleanup, retained identity, reset voice default, failed reset, idempotent retry, cache recovery, generation headers');
})().catch(error => { console.error(error); process.exitCode = 1; });
