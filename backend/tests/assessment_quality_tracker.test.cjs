const {test}=require('node:test');
const assert=require('node:assert/strict');
const {Tracker}=require('../assessment_quality.js');
const trunkLeanMetrics=require('../../testing/trunk-lean-comparison/trunk_lean_metrics.js');
const config={version:'rehyn-task-quality-1',compensations:{trunk_lean:{threshold:12},wrist_bend:{threshold:25}}};
const rule={criteria:[{metric:'elbow_extension',target:150}],compensations:['wrist_bend']};

test('one noisy frame, missing data and long gaps never confirm compensation',()=>{
  const t=new Tracker(config,'right');t.reset(rule);
  let bend=0;
  t.raw=()=>({elbow_extension:150,wrist_bend:bend});
  for(let now=0;now<=1000;now+=50) t.sample({now,inTarget:true});
  bend=55;t.sample({now:1050,inTarget:true});
  assert.deepEqual(t.active(),[]);
  bend=NaN;t.sample({now:1100,inTarget:true});
  bend=55;t.sample({now:5000,inTarget:true});
  assert.deepEqual(t.active(),[]);
  for(let now=5050;now<=5650;now+=50)t.sample({now,inTarget:true});
  assert.deepEqual(t.active(),['wrist_bend']);
  assert.equal(t.snapshot().measurements.elbow_extension.value,150);
  bend=NaN;t.sample({now:5700});assert.deepEqual(t.active(),[]);
});

test('full elbow at rest cannot hide bent elbow at target; steps reset evidence',()=>{
  const t=new Tracker(config,'left');t.reset(rule);
  let extension=180;t.raw=()=>({elbow_extension:extension,wrist_bend:0});
  for(let now=0;now<1000;now+=50)t.sample({now,inTarget:false});
  extension=90;
  for(let now=1000;now<2000;now+=50)t.sample({now,inTarget:true});
  assert.equal(t.snapshot().measurements.elbow_extension.value,90);
  t.reset(rule);
  assert.deepEqual(t.snapshot().measurements,{});
});

test('elbow extension uses the aspect-corrected 2D image angle and is visibility-gated',()=>{
  const t=new Tracker(config,'right');
  const p=Array.from({length:33},()=>({x:.5,y:.5,z:0,visibility:.99}));
  const w=structuredClone(p);
  p[12]={x:.3,y:.5,z:0,visibility:.99};p[14]={x:.5,y:.5,z:0,visibility:.99};p[16]={x:.7,y:.5,z:0,visibility:.99};
  w[12]={x:0,y:0,z:0};w[14]={x:.2,y:0,z:0};w[16]={x:.2,y:.2,z:0};w[24]={x:0,y:.4,z:0};
  assert.equal(t.raw(p,w,16/9).elbow_extension,180);
  assert.equal(t.raw(p,null,16/9).elbow_extension,180);
  p[12]={x:.4,y:.4,z:0,visibility:.99};p[14]={x:.5,y:.5,z:0,visibility:.99};p[16]={x:.6,y:.5,z:0,visibility:.99};
  assert.ok(Math.abs(t.raw(p,w,2).elbow_extension-153.4349488)<.0001);
  p[16].visibility=.2;
  assert.equal(t.raw(p,w,2).elbow_extension,undefined);
});

test('baseline is a stable median, and a bent trunk is detected after calibration',()=>{
  const t=new Tracker(config,'right');
  let torso=[0,-.5,0];t.raw=()=>({torso,width:.4,screenWidth:.25,shoulderLine:0,hipLine:0,elbow_extension:150});
  for(let i=0;i<20;i++)t.calibrate([],[]);
  assert.ok(t.baseline);
  t.reset({criteria:rule.criteria,compensations:['trunk_lean']});
  torso=[.25,-.433,0];
  for(let now=0;now<1000;now+=50)t.sample({now,inTarget:true});
  assert.deepEqual(t.active(),['trunk_lean']);
});

test('normal shoulder rise and opposite shoulder drop do not become shoulder hiking',()=>{
  const t=new Tracker({...config,compensations:{shoulder_hike:{threshold:12}}},'right');
  let r={torso:[0,-.5,0],width:.4,screenWidth:.25,shoulderLine:0,hipLine:0,neckGap:.2,arm_elevation:0};
  t.raw=()=>r;
  for(let i=0;i<20;i++)t.calibrate([],[]);
  t.reset({criteria:[],compensations:['shoulder_hike']});
  r={...r,shoulderLine:.08,neckGap:.17,arm_elevation:90};
  for(let now=0;now<1000;now+=50)t.sample({now});
  assert.deepEqual(t.active(),[]);
  r={...r,shoulderLine:.35,neckGap:.2};
  for(let now=1000;now<2000;now+=50)t.sample({now});
  assert.deepEqual(t.active(),[]);
  r={...r,neckGap:.1,arm_elevation:40};
  for(let now=2000;now<3000;now+=50)t.sample({now});
  assert.deepEqual(t.active(),['shoulder_hike']);
});


