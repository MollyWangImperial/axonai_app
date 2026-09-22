(function attachTrunkLeanMetrics(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.TrunkLeanMetrics = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildTrunkLeanMetrics() {
  "use strict";

  const LANDMARK = Object.freeze({
    nose: 0,
    leftEar: 7,
    rightEar: 8,
    leftShoulder: 11,
    rightShoulder: 12,
    leftHip: 23,
    rightHip: 24,
  });
  const NUMERIC_BASELINE_FIELDS = Object.freeze([
    "shoulder_width",
    "shoulder_line_delta",
    "ear_width",
    "trunk_depth_tilt",
    "torso_length",
    "shoulder_width_corrected",
    "hip_width_corrected",
    "torso_length_corrected",
    "torso_area_corrected",
  ]);

  function clamp(value, low, high) {
    return Math.min(high, Math.max(low, value));
  }

  function radToDeg(value) {
    return value * 180 / Math.PI;
  }

  function median(values) {
    const sorted = values.filter(Number.isFinite).slice().sort((a, b) => a - b);
    if (!sorted.length) return NaN;
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function pointUsable(point, minimumVisibility) {
    if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) return false;
    const threshold = Number.isFinite(minimumVisibility) ? minimumVisibility : 0.45;
    const confidence = Number.isFinite(point.visibility)
      ? point.visibility
      : (Number.isFinite(point.presence) ? point.presence : 1);
    return confidence >= threshold;
  }

  function midpoint(first, second) {
    return {
      x: (first.x + second.x) / 2,
      y: (first.y + second.y) / 2,
      z: ((Number(first.z) || 0) + (Number(second.z) || 0)) / 2,
    };
  }

  function distance2d(first, second, aspect) {
    const xScale = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
    return Math.hypot((first.x - second.x) * xScale, first.y - second.y);
  }

  function polygonArea(points, aspect) {
    const xScale = Number.isFinite(aspect) && aspect > 0 ? aspect : 1;
    let twiceArea = 0;
    for (let index = 0; index < points.length; index += 1) {
      const current = points[index];
      const next = points[(index + 1) % points.length];
      twiceArea += current.x * xScale * next.y - next.x * xScale * current.y;
    }
    return Math.abs(twiceArea) / 2;
  }

  function clonePoint(point) {
    return {x: point.x, y: point.y, z: Number(point.z) || 0};
  }

  function metricsFromLandmarks(landmarks, aspect) {
    if (!Array.isArray(landmarks)) return {valid: false, reason: "No pose was detected."};
    const core = {
      nose: landmarks[LANDMARK.nose],
      leftShoulder: landmarks[LANDMARK.leftShoulder],
      rightShoulder: landmarks[LANDMARK.rightShoulder],
      leftHip: landmarks[LANDMARK.leftHip],
      rightHip: landmarks[LANDMARK.rightHip],
    };
    const torsoPoints = [core.leftShoulder, core.rightShoulder, core.leftHip, core.rightHip];
    if (!torsoPoints.every(point => pointUsable(point))) {
      return {valid: false, reason: "Keep both shoulders and both hips in view."};
    }

    const midShoulder = midpoint(core.leftShoulder, core.rightShoulder);
    const midHip = midpoint(core.leftHip, core.rightHip);
    const shoulderWidth = Math.max(
      0.03,
      Math.hypot(core.leftShoulder.x - core.rightShoulder.x, core.leftShoulder.y - core.rightShoulder.y),
    );
    const torsoLength = Math.max(0.04, Math.hypot(midShoulder.x - midHip.x, midShoulder.y - midHip.y));
    const correctedShoulderWidth = Math.max(0.03, distance2d(core.leftShoulder, core.rightShoulder, aspect));
    const correctedHipWidth = Math.max(0.03, distance2d(core.leftHip, core.rightHip, aspect));
    const correctedTorsoLength = Math.max(0.04, distance2d(midShoulder, midHip, aspect));
    const earLeft = landmarks[LANDMARK.leftEar];
    const earRight = landmarks[LANDMARK.rightEar];
    const earWidth = pointUsable(earLeft) && pointUsable(earRight)
      ? Math.max(0.01, Math.hypot(earLeft.x - earRight.x, earLeft.y - earRight.y))
      : NaN;
    const depthDifference = (Number(midHip.z) || 0) - (Number(midShoulder.z) || 0);
    const confidences = torsoPoints.concat(pointUsable(core.nose) ? [core.nose] : []).map(point => (
      Number.isFinite(point.visibility) ? point.visibility : (Number.isFinite(point.presence) ? point.presence : 1)
    ));

    return {
      valid: true,
      quality: Math.min(...confidences),
      trunk_projection_visible: true,
      shoulder_width: shoulderWidth,
      shoulder_line_delta: core.rightShoulder.y - core.leftShoulder.y,
      ear_width: earWidth,
      torso_length: torsoLength,
      trunk_depth_tilt: radToDeg(Math.asin(clamp(depthDifference / Math.max(0.05, torsoLength), -1, 1))),
      shoulder_width_corrected: correctedShoulderWidth,
      hip_width_corrected: correctedHipWidth,
      torso_length_corrected: correctedTorsoLength,
      torso_area_corrected: polygonArea(
        [core.leftShoulder, core.rightShoulder, core.rightHip, core.leftHip],
        aspect,
      ),
      points: {
        nose: pointUsable(core.nose) ? clonePoint(core.nose) : null,
        leftShoulder: clonePoint(core.leftShoulder),
        rightShoulder: clonePoint(core.rightShoulder),
        leftHip: clonePoint(core.leftHip),
        rightHip: clonePoint(core.rightHip),
        midShoulder: clonePoint(midShoulder),
        midHip: clonePoint(midHip),
      },
      aspect: Number.isFinite(aspect) && aspect > 0 ? aspect : 1,
    };
  }

  function baselineFromSamples(samples) {
    const validSamples = (samples || []).filter(sample => sample && sample.valid);
    if (!validSamples.length) return null;
    const baseline = {valid: true, trunk_projection_visible: true};
    for (const field of NUMERIC_BASELINE_FIELDS) {
      baseline[field] = median(validSamples.map(sample => Number(sample[field])));
    }
    const pointNames = ["nose", "leftShoulder", "rightShoulder", "leftHip", "rightHip", "midShoulder", "midHip"];
    baseline.points = {};
    for (const name of pointNames) {
      const points = validSamples.map(sample => sample.points && sample.points[name]).filter(Boolean);
      baseline.points[name] = points.length ? {
        x: median(points.map(point => point.x)),
        y: median(points.map(point => point.y)),
        z: median(points.map(point => Number(point.z) || 0)),
      } : null;
    }
    baseline.aspect = median(validSamples.map(sample => Number(sample.aspect)));
    return baseline;
  }

  function horizontalShoulderSpan(metrics) {
    const width = Number(metrics && metrics.shoulder_width);
    const rise = Number(metrics && metrics.shoulder_line_delta);
    return Number.isFinite(width) && Number.isFinite(rise) && width > Math.abs(rise)
      ? Math.sqrt(width * width - rise * rise)
      : NaN;
  }

  // This is the current Graded Forward Reach calculation copied without
  // modification so the right-hand panel remains a faithful benchmark.
  function legacyForwardLeanDegrees(raw, baseline) {
    if (!raw || !baseline || raw.trunk_projection_visible === false) return NaN;
    const width0 = horizontalShoulderSpan(baseline);
    const width = horizontalShoulderSpan(raw);
    if (!Number.isFinite(width0) || !Number.isFinite(width) || width0 < 0.03 || width < 0.03) return NaN;
    const evidence = [];
    const ear0 = Number(baseline.ear_width);
    const ear = Number(raw.ear_width);
    if (Number.isFinite(ear0) && Number.isFinite(ear) && ear0 > 0.01 && ear > 0.01) {
      const shoulderApproach = radToDeg(Math.asin(clamp(2 * (1 - width0 / width), 0, 1)));
      const faceApproach = radToDeg(Math.asin(clamp(1.5 * (1 - ear0 / ear), 0, 1)));
      evidence.push(Math.min(shoulderApproach, faceApproach));
    }
    const depth0 = Number(baseline.trunk_depth_tilt);
    const depth = Number(raw.trunk_depth_tilt);
    const torso0 = Number(baseline.torso_length);
    const torso = Number(raw.torso_length);
    if (Number.isFinite(depth0) && Number.isFinite(depth) && torso0 > 0 && torso > 0) {
      const shortening = radToDeg(Math.acos(clamp((torso / width) / (torso0 / width0), 0, 1)));
      evidence.push(Math.min(Math.max(0, depth - depth0), shortening));
    }
    return evidence.length ? Math.max(...evidence) : NaN;
  }

  function relativeVector(point, hip, aspect) {
    if (!point || !hip) return null;
    return {x: (point.x - hip.x) * aspect, y: point.y - hip.y};
  }

  function vectorDelta(current, baseline) {
    if (!current || !baseline) return null;
    return {x: current.x - baseline.x, y: current.y - baseline.y};
  }

  function vectorLength(vector) {
    return vector ? Math.hypot(vector.x, vector.y) : 0;
  }

  function directionAgreement(first, second, minimumLength) {
    const firstLength = vectorLength(first);
    const secondLength = vectorLength(second);
    if (firstLength < minimumLength || secondLength < minimumLength) return null;
    return clamp((first.x * second.x + first.y * second.y) / (firstLength * secondLength), 0, 1);
  }

  function bilateralVerticalAgreement(raw, baseline, minimumMovement) {
    const rawPoints = raw.points || {};
    const basePoints = baseline.points || {};
    if (![rawPoints.leftShoulder, rawPoints.rightShoulder, rawPoints.leftHip, rawPoints.rightHip,
      basePoints.leftShoulder, basePoints.rightShoulder, basePoints.leftHip, basePoints.rightHip].every(Boolean)) return null;
    const leftDelta = (rawPoints.leftShoulder.y - rawPoints.leftHip.y)
      - (basePoints.leftShoulder.y - basePoints.leftHip.y);
    const rightDelta = (rawPoints.rightShoulder.y - rawPoints.rightHip.y)
      - (basePoints.rightShoulder.y - basePoints.rightHip.y);
    if (Math.abs(leftDelta) < minimumMovement && Math.abs(rightDelta) < minimumMovement) return null;
    if (leftDelta * rightDelta < 0) return 0;
    return clamp(1 - Math.abs(Math.abs(leftDelta) - Math.abs(rightDelta))
      / Math.max(0.0001, Math.abs(leftDelta) + Math.abs(rightDelta)), 0, 1);
  }

  function approachAngle(scale, distanceFactor) {
    if (!Number.isFinite(scale) || scale <= 0) return NaN;
    return radToDeg(Math.asin(clamp(distanceFactor * (1 - 1 / scale), 0, 1)));
  }

  function newForwardLeanEvidence(raw, baseline) {
    if (!raw || !baseline || !raw.valid || !baseline.valid) {
      return {degrees: NaN, detected: false, supported: false, reason: "A calibrated torso pose is required."};
    }
    const width0 = Number(baseline.shoulder_width_corrected);
    const width = Number(raw.shoulder_width_corrected);
    const hip0 = Number(baseline.hip_width_corrected);
    const hip = Number(raw.hip_width_corrected);
    const torso0 = Number(baseline.torso_length_corrected);
    const torso = Number(raw.torso_length_corrected);
    const pelvisScale = hip0 > 0 && hip > 0 ? hip / hip0 : NaN;
    const upperScale = width0 > 0 && width > 0 && Number.isFinite(pelvisScale) && pelvisScale > 0
      ? (width / width0) / pelvisScale
      : NaN;
    const face0 = Number(baseline.ear_width);
    const face = Number(raw.ear_width);
    const faceScale = face0 > 0 && face > 0 && Number.isFinite(pelvisScale) && pelvisScale > 0
      ? (face / face0) / pelvisScale
      : NaN;
    const normalizedTorsoRatio = torso0 > 0 && torso > 0 && hip0 > 0 && hip > 0
      ? (torso / hip) / (torso0 / hip0)
      : NaN;
    const depth0 = Number(baseline.trunk_depth_tilt);
    const depth = Number(raw.trunk_depth_tilt);
    const cues = {
      pelvisNormalizedShoulderScale: approachAngle(upperScale, 2),
      pelvisNormalizedFaceScale: approachAngle(faceScale, 1.5),
      pelvisNormalizedTorsoShortening: Number.isFinite(normalizedTorsoRatio)
        ? radToDeg(Math.acos(clamp(normalizedTorsoRatio, 0, 1)))
        : NaN,
      relativePoseDepth: Number.isFinite(depth0) && Number.isFinite(depth) ? Math.max(0, depth - depth0) : NaN,
    };

    const aspect = Number.isFinite(raw.aspect) ? raw.aspect : (Number.isFinite(baseline.aspect) ? baseline.aspect : 1);
    const rawPoints = raw.points || {};
    const basePoints = baseline.points || {};
    const rawShoulder = relativeVector(rawPoints.midShoulder, rawPoints.midHip, aspect);
    const baseShoulder = relativeVector(basePoints.midShoulder, basePoints.midHip, aspect);
    const rawNose = relativeVector(rawPoints.nose, rawPoints.midHip, aspect);
    const baseNose = relativeVector(basePoints.nose, basePoints.midHip, aspect);
    const shoulderDelta = vectorDelta(rawShoulder, baseShoulder);
    const noseDelta = vectorDelta(rawNose, baseNose);
    const minimumCoherentMovement = Math.max(0.004, torso0 * 0.025);
    const headShoulderCoherence = directionAgreement(shoulderDelta, noseDelta, minimumCoherentMovement);
    const bilateralShoulderCoherence = bilateralVerticalAgreement(raw, baseline, minimumCoherentMovement * 0.5);
    const coherenceValues = [headShoulderCoherence, bilateralShoulderCoherence].filter(Number.isFinite);
    const coherence = coherenceValues.length
      ? coherenceValues.reduce((sum, value) => sum + value, 0) / coherenceValues.length
      : null;

    // Four degrees is the existing runner's pose-jitter floor. The new
    // detector requires two independent geometric cues, then uses the weaker
    // one as the conservative estimate instead of allowing one cue to decide.
    const cueFloor = 4;
    const eligible = Object.values(cues).filter(value => Number.isFinite(value) && value >= cueFloor).sort((a, b) => b - a);
    const visualPair = cues.pelvisNormalizedShoulderScale >= cueFloor
      && cues.pelvisNormalizedFaceScale >= cueFloor;
    const torsoPair = cues.relativePoseDepth >= cueFloor
      && cues.pelvisNormalizedTorsoShortening >= cueFloor;
    const coherentMixedPair = eligible.length >= 2 && Number.isFinite(coherence) && coherence >= 0.5;
    const supported = eligible.length >= 2 && (visualPair || torsoPair || coherentMixedPair);
    const degrees = supported ? eligible[1] : 0;
    let supportReason = "Waiting for two agreeing trunk cues.";
    if (visualPair) supportReason = "Shoulder and face scale changed relative to the pelvis.";
    else if (torsoPair) supportReason = "Pose depth and pelvis-normalized torso shortening agree.";
    else if (coherentMixedPair) supportReason = "Head and both shoulders moved coherently relative to the pelvis.";

    return {
      degrees,
      detected: Number.isFinite(degrees) && degrees > 12,
      supported,
      supportReason,
      cues,
      coherence,
      headShoulderCoherence,
      bilateralShoulderCoherence,
      pelvisScale,
      upperScale,
      normalizedTorsoRatio,
      shoulderDeltaMagnitude: vectorLength(shoulderDelta) / Math.max(0.04, torso0),
      noseDeltaMagnitude: vectorLength(noseDelta) / Math.max(0.04, torso0),
    };
  }

  function createTemporalState() {
    return {trackedFrames: 0, aboveFrames: 0, consecutiveFrames: 0, confirmed: false, ratio: 0};
  }

  function updateTemporalState(state, degrees, options) {
    const target = state || createTemporalState();
    const config = Object.assign({threshold: 12, minFrames: 8, minRatio: 0.35}, options || {});
    if (!Number.isFinite(degrees)) return target;
    target.trackedFrames += 1;
    if (degrees > config.threshold) {
      target.aboveFrames += 1;
      target.consecutiveFrames += 1;
    } else {
      target.consecutiveFrames = 0;
    }
    target.ratio = target.aboveFrames / Math.max(1, target.trackedFrames);
    target.confirmed = target.confirmed
      || (target.aboveFrames >= config.minFrames && target.ratio >= config.minRatio);
    return target;
  }

  return Object.freeze({
    LANDMARK,
    baselineFromSamples,
    createTemporalState,
    legacyForwardLeanDegrees,
    metricsFromLandmarks,
    newForwardLeanEvidence,
    updateTemporalState,
  });
});
