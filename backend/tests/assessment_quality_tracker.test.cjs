const {test}=require('node:test');
const assert=require('node:assert/strict');
const {Tracker}=require('../assessment_quality.js');
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
