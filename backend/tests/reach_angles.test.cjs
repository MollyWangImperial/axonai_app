const { test } = require('node:test');
const assert = require('node:assert/strict');
const { Tracker } = require('../assessment_quality.js');
const { assessmentReadout } = require('../reach_angles.js');
test('Testing readout preserves scoring values and distinguishes 3D elevation from the 2D arc', () => {
  for (const side of ['right', 'left']) {
    const tracker = new Tracker({version:'test',compensations:{}}, side);
    const {s,e,w,h} = tracker.a;
    const p=Array.from({length:33},()=>({x:.5,y:.5,z:0,visibility:1}));
    p[s]={x:.4,y:.3,z:0,visibility:1};p[e]={x:.6,y:.3,z:0,visibility:1};
    p[w]={x:.8,y:.3,z:0,visibility:1};p[h]={x:.4,y:.7,z:0,visibility:1};
    const world=structuredClone(p);
    world[s]={x:0,y:0,z:0};world[h]={x:0,y:.5,z:0};
    world[e]={x:0,y:.2,z:.2};world[w]={x:0,y:.4,z:.4};
    const before=tracker.snapshot();
    const raw=tracker.raw(p,world,16/9), readout=assessmentReadout(tracker,p,world,16/9);
    assert.equal(readout.armScore,raw.arm_elevation);
    assert.ok(Math.abs(readout.armScore-45)<1e-8);
    assert.equal(readout.armElevationArc.degrees,90);
    assert.equal(readout.elbowScore,raw.elbow_extension);
    assert.equal(readout.elbowArc.degrees,180);
    assert.deepEqual(tracker.snapshot(),before);
    assert.equal(assessmentReadout(tracker,p,null,16/9).armScore,null);
    p[e].visibility=.2;
    assert.equal(assessmentReadout(tracker,p,world,16/9).elbowArc,null);
    assert.equal(assessmentReadout(tracker,p,world,16/9).elbowScore,null);
    assert.equal(assessmentReadout(tracker,null,null,16/9).armElevationArc,null);
  }
});
