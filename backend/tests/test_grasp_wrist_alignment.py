"""Execute the runner's JS against wrist trajectories, not source-string copies."""

import json
import os
import re
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "axonai_grasp_wrist_test")

from backend import server


@pytest.fixture(scope="module")
def runner_js():
    names = """
        rad2deg clamp pointVisible angle midpoint median sideIndexes
        poseWristBendDegrees projectedWristBendDegrees rawMovementMetrics
        forwardLeanDegrees restrainedForwardLeanDegrees headDropDegrees shoulderHikeDegrees metricValue
        poseAlignmentDeviation poseTrackingQuality handTrackingQuality trackingQuality
        activeMovementPhase movementUnderway ruleAppliesNow expectedShoulderRise
        compensationThreshold resetRepMetrics updateMetrics reachKeyMetric elbowAtPeakReach
        confirmedCompensations repRomDetails measuredRomDetails incompleteRomSteps
        unmeasuredRomSteps wristAlignmentUnmeasured computeRepScore repEarnsPoint
        pointBlockedByVisibility compensationProblemText joinProblems romProblemText pickFeedback
    """.split()
    functions = []
    for name in names:
        match = re.search(
            rf"^function {name}\([^\n]*\)\{{.*?^\}}",
            server.REHAB_RUNNER_HTML_TEMPLATE,
            re.MULTILINE | re.DOTALL,
        )
        assert match is not None, name
        functions.append(match.group(0))
    cfg = server._configure_rehab_runner("ex_grasp", "medium", "standard")
    return "\n".join(functions) + "\n" + f"const CFG={json.dumps(cfg)};" + r"""
const assert=require('node:assert/strict');
const STANDARD=CFG.movement_standard, SCORING_METHOD=CFG.scoring_method;
let ACTIVE=sideIndexes('right'), OTHER=sideIndexes('left');
let video={videoWidth:1280,videoHeight:720};
let HAS_SIDE_LEAN_RULE=true;
const CALIBRATION_MIN_TRACKING_QUALITY=.72;
const SCORING_MIN_FRAMES=8, POINT_THRESHOLD=90, SUSTAINED_COMPENSATION_FRAMES=24;
const ROM_FULL_CREDIT_RATIO=.95, ROM_COMPLETE_RATIO=.90;
const FORM_CRITICAL_METRICS=new Set(['elbow_extension','elbow_flexion','finger_extension']);
const NEAR_PEAK_REACH_RATIO=.9, MAX_REACH_FRAMES=8;
const SHOULDER_HIKE_ALLOWANCE_PER_FLEXION_DEG=.1, SHOULDER_HIKE_FREE_FLEXION_DEG=10;
const EVIDENCE_COMPENSATION_IDS=new Set(['wrist_flexion']), TEMPORARY_COMPENSATION_EVIDENCE=false;
const fbEl={classList:{contains:()=>false}};
function clearTemporaryCompensationEvidence(){}
let baselineMetrics={}, currentSubStep=3, romBest={}, compensationHits={}, compensationEligible={};
let compensationConsecutive={}, compensationLongestStreak={};
let liveCompensationStreaks={}, liveCompensationIds=new Set(), trackingFrames=0, lowQualityFrames=0;
let activeFrames=0, peakReachExtent=-1, peakReachElbow=NaN, reachFrames=[], peakCompensationDegrees={};
let lastRawMetrics=null, latestExercisePoseLandmarks=null;
function fixture(degrees=0,{side='right',aspect=16/9,rotation=0,mirror=false,closed=true}={}){
  ACTIVE=sideIndexes(side); OTHER=sideIndexes(side==='left'?'right':'left');
  video={videoWidth:720*aspect,videoHeight:720};
  const p=(x,y,z=0)=>({x,y,z,visibility:1});
  const lm=Array.from({length:33},()=>p(.5,.5));
  lm[11]=p(.4,.3); lm[12]=p(.6,.3); lm[23]=p(.42,.7); lm[24]=p(.58,.7);
  lm[OTHER.wrist]=p(.2,.6);
  const r=rotation*Math.PI/180, b=(rotation+degrees)*Math.PI/180;
  lm[ACTIVE.elbow]=p(.65-Math.sin(r)*.24/aspect,.58-Math.cos(r)*.24);
  lm[ACTIVE.wrist]=p(.65,.58);
  const hand=Array.from({length:21},()=>p(.65,.58));
  hand[9]=p(.65+Math.sin(b)*.08/aspect,.58+Math.cos(b)*.08);
  hand[5]=p(hand[9].x+.022/aspect,hand[9].y);
  hand[17]=p(hand[9].x-.022/aspect,hand[9].y);
  hand[13]=p(hand[9].x-.008/aspect,hand[9].y);
  for(const [base,joint,tip] of [[5,6,8],[9,10,12],[13,14,16],[17,18,20]]){
    hand[joint]=p(hand[base].x+Math.sin(b)*.03/aspect,hand[base].y+Math.cos(b)*.03);
    hand[tip]=closed ? p(.65,.58) : p(hand[base].x+Math.sin(b)*.07/aspect,hand[base].y+Math.cos(b)*.07);
  }
  // The coarse pose endpoints collapse on a closed hand: the original miss.
  lm[side==='left'?19:20]=p(.65,.58);
  lm[side==='left'?17:18]=p(.65,.58);
  if(mirror){ for(const point of [...lm,...hand]) point.x=1-point.x; }
  return {lm,hand};
}
function scoreFrames(degrees,count,{step=3,fresh=true,missing=false}={}){
  currentSubStep=step;
  for(let i=0;i<count;i++){
    const {lm,hand}=fixture(degrees);
    updateMetrics(lm,missing?null:hand,fresh);
  }
}
function isolateWrist(){
  STANDARD.compensations=STANDARD.compensations.filter(rule=>rule.id==='wrist_flexion');
  baselineMetrics={shoulder_flexion:0,wrist_bend:50};
  resetRepMetrics();
}
function completeRom(){
  for(const step of STANDARD.rom_steps) romBest[step.id]=step.target_deg;
}
"""


