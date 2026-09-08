/* global __dirname */
// Exercise the screen's actual save handler with controlled network promises.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../app/rehab-plan.tsx'), 'utf8');
const ast = ts.createSourceFile('rehab-plan.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler;
function find(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'finishTodayForTesting') handler = node.initializer.getText(ast);
  ts.forEachChild(node, find);
}
find(ast);
assert.ok(handler);
const compiled = ts.transpileModule(`exports.save = ${handler}`, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const date = '2026-09-10';

function fixture({ dayComplete = true } = {}) {
  const pending = [];
  const events = [];
  const state = { busy: false, award: false, error: '', saved: 0 };
  const context = {
    exports: {}, data: { rehab_plan: ['reach', 'grasp', 'pinch', 'open'].map(id => ({ id, reps: 10, sets: 2 })) },
    finishingForTesting: false, testingScore: '90', planId: 'a1', isDemo: false,
    appNow: () => new Date(`${date}T12:00:00Z`), appDateString: () => date,
    PROGRESS_KEY: async (_plan, exercise) => exercise,
    storage: { getItem: async () => '', setItem: async () => true },
    setFinishingForTesting: value => { state.busy = value; },
    setSavedTestingExercises: value => { state.saved = typeof value === 'function' ? value(state.saved) : value; },
    setSaveError: value => { state.error = value; },
    setShowTestingFinish: () => {}, setShowAwardPrompt: value => { state.award = value; },
    loadProgress: async () => { events.push('reload'); },
    Haptics: { notificationAsync: () => {}, NotificationFeedbackType: { Success: 1 } },
    authedFetch: (url, options) => {
      const body = JSON.parse(options.body);
      events.push(url);
      if (url === '/api/alira/activities') return new Promise(resolve => pending.push({ body, resolve }));
      assert.equal(pending.length, 4);
      return Promise.resolve({ ok: true, json: async () => ({ status: dayComplete ? 'complete' : 'in_progress' }) });
    },
  };
  vm.runInNewContext(compiled, context);
  return { save: context.exports.save, pending, events, state };
}
const response = ok => ({ ok, json: async () => ({ ok }) });
const tick = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };

async function test() {
  const good = fixture();
  const run = good.save();
  assert.equal(good.pending.length, 4, 'all four independent saves should start immediately');
  assert.equal(good.state.busy, true);
  assert.equal(good.state.award, false);
  for (const [index, save] of good.pending.entries()) {
    assert.equal(save.body.average_score, 90);
    assert.equal(save.body.repetition_scores.length, 20);
    assert.equal(save.body.testing_shortcut, true);
    save.resolve(response(true));
    await tick();
    if (index < 3) assert.equal(good.events.includes('/api/users/daily-checkin/complete'), false);
  }
  await run;
  assert.equal(good.state.saved, 4);
  assert.equal(good.state.award, true);
  assert.equal(good.state.busy, false);
  assert.equal(good.events.at(-1), 'reload');

  const partial = fixture();
  const failed = partial.save();
  partial.pending[0].resolve(response(false));
  await tick();
  assert.equal(partial.state.busy, true, 'do not allow a retry while other writes are still running');
  partial.pending.slice(1).forEach(save => save.resolve(response(true)));
  await failed;
  assert.equal(partial.state.award, false);
  assert.ok(partial.state.error);
  assert.equal(partial.events.includes('/api/users/daily-checkin/complete'), false);
  assert.equal(partial.state.busy, false);

  const incomplete = fixture({ dayComplete: false });
  const incompleteRun = incomplete.save();
  incomplete.pending.forEach(save => save.resolve(response(true)));
  await incompleteRun;
  assert.equal(incomplete.state.award, false, 'an HTTP 200 without a completed day is not success');
  assert.ok(incomplete.state.error);
  assert.equal(new Set(good.pending.map(save => save.body.client_activity_id)).size, 4);
  assert.deepEqual(good.pending.map(save => save.body.client_activity_id), partial.pending.map(save => save.body.client_activity_id), 'retries keep the same idempotency keys');
  console.log('Score-save checks passed: concurrent saves, completion ordering, partial failure, safe retries.');
}
test().catch(error => { console.error(error); process.exitCode = 1; });
