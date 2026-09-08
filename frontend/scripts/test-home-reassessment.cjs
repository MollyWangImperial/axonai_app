/* global __dirname */
// Run with: node scripts/test-home-reassessment.cjs
// Render the real Home component with cached account state and inspect its
// day cards and navigation callbacks, without requiring a native runtime.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const today = '2026-09-10';
const source = fs.readFileSync(path.join(__dirname, '../app/(tabs)/index.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
}).outputText;

function render({ due = false, canStart = true, checkedIn = true, complete = false, initial = false, exercises = ['reach', 'grasp'], width = 1440 } = {}) {
  const routes = [];
  const cache = {
    history: initial ? [] : [{ id: 'assessment-1', created_at: '2026-09-01T12:00:00Z', assessment_package: 'hand' }],
    carePlan: {
      account_state: { has_completed_initial_assessment: !initial },
      assessment: { due, can_start: canStart, packages: ['hand'], task_ids: ['H1', 'H3'], due_at: today },
      daily_monitoring: { active_exercise_ids: exercises, completed_exercise_ids_today: complete ? exercises : [], remaining_exercise_ids_today: complete ? [] : exercises },
      next_step: { destination: 'rehab_plan' },
    },
    checkIn: { date: today, status: checkedIn ? 'in_progress' : 'not_checked_in', days: [] },
  };
  const element = (type, props) => ({ type, props });
  const noop = () => {};
  const mocks = {
    'react': { useState: value => [typeof value === 'function' ? value() : value, noop], useMemo: fn => fn(), useCallback: fn => fn, useRef: value => ({ current: value }), useEffect: noop },
    'react/jsx-runtime': { jsx: element, jsxs: element, Fragment: 'Fragment' },
    'react-native': { StyleSheet: { create: value => value }, Animated: { createAnimatedComponent: value => value }, useWindowDimensions: () => ({ width }) },
    'expo-router': { useRouter: () => ({ push: route => routes.push(route) }), useFocusEffect: noop },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0 }) },
    'expo-haptics': { selectionAsync: noop, impactAsync: noop, ImpactFeedbackStyle: { Medium: 1 } },
    '@/src/screenCache': { getScreenCache: () => cache },
    '@/src/displayPreferences': { useDisplayPreferences: () => ({ palette: {} }) },
    '@/src/theme': { colors: {}, radius: {}, spacing: {} },
    '@/src/appDate': { appDateString: () => today, parseLocalDate: value => new Date(`${value}T12:00:00`), isAppDateOverridden: () => true },
  };
  const sandbox = { exports: {}, require: name => mocks[name] || {} };
  vm.runInNewContext(compiled, sandbox, { filename: 'HomeScreen.js' });
  const tree = sandbox.exports.default();
  const cards = [];
  function visit(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) return node.forEach(visit);
    if (node.type?.name === 'DayStep') cards.push(node.props);
    visit(node.props?.children);
  }
  visit(tree);
  return { cards, routes };
}

for (const width of [390, 1440]) {
  for (const complete of [false, true]) {
    const { cards, routes } = render({ due: true, complete, width });
    const primary = cards[1];
    assert.equal(primary.title, 'Re-assessment');
    assert.equal(primary.button.label, 'Start re-assessment');
    assert.equal(primary.icon, 'clipboard-outline');
    assert.equal(primary.progress, undefined);
    assert.notEqual(primary.badge.props.label, 'Complete');
    primary.button.onPress();
    assert.equal(routes[0].pathname, '/session-check');
    assert.equal(routes[0].params.target, 'assessment');
    assert.equal(routes[0].params.mode, 'followup');
    assert.equal(routes[0].params.package, 'hand');
    assert.equal(routes[0].params.task_ids, 'H1,H3');
  }
  const regular = render({ width });
  assert.equal(regular.cards[1].title, "Today's exercises");
  assert.equal(regular.cards[1].button.label, 'Continue exercises');
  assert.equal(regular.cards[1].progress.total, 2);
  regular.cards[1].button.onPress();
  assert.equal(regular.routes[0].pathname, '/rehab-plan');
  assert.equal(render({ due: true, checkedIn: false, width }).cards[1].button, undefined);
  assert.equal(render({ due: true, canStart: false, width }).cards[1].title, "Today's exercises");
  assert.equal(render({ due: true, initial: true, width }).cards[1].title, 'Initial assessment');
  assert.equal(render({ due: true, exercises: [], width }).cards[1].title, 'Re-assessment');
  assert.equal(render({ due: false, complete: true, width }).cards[1].button.label, 'Review exercises');
}
console.log('Home re-assessment regression checks passed at mobile and desktop widths.');
