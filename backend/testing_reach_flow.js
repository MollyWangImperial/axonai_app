// Runs inside the assessment module, so targets, holds and scoring use one state.
const reachFlow={support:null,assisted:false,step:null,
  policy:new RehynTestingReach.LoweringPolicy(),raisedLevel:0,lastVideo:null,lastVideoAt:0,waiting:false,
  stopped:false,voiceUnavailable:false};
const reachPanel=document.getElementById('reachSupportPanel');
const reachCaption=document.getElementById('reachGuidance');
const reachPolicyKey=`rehyn-testing-reach-policy-1:${CURRENT_USER_ID}:${AFFECTED_SIDE}`;
try{reachFlow.policy.restore(JSON.parse(sessionStorage.getItem(reachPolicyKey)||'null'));}catch{}
function saveReachPolicy(){try{sessionStorage.setItem(reachPolicyKey,JSON.stringify(reachFlow.policy.snapshot()));}catch{}}
function testingReachEnabled(){return LIBRARY_TEST_MODE && tasks.length===1 && tasks[0]?.id==='T1';}
function reachStepVoiceLines(step){
  if(step.id==='T1-S2'){
    // Give the hold cue before the raised target unlocks so the patient does
    // not lower their hand between the reach and hold steps. Both lines are
    // already available as private Molly clips.
    const holdVoice=tasks[0]?.steps?.find(item=>item.id==='T1-S3')?.voice;
    return [step.voice,holdVoice].filter(Boolean);
  }
  if(step.id==='T1-S3')return [];
  return [step.voice].filter(Boolean);
}
function syncReachCaption(){
  // The calibration card already contains the instruction. Keep the camera
  // clear when speech works; show text in the controls if speech is off.
  reachCaption.classList.toggle('hidden',reachVoice.enabled || calibratingAssessment || !reachCaption.textContent);
}
const reachMollyCache=new Map(),reachMollyInflight=new Map();
async function fetchReachMollyAudio(text){
  if(reachMollyCache.has(text))return reachMollyCache.get(text);
  if(reachMollyInflight.has(text))return reachMollyInflight.get(text);
  const request=fetch(`${API_BASE}/testing/reach/voice`,{
    method:'POST',headers:{'Content-Type':'application/json',...ACCOUNT_HEADERS},
    body:JSON.stringify({text}),
  }).then(async response=>{
    if(!response.ok)throw new Error(`Molly voice unavailable (${response.status})`);
    const data=await response.json();
    if(!data.audio_b64)throw new Error('Molly voice audio is empty');
    reachMollyCache.set(text,data.audio_b64);
    return data.audio_b64;
  }).finally(()=>reachMollyInflight.delete(text));
  reachMollyInflight.set(text,request);
  return request;
}
function prefetchReachMollyAudio(text){
  if(text && reachVoice.enabled)void fetchReachMollyAudio(text).catch(()=>{});
}
const reachVoice=new RehynVoiceGuide.VoiceGuide({fetchAudio:fetchReachMollyAudio,audio:audioEl,timeoutMs:60000,onChange(v){
  document.getElementById('reachVoiceState').textContent=reachFlow.voiceUnavailable && !v.enabled
    ? 'Molly voice unavailable · continuing with captions' : v.status;
  if(v.caption)reachCaption.textContent=v.caption;
  syncReachCaption();
}});
reachVoice.enabled=VOICE_GUIDANCE_ENABLED;
document.getElementById('reachVoiceOn').checked=VOICE_GUIDANCE_ENABLED;
async function reachSay(text){
  if(reachFlow.stopped)return false;
  const ok=await reachVoice.speak(text);
  if(ok)return !reachFlow.stopped;
  if(reachFlow.stopped || !reachVoice.failed)return false;
  // Failed audio must not strand camera calibration or a movement
  // step. Keep the instruction visible for the caption interval, then proceed.
  reachFlow.voiceUnavailable=true;
  reachVoice.enabled=false;
  document.getElementById('reachVoiceOn').checked=false;
  return await reachVoice.speak(text) && !reachFlow.stopped;
}
document.getElementById('reachVoiceOn').onchange=event=>{
  reachVoice.enabled=event.target.checked;
  if(reachVoice.enabled){reachFlow.voiceUnavailable=false;
    document.getElementById('reachVoiceState').textContent='Molly voice enabled for the next instruction.';}
  syncReachCaption();
};
function reachChoice(title,copy,choices){
  reachFlow.waiting=true;reachPanel.classList.remove('hidden');
  document.getElementById('reachPause').disabled=true;
  document.getElementById('reachAssistance').disabled=true;
  document.getElementById('reachSupportTitle').textContent=title;
  document.getElementById('reachSupportCopy').textContent=copy;
  const actions=document.getElementById('reachSupportActions');actions.replaceChildren();
  choices.forEach(([label,action])=>{
    const button=document.createElement('button');button.type='button';button.textContent=label;
    button.onclick=()=>{actions.querySelectorAll('button').forEach(b=>b.disabled=true);reachFlow.waiting=false;reachPanel.classList.add('hidden');document.getElementById('reachPause').disabled=false;document.getElementById('reachAssistance').disabled=false;void action();};actions.append(button);
  });
}
function askReachSupport(){
  // Testing has its own caption strip. The generic assessment footer repeats
  // "Single task test / Preparing…" and can cover the low lap target.
  document.getElementById('bottom').classList.add('hidden');
  document.getElementById('reachControls').classList.remove('hidden');
  syncReachCaption();
  prefetchReachMollyAudio(TESTING_REACH_CALIBRATION_INSTRUCTION);
  prefetchReachMollyAudio(CALIBRATION_COMPLETE_INSTRUCTION);
  prefetchReachMollyAudio(tasks[0]?.steps?.[0]?.voice);
  reachChoice('Is someone beside you?',
    'Is a carer or family member here who could help if needed? We will ask before any assisted movement. Your camera will start after you answer.'+(localReview.enabled?' This local test saves a review video on this computer.':''),[
      ['Yes, someone is here',()=>{reachFlow.support=true;void beginAssessmentSetup();}],
      ['No, I am on my own',()=>{reachFlow.support=false;void beginAssessmentSetup();}],
    ]);
}
function reachObservation(lm,now){
  const sourceTime=video.currentTime;
  if(sourceTime!==reachFlow.lastVideo){reachFlow.lastVideo=sourceTime;reachFlow.lastVideoAt=now;}
  if(video.readyState<2 || now-reachFlow.lastVideoAt>250 || now-lastPoseScanTs>250)return null;
  return RehynTestingReach.observation(lm,AFFECTED_SIDE,video.videoWidth/video.videoHeight);
}
function showReachHelp(){
  const copy='The target has not been completed after another comfortable attempt. You can rest, finish, or use help if someone is here.';
  const choices=[];
  if(reachFlow.support)choices.push(['Continue with assistance',async()=>{
    reachFlow.assisted=true;if(reachFlow.step)reachFlow.step.assisted=true;
    const ok=await reachSay('Ask the person beside you to help only in the way your therapist has shown you. Do not pull or force the arm. This attempt will be marked as assisted. Stop if it hurts.');
    if(!ok)return;
    if(reachFlow.step)reachFlow.step.retry();
  }]);
  choices.push(['Try again independently',async()=>{
    reachFlow.step.retry();
  }]);
  choices.push(['Finish test for now',()=>endReachTest()]);
  reachChoice(reachFlow.support?'Help is available':'Pause and get support',
    copy+(reachFlow.support?' Assistance must be confirmed; the camera cannot identify it reliably.':' If you need hands-on help, pause until a carer or family member is available.'),choices);
  void reachSay(reachFlow.support
    ? 'I have not detected a completed movement. If needed, ask the person beside you to help in the way your therapist has shown you. Choose assisted practice, try again, or finish for now.'
    : 'Let us pause. I have not detected a completed movement. If you need help, wait until a carer or family member is with you. You can try again or finish for now.');
}
function beginReachStep(step){
  if(!testingReachEnabled())return;
  reachStepVoiceLines(step).forEach(prefetchReachMollyAudio);
  const base=step.id==='T1-S1'?forwardReachPlacement.start:step.id==='T1-S4'?assessmentLapTarget:forwardReachPlacement.raised;
  reachFlow.step=new RehynTestingReach.ReachStep({policy:reachFlow.policy,id:step.id,base,lap:mirrorX(assessmentLapTarget),
    level:step.id==='T1-S3'?reachFlow.raisedLevel:0,assisted:reachFlow.assisted});
}
function reachCanMeasure(){return !testingReachEnabled() || (!reachFlow.stopped && !reachFlow.waiting
  && !reachVoice.busy && !reachVoice.failed && reachFlow.step && ['attempt','retry'].includes(reachFlow.step.phase));}
