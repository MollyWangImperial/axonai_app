const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { VoiceGuide } = require('../reach_voice.js');

test('the prior device voice speaks a Testing instruction without a server audio request', async () => {
  let spoken;
  const synth={getVoices:()=>[{lang:'en-GB',name:'English device voice'}],cancel(){},
    speak(utterance){spoken=utterance;queueMicrotask(()=>utterance.onend());}};
  const Utterance=class {constructor(text){this.text=text;}};
  const guide=new VoiceGuide({synth,Utterance});
  assert.equal(await guide.speak('Rest your hand on your lap.'),true);
  assert.equal(spoken.text,'Rest your hand on your lap.');
  assert.equal(spoken.voice.name,'English device voice');
  assert.equal(guide.status,'Device voice');
});

test('Testing uses signed-in Molly audio and continues with captions if it fails', async () => {
  const source=fs.readFileSync(path.join(__dirname,'..','testing_reach_flow.js'),'utf8');
  assert.match(source,/fetchAudio:fetchReachMollyAudio/);
  assert.match(source,/\/testing\/reach\/voice/);
  assert.match(source,/\.\.\.ACCOUNT_HEADERS/);
  const start=source.indexOf('async function reachSay(text){');
  const end=source.indexOf('\n}',start)+2;
  const calls=[];
  const reachVoice={enabled:true,failed:false,async speak(text){
    calls.push({text,enabled:this.enabled});
    if(this.enabled){this.failed=true;return false;}
    this.failed=false;return true;
  }};
  const checkbox={checked:true};
  const context={reachFlow:{stopped:false,voiceUnavailable:false},reachVoice,
    document:{getElementById:()=>checkbox}};
  assert.equal(await vm.runInNewContext(source.slice(start,end)+'\nreachSay("Reach forward")',context),true);
  assert.deepEqual(calls,[{text:'Reach forward',enabled:true},{text:'Reach forward',enabled:false}]);
  assert.equal(reachVoice.enabled,false);
  assert.equal(context.reachFlow.voiceUnavailable,true);
  assert.equal(checkbox.checked,false);
});

test('testing voice waits for Molly audio to finish', async () => {
  const audio = {
    pause() {},
    play() { return Promise.resolve(); },
  };
  const guide = new VoiceGuide({ fetchAudio: async () => 'SUQz', audio, synth: null });
  const speaking = guide.speak('Reach forward');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(audio.src, 'data:audio/mpeg;base64,SUQz');
  assert.equal(guide.busy, true);
  audio.onended();
  assert.equal(await speaking, true);
  assert.equal(guide.busy, false);
  assert.equal(guide.status, 'Molly voice');
});

test('failed Molly audio leaves the test waiting for retry or captions', async () => {
  const audio = { pause() {}, play() { return Promise.reject(new Error('blocked')); } };
  const guide = new VoiceGuide({ fetchAudio: async () => 'SUQz', audio, synth: null });
  assert.equal(await guide.speak('Reach forward'), false);
  assert.equal(guide.failed, true);
  guide.enabled = false;
  guide.captionMs = 0;
  assert.equal(await guide.speak('Reach forward'), true);
  assert.equal(guide.status, 'Captions only');
});

test('Testing gives the hold instruction before the raised target unlocks', () => {
  const flow=fs.readFileSync(path.join(__dirname,'..','testing_reach_flow.js'),'utf8');
  const start=flow.indexOf('function reachStepVoiceLines(step){');
  const end=flow.indexOf('\n}',start)+2;
  assert.ok(start>=0 && end>start);
  const reach='Reach toward the bright circle.';
  const hold='Hold your hand steadily at the forward target for a moment.';
  const tasks=[{steps:[{id:'T1-S2',voice:reach},{id:'T1-S3',voice:hold}]}];
  const context=vm.createContext({tasks});
  vm.runInContext(flow.slice(start,end),context);
  assert.deepEqual(Array.from(context.reachStepVoiceLines(tasks[0].steps[0])),[reach,hold]);
  assert.deepEqual(Array.from(context.reachStepVoiceLines(tasks[0].steps[1])),[]);

  const server=fs.readFileSync(path.join(__dirname,'..','server.py'),'utf8');
  const runner=server.slice(server.indexOf('async function startStep(){'),server.indexOf('function distance(a,b){'));
  assert.ok(runner.indexOf('for(const line of reachStepVoiceLines(step))await playVoice(line);')
    < runner.indexOf('voiceFinishedAt = performance.now();'));
  assert.match(server,/Reach the target, then keep your hand there\. Do not lower it until asked\./);
});
