const {test} = require('node:test');
const assert = require('node:assert/strict');
const {
  legacyForwardLeanDegrees,
  newForwardLeanEvidence,
  createTemporalState,
  updateTemporalState,
} = require('../trunk_lean_metrics.js');

function sample(overrides = {}) {
  return {
    valid: true,
    trunk_projection_visible: true,
    shoulder_width: 0.20,
    shoulder_line_delta: 0,
    ear_width: 0.08,
    trunk_depth_tilt: 5,
    torso_length: 0.40,
    shoulder_width_corrected: 0.30,
    hip_width_corrected: 0.28,
    torso_length_corrected: 0.40,
    torso_area_corrected: 0.10,
    aspect: 1.5,
    points: {},
    ...overrides,
  };
}

test('legacy detector preserves the current Graded Forward Reach calculation', () => {
  const baseline = sample();
  const current = sample({
    shoulder_width: 0.24,
    ear_width: 0.096,
    trunk_depth_tilt: 22,
    torso_length: 0.36,
  });
  const shoulder = Math.asin(2 * (1 - 0.20 / 0.24)) * 180 / Math.PI;
  const face = Math.asin(1.5 * (1 - 0.08 / 0.096)) * 180 / Math.PI;
  const shortening = Math.acos((0.36 / 0.24) / (0.40 / 0.20)) * 180 / Math.PI;
  const expected = Math.max(Math.min(shoulder, face), Math.min(17, shortening));
  assert.ok(Math.abs(legacyForwardLeanDegrees(current, baseline) - expected) < 1e-10);
});

test('new detector cancels uniform camera approach using hip normalization', () => {
  const baseline = sample();
  const zoomed = sample({
    shoulder_width: 0.24,
    ear_width: 0.096,
    torso_length: 0.48,
    shoulder_width_corrected: 0.36,
    hip_width_corrected: 0.336,
    torso_length_corrected: 0.48,
  });
  assert.ok(legacyForwardLeanDegrees(zoomed, baseline) > 12);
  const result = newForwardLeanEvidence(zoomed, baseline);
  assert.equal(result.detected, false);
  assert.ok(result.degrees < 0.001);
  assert.ok(Math.abs(result.pelvisScale - 1.2) < 1e-10);
});

test('new detector requires two agreeing geometric cues', () => {
  const baseline = sample();
  const lean = sample({
    shoulder_width_corrected: 0.345,
    hip_width_corrected: 0.28,
    ear_width: 0.0944,
    torso_length_corrected: 0.376,
    trunk_depth_tilt: 21,
  });
  const result = newForwardLeanEvidence(lean, baseline);
  assert.equal(result.supported, true);
  assert.equal(result.detected, true);
  assert.ok(result.degrees > 12);
});

test('both detectors use the production 8-frame and 35-percent confirmation rule', () => {
  const state = createTemporalState();
  for (let index = 0; index < 7; index += 1) updateTemporalState(state, 15);
  assert.equal(state.confirmed, false);
  updateTemporalState(state, 15);
  assert.equal(state.confirmed, true);
  assert.equal(state.aboveFrames, 8);
  assert.equal(state.ratio, 1);
  for (let index = 0; index < 30; index += 1) updateTemporalState(state, 0);
  assert.equal(state.confirmed, true, 'the result remains visible after the patient returns upright');
});
