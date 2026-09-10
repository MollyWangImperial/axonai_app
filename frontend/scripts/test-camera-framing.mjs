import assert from "node:assert/strict";
import { checkFraming, createFramingTracker, project } from "../public/camera-setup/framing.mjs";

const body = Array.from({ length: 33 }, () => ({ x: .5, y: .5, visibility: .99 }));
for (const i of [0, 2, 5]) body[i] = { x: .5, y: .18, visibility: .99 };
for (const [i, x, y] of [[11,.35,.32],[12,.65,.32],[13,.3,.53],[14,.7,.53],[15,.28,.75],[16,.72,.75],[17,.28,.78],[18,.72,.78],[19,.28,.78],[20,.72,.78]]) body[i] = {x,y,visibility:.99};
const desktop = [720,960,560,700,"contain"];
const mobile = [720,960,361,481,"cover"];
assert.equal(checkFraming(body, desktop).ready, true);
assert.equal(checkFraming(body, mobile).ready, true);
assert.equal(checkFraming([], desktop).ready, false);
for (const indices of [[0], [11], [13], [16], [17,19]]) {
  const missing = structuredClone(body);
  for (const i of indices) missing[i].visibility = .1;
  assert.equal(checkFraming(missing, mobile).ready, false, `missing ${indices}`);
}
// A landmark can be inside the source image but cropped out of a portrait preview.
const landscape = [1280,720,361,481,"cover"];
const cutOff = structuredClone(body);
cutOff[15].x = .05;
assert.equal(checkFraming(cutOff, landscape).ready, false);
assert.deepEqual(project({x:.5,y:.5},720,960,360,480,"cover"), {x:180,y:240});
assert.equal(project({x:.2,y:.5},720,960,360,480,"cover").x,288);
const tracker = createFramingTracker();
for (let t=0;t<1200;t+=100) assert.equal(tracker.update(true,t),false);
assert.equal(tracker.update(true,1200),true);
assert.equal(tracker.update(false,1300),false);
assert.equal(tracker.update(true,1400),false);
assert.equal(tracker.update(true,3000),false, "a long camera gap resets the stable interval");
tracker.reset();
assert.equal(tracker.update(true,3100),false);
console.log("Camera framing: desktop, iPhone crop, missing body parts, mirroring and stable-frame checks passed.");