test('diagnostic observations keep endpoint, peak and target fraction without changing scoring',()=>{
  const t=new Tracker(config,'right'); t.reset(rule);
  let elevation=20;
  t.raw=()=>({arm_elevation:elevation,elbow_extension:150,torso:[0,-.5,0]});
  for(let now=0;now<500;now+=50)t.sample({now,inTarget:false});
  elevation=60;
  for(let now=500;now<1000;now+=50)t.sample({now,inTarget:true});
  const snapshot=t.snapshot();
  assert.equal(snapshot.observations.arm_elevation.endpoint,60);
  assert.equal(snapshot.observations.arm_elevation.max,60);
  assert.equal(snapshot.observations.arm_elevation.min,20);
  assert.equal(snapshot.observations.target_control.target_fraction,.5);
  assert.equal(snapshot.measurements.arm_elevation,undefined);
  t.raw=()=>({});t.sample({now:1100});
  assert.equal(t.snapshot().observations.arm_elevation.samples,20);
  t.reset(rule);assert.deepEqual(t.snapshot().observations,{});
});

test('reach ratio describes extension without assuming real-world distance',()=>{
  const t=new Tracker(config,'right');
  const p=Array.from({length:33},()=>({x:.5,y:.5,z:0,visibility:.99}));
  const w=structuredClone(p);
  w[12]={x:0,y:0,z:0};w[14]={x:.2,y:0,z:0};w[16]={x:.4,y:0,z:0};w[24]={x:0,y:.4,z:0};
  assert.equal(t.raw(p,w).reach_ratio,1);
  w[16]={x:.2,y:.2,z:0};assert.ok(t.raw(p,w).reach_ratio<.71);
  p[16].visibility=.1;assert.equal(t.raw(p,w).reach_ratio,undefined);
});

test('scoring measurements include a bounded time series and target control uses the observed proportion',()=>{
  const t=new Tracker(config,'right');
  t.reset({criteria:[{metric:'target_control',target:.8}],compensations:[]});
  t.raw=()=>({torso:[0,-.5,0]});
  for(let now=0;now<1000;now+=50)t.sample({now,inTarget:now>=250});
  const measurement=t.snapshot().measurements.target_control;
  assert.equal(measurement.value,.75);
  assert.equal(measurement.statistic_source,'sample_proportion');
  assert.equal(measurement.series[0].elapsed_ms,0);
  assert.equal(measurement.series.at(-1).elapsed_ms,900);
  assert.equal(measurement.series.some(point=>point.in_target),true);
  assert.ok(measurement.series.length<=240);
});

test('Testing reach uses an early maximum for both angles even after returning or buffer eviction',()=>{
  const t=new Tracker(config,'right',{peakReachAngles:true});
  const reachRule={id:'T1-S2',criteria:[{metric:'arm_elevation'},{metric:'elbow_extension'}],compensations:[]};
  t.reset(reachRule);
  let arm=20,elbow=90;t.raw=()=>({arm_elevation:arm,elbow_extension:elbow});
  for(let now=0;now<500;now+=50){if(now===150){arm=65;elbow=162;}else{arm=20;elbow=90;}t.sample({now,inTarget:false});}
  for(let now=500;now<100000;now+=50)t.sample({now,inTarget:true});
  const m=t.snapshot().measurements;
  assert.equal(m.arm_elevation.value,65);assert.equal(m.elbow_extension.value,162);
  for(const metric of Object.values(m)){
    assert.equal(metric.statistic_source,'movement_maximum');assert.equal(metric.peak_elapsed_ms,150);
    assert.ok(metric.series.some(p=>p.elapsed_ms===150&&p.value===metric.value));assert.ok(metric.series.length<=240);
  }
  t.reset(reachRule);assert.deepEqual(t.snapshot().measurements,{});
  arm=NaN;elbow=NaN;t.sample({now:100100});assert.deepEqual(t.snapshot().measurements,{});
});

test('maximum option does not change non-reach tasks or target-control scoring',()=>{
  const t=new Tracker(config,'right',{peakReachAngles:true});
  t.reset({id:'T2-S1',criteria:[{metric:'elbow_extension'}],compensations:[]});
  let elbow=170;t.raw=()=>({elbow_extension:elbow});t.sample({now:0});elbow=80;
  for(let now=50;now<1000;now+=50)t.sample({now,inTarget:true});
  assert.equal(t.snapshot().measurements.elbow_extension.value,80);
});

function torsoPose({shoulderScale=1,hipScale=1,faceScale=1,visible=true}={}) {
  const p=Array.from({length:33},()=>({x:.5,y:.5,z:0,visibility:.99}));
  p[0]={x:.5,y:.19,z:0,visibility:.99};
  p[7]={x:.5-.04*faceScale,y:.21,z:0,visibility:.99};
  p[8]={x:.5+.04*faceScale,y:.21,z:0,visibility:.99};
  p[11]={x:.5-.10*shoulderScale,y:.31,z:0,visibility:visible?.99:.1};
  p[12]={x:.5+.10*shoulderScale,y:.31,z:0,visibility:.99};
  p[23]={x:.5-.09*hipScale,y:.70,z:0,visibility:.99};
  p[24]={x:.5+.09*hipScale,y:.70,z:0,visibility:.99};
  return p;
}