async function handleReachEvent(event){
  const step=reachFlow.step;if(!step)return;
  inTargetSince=null;lastInTargetTs=0;
  if(event==='encourage'){
    if(await reachSay('You are doing well to keep trying. If comfortable, try once more toward the centre of the circle. Take your time and keep your shoulder relaxed. You can stop or ask for help.'))step.cueDone();
  }else if(event==='announce_lower'){
    const prompt=step.id==='T1-S1'
      ? 'Thank you for trying. I will bring this low target a little closer to your resting hand. Wait for the circle to stop, then try again comfortably.'
      : 'Thank you for trying. I will lower the target to make the next reach easier. Wait for the circle to stop, then try again comfortably.';
    if(await reachSay(prompt))step.commitLowering();
  }else if(event==='lowered'){
    reachCaption.textContent='The circle is ready. Reach comfortably toward its centre.';
    syncReachCaption();
  }else if(event==='needs_support'){step.finish(false);saveReachPolicy();showReachHelp();}
}
function tickTestingReach(lm,now){
  if(!testingReachEnabled() || reachFlow.stopped || calibratingAssessment)return;
  const obs=reachObservation(lm,now),paused=reachVoice.busy || reachVoice.failed || reachFlow.waiting || correctionVoicePlaying;
  const step=reachFlow.step;
  if(!step || stepCompleted || voiceFinishedAt===0)return;
  const event=step.tick({now,valid:!!obs,paused,distance:obs?forwardReachDistance(obs.hand,step.target):Infinity});
  if(event)void handleReachEvent(event);
  document.getElementById('reachDifficulty').textContent=`${step.assisted?'Assisted':'Independent'} · target difficulty ${Math.round(step.difficulty*100)}%`;
}
function finishTestingReachStep(success){
  if(!testingReachEnabled() || !reachFlow.step)return null;
  const step=reachFlow.step;step.finish(success);
  saveReachPolicy();
  if(step.id==='T1-S2')reachFlow.raisedLevel=step.level;
  return {...step.snapshot(),support_available:reachFlow.support};
}
function stopReachVoice(){
  reachFlow.stopped=true;reachVoice.cancel();
}
function endReachTest(){
  if(reachFlow.step&&!reachFlow.step.finished)reachFlow.step.finish(false,true);
  stopReachVoice();reachPanel.classList.add('hidden');
  if(!taskResults[0])taskResults[0]={task_id:'T1',completed_steps:0,total_steps:4,duration_ms:0,steps:[],metrics:{}};
  taskResults[0].metrics.testing_reach={support_available:reachFlow.support,stopped:true};
  finishAssessment();
}
document.getElementById('reachPause').onclick=()=>{
  if(reachFlow.stopped)return;
  reachChoice('Take a pause','Rest your arm. Timing and targets are paused. You can continue when comfortable or finish now.',[
    ['Continue',()=>{}],['Finish test for now',endReachTest],
  ]);
};
document.getElementById('reachAssistance').onclick=()=>{
  if(!reachFlow.step || reachFlow.stopped)return;
  reachChoice('Is someone helping your arm?', 'Record hands-on help for this and the remaining steps. Someone simply being beside you does not count as assistance.',[
    ['Yes, record assistance',()=>{reachFlow.support=true;reachFlow.assisted=true;reachFlow.step.assisted=true;}],['No, continue',()=>{}],
  ]);
};
