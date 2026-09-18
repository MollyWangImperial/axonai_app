const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const base = process.env.CAMERA_TEST_URL || "http://127.0.0.1:8001";
const fixture = process.env.CAMERA_SETUP_FIXTURE;
if (!fixture) throw new Error("Set CAMERA_SETUP_FIXTURE to an upper-body image for a simulated camera. No real camera is used.");
const crop = JSON.parse(process.env.CAMERA_FIXTURE_CROP || "[24,295,806,908]");
const out = path.resolve(__dirname, "../../output/playwright/camera-setup");
fs.mkdirSync(out, { recursive: true });

async function installCamera(context, captureBridge = true, source = { fixture, crop, size: [720,960] }) {
  await context.route("**/__camera_fixture.png", (route) => route.fulfill({ path: source.fixture, contentType: "image/png" }));
  await context.addInitScript(({ captureBridge, crop, size }) => {
    window.testStreams = [];
    window.setupMessages = [];
    if (captureBridge) window.ReactNativeWebView = { postMessage: (data) => window.setupMessages.push(JSON.parse(data)) };
    navigator.mediaDevices.getUserMedia = async () => {
      if (window.denyCamera) throw new DOMException("Permission denied", "NotAllowedError");
      const image = new Image(); image.src = "/__camera_fixture.png"; await image.decode();
      const canvas = document.createElement("canvas"); [canvas.width,canvas.height] = size;
      const ctx = canvas.getContext("2d");
      function draw() { ctx.drawImage(image, ...crop, 0, 0, ...size); }
      draw();
      const timer = setInterval(draw, 100);
      const stream = canvas.captureStream(10);
      window.testStreams.push(stream);
      for (const track of stream.getTracks()) {
        const stop = track.stop.bind(track);
        track.stop = () => { clearInterval(timer); stop(); };
      }
      return stream;
    };
  }, { captureBridge, crop: source.crop, size: source.size });
}

