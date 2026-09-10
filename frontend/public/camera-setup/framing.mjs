// Use the same object-fit transform for landmark checks and the visible overlay.
export function project(point, sourceWidth, sourceHeight, width, height, fit = "contain") {
  const scale = (fit === "cover" ? Math.max : Math.min)(width / sourceWidth, height / sourceHeight);
  return {
    x: (width - sourceWidth * scale) / 2 + (1 - point.x) * sourceWidth * scale,
    y: (height - sourceHeight * scale) / 2 + point.y * sourceHeight * scale,
  };
}

export function checkFraming(landmarks, geometry) {
  if (!landmarks?.length) return { ready: false, hint: "Face the camera so it can find your upper body." };
  const visible = (index) => {
    const point = landmarks[index];
    if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y) || (point.visibility ?? 0) < 0.45) return false;
    const mapped = project(point, ...geometry);
    return mapped.x > geometry[2] * 0.04 && mapped.x < geometry[2] * 0.96 && mapped.y > geometry[3] * 0.04 && mapped.y < geometry[3] * 0.96;
  };
  if (![0, 2, 5].every(visible)) return { ready: false, hint: "Bring your whole head into view, with some space above it." };
  if (![11, 12].every(visible)) return { ready: false, hint: "Face the camera and keep both shoulders in view." };
  if (![13, 14, 15, 16].every(visible)) return { ready: false, hint: "Move the camera farther away until both arms and hands fit. Ask for help if needed." };
  if (!([17, 19].some(visible) && [18, 20].some(visible))) return { ready: false, hint: "Keep both hands visible, relaxed beside you or on your lap." };
  if (Math.abs(landmarks[11].x - landmarks[12].x) < 0.1) return { ready: false, hint: "Move the camera a little closer while keeping both hands in view." };
  return { ready: true, hint: "Your upper body is in view. Hold your position for a moment." };
}

export function createFramingTracker() {
  let started = null;
  let previous = null;
  return {
    update(valid, now) {
      if (previous !== null && now - previous > 500) started = null;
      previous = now;
      if (!valid) started = null;
      else if (started === null) started = now;
      return started !== null && now - started >= 1200;
    },
    reset() { started = null; previous = null; },
  };
}
