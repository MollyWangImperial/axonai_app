/* global __dirname */
// Exercise Home's real 100-point collection callback with controlled API data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const homeSource = fs.readFileSync(path.join(__dirname, '../app/(tabs)/index.tsx'), 'utf8');
const componentSource = fs.readFileSync(path.join(__dirname, '../src/components/HundredPointCelebration.tsx'), 'utf8');
const ast = ts.createSourceFile('index.tsx', homeSource, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
let handler;
function find(node) {
  if (ts.isVariableDeclaration(node) && node.name.getText(ast) === 'collectHundredPointAward') {
    handler = node.initializer.getText(ast);
  }
  ts.forEachChild(node, find);
}
find(ast);
assert.ok(handler, 'Home must define the 100-point collection callback');
assert.match(componentSource, /testID="hundred-point-collect"/);
assert.match(componentSource, /onPress=\{onCollect\}/);
assert.doesNotMatch(componentSource, /hundred-point-continue/);

const compiled = ts.transpileModule(`exports.collect = ${handler}`, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const date = '2026-09-08';
const award = {
  name: 'Molly', points: 101, userId: 'patient-100',
  milestoneId: 'hundred_point_medal', testingRevision: 'test-revision',
};
const calendarPayload = {
  date,
  status: 'not_checked_in',
  medal_collected: false,
  available_medal_date: null,
  days: [{
    date, status: 'in_progress', medal: true, daily_medal: false,
    milestone_medals: [{ id: 'hundred_point_medal', name: 'Rehyn Consistency Champion', points: 101 }],
  }],
  collected_medal: { id: 'hundred_point_medal', name: 'Rehyn Consistency Champion', points: 101 },
};

function fixture(response) {
  const state = { award, busy: [], error: '', calendar: false, hiddenDailyMedal: false };
  const requests = [];
  const remembered = [];
  const cacheWrites = [];
  const cachedHome = { checkIn: { days: [] }, rewards: { points: 101 } };
  const context = {
    exports: {},
    useCallback: fn => fn,
    hundredPointAward: award,
    collectingHundredPoint: false,
    todayIso: date,
    rewards: { points: 101, medals: [{ id: 'hundred_point_medal', name: 'Rehyn Consistency Champion', threshold: 100, earned: true }] },
    setCollectingHundredPoint: value => state.busy.push(value),
    setHundredPointError: value => { state.error = value; },
    setCheckIn: value => { state.checkIn = value; },
    setRewards: value => { state.rewards = value; },
    setHundredPointAward: value => { state.award = value; },
    setShowMedal: value => { state.hiddenDailyMedal = value === false; },
    setCalendarHighlight: value => { state.highlight = value; },
    setShowCalendar: value => { state.calendar = value; },
    getScreenCache: () => cachedHome,
    setScreenCache: (key, value) => cacheWrites.push({ key, value }),
    rememberHundredPointCollection: async (...args) => remembered.push(args),
    Haptics: { notificationAsync() {}, NotificationFeedbackType: { Success: 'success' } },
    authedFetch: async (url, options) => {
      requests.push({ url, options });
      return response;
    },
  };
  vm.runInNewContext(compiled, context, { filename: 'collectHundredPointAward.js' });
  return { collect: context.exports.collect, state, requests, remembered, cacheWrites };
}

(async () => {
  const success = fixture({ ok: true, json: async () => calendarPayload });
  await success.collect();
  assert.deepEqual(success.state.busy, [true, false]);
  assert.equal(success.requests[0].url, '/api/users/rewards/milestones/hundred_point_medal/collect');
  assert.deepEqual(JSON.parse(success.requests[0].options.body), { date, testing_revision: 'test-revision' });
  assert.deepEqual(success.remembered[0], ['patient-100', 'hundred_point_medal', 'test-revision']);
  assert.equal(success.state.award, null);
  assert.equal(success.state.calendar, true);
  assert.equal(success.state.highlight, date);
  assert.equal(success.state.hiddenDailyMedal, true);
  assert.equal(success.state.checkIn.days[0].milestone_medals[0].points, 101);
  assert.equal(success.state.rewards.medals[0].celebrated, true);
  assert.equal(success.cacheWrites.at(-1).value.checkIn.days[0].medal, true);

  const failure = fixture({ ok: false, json: async () => ({ detail: 'Synthetic save failure' }) });
  await failure.collect();
  assert.deepEqual(failure.state.busy, [true, false]);
  assert.equal(failure.state.error, 'Synthetic save failure');
  assert.equal(failure.state.award, award, 'failed persistence keeps the award open');
  assert.equal(failure.state.calendar, false);
  assert.equal(failure.remembered.length, 0);

  console.log('100-point medal checks passed: Collect persists first, updates Home, and opens today in the calendar.');
})().catch(error => { console.error(error); process.exitCode = 1; });
