import {PoseLandmarker, FilesetResolver} from "/vendor/mediapipe/vision_bundle.mjs";

const metrics = window.TrunkLeanMetrics;
const video = document.getElementById("sourceVideo");
const newCanvas = document.getElementById("newCanvas");
const oldCanvas = document.getElementById("oldCanvas");
const sharedFrameCanvas = document.createElement("canvas");
const cameraButton = document.getElementById("cameraButton");
const startButton = document.getElementById("startButton");
const recalibrateButton = document.getElementById("recalibrateButton");
const instructionTitle = document.getElementById("instructionTitle");
const instructionText = document.getElementById("instructionText");
const calibrationFill = document.getElementById("calibrationFill");
const CALIBRATION_SAMPLES = 45;
const THRESHOLD = 12;

let landmarker = null;
let stream = null;
let animationFrame = 0;
let lastVideoTime = -1;
let calibrationSamples = [];
let baseline = null;
let comparing = false;
let newTemporal = metrics.createTemporalState();
let oldTemporal = metrics.createTemporalState();
let latestLandmarks = null;
let latestNewEvidence = {detected: false};
let latestOldDegrees = NaN;

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function formatDegrees(value) {
  return Number.isFinite(value) ? `${value.toFixed(1)}°` : "--°";
}

function formatPercent(value) {
  return Number.isFinite(value) ? `${Math.round(value * 100)}%` : "--";
}

function setState(elementId, temporal, degrees) {
  const element = document.getElementById(elementId);
  element.className = "state";
  if (temporal.confirmed) {
    element.textContent = "Trunk lean detected";
    element.classList.add("detected");
  } else if (Number.isFinite(degrees) && degrees > THRESHOLD) {
    element.textContent = "Lean signal";
    element.classList.add("signal");
  } else {
    element.textContent = comparing ? "Within current threshold" : "Ready";
  }
}

function sizeCanvases() {
  const width = video.videoWidth || 1280;
  const height = video.videoHeight || 720;
  for (const canvas of [newCanvas, oldCanvas]) {
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
  }
  if (sharedFrameCanvas.width !== width || sharedFrameCanvas.height !== height) {
    sharedFrameCanvas.width = width;
    sharedFrameCanvas.height = height;
  }
}

function captureSharedFrame() {
  const context = sharedFrameCanvas.getContext("2d");
  context.clearRect(0, 0, sharedFrameCanvas.width, sharedFrameCanvas.height);
  context.drawImage(video, 0, 0, sharedFrameCanvas.width, sharedFrameCanvas.height);
}

