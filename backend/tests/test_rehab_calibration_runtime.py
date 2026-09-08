"""Execute the production runner JS with synthetic camera frames, not source-only checks."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "rehyn_calibration_test")

from backend import server


HARNESS = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const elements = new Map(), messages = [], arcs = [];
const ctx = new Proxy({arc:(...args)=>arcs.push(args), measureText:()=>({width:50})}, {
  get:(target,key)=>key in target ? target[key] : ()=>{},
});
function element(id){
  if(!elements.has(id)){
    const classes = new Set(['hidden']);
    elements.set(id, {style:{}, listeners:{}, width:640, height:480,
      classList:{add:k=>classes.add(k), remove:k=>classes.delete(k), contains:k=>classes.has(k)},
      addEventListener(type,fn){this.listeners[type]=fn;}, removeEventListener(){},
      getContext:()=>ctx, removeAttribute(){}, querySelectorAll:()=>[],
    });
  }
  return elements.get(id);
}
let now = 10000;
const sandbox = {
  URLSearchParams, console, performance:{now:()=>now},
  navigator:{userAgent:'test',maxTouchPoints:0}, screen:{width:1440,height:900},
  document:{getElementById:element,body:{dataset:{}}},
  Audio:class {pause(){}}, requestAnimationFrame:()=>{}, setTimeout:()=>1, clearTimeout:()=>{},
  localStorage:{getItem:()=>JSON.stringify(input.oldCache),setItem:()=>assert.fail('Must not persist camera coordinates')},
  location:{origin:'http://localhost',search:`?test_mode=rep_feedback&voice_guidance=0&affected_side=${input.side}&rehab_session_id=existing-plan`},
  listeners:{}, addEventListener(type,fn){this.listeners[type]=fn;},
  ReactNativeWebView:{postMessage:value=>messages.push(JSON.parse(value))},
  PoseLandmarker:{POSE_CONNECTIONS:[]}, HandLandmarker:{HAND_CONNECTIONS:[]},
};
sandbox.window=sandbox;
const context=vm.createContext(sandbox);
const run=code=>vm.runInContext(code,context);
run(input.script);
run(`
  setupCamera=async()=>true;
  warmUpModels=async()=>{};
  unlockAudioPlayback=async()=>{};
  playVoice=async()=>"completed";
  drawingUtils={drawConnectors(){},drawLandmarks(){}};
  fbEl.classList.remove("show");
  fbEl.classList.add("hidden");
`);
async function main(){
  await elements.get('startBtn').listeners.click();
  assert.equal(run('calibrating'),true);
  assert.equal(run('calibrationReady'),false);
  assert.equal(run('exerciseLapTarget'),null);
  assert.equal(run('exerciseLapTargetRadius'),null);
  assert.equal(run('Object.keys(baselineMetrics).length'),0);
  assert.equal(elements.get('calibration').classList.contains('hidden'),false);
  // A partially visible person / hand near their face must not pass calibration.
  run('updateCalibration(null,null)');
  assert.equal(run('calibrationReady'),false);
  const lm=Array.from({length:33},()=>({x:.5,y:.3,z:0,visibility:1}));
  const coords={0:[.5,.18],7:[.46,.18],8:[.54,.18],11:[.4,.35],12:[.6,.35],
    13:[.4,.5],14:[.6,.5],15:[.43,.76],16:[.57,.76],23:[.43,.7],24:[.57,.7]};
  for(const [i,[x,y]] of Object.entries(coords)) Object.assign(lm[i],{x,y});
  sandbox.frames=lm;
  // The other hand resting correctly cannot substitute for the affected hand:
  // an affected wrist near the face must be rejected instead of calibrating an
  // abdomen/face target or silently choosing the wrong side.
  const affectedWrist=input.side==='left'?15:16;
  const validAffectedWrist={...lm[affectedWrist]};
  Object.assign(lm[affectedWrist],{x:.5,y:.24});
  for(let i=0;i<15;i++){now+=100; run('if(calibrating) updateCalibration(frames,null)');}
  assert.equal(run('calibrationReady'),false);
  assert.equal(run('exerciseLapTarget'),null);
  Object.assign(lm[affectedWrist],validAffectedWrist);
  for(let i=0;i<60;i++){
    now+=100;
    run('if(calibrating) updateCalibration(frames,null)');
    await Promise.resolve();
  }
  assert.equal(run('calibrationReady'),true);
  assert.equal(run('calibrating'),false);
  const target=JSON.parse(run('JSON.stringify(exerciseLapTarget)'));
  assert.equal(target.x,input.side==='left' ? .43 : .57);
  assert.equal(target.y,.76);
  run('currentSubStep=CFG.cycle.findIndex(step=>isExerciseLapTarget(step)); stepVoiceFinishedAt=1;');
  assert.equal(run('checkTarget(frames)'),true);
  for(const radius of ['null','0','-1','NaN','Infinity','"0.1"']){
    run(`exerciseLapTargetRadius=${radius}`);
    const r=run('effectiveExerciseTargetRadius(CFG.cycle[currentSubStep],frames)');
    assert.ok(r>=.10 && r<=.18, `invalid radius ${radius} must be repaired`);
    assert.equal(run('exerciseLapTargetRadius'),r);
  }
  run('exerciseLapTargetRadius=.12');
  assert.equal(run('effectiveExerciseTargetRadius(CFG.cycle[currentSubStep],frames)'),.12);
  arcs.length=0;
  run('drawOverlay(frames,null)');
  assert.ok(arcs.some(([x,y,r])=>Math.abs(x-target.x*640)<.001 && Math.abs(y-target.y*480)<.001 && r>40),
    'Return-to-lap must draw a visible circle at the calibrated wrist');
  // The arm can move, but start/end targets stay locked for this entry.
  lm[input.side==='left'?15:16].y=.4;
  now+=100;
  run('updateExerciseLapTargetCalibration(frames,performance.now())');
  assert.equal(run('exerciseLapTarget.y'),.76);
  assert.equal(run('checkTarget(frames)'),false);
  run('currentRep=2; resetExerciseCalibration()');
  assert.equal(run('currentRep'),2,'Calibration reset must not erase completed reps');
  assert.equal(run('exerciseLapTarget'),null);
  assert.equal(run('exerciseLapTargetCalibration.ready'),false);
  assert.equal(run('calibrationSamples.length'),0);
  // Re-entry can learn a different lap position without resurrecting old coordinates.
  lm[input.side==='left'?15:16].y=.82;
  for(let i=0;i<12;i++){now+=100; run('updateExerciseLapTargetCalibration(frames,performance.now())');}
  assert.equal(run('exerciseLapTarget.y'),.82);
  sandbox.stopped=0;
  run('cameraStream={getTracks:()=>[{stop:()=>window.stopped++}]}; confirmationAudioStream={getTracks:()=>[{stop:()=>window.stopped++}]};');
  elements.get('exitBtn').listeners.click();
  assert.equal(sandbox.stopped,2);
  assert.equal(run('running'),false);
  assert.equal(run('runnerExited'),true);
  assert.equal(messages.filter(m=>m.type==='exit').length,1);
  const repsBefore=run('currentRep');
  const stepBefore=run('currentSubStep');
  run('advanceSubStep()');
  assert.equal(run('currentSubStep'),stepBefore,'An old frame callback cannot advance after exit');
  await run('startRep()');
  assert.equal(run('currentRep'),repsBefore);
  assert.equal(messages.filter(m=>m.type==='exercise_calibrated').length,1);
  assert.equal(messages.some(m=>m.type==='exercise_calibration_reused'),false);
  console.log('Fresh calibration, visible locked lap target, and exit cleanup verified');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
"""


