const assert = require("assert");
const fs = require("fs");
const path = require("path");

const serverPath = path.join(__dirname, "..", "..", "backend", "server.py");
const source = fs.readFileSync(serverPath, "utf8");
const runnerStart = source.indexOf('POSE_RUNNER_HTML = r"""');
const runnerEnd = source.indexOf('"""', runnerStart + 'POSE_RUNNER_HTML = r"""'.length);
assert(runnerStart >= 0 && runnerEnd > runnerStart, "pose runner HTML was not found");
const runner = source.slice(runnerStart, runnerEnd);
const scriptStart = runner.indexOf('<script type="module">');
const scriptEnd = runner.lastIndexOf("</script>");
assert(scriptStart >= 0 && scriptEnd > scriptStart, "pose runner module script was not found");

const script = runner
  .slice(scriptStart + '<script type="module">'.length, scriptEnd)
  .replace(/^import .*;\s*$/m, "");
new Function(script);

assert(script.includes('analysis_method:"mediapipe_browser_body_centric_2d_v1"'));
assert(script.includes('camera_motion_handling:"body_centric_2d_browser"'));
assert(script.includes('source_video_id:String(cloudRecord.id)'));
assert(script.includes("bodyNormalizedWalkingPose2D"));
assert(script.includes("walkingPeaks"));
assert(!script.includes('pose_world_3d:compactLandmarks(frame.world)'));

console.log("Walking gait 2D checks passed: browser syntax, body normalization, step events, and video binding.");