async function noOverflow(page) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, "horizontal overflow");
}

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    for (const [label, width, height, mobile] of (process.env.CAMERA_APP_ONLY ? [] : [["iphone",393,852,true],["small-iphone",375,667,true],["desktop",1440,1000,false]])) {
      const context = await browser.newContext({ viewport: { width, height }, isMobile: mobile, hasTouch: mobile, deviceScaleFactor: 1 });
      await installCamera(context);
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`${base}/camera-setup/index.html?devices=iphone&purpose=assessment`);
      await page.getByRole("heading", { name: "Place your iPhone like this" }).waitFor();
      await page.locator("#illustration img").evaluate((image) => image.decode());
      await noOverflow(page);
      await page.screenshot({ path: path.join(out, `${label}-placement.png`), fullPage: true });
      await page.getByRole("button", { name: "Play setup demonstration" }).click();
      await page.getByRole("dialog").waitFor();
      await page.getByRole("button", { name: "Next step" }).click();
      assert.match(await page.locator("#demo-caption").innerText(), /shoulder height/);
      await page.getByRole("button", { name: "Close demonstration" }).click();
      await page.getByRole("button", { name: "Open camera check" }).click();
      await page.locator("#live").waitFor();
      await page.getByText("All camera checks complete", { exact: true }).waitFor({ timeout: 60000 });
      assert.equal(await page.locator("#continue").isEnabled(), true, "setup should pass automatically");
      assert.equal(await page.getByRole("checkbox").count(),0);
      await page.waitForFunction(() => !document.getElementById("continue").disabled);
      await noOverflow(page);
      await page.screenshot({ path: path.join(out, `${label}-check.png`), fullPage: true });
      await page.getByRole("button", { name: "Stop test", exact: true }).click();
      assert.equal(await page.evaluate(() => window.testStreams.every((s) => s.getTracks().every((t) => t.readyState === "ended"))), true);
      await page.getByRole("button", { name: "Open camera check" }).click();
      assert.equal(await page.locator("#continue").isEnabled(), false, "restart needs new observations");
      await page.getByText("All camera checks complete", { exact: true }).waitFor({ timeout: 60000 });
      await page.getByRole("button", { name: "Continue to assessment", exact: true }).click();
      assert.equal(await page.evaluate(() => window.setupMessages.some((m) => m.type === "camera_setup_ready")), true);
      assert.equal(await page.evaluate(() => window.testStreams.every((s) => s.getTracks().every((t) => t.readyState === "ended"))), true);
      assert.deepEqual(errors, []);
      console.log(`${label}: real MediaPipe model + simulated video passed; stop, restart, ready, no overflow`);
      await context.close();
    }
    const context = await browser.newContext({ viewport: { width: 393, height: 852 } });
    await installCamera(context);
    const page = await context.newPage();
    await page.goto(`${base}/camera-setup/index.html?devices=iphone`);
    await page.evaluate(() => { window.denyCamera = true; });
    await page.getByRole("button", { name: "Open camera check" }).click();
    await page.getByRole("alert").waitFor();
    assert.match(await page.getByRole("alert").innerText(), /Camera access was not allowed/);
    await page.screenshot({path:path.join(out,"iphone-denied.png"),fullPage:true});
    await page.evaluate(() => { window.denyCamera = false; });
    await page.route("**/vendor/mediapipe/vision_bundle.mjs", (route) => route.abort());
    await page.getByRole("button", { name: "Try camera again" }).click();
    await page.getByRole("alert").waitFor();
    assert.equal(await page.locator("#continue").isEnabled(), false);
    assert.equal(await page.evaluate(() => window.testStreams.every((s) => s.getTracks().every((t) => t.readyState === "ended"))), true);
    await page.goto(`${base}/camera-setup/index.html?devices=none`);
    await page.getByRole("heading", { name: "No camera available?" }).waitFor();
    assert.equal(await page.evaluate(() => window.testStreams.length),0);
    console.log("permission denial, model failure, and no-camera path passed");
    await context.close();
    if (process.env.CAMERA_NEGATIVE_FIXTURE) {
      const incomplete = await browser.newContext({viewport:{width:1440,height:1000}});
      await installCamera(incomplete,true,{fixture:process.env.CAMERA_NEGATIVE_FIXTURE,
        crop:JSON.parse(process.env.CAMERA_NEGATIVE_CROP || "[110,146,720,480]"),size:[720,480]});
      const check = await incomplete.newPage();
      await check.goto(`${base}/camera-setup/index.html?devices=laptop`);
      await check.getByRole("button",{name:"Open camera check"}).click();
      await check.getByText("Head and shoulders in view",{exact:true}).waitFor({timeout:45000});
      await check.getByText("View is steady",{exact:true}).waitFor();
      assert.equal(await check.locator("#continue").isDisabled(),true,"real partial-body image must not pass");
      assert.match(await check.locator("#frame-hint").innerText(),/both arms and hands|Keep both hands visible/);
      await check.screenshot({path:path.join(out,"real-model-hands-out-of-frame.png"),fullPage:true});
      await check.getByRole("button",{name:"Stop test",exact:true}).click();
      await incomplete.close();
      console.log("real MediaPipe model: supplied partial-body screenshot correctly requires arms and hands in view");
    }
    const appContext = await browser.newContext({viewport:{width:393,height:852}});
    await installCamera(appContext, false);
    const user = {id:"camera-local-test",name:"Test",email:"camera-test@example.invalid",role:"patient",trial_access_granted:true,consent_accepted:true,onboarding_complete:true,account_generation:0,profile:{camera_devices:["iphone"]}};
    await appContext.addInitScript((user) => {
      localStorage.setItem("active_user_id_v2",JSON.stringify(user.id));
      localStorage.setItem("active_user_obj_v2",JSON.stringify(JSON.stringify(user)));
      localStorage.setItem(`patient_profile_v2:${user.id}`,JSON.stringify(JSON.stringify(user.profile)));
      localStorage.setItem(`legal_consent_v2:1.0:${user.id}`,JSON.stringify("1"));
      localStorage.setItem(`onboarding_complete_v2:${user.id}`,JSON.stringify("1"));
    }, user);
    await appContext.route("**/api/**", (route) => {
      const url = route.request().url();
      if (url.includes("/runner")) return route.fulfill({contentType:"text/html",body:"<!doctype html><html><body><h1>Session runner reached</h1></body></html>"});
      return route.fulfill({json:url.includes("/users/me") ? user : {ok:true,accepted:true,profile:user.profile,onboarding_complete:true}});
    });
    const app = await appContext.newPage();
    app.on("pageerror",error=>console.error("App browser error:",error.message));
    for (const [route,runner,marker] of [
      ["/assessment?package=initial&start_task=T3&task_ids=T1%2CT3&affected_side=left","/api/pose/runner","start_task=T3"],
      ["/exercise?exercise_id=ex_reach&reps=7&difficulty=easy&affected_side=left","/api/rehab/runner","exercise_id=ex_reach"],
    ]) {
      await app.goto(base+route);
      await app.waitForLoadState("networkidle");
      const setup=app.frameLocator('iframe[src*="/camera-setup/"]');
      try { await setup.getByRole("button",{name:"Open camera check"}).click(); }
      catch (error) {
        console.error("App setup state:",app.url(),await app.locator("body").innerText(),await app.locator("iframe").evaluateAll((frames)=>frames.map((frame)=>frame.src)));
        await app.screenshot({path:path.join(out,"app-error.png"),fullPage:true});
        throw error;
      }
      try { await setup.getByText("All camera checks complete",{exact:true}).waitFor({timeout:45000}); }
      catch (error) {
        for (const frame of app.frames()) console.error("Frame at failure:",frame.url(),await frame.locator("body").innerText().catch(()=>"unavailable"));
        await app.screenshot({path:path.join(out,"app-error.png"),fullPage:true});
        throw error;
      }
      await setup.getByRole("button",{name:/Continue to (assessment|exercise)/}).click();
      const frame=app.locator(`iframe[src*="${runner}"]`);
      try { await frame.waitFor({timeout:20000}); }
      catch(error) {
        console.error("After setup:", app.url(), await app.locator("body").innerText(), await app.locator("iframe").evaluateAll(frames=>frames.map(frame=>frame.src)));
        await app.screenshot({path:path.join(out,"app-error.png"),fullPage:true});
        throw error;
      }
      const src=await frame.getAttribute("src");
      assert.ok(src.includes(marker),src);
      assert.ok(src.includes("affected_side=left"),src);
      if (route.startsWith("/assessment")) assert.ok(src.includes("task_ids=T1%2CT3"),src);
      await app.reload();
      await app.frameLocator('iframe[src*="/camera-setup/"]').getByRole("button",{name:"Open camera check"}).waitFor();
      assert.equal(await app.locator(`iframe[src*="${runner}"]`).count(),0,"re-entry must start with setup");
      console.log(`${runner}: full Expo route, setup bridge, preserved task params and re-entry passed`);
    }
    await app.goto(base+"/onboarding");
    await app.getByTestId("onb-input-preferred_name").fill("Camera test");
    await app.getByTestId("onb-continue").click();
    await app.getByTestId("onb-q-camera_devices").waitFor();
    const iphoneChoice=app.getByTestId("onb-multi-camera_devices-iphone");
    const laptopChoice=app.getByTestId("onb-multi-camera_devices-laptop");
    const noCamera=app.getByTestId("onb-multi-camera_devices-none");
    await iphoneChoice.click(); await laptopChoice.click();
    assert.equal(await iphoneChoice.getAttribute("aria-checked"),"true");
    assert.equal(await laptopChoice.getAttribute("aria-checked"),"true");
    await noCamera.click();
    assert.equal(await iphoneChoice.getAttribute("aria-checked"),"false");
    assert.equal(await laptopChoice.getAttribute("aria-checked"),"false");
    assert.equal(await noCamera.getAttribute("aria-checked"),"true");
    await iphoneChoice.click();
    assert.equal(await noCamera.getAttribute("aria-checked"),"false");
    await app.screenshot({path:path.join(out,"iphone-device-survey.png"),fullPage:true});
    console.log("registration device multi-select and exclusive no-camera option passed");
    await appContext.close();
  } finally { await browser.close(); }
})().catch((error) => { console.error(error); process.exitCode = 1; });
