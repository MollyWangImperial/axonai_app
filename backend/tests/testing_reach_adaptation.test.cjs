const {test}=require('node:test');
const assert=require('node:assert/strict');
const {LoweringPolicy,ReachStep,CONFIG,LEVELS,observation}=require('../testing_reach.js');
test('selected side and low visibility never substitute an unaffected hand',()=>{
  const p=Array.from({length:33},()=>({x:.5,y:.5,visibility:1}));p[11].x=.6;p[12].x=.4;p[16].visibility=.1;
  assert.equal(observation(p,'right'),null);assert.ok(observation(p,'left'));
});
function step(policy=new LoweringPolicy(()=>0),id='T1-S2',level=0){return new ReachStep({policy,id,level,base:{x:.7,y:.3},lap:{x:.4,y:.7}});}
function tick(s,ms,{valid=true,paused=false}={}){let event;for(let t=0;t<=ms;t+=50){event=s.tick({now:(s.last??0)+50,valid,paused});if(event)return event;}return event;}
test('full starting height, encouragement and retry precede lowering; speech/tracking loss never advance targets',()=>{
  const s=step();assert.equal(s.difficulty,1);assert.equal(s.target.y,.3);
  tick(s,20000,{valid:false});assert.equal(s.phase,'attempt');
  assert.equal(tick(s,8500),'encourage');const original={...s.target};
  tick(s,10000);assert.deepEqual(s.target,original);assert.equal(s.phase,'encourage');
  s.cueDone();tick(s,15000,{paused:true});assert.equal(s.phase,'retry');
  assert.equal(tick(s,6500),'announce_lower');assert.deepEqual(s.target,original);assert.equal(s.difficulty,1);
  s.commitLowering();assert.equal(s.difficulty,.85);assert.equal(s.phase,'lowering');
  assert.equal(tick(s,1000),'lowered');assert.equal(s.target.x,original.x);assert.ok(s.target.y>original.y);
  assert.equal(s.events.length,1);assert.equal(s.events[0].after_encouraged_retry,true);
});
test('bounded lowering ends in support request, S3 inherits height, S4 and lap anchor never drift',()=>{
  const s=step();for(let i=0;i<4;i++){tick(s,8500);s.cueDone();tick(s,6500);s.commitLowering();tick(s,1000);}
  assert.equal(s.difficulty,.4);tick(s,8500);s.cueDone();assert.equal(tick(s,6500),'needs_support');
  const hold=step(s.policy,'T1-S3',s.level);assert.deepEqual(hold.target,s.target);
  const lap=step(s.policy,'T1-S4');const target={...lap.target};tick(lap,8500);lap.cueDone();assert.equal(tick(lap,6500),'needs_support');assert.deepEqual(lap.target,target);
});
test('reward ranks full independent completion above easier and assisted completion and above failure; cancellation never learns',()=>{
  const results=[];
  for(const [success,difficulty,assisted] of [[true,1,false],[true,.7,false],[true,.7,true],[false,.7,false]]){
    const p=new LoweringPolicy(()=>0),d=p.choose(0,false,assisted);results.push(p.learn([d],{success,difficulty,assisted}).terminal_reward);
  }
  assert.deepEqual(results,[2,1.4,.7,-1]);
  const p=new LoweringPolicy(()=>0),d=p.choose(0,false,false);assert.equal(p.learn([d],{success:false,difficulty:1,assisted:false,cancelled:true}),null);assert.equal(p.updates.length,0);
});
test('REINFORCE uses sampled probabilities, discounted return and an action-independent baseline',()=>{
  const p=new LoweringPolicy(()=>0);const d=p.choose(0,false,false),u=p.learn([d],{success:true,difficulty:.85,assisted:false});
  const g=u.updates[0];assert.deepEqual(g.probabilities,[.5,.5]);assert.equal(g.baseline,0);
  assert.ok(Math.abs(g.return-(-CONFIG.lowerCost+CONFIG.discount*1.7))<1e-10);
  assert.ok(Math.abs(g.gradient[0]-g.return*.5)<1e-10);assert.ok(p.choose(0,false,false).probabilities[0]>.5);
});
test('policy learns the useful reduction for reachable versus unreachable retry outcomes',()=>{
  for(const best of [1,2]){
    let seed=42;const p=new LoweringPolicy(()=>{seed=(1664525*seed+1013904223)>>>0;return seed/2**32;});
    for(let i=0;i<500;i++){const d=p.choose(0,false,false);p.learn([d],{success:d.levels===best,difficulty:LEVELS[d.levels],assisted:false});}
    assert.ok(p.choose(0,false,false).probabilities[best-1]>.95);
  }
});
test('learned policy survives a new run without trusting invalid stored parameters',()=>{
  const p=new LoweringPolicy(()=>0),d=p.choose(0,false,false,'T1-S2');
  p.learn([d],{success:true,difficulty:.85,assisted:false});
  const saved=p.snapshot(),restored=new LoweringPolicy(()=>0);restored.restore(saved);
  assert.deepEqual(restored.choose(0,false,false,'T1-S2').probabilities,p.choose(0,false,false,'T1-S2').probabilities);
  saved.states[d.key].logits[0]=999;assert.notEqual(restored.states[d.key].logits[0],999);
  restored.restore({version:1,states:{invalid:{logits:[0,0],baseline:0},'T1-S1:0:far:independent':{logits:[NaN,1],baseline:0},'T1-S3:0:far:independent':{logits:[100,-100],baseline:100}}});
  assert.equal(restored.states.invalid,undefined);assert.equal(restored.states['T1-S1:0:far:independent'],undefined);
  assert.deepEqual(restored.states['T1-S3:0:far:independent'],{logits:[20,-20],baseline:5});
});
