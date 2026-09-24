(function(root) {
// Angles and arcs share the same aspect-corrected image vectors. Coordinates
// are already mirrored by measurePose; drawing must not mirror them again.
function jointArc(a, vertex, c, aspect = 1) {
  if (![a, vertex, c].every(p => p && [p.x, p.y].every(Number.isFinite))
    || !Number.isFinite(aspect) || aspect <= 0) return null;
  const u = { x: (a.x - vertex.x) * aspect, y: a.y - vertex.y };
  const v = { x: (c.x - vertex.x) * aspect, y: c.y - vertex.y };
  const firstLength = Math.hypot(u.x, u.y), secondLength = Math.hypot(v.x, v.y);
  if (Math.min(firstLength, secondLength) < 0.005) return null;
  const start = Math.atan2(u.y, u.x);
  const sweep = Math.atan2(u.x * v.y - u.y * v.x, u.x * v.x + u.y * v.y);
  return { vertex, start, sweep, degrees: Math.abs(sweep) * 180 / Math.PI,
    shorterLength: Math.min(firstLength, secondLength) };
}

const ANGLE_COLORS = { arm: '#67e8f9', elbow: '#facc15' };

function drawAngleArcs(ctx, pose, width, height, displayWidth = width) {
  if (!pose?.tracking) return;
  // Avoid subpixel strokes/tiny bitmap text when a low-resolution camera is
  // enlarged on a desktop; still keep labels readable when reduced on phones.
  const scale = Math.max(0.8, width / Math.max(1, displayWidth));
  const fontSize = 14 * scale, padding = 5 * scale;
  const boxes = [];
  ctx.save(); ctx.lineCap = 'round'; ctx.lineWidth = 2.5 * scale;
  ctx.font = `700 ${fontSize}px system-ui, sans-serif`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  for (const [arc, color] of [[pose.armElevationArc, ANGLE_COLORS.arm], [pose.elbowArc, ANGLE_COLORS.elbow]]) {
    if (!arc) continue;
    const x = arc.vertex.x * width, y = arc.vertex.y * height;
    const radius = Math.min(34 * scale, arc.shorterLength * height * 0.4);
    const end = arc.start + arc.sweep;
    ctx.strokeStyle = color; ctx.fillStyle = color;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, radius, arc.start, end, arc.sweep < 0); ctx.closePath();
    ctx.globalAlpha = 0.15; ctx.fill(); ctx.globalAlpha = 1;
    // Dashed rays identify the exact two vectors, including the torso reference.
    ctx.setLineDash([4 * scale, 3 * scale]);
    ctx.beginPath();
    for (const angle of [arc.start, end]) {
      ctx.moveTo(x, y); ctx.lineTo(x + (radius + 10 * scale) * Math.cos(angle), y + (radius + 10 * scale) * Math.sin(angle));
    }
    ctx.stroke(); ctx.setLineDash([]);
    ctx.beginPath(); ctx.arc(x, y, radius, arc.start, end, arc.sweep < 0); ctx.stroke();
    const text = `${arc.degrees.toFixed(1)}°`;
    const boxWidth = ctx.measureText(text).width + padding * 2, boxHeight = fontSize + padding * 2;
    const bisector = arc.start + arc.sweep / 2;
    const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
    const bx = clamp(x + (radius + 22 * scale) * Math.cos(bisector) - boxWidth / 2, padding, width - padding - boxWidth);
    let by = clamp(y + (radius + 22 * scale) * Math.sin(bisector) - boxHeight / 2, padding, height - padding - boxHeight);
    if (boxes.some(b => bx < b.x + b.width && bx + boxWidth > b.x && by < b.y + b.height && by + boxHeight > b.y)) {
      const previous = boxes[boxes.length - 1];
      by = previous.y + previous.height + padding + boxHeight <= height - padding
        ? previous.y + previous.height + padding : Math.max(padding, previous.y - boxHeight - padding);
    }
    boxes.push({ x: bx, y: by, width: boxWidth, height: boxHeight });
    ctx.fillStyle = 'rgba(5, 25, 23, .9)'; ctx.fillRect(bx, by, boxWidth, boxHeight);
    ctx.fillStyle = color; ctx.fillText(text, bx + boxWidth / 2, by + boxHeight / 2);
  }
  ctx.restore();
}

function assessmentReadout(tracker, pose, world, aspect = 1) {
  const raw = tracker.raw(pose, world, aspect), a = tracker.a;
  const visible = indices => pose && indices.every(i => pose[i] && [pose[i].x, pose[i].y].every(Number.isFinite) && (pose[i].visibility ?? 0) >= .65);
  const point = i => ({ x: 1 - pose[i].x, y: pose[i].y });
  const armElevationArc = visible([a.h, a.s, a.e]) ? jointArc(point(a.h), point(a.s), point(a.e), aspect) : null;
  const elbowArc = visible([a.s, a.e, a.w]) ? jointArc(point(a.s), point(a.e), point(a.w), aspect) : null;
  return { tracking: !!pose, armElevationArc, elbowArc,
    armScore: Number.isFinite(raw.arm_elevation) ? raw.arm_elevation : null,
    elbowScore: Number.isFinite(raw.elbow_extension) ? raw.elbow_extension : null };
}
const api = { jointArc, ANGLE_COLORS, drawAngleArcs, assessmentReadout };
root.RehynReachAngles = api;
if (typeof module !== "undefined" && module.exports) module.exports = api;
})(globalThis);
