// Deterministic failure/recovery coverage. verify-camera-setup.cjs separately
// exercises the real MediaPipe model with a supplied image-based video feed.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const fs = require("node:fs");
const path = require("node:path");
const base = process.env.CAMERA_TEST_URL || "http://127.0.0.1:8001";
const out = path.resolve(__dirname, "../../output/playwright/camera-setup");
fs.mkdirSync(out, { recursive: true });
const poseModule = `
export const FilesetResolver = {forVisionTasks: async () => ({})};
export const PoseLandmarker = {createFromOptions: async () => ({
  close() {},
  detectForVideo() {
    window.poseFrames = (window.poseFrames || 0) + 1;
    if (window.poseMode === "absent") return {landmarks: []};
    const points = Array.from({length:33}, () => ({x:.5,y:.5,visibility:.99}));
    for (const i of [0,2,5]) points[i].y = .18;
    for (const [i,x,y] of [[11,.35,.32],[12,.65,.32],[13,.3,.53],[14,.7,.53],
      [15,.28,.75],[16,.72,.75],[17,.28,.78],[18,.72,.78],[19,.28,.78],[20,.72,.78]]) points[i]={x,y,visibility:.99};
    if (window.poseMode === "missing") points[16].visibility = .1;
    if (window.poseMode === "moving") for (const p of points) p.x += window.poseFrames % 2 ? .05 : -.05;
    return {landmarks:[points]};
  }
})};`;

(async () => {
  const browser = await chromium.launch({channel:"msedge",headless:true});
  try {
    for (const [width,height] of [[390,844],[320,667],[1440,1000]]) {
      const context = await browser.newContext({viewport:{width,height}});
      await context.route("**/vendor/mediapipe/vision_bundle.mjs", route => route.fulfill({contentType:"text/javascript",body:poseModule}));
      await context.addInitScript(() => {
        window.poseMode = "missing"; window.testStreams = []; window.setupMessages = [];
        window.ReactNativeWebView = {postMessage:data=>window.setupMessages.push(JSON.parse(data))};
        navigator.mediaDevices.enumerateDevices = async () => ["one","two"].map(deviceId=>({kind:"videoinput",deviceId,label:`Camera ${deviceId}`}));
        navigator.mediaDevices.getUserMedia = async () => {
          const canvas = document.createElement("canvas"); canvas.width = 720; canvas.height = 960;
          const ctx = canvas.getContext("2d"); let tick=0;
          const timer=setInterval(()=>{
            if (window.freezeVideo) return;
            ctx.fillStyle=`rgb(${tick++ % 255},50,60)`; ctx.fillRect(0,0,720,960);
          },100);
          const stream=canvas.captureStream(10); window.testStreams.push(stream);
          for(const track of stream.getTracks()) {
            const stop=track.stop.bind(track); track.stop=()=>{clearInterval(timer);stop();};
          }
          return stream;
        };
      });
      const page=await context.newPage(); const errors=[];
      page.on("pageerror",e=>errors.push(e.message));
      const ready=()=>page.waitForFunction(()=>!document.getElementById("continue").disabled);
      const notReady=()=>page.waitForFunction(()=>document.getElementById("continue").disabled);
      const open=()=>page.getByRole("button",{name:"Open camera check"}).click();
      await page.goto(`${base}/camera-setup/index.html?devices=iphone&purpose=exercise`);
      await open();
      await page.getByText("View is steady",{exact:true}).waitFor();
      assert.equal(await page.locator("#position-text").innerText(),"Head and shoulders in view");
      assert.equal(await page.locator("#continue").isDisabled(),true,"missing hand must block Continue");
      assert.match(await page.locator("#frame-hint").innerText(),/both arms and hands/);
      assert.equal(await page.getByRole("checkbox").count(),0);
      await page.evaluate(()=>{window.poseMode="stable";}); await ready();
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
      await page.screenshot({path:path.join(out,`auto-${width}.png`),fullPage:true});
      await page.evaluate(()=>{window.freezeVideo=true;}); await notReady();
      assert.match(await page.locator("#frame-hint").innerText(),/paused/);
      await page.evaluate(()=>{window.freezeVideo=false;}); await ready();
      await page.locator("#camera-source").selectOption("two");
      assert.equal(await page.locator("#continue").isDisabled(),true,"source change requires new check");
      await ready();
      await page.evaluate(()=>document.getElementById("video").pause()); await notReady();
      await page.evaluate(()=>document.getElementById("video").play()); await ready();
      // Leaving view allows a bounded approach-to-screen grace period, not an unlimited pass.
      await page.evaluate(()=>{window.poseMode="absent";});
      await notReady();
      assert.match(await page.locator("#frame-hint").innerText(),/Face the camera/);
      await page.getByRole("button",{name:"Stop test",exact:true}).click();
      await page.evaluate(()=>{window.poseMode="moving";}); await open();
      await page.getByText("Arms and hands in view",{exact:true}).waitFor();
      assert.equal(await page.locator("#continue").isDisabled(),true,"moving view must not pass");
      assert.equal(await page.locator("#steady-text").innerText(),"Checking view steadiness");
      await page.evaluate(()=>{window.poseMode="stable";}); await ready();
      await page.getByRole("button",{name:"Continue to exercise",exact:true}).click();
      assert.deepEqual(await page.evaluate(()=>window.setupMessages),[{type:"camera_setup_ready"}]);
      assert.equal(await page.evaluate(()=>window.testStreams.every(s=>s.getTracks().every(t=>t.readyState==="ended"))),true);
      assert.deepEqual(errors,[]);
      console.log(`${width}px: automatic checks, missing hand, motion, frozen/paused video, source switch, expiry, recovery, Continue and cleanup passed`);
      await context.close();
    }
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
