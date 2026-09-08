"""Graded reach must detect trunk substitution even when arm movement is small."""

import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_graded_reach_test")

from backend import server
from backend.tests.test_grasp_wrist_alignment import run_js, runner_js


@pytest.fixture(scope="module")
def reach_js(runner_js):
    cfg = server._configure_rehab_runner("ex_reach", "medium", "standard")
    return runner_js + f"\nfor(const key of Object.keys(CFG)) delete CFG[key]; Object.assign(CFG,{json.dumps(cfg)}); Object.assign(STANDARD,CFG.movement_standard);" + r"""
HAS_SIDE_LEAN_RULE=false;
function reachSetup(){
  const {lm}=fixture();
  lm[ACTIVE.elbow]={x:.64,y:.45,z:0,visibility:1};
  lm[ACTIVE.wrist]={x:.65,y:.6,z:0,visibility:1};
  lm[7]={x:.46,y:.19,z:0,visibility:1}; lm[8]={x:.54,y:.19,z:0,visibility:1};
  baselineMetrics=rawMovementMetrics(lm,null);
  resetRepMetrics(); currentSubStep=0;
  return lm;
}
function pitchTrunk(base,degrees){
  const lm=structuredClone(base), a=degrees*Math.PI/180;
  // Rigid pitch about the hips preserves shoulder/elbow joint angles, moves
  // the wrist only slightly on screen, and does not enlarge projected widths.
  for(let i=0;i<23;i++){
    const length=.7-base[i].y;
    lm[i].y=.7-length*Math.cos(a);
    lm[i].z=-length*Math.sin(a);
  }
  return lm;
}
function approachTrunk(base,degrees){
  const lm=structuredClone(base), a=degrees*Math.PI/180;
  const shoulderScale=1/(1-Math.sin(a)/2), faceScale=1/(1-Math.sin(a)/1.5);
  for(const i of [11,12]) lm[i].x=.5+(base[i].x-.5)*shoulderScale;
  for(const i of [7,8]) lm[i].x=.5+(base[i].x-.5)*faceScale;
  return lm;
}
function collect(lm,count=30){for(let i=0;i<count;i++) updateMetrics(lm,null);}
function ids(){return confirmedCompensations().map(rule=>rule.id);}
"""


def test_clear_forward_pitch_is_detected_without_face_or_shoulder_enlargement(reach_js):
    run_js(reach_js, """
      const base=reachSetup(), lm=pitchTrunk(base,30), raw=rawMovementMetrics(lm,null);
      assert.ok(Math.abs(raw.shoulder_width-baselineMetrics.shoulder_width)<1e-6);
      assert.ok(Math.abs(raw.ear_width-baselineMetrics.ear_width)<1e-6);
      assert.ok(forwardLeanDegrees(raw)>=25);
      collect(lm);
      assert.ok(ids().includes('trunk_lean'));
      assert.match(pickFeedback(),/trunk leaned forward/);
      assert.equal(computeRepScore(),70);
    """)


def test_front_approach_is_counted_when_arm_gate_stays_closed(reach_js):
    run_js(reach_js, """
      const base=reachSetup(), lm=approachTrunk(base,25), raw=rawMovementMetrics(lm,null);
      const wristTravel=Math.hypot(raw.active_wrist_x-baselineMetrics.active_wrist_x,raw.active_wrist_y-baselineMetrics.active_wrist_y);
      assert.ok(wristTravel<raw.shoulder_width*.5);
      const target=STANDARD.rom_steps.find(step=>step.metric==='shoulder_flexion').target_deg;
      assert.ok(raw.shoulder_flexion-baselineMetrics.shoulder_flexion<(target-baselineMetrics.shoulder_flexion)*.25);
      assert.equal(movementUnderway(raw),true);
      assert.ok(forwardLeanDegrees(raw)>=24);
      collect(lm);
      assert.ok(ids().includes('trunk_lean'));
      assert.ok(compensationEligible.trunk_lean>=8);
    """)


@pytest.mark.parametrize("lean", [0, 5, 9, 11])
def test_small_posture_changes_remain_below_threshold(reach_js, lean):
    run_js(reach_js, f"""
      const base=reachSetup(); collect(pitchTrunk(base,{lean}));
      assert.ok(!ids().includes('trunk_lean'));
    """)


def test_a_shrug_or_isolated_size_depth_or_shape_artifact_is_not_forward_lean(reach_js):
    run_js(reach_js, """
      const base=reachSetup(), shrug=structuredClone(base);
      shrug[ACTIVE.shoulder].y-=.12;
      assert.ok(forwardLeanDegrees(rawMovementMetrics(shrug,null))<12);
      for(const changes of [
        {trunk_depth_tilt:40},
        {torso_length:baselineMetrics.torso_length*.7},
        {shoulder_width:baselineMetrics.shoulder_width*1.4},
        {ear_width:baselineMetrics.ear_width*1.4},
      ]) assert.ok(forwardLeanDegrees({...baselineMetrics,...changes})<12);
    """)


def test_return_phase_does_not_add_lean_findings(reach_js):
    run_js(reach_js, """
      const base=reachSetup(); currentSubStep=1; collect(pitchTrunk(base,30));
      assert.equal(compensationEligible.trunk_lean,undefined);
      assert.ok(!ids().includes('trunk_lean'));
    """)


def test_lean_before_instruction_ends_does_not_add_compensation_frames(reach_js):
    run_js(reach_js, """
      const base=reachSetup(), lm=pitchTrunk(base,30);
      stepVoiceFinishedAt=0; collect(lm);
      assert.equal(compensationEligible.trunk_lean,undefined);
      stepVoiceFinishedAt=1; activeVoiceSequence=1; collect(lm);
      assert.equal(compensationEligible.trunk_lean,undefined);
      activeVoiceSequence=0; collect(lm);
      assert.ok(ids().includes('trunk_lean'));
    """)


def test_brief_lean_outliers_do_not_meet_confirmation_count(reach_js):
    run_js(reach_js, """
      const base=reachSetup(); collect(pitchTrunk(base,30),2);
      collect(base,30);
      assert.ok(!ids().includes('trunk_lean'));
    """)


def test_missing_trunk_landmarks_cannot_create_a_lean_finding(reach_js):
    run_js(reach_js, """
      const base=reachSetup(), lm=pitchTrunk(base,30);
      lm[11].visibility=.1; collect(lm);
      assert.ok(!ids().includes('trunk_lean'));
      assert.ok(Number.isNaN(forwardLeanDegrees(lastRawMetrics)));
    """)


def test_live_threshold_and_confirmation_counts_remain_unchanged():
    rule = server.EXERCISE_MOVEMENT_STANDARDS['ex_reach']['compensations'][0]
    assert rule['threshold_deg'] == 12
    assert rule['min_frames'] == 8
    assert rule['min_ratio'] == .35
    assert server.EXERCISE_SCORING_METHOD['sustained_compensation_frames'] == 24
