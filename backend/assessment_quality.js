/* Camera screening evidence. All joint angles use one model's world space.
 * Missing/occluded landmarks abstain; thresholds are not clinical diagnoses. */
(function(root) {
  const finite = Number.isFinite;
  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const sub = (a, b) => [a.x-b.x, a.y-b.y, a.z-b.z];
  const length = a => Math.hypot(...a);
  const midpoint = (a,b) => ({x:(a.x+b.x)/2,y:(a.y+b.y)/2,z:(a.z+b.z)/2});
  const angleV = (a,b) => length(a) > .005 && length(b) > .005 ? Math.acos(clamp(a.reduce((v,x,i)=>v+x*b[i],0)/(length(a)*length(b)),-1,1))*180/Math.PI : NaN;
  const angle = (a,b,c) => a && b && c ? angleV(sub(a,b),sub(c,b)) : NaN;
  const quantile = (a,q=.5) => a.length ? [...a].sort((x,y)=>x-y)[Math.floor((a.length-1)*q)] : NaN;

  class Tracker {
    constructor(config, side) {
      this.config=config;
      this.a=side === "left" ? {s:11,e:13,w:15,h:23,k:25,f:27,ear:7,i:19,p:17,t:31} : {s:12,e:14,w:16,h:24,k:26,f:28,ear:8,i:20,p:18,t:32};
      this.o=side === "left" ? {s:12,h:24,k:26,f:28,ear:8} : {s:11,h:23,k:25,f:27,ear:7};
      this.baselines=[];
      this.baseline=null;
      this.reset(null);
    }
    reset(rubric) {
      this.rubric=rubric;
      this.measurements={}; this.compensations={}; this.lastTime=null;
      this.sawClosed=false; this.openCloseCycle=0;
    }
    raw(p,w) {
      const a=this.a,o=this.o,r={};
      const usable = ids => p && w && ids.every(i=>p[i] && w[i] && [w[i].x,w[i].y,w[i].z,p[i].x,p[i].y].every(finite) && (p[i].visibility ?? 0)>=.65);
      if(usable([a.s,a.e,a.w,a.h])) {
        r.elbow_extension=angle(w[a.s],w[a.e],w[a.w]);
        r.elbow_flexion=180-r.elbow_extension;
        r.arm_elevation=angle(w[a.h],w[a.s],w[a.e]);
      }
      if(usable([11,12,23,24])) {
        const sh=midpoint(w[11],w[12]), hip=midpoint(w[23],w[24]);
        r.torso=sub(sh,hip);
        r.width=length(sub(w[11],w[12]));
        r.screenWidth=Math.hypot(p[11].x-p[12].x,p[11].y-p[12].y);
        r.shoulderLine=(w[o.s].y-w[a.s].y)/Math.max(.05,r.width);
        r.hipLine=(w[o.h].y-w[a.h].y)/Math.max(.05,r.width);
      }
      if(usable([a.s,a.ear])) r.neckGap=length(sub(w[a.s],w[a.ear]));
      if(usable([7,8,0])) {
        const ears=midpoint(w[7],w[8]);
        r.headPitch=(w[0].y-ears.y)/Math.max(.04,length(sub(w[7],w[8])));
      }
      if(usable([a.s,a.h,a.k,a.f])) {
        r.knee_extension=angle(w[a.h],w[a.k],w[a.f]);
        r.hip_extension=angle(w[a.s],w[a.h],w[a.k]);
        r.hip_flexion=180-r.hip_extension;
      }
      if(usable([o.s,o.h,o.k])) r.other_hip_flexion=180-angle(w[o.s],w[o.h],w[o.k]);
      if(usable([a.k,a.f,a.t])) r.ankle=angle(w[a.k],w[a.f],w[a.t]);
      if(usable([a.h,a.k,a.f,o.f])) r.step_distance=length(sub(w[a.f],w[o.f]))/Math.max(.2,length(sub(w[a.h],w[a.k]))+length(sub(w[a.k],w[a.f])));
      // Coarse pose fingers cannot establish inward vs outward bend. Report
      // alignment only, and abstain for foreshortened, closed or occluded hands.
      if(usable([a.e,a.w,a.i,a.p])) {
        const hand=midpoint(w[a.i],w[a.p]);
        const screenHand=midpoint(p[a.i],p[a.p]);
        const fore=length(sub(w[a.e],w[a.w])), palm=length(sub(hand,w[a.w]));
        const projection=Math.hypot(screenHand.x-p[a.w].x,screenHand.y-p[a.w].y);
        if(fore>.12 && palm>.055 && projection>.025 && palm/fore>.22 && palm/fore<.9) r.wrist_bend=180-angle(w[a.e],w[a.w],hand);
      }
      return r;
    }
    calibrate(p,w) {
      const r=this.raw(p,w);
      if(!r.torso || !finite(r.width)) return;
      this.baselines.push(r);
      if(this.baselines.length>45) this.baselines.shift();
      if(this.baselines.length<15) return;
      const keys=["width","screenWidth","shoulderLine","hipLine","neckGap","headPitch","ankle","wrist_bend"];
      const b=Object.fromEntries(keys.map(k=>[k,quantile(this.baselines.map(x=>x[k]).filter(finite))]));
      const directions=this.baselines.map(x=>x.torso);
      b.torso=[0,1,2].map(i=>quantile(directions.map(v=>v[i])));
      if(Math.max(...directions.map(v=>angleV(v,b.torso)))<6) this.baseline=b;
    }
    sample({pose,world,hand,handOpen,handClosed,pinch,gaitAlternations,inTarget,now}) {
      if(!this.rubric) return;
      const dt=this.lastTime===null ? 0 : clamp(now-this.lastTime,0,100);
      const gap=this.lastTime!==null && now-this.lastTime>200;
      this.lastTime=now;
      const r=this.raw(pose,world), b=this.baseline;
      const handValid=hand && hand.length===21 && hand.every(p=>p && finite(p.x) && finite(p.y));
      if(handValid) {
        r.hand_open=handOpen; r.hand_closed=handClosed; r.pinch=pinch;
        if(handClosed>=.65) this.sawClosed=true;
        if(this.sawClosed && handOpen>=.7) this.openCloseCycle=1;
        r.open_close_cycle=this.openCloseCycle;
      }
      if(r.torso) r.target_control=inTarget ? 1 : 0;
      if(finite(r.step_distance)) r.gait_alternations=gaitAlternations;
      if(b && r.torso && finite(r.screenWidth) && Math.abs(r.screenWidth/b.screenWidth-1)<.3) {
        r.trunk_lean=angleV(r.torso,b.torso);
        // Subtract normal elevation-related shoulder rise. Require both line
        // elevation and neck shortening so opposite shoulder drop alone is not a shrug.
        if(finite(r.neckGap) && finite(b.neckGap)) {
          const rise=Math.max(0,r.shoulderLine-b.shoulderLine);
          const shortened=Math.max(0,(b.neckGap-r.neckGap)/b.width);
          r.shoulder_hike=Math.max(0,Math.atan2(Math.min(rise,shortened),.5)*180/Math.PI-(r.arm_elevation||0)*.12);
        }
        r.hip_hike=Math.atan2(Math.max(0,r.hipLine-b.hipLine),.5)*180/Math.PI;
        if(finite(r.headPitch) && finite(b.headPitch)) r.head_drop=Math.max(0,r.headPitch-b.headPitch)*60;
        if(finite(r.ankle) && finite(b.ankle)) r.ankle_change=Math.abs(r.ankle-b.ankle);
        if(finite(r.wrist_bend) && finite(b.wrist_bend)) r.wrist_extension_change=Math.abs(r.wrist_bend-b.wrist_bend);
      }
      for(const rule of this.rubric.criteria) {
        const v=r[rule.metric];
        if(!finite(v)) continue;
        const record=this.measurements[rule.metric] ||= {samples:0,values:[],endpoints:[]};
        record.samples++;
        record.values.push(v);
        if(record.values.length>600) record.values.shift();
        if(inTarget) {record.endpoints.push(v); if(record.endpoints.length>120) record.endpoints.shift();}
      }
      for(const id of this.rubric.compensations) {
        const c=this.compensations[id] ||= {eligible_ms:0,max_value:0,max_streak_ms:0,streak:0,active:false};
        const v=r[id];
        if(!finite(v)) {c.streak=0; c.active=false; continue;}
        c.eligible_ms+=dt;
        c.max_value=Math.max(c.max_value,v);
        c.streak=v>this.config.compensations[id].threshold ? (gap?0:c.streak)+dt : 0;
        c.max_streak_ms=Math.max(c.max_streak_ms,c.streak);
        c.active=c.streak>=500;
      }
    }
    snapshot() {
      return {version:this.config.version,measurements:Object.fromEntries(Object.entries(this.measurements).map(([k,r])=>[k,{samples:r.samples,value:quantile(r.endpoints.length>=5?r.endpoints:r.values,.5)}])),
        compensations:Object.fromEntries(Object.entries(this.compensations).map(([k,c])=>[k,{eligible_ms:Math.round(c.eligible_ms),max_value:c.max_value,max_streak_ms:Math.round(c.max_streak_ms)}]))};
    }
    active() {return Object.keys(this.compensations).filter(id=>this.compensations[id].active);}
    draw(ctx,pose,width,height) {
      if(!pose) return;
      const a=this.a;
      const paths={trunk_lean:[11,23,24,12,11],shoulder_hike:[a.ear,a.s],head_drop:[7,0,8],wrist_bend:[a.e,a.w,a.i],hip_hike:[23,24]};
      ctx.save(); ctx.strokeStyle="#FF5757"; ctx.lineWidth=4; ctx.lineCap="round"; ctx.setLineDash([2,7]);
      for(const id of this.active()) {
        const points=paths[id].map(i=>pose[i]);
        if(points.some(p=>!p || (p.visibility??0)<.65)) continue;
        ctx.beginPath();points.forEach((p,i)=>{if(i)ctx.lineTo(p.x*width,p.y*height);else ctx.moveTo(p.x*width,p.y*height);});ctx.stroke();
        const p=pose[id==="wrist_bend"?a.w:id==="shoulder_hike"?a.s:id==="head_drop"?0:a.h];
        ctx.beginPath();ctx.arc(p.x*width,p.y*height,Math.max(22,width*.035),0,Math.PI*2);ctx.stroke();
      }
      ctx.restore();
    }
  }
  root.RehynAssessmentQuality={Tracker};
  if(typeof module!=="undefined") module.exports={Tracker};
})(globalThis);
