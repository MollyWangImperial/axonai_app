"""Regression trajectories for shoulder hiking mistaken for forward trunk lean."""

import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_trunk_compensation_test")

from backend import server
from backend.tests.test_grasp_wrist_alignment import run_js, runner_js


@pytest.fixture(scope="module")
def trunk_js(runner_js):
    cfg = server._configure_rehab_runner("ex_trunk", "medium", "standard")
    return runner_js + f"\nObject.assign(CFG,{json.dumps(cfg)}); Object.assign(STANDARD,CFG.movement_standard);" + r"""
HAS_SIDE_LEAN_RULE=STANDARD.compensations.some(rule=>rule.metric==='trunk_side_lean_delta');
function trunkSetup(){
  const {lm}=fixture();
  lm[7]={x:.46,y:.19,z:0,visibility:1};
  lm[8]={x:.54,y:.19,z:0,visibility:1};
  baselineMetrics=rawMovementMetrics(lm,null);
  baselineMetrics.active_wrist_x=.65;
  baselineMetrics.active_wrist_y=.9;
  baselineMetrics.shoulder_flexion=0;
  resetRepMetrics(); currentSubStep=0;
  return lm;
}
function trunkFrame(base,{lean=0,hike=0,widthArtifact=1,faceArtifact=1,sideLean=0}={}){
  const lm=structuredClone(base);
  const width=1/(1-Math.sin(lean*Math.PI/180)/2)*widthArtifact;
  const face=1/(1-Math.sin(lean*Math.PI/180)/1.5)*faceArtifact;
  for(const i of [11,12]) lm[i].x=.5+(lm[i].x-.5)*width;
  for(const i of [7,8]) lm[i].x=.5+(lm[i].x-.5)*face;
  lm[ACTIVE.shoulder].y-=Math.tan(hike*Math.PI/180)*.10;
  for(const i of [11,12]) lm[i].x+=Math.tan(sideLean*Math.PI/180)*.4;
  return lm;
}
function feed(base,options,count=30){ for(let i=0;i<count;i++) updateMetrics(trunkFrame(base,options),null); }
function ids(){return confirmedCompensations().map(rule=>rule.id);}
"""


def test_shrug_alone_is_not_forward_lean_and_bent_elbow_is_reported(trunk_js):
    run_js(trunk_js, """
      const base=trunkSetup(); feed(base,{hike:45});
      assert.deepEqual(ids(),['shoulder_hike']);
      assert.ok(Math.abs(forwardLeanDegrees(lastRawMetrics))<1e-5);
      romBest.elbow_extension=85;
      assert.match(pickFeedback(),/shoulder lifted/);
      assert.match(pickFeedback(),/elbow stayed bent/);
      assert.doesNotMatch(pickFeedback(),/trunk leaned|back came away/);
      assert.equal(computeRepScore(),70);
      assert.equal(repEarnsPoint(computeRepScore()),false);
    """)


def test_shoulder_line_artifact_without_neck_gap_change_is_not_a_shrug(trunk_js):
    run_js(trunk_js, """
      trunkSetup();
      const raw={...baselineMetrics};
      raw.shoulder_line_delta+=Math.tan(20*Math.PI/180)*.10;
      assert.equal(shoulderHikeDegrees(raw),0);
    """)


@pytest.mark.parametrize("lean", [0, 5, 9, 11])
def test_small_posture_changes_are_allowed(trunk_js, lean):
    run_js(trunk_js, f"""
      const base=trunkSetup(); feed(base,{{lean:{lean}}});
      assert.ok(!ids().includes('trunk_lean'));
      assert.doesNotMatch(pickFeedback(),/trunk leaned|back came away/);
    """)


def test_small_lean_with_shrug_only_flags_shrug(trunk_js):
    run_js(trunk_js, """
      const base=trunkSetup(); feed(base,{lean:9,hike:45});
      assert.deepEqual(ids(),['shoulder_hike']);
    """)


@pytest.mark.parametrize("hike", [0, 30])
def test_clear_forward_lean_is_still_detected_with_or_without_shrug(trunk_js, hike):
    run_js(trunk_js, f"""
      const base=trunkSetup(); feed(base,{{lean:20,hike:{hike}}});
      assert.ok(ids().includes('trunk_lean'));
      assert.match(pickFeedback(),/trunk leaned beyond the small posture allowance/);
      assert.doesNotMatch(pickFeedback(),/back came away/);
      assert.equal(computeRepScore(),70);
    """)


def test_isolated_shoulder_or_face_size_artifacts_do_not_count(trunk_js):
    run_js(trunk_js, """
      let base=trunkSetup(); feed(base,{widthArtifact:1.35});
      assert.ok(!ids().includes('trunk_lean'));
      base=trunkSetup(); feed(base,{faceArtifact:1.35});
      assert.ok(!ids().includes('trunk_lean'));
    """)


