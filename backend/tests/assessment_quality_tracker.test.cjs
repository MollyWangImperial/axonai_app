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

test('pose world-space angle is rotation invariant and visibility-gated',()=>{
  const t=new Tracker(config,'right');
  const p=Array.from({length:33},()=>({x:.5,y:.5,z:0,visibility:.99}));
  const w=structuredClone(p);
  w[12]={x:0,y:0,z:0};w[14]={x:.2,y:0,z:0};w[16]={x:.4,y:0,z:0};w[24]={x:0,y:.4,z:0};
  assert.equal(t.raw(p,w).elbow_extension,180);
  const rotated=w.map(v=>({x:v.z,y:v.y,z:-v.x}));
  assert.equal(t.raw(p,rotated).elbow_extension,180);
  p[16].visibility=.2;
  assert.equal(t.raw(p,w).elbow_extension,undefined);
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
