from __future__ import annotations

from typing import Any, Dict, Mapping


FAST_ALGORITHM_VERSION = "rehyn-fast-1.1-demo-911"
FAST_SIGNS = ("face", "arms", "speech")
FAST_ANSWERS = {"no", "yes", "unsure"}


def evaluate_fast_screen(
    answers: Mapping[str, Any],
    automated: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Apply the NHS FAST escalation rule without presenting a diagnosis."""
    automated = automated or {}
    normalized = {
        sign: str(answers.get(sign) or "unsure").strip().lower()
        for sign in FAST_SIGNS
    }
    for sign, answer in normalized.items():
        if answer not in FAST_ANSWERS:
            raise ValueError(f"Invalid FAST answer for {sign}")

    observed = [
        sign
        for sign in FAST_SIGNS
        if normalized[sign] == "yes"
        or bool((automated.get(sign) or {}).get("positive"))
    ]
    uncertain = [sign for sign in FAST_SIGNS if normalized[sign] == "unsure"]
    call_999 = bool(observed or uncertain)

    if call_999:
        return {
            "algorithm_version": FAST_ALGORITHM_VERSION,
            "status": "call_999",
            "call_999": True,
            "demo_call_911": True,
            "emergency_call_mode": "simulation",
            "red_flag": True,
            "observed_signs": observed,
            "uncertain_signs": uncertain,
            "headline": "Call 999 now",
            "message": (
                "A FAST sign was noticed or could not be ruled out. Say that you suspect a stroke. "
                "Do not wait for symptoms to pass and do not drive the person to A&E."
            ),
        }

    return {
        "algorithm_version": FAST_ALGORITHM_VERSION,
        "status": "no_fast_signs_identified",
        "call_999": False,
        "demo_call_911": False,
        "emergency_call_mode": "simulation",
        "red_flag": False,
        "observed_signs": [],
        "uncertain_signs": [],
        "headline": "No FAST signs identified",
        "message": (
            "This brief screen did not identify a FAST sign, but it cannot rule out a stroke or TIA. "
            "Call 999 if symptoms were sudden, have faded, or you remain concerned."
        ),
    }


FAST_RUNNER_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
<title>Emergency FAST check</title>
<style>
  *{box-sizing:border-box}
  html,body{margin:0;width:100%;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#F7F8F6;color:#17211B}
  button,input{font:inherit}
  button{cursor:pointer}
  .shell{min-height:100%;display:flex;flex-direction:column}
  .emergencyBar{background:#B42318;color:#fff;padding:12px 16px;display:flex;align-items:center;justify-content:center;gap:12px;font-weight:850;text-align:center}
  .emergencyBar button{border:2px solid #fff;background:#fff;color:#8F1D14;border-radius:6px;padding:9px 15px;font-weight:900;white-space:nowrap}
  .top{height:58px;padding:0 16px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #D9DEDA;background:#fff}
  .top strong{font-size:18px;color:#183E2E}
  .exit{border:0;background:transparent;color:#34443B;font-weight:800;padding:10px}
  .workspace{flex:1;position:relative;min-height:520px;display:grid;grid-template-columns:minmax(280px,1.05fr) minmax(330px,.95fr)}
  .camera{position:relative;overflow:hidden;background:#101713;min-height:460px}
  video,canvas{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;transform:scaleX(-1)}
  canvas{pointer-events:none}
  .cameraLabel{position:absolute;left:16px;bottom:16px;right:16px;padding:10px 12px;border-radius:6px;background:rgba(14,23,18,.78);color:#fff;font-size:14px;line-height:1.35;backdrop-filter:blur(8px)}
  .panel{padding:28px;display:flex;flex-direction:column;justify-content:center;background:#fff;border-left:1px solid #D9DEDA}
  .letter{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;background:#FCE6E3;color:#B42318;font-size:28px;font-weight:950;margin-bottom:16px}
  .eyebrow{font-size:13px;text-transform:uppercase;font-weight:900;color:#B42318;margin-bottom:8px}
  h1{font-size:30px;line-height:1.12;margin:0 0 12px;color:#183E2E}
  p{font-size:17px;line-height:1.48;margin:0 0 16px;color:#35443C}
  .important{border-left:5px solid #B42318;background:#FFF1EF;padding:13px 14px;margin:8px 0 18px;font-weight:750;color:#6E1A14;line-height:1.4}
  .assist{display:flex;align-items:flex-start;gap:10px;background:#EEF4F0;border:1px solid #D8E3DB;padding:12px;border-radius:6px;margin:0 0 18px;color:#294638;font-size:14px;line-height:1.4}
  .assistDot{width:10px;height:10px;border-radius:50%;background:#78847D;margin-top:5px;flex:0 0 auto}
  .assist.good .assistDot{background:#2F7A4D}.assist.warn .assistDot{background:#B42318}
  .actions{display:grid;gap:10px}
  .primary,.answer,.secondary{min-height:54px;border-radius:6px;font-weight:850;padding:13px 16px}
  .primary{border:0;background:#155B3C;color:#fff}
  .answer{border:1px solid #B9C2BC;background:#fff;color:#183E2E;text-align:left;display:flex;align-items:center;justify-content:space-between}
  .answer.danger{border-color:#D78B85;color:#8F1D14;background:#FFF8F7}
  .answer.unsure{border-color:#D9A441;color:#6B4A0B;background:#FFFBF0}
  .secondary{border:1px solid #8DA095;background:#fff;color:#183E2E}
  .hidden{display:none!important}
  .progress{display:flex;gap:7px;margin-bottom:22px}.progress span{height:6px;flex:1;border-radius:3px;background:#DEE3DF}.progress span.done{background:#1F7047}.progress span.active{background:#B42318}
  .phrase{font-size:23px;font-weight:850;color:#183E2E;padding:16px;border:1px solid #CBD5CE;background:#F7F9F7;border-radius:6px;margin:2px 0 16px;text-align:center}
  .transcript{min-height:48px;padding:12px;border-radius:6px;background:#F0F2EF;color:#34443B;margin-bottom:12px;font-size:14px}
  .result{grid-column:1/-1;padding:30px;display:flex;align-items:center;justify-content:center;background:#F7F8F6}
  .resultInner{width:min(740px,100%);background:#fff;border:2px solid #B42318;border-radius:8px;padding:28px;text-align:center}
  .resultInner.clear{border-color:#2F7A4D}
  .resultIcon{width:76px;height:76px;border-radius:50%;display:grid;place-items:center;margin:0 auto 16px;background:#FCE6E3;color:#B42318;font-size:42px;font-weight:950}
  .clear .resultIcon{background:#E2F1E7;color:#2F7A4D}
  .result h1{font-size:36px;color:#8F1D14}.result .clear h1{color:#1F7047}
  .callButton{display:block;width:100%;border:0;border-radius:6px;background:#B42318;color:#fff;padding:17px;font-size:20px;font-weight:950;margin:18px 0 12px}
  .onset{margin:16px 0;text-align:left}.onset label{display:block;font-weight:850;margin-bottom:7px}.onset input{width:100%;padding:13px;border:1px solid #AAB5AE;border-radius:6px;background:#fff}
  .small{font-size:14px;color:#59655E}.source{font-size:12px;color:#667269;margin-top:16px}
  .callOverlay{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;padding:20px;background:rgba(18,24,20,.78);backdrop-filter:blur(5px)}
  .callCard{width:min(430px,100%);padding:28px;border-radius:8px;background:#fff;text-align:center;box-shadow:0 24px 70px rgba(0,0,0,.35)}
  .demoBadge{display:inline-block;padding:6px 10px;border-radius:4px;background:#FFF0CE;color:#6B4500;font-size:12px;font-weight:950;text-transform:uppercase}
  .callPulse{width:104px;height:104px;border-radius:50%;display:grid;place-items:center;margin:22px auto 18px;background:#B42318;color:#fff;font-size:34px;font-weight:950;animation:callPulse 1.15s ease-in-out infinite}
  .callCard h2{margin:0 0 10px;color:#8F1D14;font-size:28px}.callCard p{font-size:16px}
  .demoWarning{margin:16px 0;padding:13px;border:2px solid #B42318;border-radius:6px;background:#FFF1EF;color:#751D16;font-weight:900;line-height:1.4}
  @keyframes callPulse{50%{transform:scale(1.07);box-shadow:0 0 0 16px rgba(180,35,24,.13)}}
  body.intro-mode .workspace{display:flex;align-items:center;justify-content:center;padding:24px}
  body.intro-mode .camera{display:none}
  body.intro-mode .panel{width:min(720px,100%);min-height:0;border:1px solid #D9DEDA;border-radius:8px}
  @media(max-width:760px){
    .emergencyBar{align-items:stretch;flex-direction:column;gap:7px;padding:10px 14px}.emergencyBar button{width:100%}
    .workspace{display:block}.camera{height:38vh;min-height:270px}.panel{border-left:0;border-top:1px solid #D9DEDA;padding:22px 18px;min-height:430px;justify-content:flex-start}
    h1{font-size:26px}.result{padding:18px}.resultInner{padding:22px 16px}.result h1{font-size:31px}
  }
</style>
</head>
<body>
<div class="shell">
  <div class="emergencyBar"><span>Prototype only: any 911 call shown here is simulated. If this is a real emergency, use a phone to call 911 now.</span></div>
  <div class="top"><button class="exit" type="button" onclick="postRN({type:'exit'})">Exit</button><strong>Emergency FAST check</strong><span style="width:44px"></span></div>
  <main class="workspace" id="workspace">
    <section class="camera" id="cameraPane">
      <video id="video" playsinline autoplay muted></video>
      <canvas id="canvas"></canvas>
      <div class="cameraLabel" id="cameraLabel">Camera assistance starts only when you begin. A carer or family member should make the final observation.</div>
    </section>
    <section class="panel" id="panel"></section>
  </main>
</div>
<script type="module">
import { PoseLandmarker, FilesetResolver, DrawingUtils } from "/vendor/mediapipe/vision_bundle.mjs";

const video=document.getElementById("video"),canvas=document.getElementById("canvas"),ctx=canvas.getContext("2d"),panel=document.getElementById("panel"),cameraLabel=document.getElementById("cameraLabel");
const answers={face:null,arms:null,speech:null};
const automated={
  face:{available:false,positive:false,samples:0,positive_samples:0,metric:null},
  arms:{available:false,positive:false,samples:0,positive_samples:0,metric:null},
  speech:{available:false,positive:false,transcript:"",similarity:null,confidence:null}
};
let landmarker=null,stream=null,current="intro",lastVideoTime=-1,animationId=null,stepStartedAt=0,reported=false;
const phrase="The sky is blue today";

function postRN(data){
  const message=JSON.stringify(data);
  if(window.ReactNativeWebView&&window.ReactNativeWebView.postMessage) window.ReactNativeWebView.postMessage(message);
  else if(window.parent&&window.parent!==window) window.parent.postMessage(message,"*");
}
function startDemo911Call(){
  if(document.getElementById("demoCallOverlay")) return;
  const overlay=document.createElement("div");overlay.className="callOverlay";overlay.id="demoCallOverlay";overlay.setAttribute("data-testid","fast-demo-911");
  overlay.innerHTML=`<div class="callCard"><div class="demoBadge">Demo only</div><div class="callPulse">911</div><h2>Simulating a 911 call...</h2><p>This prototype is demonstrating the emergency handoff that follows a red FAST result.</p><div class="demoWarning">No emergency call has been placed.</div><p class="small">In a real emergency, use a phone to call 911 immediately and say that you suspect a stroke.</p><button class="secondary" id="closeDemoCall" style="width:100%">Close simulation</button></div>`;
  document.body.appendChild(overlay);document.getElementById("closeDemoCall").onclick=()=>overlay.remove();postRN({type:"demo_911_started"});
  speak("Demo only. The app is simulating a 911 call. No emergency call has been placed. In a real emergency, call 911 immediately.");
}
function speak(text){
  try{speechSynthesis.cancel();const utterance=new SpeechSynthesisUtterance(text);utterance.rate=.88;utterance.pitch=1;utterance.lang="en-GB";speechSynthesis.speak(utterance)}catch{}
}
function progress(index){return `<div class="progress" aria-label="FAST step ${index+1} of 4">${[0,1,2,3].map(i=>`<span class="${i<index?'done':i===index?'active':''}"></span>`).join('')}</div>`}
function distance(a,b){return Math.hypot((a.x||0)-(b.x||0),(a.y||0)-(b.y||0))}
function visible(lm,indexes){return indexes.every(i=>lm[i]&&(lm[i].visibility??1)>.55)}

async function ensureCamera(){
  if(stream&&landmarker) return true;
  cameraLabel.textContent="Starting private on-device camera assistance...";
  try{
    let cameraTimedOut=false;
    const cameraRequest=navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:960},height:{ideal:720}},audio:false});
    cameraRequest.then(candidate=>{if(cameraTimedOut)candidate.getTracks().forEach(track=>track.stop())}).catch(()=>{});
    stream=await Promise.race([cameraRequest,new Promise((_,reject)=>setTimeout(()=>{cameraTimedOut=true;reject(new Error("camera timeout"))},4500))]);
    video.srcObject=stream;await video.play();
    const files=await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
    landmarker=await PoseLandmarker.createFromOptions(files,{baseOptions:{modelAssetPath:"/vendor/mediapipe/models/pose_landmarker_lite.task"},runningMode:"VIDEO",numPoses:1,minPoseDetectionConfidence:.55,minPosePresenceConfidence:.55,minTrackingConfidence:.55});
    cameraLabel.textContent="Camera assistance is ready. Video stays on this device and is not saved.";
    animationId=requestAnimationFrame(loop);
    return true;
  }catch(error){
    cameraLabel.textContent="Camera assistance is unavailable. A carer can still complete FAST by observing the person directly.";
    return false;
  }
}

function loop(){
  if(video.readyState>=2&&landmarker&&video.currentTime!==lastVideoTime){
    lastVideoTime=video.currentTime;
    if(canvas.width!==video.videoWidth){canvas.width=video.videoWidth;canvas.height=video.videoHeight}
    const result=landmarker.detectForVideo(video,performance.now());
    ctx.clearRect(0,0,canvas.width,canvas.height);
    const lm=result.landmarks&&result.landmarks[0];
    if(lm){
      const draw=new DrawingUtils(ctx);draw.drawConnectors(lm,PoseLandmarker.POSE_CONNECTIONS,{color:"rgba(155,226,182,.78)",lineWidth:3});draw.drawLandmarks(lm,{color:"#FFFFFF",fillColor:"#B42318",radius:3});
      if(current==="face") analyseFace(lm);
      if(current==="arms") analyseArms(lm);
    }
  }
  animationId=requestAnimationFrame(loop);
}

function analyseFace(lm){
  if(!visible(lm,[2,5,9,10])) return;
  const faceWidth=Math.max(distance(lm[2],lm[5]),distance(lm[9],lm[10]),.02);
  const headTilt=(lm[2].y-lm[5].y);
  const mouthTilt=(lm[9].y-lm[10].y);
  const corrected=Math.abs(mouthTilt-headTilt)/faceWidth;
  automated.face.available=true;automated.face.samples+=1;automated.face.metric=Number(corrected.toFixed(3));
  if(corrected>.24) automated.face.positive_samples+=1;
  automated.face.positive=automated.face.samples>=12&&automated.face.positive_samples/automated.face.samples>.38;
  updateAssist("face",automated.face.positive?"Camera assistance noticed possible unevenness. Treat this as a sign.":"Camera assistance is comparing both sides of the smile.",automated.face.positive?"warn":"good");
}

function analyseArms(lm){
  if(!visible(lm,[11,12,13,14,15,16])) return;
  const shoulderWidth=Math.max(distance(lm[11],lm[12]),.04);
  const leftRaised=lm[15].y<=lm[11].y+shoulderWidth*.55;
  const rightRaised=lm[16].y<=lm[12].y+shoulderWidth*.55;
  const wristDifference=Math.abs(lm[15].y-lm[16].y)/shoulderWidth;
  const possibleDifference=!leftRaised||!rightRaised||wristDifference>.42;
  automated.arms.available=true;automated.arms.samples+=1;automated.arms.metric=Number(wristDifference.toFixed(3));
  if(possibleDifference) automated.arms.positive_samples+=1;
  automated.arms.positive=automated.arms.samples>=18&&automated.arms.positive_samples/automated.arms.samples>.48;
  updateAssist("arms",automated.arms.positive?"Camera assistance noticed one arm may be lower or drifting. Treat this as a sign.":"Keep both arms raised while Alira watches for drift.",automated.arms.positive?"warn":"good");
}

function updateAssist(sign,text,state){
  if(current!==sign) return;const el=document.getElementById("assist");if(!el)return;el.className=`assist ${state||''}`;el.querySelector("span:last-child").textContent=text;
}

function normalizeSpeech(text){return String(text||"").toLowerCase().replace(/[^a-z0-9 ]/g," ").replace(/\s+/g," ").trim()}
function editDistance(a,b){const dp=Array.from({length:a.length+1},()=>Array(b.length+1).fill(0));for(let i=0;i<=a.length;i++)dp[i][0]=i;for(let j=0;j<=b.length;j++)dp[0][j]=j;for(let i=1;i<=a.length;i++)for(let j=1;j<=b.length;j++)dp[i][j]=Math.min(dp[i-1][j]+1,dp[i][j-1]+1,dp[i-1][j-1]+(a[i-1]===b[j-1]?0:1));return dp[a.length][b.length]}
function similarity(a,b){a=normalizeSpeech(a);b=normalizeSpeech(b);return Math.max(0,1-editDistance(a,b)/Math.max(a.length,b.length,1))}
function startSpeechCheck(){
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
  const status=document.getElementById("transcript");
  if(!Recognition){status.textContent="Automatic speech assistance is not supported here. Listen to the phrase and choose what you observed below.";return}
  const recognition=new Recognition();recognition.lang="en-GB";recognition.interimResults=false;recognition.maxAlternatives=1;
  status.textContent="Listening... Ask the person to repeat the phrase now.";speak(`Please repeat: ${phrase}.`);
  recognition.onresult=(event)=>{const item=event.results[0][0];const transcript=item.transcript||"";const score=similarity(transcript,phrase);automated.speech={available:true,positive:score<.45&&(item.confidence||0)>.5,transcript,similarity:Number(score.toFixed(3)),confidence:Number((item.confidence||0).toFixed(3))};status.textContent=`Heard: "${transcript}". A carer should still decide whether speech sounded clear.`;if(automated.speech.positive)status.textContent+=" The repeat phrase was very different, so treat this as a possible sign."};
  recognition.onerror=()=>{status.textContent="Speech assistance could not hear clearly. Listen directly and choose below."};
  try{recognition.start()}catch{status.textContent="Speech assistance could not start. Listen directly and choose below."}
}

function renderIntro(){
  current="intro";document.body.classList.add("intro-mode");panel.innerHTML=`<div class="letter">!</div><div class="eyebrow">Alira guided check</div><h1>Think FAST</h1><p>Alira will guide a carer or family member through Face, Arms and Speech, one step at a time. This brief screen is not a diagnosis.</p><div class="important">If any sign is already visible, or symptoms started suddenly, call 911 now. Do not use this check to delay a real emergency call.</div><div class="actions"><button class="primary" data-testid="fast-start" id="begin">Begin guided FAST check</button></div><p class="source">Based on CDC FAST guidance.</p>`;
  document.getElementById("begin").onclick=async()=>{await ensureCamera();renderFace()};
}
function renderFace(){
  current="face";document.body.classList.remove("intro-mode");stepStartedAt=performance.now();automated.face={available:false,positive:false,samples:0,positive_samples:0,metric:null};
  panel.innerHTML=`${progress(0)}<div class="letter">F</div><div class="eyebrow">Face</div><h1>Ask the person to smile</h1><p>Look at both sides of the mouth and both eyes. Has one side drooped, or is the smile uneven?</p><div class="assist" id="assist"><span class="assistDot"></span><span>Position the face clearly in the camera and ask for a smile.</span></div>${answerButtons("face")}`;speak("Face. Please smile. Look for drooping or weakness on one side of the mouth or eye.");
}
function renderArms(){
  current="arms";stepStartedAt=performance.now();automated.arms={available:false,positive:false,samples:0,positive_samples:0,metric:null};
  panel.innerHTML=`${progress(1)}<div class="letter">A</div><div class="eyebrow">Arms</div><h1>Raise both arms and hold</h1><p>Ask the person to lift both arms to a comfortable level and keep them there. Does one arm drift down or fail to lift?</p><div class="assist" id="assist"><span class="assistDot"></span><span>Keep the shoulders and both hands visible while Alira watches for a difference.</span></div>${answerButtons("arms")}`;speak("Arms. Please raise both arms and keep them there. Look for one arm drifting down or failing to lift.");
}
function renderSpeech(){
  current="speech";panel.innerHTML=`${progress(2)}<div class="letter">S</div><div class="eyebrow">Speech</div><h1>Listen to speech and understanding</h1><p>Ask the person to repeat this phrase. Listen for slurred, garbled or muddled speech, and check that they understand the request.</p><div class="phrase">"${phrase}."</div><button class="secondary" id="listen" style="width:100%;margin-bottom:10px">Use speech assistance</button><div class="transcript" id="transcript">A carer should listen directly. Speech recognition is only supporting evidence.</div>${answerButtons("speech")}`;speak(`Speech. Please repeat: ${phrase}.`);document.getElementById("listen").onclick=startSpeechCheck;
}
function answerButtons(sign){return `<div class="actions"><button class="answer" data-answer="no" onclick="chooseAnswer('${sign}','no')"><span>${sign==="speech"?"Speech was clear and understood":"No sign noticed"}</span><strong>No</strong></button><button class="answer danger" data-answer="yes" onclick="chooseAnswer('${sign}','yes')"><span>${sign==="face"?"Droop or uneven smile":sign==="arms"?"One arm drifted or could not lift":"Slurred, muddled or not understood"}</span><strong>Yes</strong></button><button class="answer unsure" data-answer="unsure" onclick="chooseAnswer('${sign}','unsure')"><span>I cannot tell clearly</span><strong>Not sure</strong></button></div>`}
function chooseAnswer(sign,value){answers[sign]=value;if(sign==="face")renderArms();else if(sign==="arms")renderSpeech();else showResult()}

function outcome(){
  const observed=["face","arms","speech"].filter(sign=>answers[sign]==="yes"||automated[sign].positive);
  const uncertain=["face","arms","speech"].filter(sign=>answers[sign]==="unsure");
  return {call_999:observed.length>0||uncertain.length>0,observed_signs:observed,uncertain_signs:uncertain};
}
function showResult(){
  current="result";if(animationId)cancelAnimationFrame(animationId);if(stream)stream.getTracks().forEach(track=>track.stop());
  const result=outcome();document.getElementById("cameraPane").classList.add("hidden");panel.classList.add("hidden");
  const workspace=document.getElementById("workspace");const resultSection=document.createElement("section");resultSection.className="result";
  if(result.call_999){
    resultSection.innerHTML=`<div class="resultInner">${progress(3)}<div class="resultIcon">!</div><div class="eyebrow">T - Time · Red flag</div><h1>Call 911 now</h1><p>A FAST sign was noticed or could not be ruled out. Say that you suspect a stroke. Do not wait to see if it passes.</p><button class="callButton" data-testid="fast-show-demo-911" onclick="startDemo911Call()">Show demo 911 call</button><div class="onset"><label for="onset">When did the symptoms start? (if known)</label><input id="onset" type="datetime-local" /></div><p class="small">Stay with the person. In a real emergency, call 911 for an ambulance rather than driving to the hospital.</p><button class="secondary" style="width:100%;margin-top:12px" onclick="location.reload()">Restart check</button><p class="source">If symptoms fade, urgent medical help is still needed.</p></div>`;
  }else{
    resultSection.innerHTML=`<div class="resultInner clear">${progress(3)}<div class="resultIcon">&#10003;</div><div class="eyebrow" style="color:#1F7047">T - Time · Green check</div><h1>No FAST signs identified</h1><p>This brief screen did not identify a FAST sign. It does not prove the person is fine and cannot rule out a stroke or TIA.</p><div class="important">Call 911 if symptoms were sudden, have faded, there are other stroke symptoms, or you remain concerned.</div><button class="secondary" style="width:100%" onclick="location.reload()">Restart check</button></div>`;
  }
  workspace.appendChild(resultSection);
  const payload={type:"fast_check_result",answers,automated,result:{...result,status:result.call_999?"call_999":"no_fast_signs_identified",demo_call_911:result.call_999,emergency_call_mode:"simulation"},onset_time:""};postRN(payload);reported=true;
  const onset=document.getElementById("onset");if(onset)onset.onchange=()=>postRN({...payload,onset_time:onset.value});
  speak(result.call_999?"Red flag. Call 911 now and say you suspect a stroke.":"No FAST signs were identified. This does not rule out a stroke. Call 911 if you remain concerned.");
  if(result.call_999)setTimeout(startDemo911Call,900);
}

window.startDemo911Call=startDemo911Call;window.postRN=postRN;window.chooseAnswer=chooseAnswer;renderIntro();
</script>
</body>
</html>"""
