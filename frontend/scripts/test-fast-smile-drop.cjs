const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../../backend/fast_screening.py'), 'utf8');
let runner = source.split('<script type="module">', 2)[1].split('</script>', 1)[0];
runner = runner
  .replace(/^import .*$/m, '')
  .replace(/window\.startDemo911Call=[\s\S]*$/, '');

let now = 1000;
const scheduled = [];
const fill = { style: {} };
const result = { className: '', innerHTML: '' };
const assistText = { textContent: '' };
const assist = { className: '', querySelector: () => assistText };
const canvas = { getContext: () => ({}) };
const elements = { video: {}, canvas, panel: {}, cameraLabel: {}, scanFill: fill, autoResult: result, assist };
const context = vm.createContext({
  console,
  document: { getElementById: id => elements[id] || null, querySelector: () => null },
  window: {},
  navigator: {},
  performance: { now: () => now },
  requestAnimationFrame: () => 0,
  cancelAnimationFrame: () => {},
  setTimeout: (callback, delay) => { scheduled.push({ callback, delay }); return scheduled.length; },
  clearTimeout: () => {},
});
vm.runInContext(runner, context);
vm.runInContext('current="face";stepStartedAt=1000;', context);

const landmarks = Array.from({ length: 292 }, () => ({ x: 0.5, y: 0.5 }));
landmarks[33] = { x: 0.3, y: 0.4 };
landmarks[263] = { x: 0.7, y: 0.4 };
landmarks[61] = { x: 0.4, y: 0.6 };
landmarks[291] = { x: 0.6, y: 0.6 };

function observe(smileActivation) {
  const faceResult = {
    faceLandmarks: [landmarks],
    faceBlendshapes: [{
      categories: [
        { categoryName: 'mouthSmileLeft', score: smileActivation },
        { categoryName: 'mouthSmileRight', score: smileActivation },
      ],
    }],
  };
  context.faceResult = faceResult;
  vm.runInContext('analyseFace(faceResult,null)', context);
}

for (let index = 0; index < 8; index += 1) {
  now += 34;
  observe(0.2);
}
assert.equal(vm.runInContext('automated.face.smile_was_established', context), true);
assert.equal(vm.runInContext('automated.face.decision', context), 'pending');

now += 34;
observe(0.01);
assert.equal(vm.runInContext('automated.face.decision', context), 'pending');

now += 500;
observe(0.01);
assert.equal(vm.runInContext('automated.face.decision', context), 'yes');
assert.equal(vm.runInContext('automated.face.positive', context), true);
assert.equal(fill.style.width, '100%');
assert.match(result.innerHTML, /Possible FAST sign detected/);
assert.match(assistText.textContent, /Moving to the arm check now/);
assert.equal(scheduled.at(-1).delay, 650);

console.log('FAST smile-drop check passed: early warning and arm-step transition are scheduled immediately.');