test('Testing T1 uses the shared calibrated shoulder-or-face lean detector for sustained face-only evidence',()=>{
  const t=new Tracker(config,'right',{testingReachTrunkLean:true,trunkLeanMetrics});
  t.raw=()=>({torso:[0,-.5,0],width:.4,screenWidth:.2,shoulderLine:0,hipLine:0});
  for(let i=0;i<44;i++)t.calibrate(torsoPose(),null,1.5);
  assert.equal(t.trunkLeanBaseline,null);
  t.calibrate(torsoPose(),null,1.5);
  assert.ok(t.trunkLeanBaseline);
  t.reset({id:'T1-S2',criteria:[],compensations:['trunk_lean']});
  const faceOnly=torsoPose({faceScale:1.1});
  for(let now=0;now<=700;now+=50)t.sample({pose:faceOnly,now,aspectRatio:1.5});
  const lean=t.snapshot().compensations.trunk_lean;
  assert.equal(lean.method,'pelvis_normalized_shoulder_or_face_v1');
  assert.ok(lean.face_peak>=7 && lean.face_peak<12);
  assert.ok(lean.shoulder_peak<1);
  assert.ok(lean.max_streak_ms>=500);
  assert.equal(lean.cue_evidence.shoulder.duration_ms,0);
  assert.ok(lean.cue_evidence.face.duration_ms>=500);
  assert.ok(lean.cue_evidence.face.peak>=7);
  assert.deepEqual(t.active(),['trunk_lean']);
});

test('briefly missing hips do not erase clear upright calibration frames',()=>{
  const t=new Tracker(config,'right',{testingReachTrunkLean:true,trunkLeanMetrics});
  t.raw=()=>({torso:[0,-.5,0],width:.4,screenWidth:.2,shoulderLine:0,hipLine:0});
  for(let i=0;i<44;i++){
    t.calibrate(torsoPose(),null,1.5);
    if(i%5===0){const occluded=torsoPose();occluded[23].visibility=.1;t.calibrate(occluded,null,1.5);}
  }
  assert.equal(t.trunkLeanBaseline,null);
  assert.equal(t.trunkLeanBaselineFrames.length,44);
  t.calibrate(torsoPose(),null,1.5);
  assert.ok(t.trunkLeanBaseline);
});

test('Testing T1 does not combine short shoulder and face cue bursts into trunk lean',()=>{
  const t=new Tracker(config,'right',{testingReachTrunkLean:true,trunkLeanMetrics});
  t.raw=()=>({torso:[0,-.5,0],width:.4,screenWidth:.2,shoulderLine:0,hipLine:0});
  for(let i=0;i<45;i++)t.calibrate(torsoPose(),null,1.5);
  t.reset({id:'T1-S2',criteria:[],compensations:['trunk_lean']});
  for(let now=0;now<=950;now+=50) {
    const pose=Math.floor(now/250)%2===0 ? torsoPose({shoulderScale:1.3}) : torsoPose({faceScale:1.12});
    t.sample({pose,now,aspectRatio:1.5});
  }
  const lean=t.snapshot().compensations.trunk_lean;
  assert.ok(lean.shoulder_peak>12 && lean.face_peak>7);
  assert.equal(lean.cue_evidence.shoulder.duration_ms,0);
  assert.equal(lean.cue_evidence.face.duration_ms,0);
  assert.equal(lean.max_streak_ms,0);
  assert.deepEqual(t.active(),[]);
});

test('Testing T1 ignores uniform camera approach, missing torso landmarks and old 3D-only lean',()=>{
  const t=new Tracker(config,'right',{testingReachTrunkLean:true,trunkLeanMetrics});
  let torso=[0,-.5,0];
  t.raw=()=>({torso,width:.4,screenWidth:.2,shoulderLine:0,hipLine:0});
  for(let i=0;i<45;i++)t.calibrate(torsoPose(),null,1.5);
  torso=[.3,-.4,0];
  t.reset({id:'T1-S2',criteria:[],compensations:['trunk_lean']});
  const zoom=torsoPose({shoulderScale:1.2,hipScale:1.2,faceScale:1.2});
  for(let now=0;now<=700;now+=50)t.sample({pose:zoom,now,aspectRatio:1.5});
  assert.deepEqual(t.active(),[]);
  assert.ok(t.snapshot().compensations.trunk_lean.max_value<1);
  const missing=torsoPose({visible:false});
  t.sample({pose:missing,now:750,aspectRatio:1.5});
  assert.deepEqual(t.active(),[]);
  assert.equal(t.snapshot().compensations.trunk_lean.eligible_ms,700);
  t.reset({id:'T2-S2',criteria:[],compensations:['trunk_lean']});
  assert.equal(t.trunkLeanReadout(torsoPose(),1.5).supported,true);
  for(let now=0;now<=700;now+=50)t.sample({pose:torsoPose(),now,aspectRatio:1.5});
  assert.equal(t.snapshot().compensations.trunk_lean.method,undefined);
  assert.deepEqual(t.active(),['trunk_lean']);
});