def test_real_lean_survives_one_conservative_visual_landmark(trunk_js):
    run_js(trunk_js, """
      trunkSetup();
      const shoulderLean=20, faceLean=5;
      const raw={...baselineMetrics};
      raw.shoulder_width*=1/(1-Math.sin(shoulderLean*Math.PI/180)/2);
      raw.ear_width*=1/(1-Math.sin(faceLean*Math.PI/180)/1.5);
      assert.ok(restrainedForwardLeanDegrees(raw)>=12);
      assert.ok(restrainedForwardLeanDegrees(raw)<20);
    """)


def test_torso_evidence_is_used_even_when_visible_ears_underestimate_lean(trunk_js):
    run_js(trunk_js, """
      trunkSetup();
      const raw={...baselineMetrics};
      raw.trunk_depth_tilt+=20;
      raw.torso_length*=Math.cos(6*Math.PI/180);
      assert.equal(raw.ear_width,baselineMetrics.ear_width);
      assert.ok(restrainedForwardLeanDegrees(raw)>=12);
    """)


def test_trunk_only_substitution_starts_scoring_without_arm_motion(trunk_js):
    run_js(trunk_js, """
      trunkSetup(); stepVoiceFinishedAt=1;
      const lean=20;
      const raw={...baselineMetrics};
      raw.shoulder_width*=1/(1-Math.sin(lean*Math.PI/180)/2);
      raw.ear_width*=1/(1-Math.sin(lean*Math.PI/180)/1.5);
      assert.equal(raw.active_wrist_x,baselineMetrics.active_wrist_x);
      assert.equal(raw.shoulder_flexion,baselineMetrics.shoulder_flexion);
      assert.equal(movementUnderway(raw),true);
    """)


def test_intermittent_tracking_spikes_do_not_accumulate_into_confirmation(trunk_js):
    run_js(trunk_js, """
      const base=trunkSetup();
      for(let i=0;i<15;i++){feed(base,{lean:25},3); feed(base,{lean:0},2);}
      assert.ok(compensationHits.trunk_lean>=24);
      assert.equal(compensationLongestStreak.trunk_lean,3);
      assert.ok(!ids().includes('trunk_lean'));
      feed(base,{lean:25},12);
      assert.ok(ids().includes('trunk_lean'));
    """)


def test_return_and_tracking_gaps_break_a_streak(trunk_js):
    run_js(trunk_js, """
      const base=trunkSetup(); feed(base,{lean:25},6);
      currentSubStep=1; feed(base,{lean:25},20);
      currentSubStep=0; feed(base,{lean:25},6);
      assert.equal(compensationLongestStreak.trunk_lean,6);
      assert.ok(!ids().includes('trunk_lean'));
      const hidden=structuredClone(base); for(const p of hidden) p.visibility=0;
      updateMetrics(hidden,null);
      feed(base,{lean:25},6);
      assert.equal(compensationLongestStreak.trunk_lean,6);
      assert.ok(!ids().includes('trunk_lean'));
    """)


def test_side_lean_remains_detectable_without_false_forward_or_chair_claim(trunk_js):
    run_js(trunk_js, """
      const base=trunkSetup(); feed(base,{sideLean:20});
      assert.ok(ids().includes('trunk_lean'));
      assert.doesNotMatch(pickFeedback(),/trunk leaned forward|back came away/);
    """)


def test_faceless_fallback_requires_corroborated_pose_evidence(trunk_js):
    run_js(trunk_js, """
      trunkSetup();
      const raw={...baselineMetrics,ear_width:NaN,shoulder_width:baselineMetrics.shoulder_width*1.25};
      assert.equal(restrainedForwardLeanDegrees(raw),0);
      raw.trunk_depth_tilt+=25; raw.torso_length*=.95;
      assert.ok(restrainedForwardLeanDegrees(raw)>=20);
      delete raw.trunk_depth_tilt;
      assert.ok(Number.isNaN(restrainedForwardLeanDegrees(raw)));
    """)


def test_tolerance_and_confirmation_are_configured_only_for_restrained_reach():
    trunk = server.EXERCISE_MOVEMENT_STANDARDS['ex_trunk']['compensations'][0]
    assert trunk['threshold_deg'] == 12
    assert trunk['min_frames'] == 12
    assert trunk['min_ratio'] == .45
    assert trunk['min_consecutive_frames'] == 8
    for exercise in ['ex_reach', 'ex_grasp', 'ex_h2m']:
        assert all('min_consecutive_frames' not in rule for rule in server.EXERCISE_MOVEMENT_STANDARDS[exercise]['compensations'])
