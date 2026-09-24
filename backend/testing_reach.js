/* Experimental, Testing-only adaptation. No diagnosis and no treatment prescription. */
(function(root) {
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const LEVELS=Object.freeze([1,.85,.70,.55,.40]);
  const CONFIG=Object.freeze({attemptMs:8000,retryMs:6000,lowerMs:700,
    discount:.95,lowerCost:.04,failureReward:-1,entropy:.01,learningRate:.08});

  // Target attempts use fresh tracked hand positions; no preliminary movement
  // test is needed before the first target is shown.
  function observation(p,side,aspect=1) {
    const ids=side==='left'?{s:11,e:13,w:15,h:23}:{s:12,e:14,w:16,h:24};
    if(!p || ![11,12,23,24,ids.e,ids.w].every(i=>p[i] && [p[i].x,p[i].y].every(Number.isFinite)
      && (p[i].visibility??0)>=.65 && p[i].x>0 && p[i].x<1 && p[i].y>0 && p[i].y<1)) return null;
    const s=p[ids.s],e=p[ids.e],w=p[ids.w],h=p[ids.h];
    const width=Math.hypot((p[11].x-p[12].x)*aspect,p[11].y-p[12].y);
    if(width<.09) return null;
    const angle=(a,b,c)=>{const u=[(a.x-b.x)*aspect,a.y-b.y],v=[(c.x-b.x)*aspect,c.y-b.y];
      const n=Math.hypot(...u)*Math.hypot(...v);return n>.000025?Math.acos(clamp((u[0]*v[0]+u[1]*v[1])/n,-1,1))*180/Math.PI:null;};
    return {x:(w.x-s.x)*aspect/width,y:(w.y-s.y)/width,elbow:angle(s,e,w),arm:angle(h,s,e),
      shoulderX:s.x,shoulderY:s.y,width,hand:{x:1-w.x,y:w.y}};
  }

  // Tabular REINFORCE learns how far to lower after an unsuccessful encouraged
  // retry. It never decides whether to ignore the patient or increase difficulty.
  class LoweringPolicy {
    constructor(random=Math.random){this.random=random;this.states={};this.updates=[];}
    choose(level,near,assisted,step='reach'){
      const key=`${step}:${level}:${near?'near':'far'}:${assisted?'assisted':'independent'}`;
      const state=this.states[key] ||= {logits:[0,0],baseline:0};
      const max=Math.max(...state.logits), weights=state.logits.map(x=>Math.exp(x-max)),sum=weights.reduce((a,b)=>a+b,0);
      const p=weights.map(x=>x/sum),action=this.random()<p[0]?0:1;
      return {key,action,probabilities:p,levels:action+1};
    }
    restore(data){
      if(data?.version!==1 || !data.states || typeof data.states!=='object')return;
      for(const [key,s] of Object.entries(data.states).slice(0,100)){
        if(!/^(reach|T1-S[123]):[0-3]:(near|far):(assisted|independent)$/.test(key) || !Array.isArray(s?.logits)
          || s.logits.length!==2 || !s.logits.every(Number.isFinite) || !Number.isFinite(s.baseline))continue;
        this.states[key]={logits:s.logits.map(v=>clamp(v,-20,20)),baseline:clamp(s.baseline,-5,5)};
      }
    }
    snapshot(){return {version:1,states:JSON.parse(JSON.stringify(this.states))};}
    learn(decisions,{success,difficulty,assisted,cancelled=false}){
      if(cancelled || !decisions.length)return null;
      const terminal=success ? 2*clamp(difficulty,.4,1)*(assisted?.5:1) : CONFIG.failureReward;
      let G=terminal;const updates=[];
      for(let i=decisions.length-1;i>=0;i--){
        const d=decisions[i];G=-CONFIG.lowerCost+CONFIG.discount*G;
        // The minimum-height final descent is forced, not a sampled action.
        if(d.forced)continue;
        const s=this.states[d.key],p=d.probabilities,b=s.baseline,A=G-b,H=-p.reduce((v,x)=>v+x*Math.log(x),0);
        const gradient=p.map((x,j)=>A*((j===d.action?1:0)-x)-CONFIG.entropy*x*(Math.log(x)+H));
        s.logits=s.logits.map((v,j)=>v+CONFIG.learningRate*gradient[j]);s.baseline+=.05*(G-b);
        updates.push({state:d.key,action:d.levels,probabilities:p,return:G,baseline:b,advantage:A,gradient});
      }
      const update={success,difficulty,assisted,terminal_reward:terminal,reductions:decisions.length,updates};
      this.updates.push(update);return update;
    }
  }

  class ReachStep {
    constructor({policy,id,base,lap,level=0,assisted=false}){
      Object.assign(this,{policy,id,base:{...base},lap:{...lap},level,assisted});
      this.phase='attempt';this.elapsed=0;this.last=null;this.decisions=[];this.events=[];this.bestDistance=Infinity;
      this.target=this.targetFor(level);this.initialLevel=level;this.finished=false;this.learning=null;this.learningHistory=[];
    }
    get difficulty(){return this.id==='T1-S4'?1:LEVELS[this.level];}
    targetFor(level){
      if(this.id==='T1-S4')return {...this.base};
      const d=LEVELS[level];
      // Lap-height S1 is eased laterally. Raised steps are eased vertically,
      // with X locked to the screen-right of the calibrated shoulder.
      return this.id==='T1-S1'?{x:this.lap.x+(this.base.x-this.lap.x)*(.65+.35*d),y:this.base.y}
        :{x:this.base.x,y:this.lap.y+(this.base.y-this.lap.y)*d};
    }
    cueDone(){
      if(this.phase==='encourage')this.phase='retry';
      else if(this.phase==='announce_lower')this.phase='lowering';
      this.elapsed=0;this.last=null;
    }
    tick({now,valid,paused=false,distance=Infinity}){
      const dt=this.last===null?0:now-this.last;this.last=now;
      if(this.finished || !valid || paused || dt>250 || dt<0)return null;
      if(['attempt','retry'].includes(this.phase))this.bestDistance=Math.min(this.bestDistance,distance);
      if(!['attempt','retry','lowering'].includes(this.phase))return null;
      this.elapsed+=Math.min(dt,100);
      if(this.phase==='lowering'){
        const f=clamp(this.elapsed/CONFIG.lowerMs,0,1);
        this.target={x:this.from.x+(this.to.x-this.from.x)*f,y:this.from.y+(this.to.y-this.from.y)*f};
        if(f===1){this.phase='attempt';this.elapsed=0;this.last=null;return 'lowered';}return null;
      }
      if(this.phase==='attempt' && this.elapsed>=CONFIG.attemptMs){this.phase='encourage';this.elapsed=0;return 'encourage';}
      if(this.phase==='retry' && this.elapsed>=CONFIG.retryMs){
        if(this.level===LEVELS.length-1 || this.id==='T1-S4'){this.phase='needs_support';return 'needs_support';}
        const d=this.level===LEVELS.length-2?{levels:1,forced:true}:this.policy.choose(this.level,this.bestDistance<.18,this.assisted,this.id);
        this.pending=d;this.from={...this.target};this.nextLevel=Math.min(LEVELS.length-1,this.level+d.levels);this.to=this.targetFor(this.nextLevel);
        this.phase='announce_lower';this.elapsed=0;return 'announce_lower';
      }
      return null;
    }
    commitLowering(){
      if(this.phase!=='announce_lower')return false;
      this.level=this.nextLevel;this.decisions.push(this.pending);
      this.events.push({difficulty:LEVELS[this.level],action:this.pending.levels,after_encouraged_retry:true});
      this.cueDone();return true;
    }
    finish(success,cancelled=false){
      if(this.finished)return;this.finished=true;
      this.learning=this.policy.learn(this.decisions,{success,difficulty:this.difficulty,assisted:this.assisted,cancelled});
      if(this.learning)this.learningHistory.push(this.learning);
    }
    retry(){this.finished=false;this.decisions=[];this.phase='attempt';this.elapsed=0;this.last=null;}
    snapshot(){return {version:'testing-reach-adaptation-1',difficulty:this.difficulty,assisted:this.assisted,
      initial_level:this.initialLevel,final_level:this.level,reductions:this.events.map(x=>({...x})),learning:this.learning,learning_history:this.learningHistory};}
  }
  const api={LEVELS,CONFIG,observation,LoweringPolicy,ReachStep};
  root.RehynTestingReach=api;if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(globalThis);
