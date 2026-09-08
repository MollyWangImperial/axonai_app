const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/journeyExerciseScores.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const exportsObject = {};
vm.runInNewContext(compiled, { exports: exportsObject }, { filename: 'journeyExerciseScores.js' });

const now = new Date('2026-09-08T12:00:00');
const result = exportsObject.weeklyExerciseScoreData([
  { id: 'manual-a', exercise_id: 'ex_reach', day: '2026-09-08', completed_reps: 5, average_score: 85, testing_shortcut: true },
  { id: 'manual-b', exercise_id: 'ex_grasp', day: '2026-09-08', completed_reps: 5, average_score: '90', testing_shortcut: true },
  { id: 'camera-a', exercise_id: 'ex_h2m', day: '2026-09-07', completed_reps: 5, average_score: 75 },
  { id: 'unscored', exercise_id: 'game', day: '2026-09-08', completed_reps: 1, average_score: null },
  { id: 'old', exercise_id: 'ex_reach', day: '2026-08-20', completed_reps: 5, average_score: 100 },
], now);

assert.deepEqual(Array.from(result.activities, item => item.id), ['camera-a', 'manual-a', 'manual-b']);
assert.deepEqual(
  Array.from(result.dailyScores, item => ({ day: item.day, average_score: item.average_score, session_count: item.session_count })),
  [
    { day: '2026-09-07', average_score: 75, session_count: 1 },
    { day: '2026-09-08', average_score: 87.5, session_count: 2 },
  ],
);

console.log('Journey daily exercise score tests passed');
