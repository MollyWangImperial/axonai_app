#!/usr/bin/env node
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..", "public", "vendor", "mediapipe");
const assets = [
  ["https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs", "vision_bundle.mjs", 100000],
  ["https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/vision_wasm_internal.js", "wasm/vision_wasm_internal.js", 10000],
  ["https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/vision_wasm_internal.wasm", "wasm/vision_wasm_internal.wasm", 1000000],
  ["https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/vision_wasm_nosimd_internal.js", "wasm/vision_wasm_nosimd_internal.js", 10000],
  ["https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/vision_wasm_nosimd_internal.wasm", "wasm/vision_wasm_nosimd_internal.wasm", 1000000],
  ["https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task", "models/pose_landmarker_lite.task", 5000000],
  ["https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task", "models/hand_landmarker.task", 7000000],
  ["https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task", "models/face_landmarker.task", 3000000],
];

async function download(url, relativePath, minimumBytes) {
  const destination = path.join(root, relativePath);
  if (fs.existsSync(destination) && fs.statSync(destination).size >= minimumBytes) return;

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not download ${url}: ${response.status}`);
  const data = Buffer.from(await response.arrayBuffer());
  if (data.length < minimumBytes) throw new Error(`Downloaded asset is unexpectedly small: ${relativePath}`);

  fs.mkdirSync(path.dirname(destination), { recursive: true });
  const temporary = `${destination}.download`;
  fs.writeFileSync(temporary, data);
  fs.renameSync(temporary, destination);
  process.stdout.write(`Bundled ${relativePath} (${data.length} bytes)\n`);
}

Promise.all(assets.map((asset) => download(...asset))).catch((error) => {
  console.error(error);
  process.exit(1);
});