@pytest.mark.parametrize("exercise_id", ["ex_reach", "ex_trunk", "ex_grasp", "ex_h2m"])
@pytest.mark.parametrize("side", ["left", "right"])
def test_fresh_entry_and_lap_target_runtime(exercise_id, side):
    node = shutil.which("node")
    assert node, "Node.js is required to execute the runner regression tests"
    html = server._rehab_runner_html(exercise_id, prescribed_reps=3)
    script = html[html.index("const API_BASE ="):html.index("</script>", html.index("const API_BASE ="))]
    result = subprocess.run(
        [node, "-e", HARNESS],
        input=json.dumps({"script": script, "side": side, "oldCache": {
            "version": 3, "affected_side": side, "lap_target": {"x": .9, "y": .5},
            "lap_target_radius": None, "baseline_metrics": {"active_wrist_x": .9, "active_wrist_y": .5},
        }}), text=True, capture_output=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_navigation_unmounts_the_camera_but_keeps_account_progress():
    source = (Path(__file__).resolve().parents[2] / "frontend/app/exercise.tsx").read_text(encoding="utf-8")
    assert 'return isFocused ? <ExerciseSession key={`${exercise_id}:${entryVersion}`} /> : null;' in source
    assert 'if (event.persisted) setEntryVersion((value) => value + 1);' in source
    assert 'exerciseProgressKey(userId, planId, exercise_id)' in source
    assert 'removeItem' not in source