def run_js(runner_js, body):
    node = shutil.which("node")
    assert node, "Node is required to execute the exercise runner regression tests"
    result = subprocess.run(
        [node, "-"], input=runner_js + "\n" + body,
        text=True, encoding="utf-8", capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("aspect", [9 / 16, 16 / 9])
@pytest.mark.parametrize("mirror", [False, True])
def test_closed_hand_inward_bend_survives_mirroring_and_camera_aspect(runner_js, side, aspect, mirror):
    options = json.dumps(dict(side=side, aspect=aspect, mirror=mirror))
    run_js(runner_js, f"""
      const {{lm,hand}}=fixture(35,{options});
      assert.ok(Number.isNaN(poseWristBendDegrees(lm)));
      baselineMetrics={{wrist_bend:60}};
      const raw=rawMovementMetrics(lm,hand);
      assert.ok(Math.abs(metricValue('wrist_flexion_delta',raw)-35)<1e-6);
    """)


def test_arm_transport_and_finger_closing_are_not_wrist_bending(runner_js):
    run_js(runner_js, """
      for(const rotation of [-75,-40,0,40,75]){
        for(const closed of [false,true]){
          const {lm,hand}=fixture(0,{rotation,closed});
          assert.ok(projectedWristBendDegrees(lm,hand)<1e-5);
        }
      }
      for(const bend of [-45,45]){
        const {lm,hand}=fixture(bend);
        assert.ok(Math.abs(projectedWristBendDegrees(lm,hand)-45)<1e-6);
      }
    """)


def test_unreliable_or_wrong_hand_projection_abstains(runner_js):
    run_js(runner_js, """
      for(const change of [
        (lm,h)=>{lm[ACTIVE.elbow].visibility=.1;},
        (lm,h)=>{h[9]={...h[0]};},
        (lm,h)=>{for(const p of h) p.x-=.35;},
        (lm,h)=>{lm[OTHER.wrist]={...h[0]}; lm[ACTIVE.wrist].x+=.01;},
        (lm,h)=>{lm[ACTIVE.elbow].z=1;},
        (lm,h)=>{h[9].z=1;},
        (lm,h)=>{video.videoWidth=0;},
      ]){
        const {lm,hand}=fixture(45); change(lm,hand);
        assert.ok(Number.isNaN(projectedWristBendDegrees(lm,hand)));
      }
      assert.ok(Number.isNaN(projectedWristBendDegrees(null,null)));
    """)


def test_sustained_bend_reaches_feedback_and_denies_quality_point(runner_js):
    run_js(runner_js, """
      isolateWrist(); scoreFrames(35,12); completeRom();
      assert.deepEqual(confirmedCompensations().map(r=>r.id),['wrist_flexion']);
      assert.ok(liveCompensationIds.has('wrist_flexion'));
      assert.match(pickFeedback(),/wrist moved out of line/);
      assert.equal(computeRepScore(),70);
      assert.equal(repEarnsPoint(computeRepScore()),false);
    """)


@pytest.mark.parametrize("step", [0, 1, 5])
def test_wrist_scoring_excludes_reach_open_and_return_phases(runner_js, step):
    run_js(runner_js, f"""
      isolateWrist(); scoreFrames(45,30,{{step:{step}}});
      assert.equal(compensationEligible.wrist_flexion,undefined);
      assert.equal(confirmedCompensations().length,0);
    """)


def test_brief_noise_or_cached_hand_cannot_confirm_compensation(runner_js):
    run_js(runner_js, """
      isolateWrist(); scoreFrames(0,30); scoreFrames(45,2); scoreFrames(0,30);
      assert.equal(confirmedCompensations().length,0);
      assert.equal(liveCompensationIds.size,0);
      isolateWrist(); scoreFrames(45,1); scoreFrames(45,30,{fresh:false});
      assert.equal(compensationEligible.wrist_flexion,1);
      assert.equal(confirmedCompensations().length,0);
    """)


def test_unseen_wrist_reports_measurement_gap_and_valid_straight_wrist_earns_point(runner_js):
    run_js(runner_js, """
      isolateWrist(); scoreFrames(0,30,{missing:true}); completeRom();
      assert.equal(confirmedCompensations().length,0);
      assert.equal(wristAlignmentUnmeasured(),true);
      assert.match(pickFeedback(),/could not see your wrist clearly enough/);
      assert.equal(pointBlockedByVisibility(),true);
      assert.equal(repEarnsPoint(computeRepScore()),false);
      assert.ok(computeRepScore()<90);
      isolateWrist(); scoreFrames(0,30); completeRom();
      assert.equal(wristAlignmentUnmeasured(),false);
      assert.equal(computeRepScore(),100);
      assert.equal(repEarnsPoint(computeRepScore()),true);
    """)


def test_pose_fallback_and_other_exercises_keep_existing_wrist_measurement(runner_js):
    run_js(runner_js, """
      baselineMetrics={wrist_bend:10};
      assert.equal(metricValue('wrist_flexion_delta',{wrist_bend:45}),35);
      CFG.exercise_id='ex_reach';
      assert.equal(metricValue('wrist_flexion_delta',{wrist_bend:45,projected_wrist_bend:80}),35);
      assert.equal(wristAlignmentUnmeasured(),false);
      STANDARD.tracking_mode='hand'; baselineMetrics={hand_axis:170};
      assert.equal(metricValue('wrist_flexion_delta',{hand_axis:-170}),20);
    """)


def test_served_grasp_runner_has_valid_module_and_updated_detector(tmp_path):
    response = TestClient(server.app).get('/api/rehab/runner?exercise_id=ex_grasp')
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert 'Cylindrical Grasp & Transport' in response.text
    assert 'projectedWristBendDegrees' in response.text
    assert 'updateMetrics(lm,handLm,!!detectedHandLm)' in response.text
    script = re.search(r'<script type="module">(.*?)</script>', response.text, re.DOTALL)
    assert script
    target = tmp_path / 'grasp-runner.mjs'
    target.write_text(script.group(1), encoding='utf-8')
    result = subprocess.run([shutil.which('node'), '--check', str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