function drawSharedFrame(canvas, landmarks, accent, detected) {
  const context = canvas.getContext("2d");
  context.save();
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(sharedFrameCanvas, 0, 0, canvas.width, canvas.height);
  if (landmarks) {
    const point = index => ({x: landmarks[index].x * canvas.width, y: landmarks[index].y * canvas.height});
    const nose = point(0);
    const leftShoulder = point(11);
    const rightShoulder = point(12);
    const leftHip = point(23);
    const rightHip = point(24);
    const shoulderMid = {x: (leftShoulder.x + rightShoulder.x) / 2, y: (leftShoulder.y + rightShoulder.y) / 2};
    const hipMid = {x: (leftHip.x + rightHip.x) / 2, y: (leftHip.y + rightHip.y) / 2};
    context.lineWidth = Math.max(3, canvas.width / 260);
    context.strokeStyle = detected ? "#ef4f4f" : accent;
    context.fillStyle = detected ? "#ef4f4f" : accent;
    context.beginPath();
    context.moveTo(leftShoulder.x, leftShoulder.y);
    context.lineTo(rightShoulder.x, rightShoulder.y);
    context.lineTo(rightHip.x, rightHip.y);
    context.lineTo(leftHip.x, leftHip.y);
    context.closePath();
    context.stroke();
    context.beginPath();
    context.moveTo(nose.x, nose.y);
    context.lineTo(shoulderMid.x, shoulderMid.y);
    context.lineTo(hipMid.x, hipMid.y);
    context.stroke();
    for (const item of [nose, leftShoulder, rightShoulder, leftHip, rightHip]) {
      context.beginPath();
      context.arc(item.x, item.y, Math.max(6, canvas.width / 150), 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = "#fff";
      context.lineWidth = Math.max(2, canvas.width / 500);
      context.stroke();
    }
  }
  context.restore();
}

function resetComparison() {
  newTemporal = metrics.createTemporalState();
  oldTemporal = metrics.createTemporalState();
  latestNewEvidence = {detected: false};
  latestOldDegrees = NaN;
  setText("oldFrames", "0 / 0");
  setText("oldRatio", "0%");
}

function beginCalibration() {
  comparing = false;
  baseline = null;
  calibrationSamples = [];
  resetComparison();
  startButton.disabled = true;
  recalibrateButton.disabled = false;
  calibrationFill.style.width = "0%";
  instructionTitle.textContent = "Sit upright and hold still for calibration.";
  instructionText.textContent = "Keep your nose, both shoulders and both hips visible. The same baseline will be used by both detectors.";
}

function startComparison() {
  if (!baseline) return;
  comparing = true;
  resetComparison();
  startButton.textContent = "Restart both";
  instructionTitle.textContent = "Perform the seated forward reach now.";
  instructionText.textContent = "Both algorithms started together and are reading the exact same pose frames.";
}

function updateCalibration(frameMetrics) {
  if (!frameMetrics.valid) {
    calibrationSamples = [];
    calibrationFill.style.width = "0%";
    instructionText.textContent = frameMetrics.reason;
    return;
  }
  calibrationSamples.push(frameMetrics);
  if (calibrationSamples.length > CALIBRATION_SAMPLES) calibrationSamples.shift();
  calibrationFill.style.width = `${Math.min(100, calibrationSamples.length / CALIBRATION_SAMPLES * 100)}%`;
  instructionText.textContent = `Hold upright: ${calibrationSamples.length} of ${CALIBRATION_SAMPLES} clear frames.`;
  if (calibrationSamples.length === CALIBRATION_SAMPLES) {
    baseline = metrics.baselineFromSamples(calibrationSamples);
    startButton.disabled = false;
    instructionTitle.textContent = "Baseline ready.";
    instructionText.textContent = "Press Start both, then complete one seated forward reach.";
    setText("newReason", "Ready to compare from the shared upright baseline.");
    setText("oldReason", "Ready to compare from the shared upright baseline.");
  }
}

function updateReadouts(frameMetrics) {
  const newEvidence = metrics.newForwardLeanEvidence(frameMetrics, baseline);
  const oldDegrees = metrics.legacyForwardLeanDegrees(frameMetrics, baseline);
  metrics.updateTemporalState(newTemporal, newEvidence.degrees);
  metrics.updateTemporalState(oldTemporal, oldDegrees);

  setText("newDegrees", formatDegrees(newEvidence.degrees));
  setText("oldDegrees", formatDegrees(oldDegrees));
  setState("newState", newTemporal, newEvidence.degrees);
  setState("oldState", oldTemporal, oldDegrees);
  setText("newScale", formatDegrees(newEvidence.cues.pelvisNormalizedShoulderScale));
  setText("newShortening", formatDegrees(newEvidence.cues.pelvisNormalizedTorsoShortening));
  setText("newDepth", formatDegrees(newEvidence.cues.relativePoseDepth));
  setText("newCoherence", newEvidence.coherence === null ? "Not measurable" : formatPercent(newEvidence.coherence));
  setText("newReason", newEvidence.supportReason);
  setText("oldFrames", `${oldTemporal.aboveFrames} / ${oldTemporal.trackedFrames}`);
  setText("oldRatio", formatPercent(oldTemporal.ratio));
  setText("oldReason", oldTemporal.confirmed
    ? "The current production confirmation rule was met."
    : "Waiting for the production 8-frame and 35% confirmation rule.");
  return {newEvidence, oldDegrees};
}

async function createLandmarker() {
  instructionTitle.textContent = "Loading pose tracking...";
  const resolver = await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
  return PoseLandmarker.createFromOptions(resolver, {
    baseOptions: {modelAssetPath: "/vendor/mediapipe/models/pose_landmarker_lite.task"},
    runningMode: "VIDEO",
    numPoses: 1,
    minPoseDetectionConfidence: 0.5,
    minPosePresenceConfidence: 0.5,
    minTrackingConfidence: 0.5,
  });
}

async function startCamera() {
  cameraButton.disabled = true;
  try {
    if (!metrics) throw new Error("The comparison metrics could not be loaded.");
    if (!landmarker) landmarker = await createLandmarker();
    stream = await navigator.mediaDevices.getUserMedia({
      video: {facingMode: "user", width: {ideal: 1280}, height: {ideal: 720}},
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    sizeCanvases();
    cameraButton.textContent = "Camera running";
    recalibrateButton.disabled = false;
    beginCalibration();
    animationFrame = requestAnimationFrame(processFrame);
  } catch (error) {
    cameraButton.disabled = false;
    instructionTitle.textContent = "The camera could not start.";
    instructionText.textContent = error && error.message ? error.message : "Check camera permission and try again.";
  }
}

function processFrame(now) {
  if (!stream || video.readyState < 2) {
    animationFrame = requestAnimationFrame(processFrame);
    return;
  }
  sizeCanvases();
  captureSharedFrame();
  if (video.currentTime !== lastVideoTime) {
    lastVideoTime = video.currentTime;
    const result = landmarker.detectForVideo(video, now);
    latestLandmarks = result.landmarks && result.landmarks[0] ? result.landmarks[0] : null;
    const frameMetrics = metrics.metricsFromLandmarks(latestLandmarks, video.videoWidth / Math.max(1, video.videoHeight));
    if (!baseline) updateCalibration(frameMetrics);
    else if (comparing && frameMetrics.valid) {
      const states = updateReadouts(frameMetrics);
      latestNewEvidence = states.newEvidence;
      latestOldDegrees = states.oldDegrees;
    }
  }
  drawSharedFrame(newCanvas, latestLandmarks, "#35d49a", Boolean(latestNewEvidence && latestNewEvidence.detected));
  drawSharedFrame(oldCanvas, latestLandmarks, "#f4aa54", Number.isFinite(latestOldDegrees) && latestOldDegrees > THRESHOLD);
  animationFrame = requestAnimationFrame(processFrame);
}

cameraButton.addEventListener("click", startCamera);
startButton.addEventListener("click", startComparison);
recalibrateButton.addEventListener("click", beginCalibration);
window.addEventListener("beforeunload", () => {
  cancelAnimationFrame(animationFrame);
  if (stream) stream.getTracks().forEach(track => track.stop());
  if (landmarker && typeof landmarker.close === "function") landmarker.close();
});
