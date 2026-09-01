"""Camera-guided rehabilitation games used as optional plan practice."""

from __future__ import annotations

import json
from typing import Any, Dict


REHAB_GAME_LIBRARY: Dict[str, Dict[str, Any]] = {
    "garden_reach": {
        "id": "garden_reach",
        "name": "Garden Reach",
        "subtitle": "Water each flower with a gentle reach.",
        "objective": "Point-to-point reaching",
        "image": "/game-assets/garden-reach.png",
        "item_label": "flowers",
        "setup_voice": (
            "Welcome to Garden Reach. Sit in a stable chair with both feet supported. "
            "Keep your usual support nearby. Move your affected hand to guide the green dot. "
            "Reach only as far as feels comfortable, and rest whenever you need to."
        ),
        "targets": [
            {"x": 0.22, "y": 0.34, "label": "purple flower", "voice": "Gently move the green dot to the purple flower on the left."},
            {"x": 0.50, "y": 0.44, "label": "blue flower", "voice": "Lovely. Now reach toward the blue flower in the middle."},
            {"x": 0.77, "y": 0.34, "label": "white flower", "voice": "Move slowly toward the white flower at the upper right."},
            {"x": 0.80, "y": 0.68, "label": "yellow flower", "voice": "Bring the dot down gently toward the yellow flower."},
            {"x": 0.21, "y": 0.66, "label": "pink flower", "voice": "For the last flower, move steadily across to the pink flower on the left."},
        ],
        "coaching": "Move gently toward the glowing flower. A small comfortable reach still counts.",
        "complete_voice": "The garden is watered. That was calm, purposeful reaching. Well done.",
    },
    "lantern_trail": {
        "id": "lantern_trail",
        "name": "Lantern Trail",
        "subtitle": "Guide the light smoothly along the path.",
        "objective": "Smooth movement control",
        "image": "/game-assets/lantern-trail.png",
        "item_label": "lanterns",
        "setup_voice": (
            "Welcome to Lantern Trail. Sit securely and let your shoulder stay relaxed. "
            "Use your affected hand to guide the green light along the wide path. "
            "Move slowly and smoothly. You can pause or rest at any time."
        ),
        "targets": [
            {"x": 0.31, "y": 0.77, "label": "first lantern", "voice": "Begin with the lantern near the lower left of the path."},
            {"x": 0.55, "y": 0.47, "label": "second lantern", "voice": "Follow the wide path gently to the second lantern."},
            {"x": 0.72, "y": 0.35, "label": "third lantern", "voice": "Keep the light moving smoothly toward the next lantern."},
            {"x": 0.84, "y": 0.22, "label": "final lantern", "voice": "One last steady reach to the lantern at the top of the path."},
        ],
        "coaching": "Keep the green light inside the wide path and move at your own pace.",
        "complete_voice": "Every lantern is glowing. You kept the movement smooth and controlled. Beautiful work.",
    },
    "set_the_table": {
        "id": "set_the_table",
        "name": "Set the Table",
        "subtitle": "Select each item, then place it carefully.",
        "objective": "Reach, hold and transfer",
        "image": "/game-assets/set-the-table.png",
        "item_label": "items",
        "setup_voice": (
            "Welcome to Set the Table. Sit in a stable position facing the screen. "
            "Guide the green dot to an item on the counter, hold there, then move it slowly to its place on the table. "
            "Use a comfortable range and stop if you feel pain or unusual fatigue."
        ),
        "targets": [
            {
                "x": 0.09, "y": 0.56, "to_x": 0.68, "to_y": 0.53, "label": "cup",
                "voice": "Move the green dot to the blue cup and hold it there.",
                "place_voice": "Good. Keep holding, then move the cup slowly to the glowing place on the table.",
            },
            {
                "x": 0.22, "y": 0.62, "to_x": 0.59, "to_y": 0.68, "label": "plate",
                "voice": "Now move to the plate on the counter and hold.",
                "place_voice": "Carry the plate gently to the lower left place on the table.",
            },
            {
                "x": 0.25, "y": 0.48, "to_x": 0.76, "to_y": 0.67, "label": "bowl",
                "voice": "Move the dot to the bowl and hold it steadily.",
                "place_voice": "Now move the bowl slowly to its place beside the plate.",
            },
            {
                "x": 0.19, "y": 0.72, "to_x": 0.87, "to_y": 0.61, "label": "spoon",
                "voice": "For the last item, move to the spoon and hold.",
                "place_voice": "Keep the movement gentle as you place the spoon on the right side of the table.",
            },
        ],
        "coaching": "Hold over the item, then move it slowly to the glowing place.",
        "complete_voice": "The table is ready. You practised reaching, holding and placing with care. Excellent work.",
    },
}


def game_catalog() -> list[Dict[str, Any]]:
    return [
        {
            "id": game["id"],
            "name": game["name"],
            "subtitle": game["subtitle"],
            "objective": game["objective"],
            "image": game["image"],
            "item_count": len(game["targets"]),
            "optional": True,
        }
        for game in REHAB_GAME_LIBRARY.values()
    ]


def rehab_game_html(game_id: str, difficulty: str = "medium") -> str:
    selected_id = game_id if game_id in REHAB_GAME_LIBRARY else "garden_reach"
    selected_level = difficulty if difficulty in {"easy", "medium", "difficult"} else "medium"
    config = {**REHAB_GAME_LIBRARY[selected_id], "difficulty": selected_level}
    return REHAB_GAME_HTML_TEMPLATE.replace("__GAME_CONFIG__", json.dumps(config))


REHAB_GAME_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, user-scalable=no" />
<title>Rehyn movement game</title>
<style>
  *{box-sizing:border-box}
  html,body{width:100%;height:100%;margin:0;overflow:hidden;background:#f5f6f2;color:#104a36;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:0}
  button{font:inherit}
  #app{width:100%;height:100%;height:100dvh;display:flex;flex-direction:column;background:#f8f8f5}
  #gameHeader{min-height:88px;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:16px;padding:12px 28px;border-bottom:1px solid #d7ddd6;background:#fbfcfa;z-index:4}
  #brand{display:flex;align-items:center;gap:12px;font-size:24px;font-weight:850;color:#0d5139}
  #brand img{width:48px;height:48px;border-radius:8px}
  #gameIdentity{text-align:center;min-width:260px}
  #gameName{font-size:34px;line-height:40px;font-weight:850;color:#0a4e37}
  #gamePace{margin-top:2px;font-size:15px;line-height:21px;color:#315f4f}
  #controls{justify-self:end;display:flex;gap:10px}
  .controlBtn{min-width:108px;min-height:52px;border:1px solid #2d6e54;border-radius:8px;background:#fff;color:#0d5139;font-weight:800;padding:0 16px;cursor:pointer}
  .controlBtn:focus-visible,#startBtn:focus-visible{outline:4px solid #f5c64f;outline-offset:2px}
  #instruction{min-height:72px;display:flex;align-items:center;justify-content:center;padding:12px 24px;background:#fffdf8;border-bottom:1px solid #dedfd9;text-align:center;z-index:3}
  #instructionText{font-size:27px;line-height:34px;font-weight:850;color:#0b4b36}
  #sceneShell{position:relative;flex:1;min-height:0;display:flex;align-items:center;justify-content:center;background:#dfe7dc;overflow:hidden}
  #scene{position:relative;width:min(100%,calc((100vh - 250px) * 2));height:100%;max-height:100%;overflow:hidden;background:#e9eee7}
  #sceneImage{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;user-select:none;-webkit-user-drag:none}
  #trailCanvas,#targetLayer{position:absolute;inset:0;width:100%;height:100%}
  #targetLayer{pointer-events:none}
  .target{position:absolute;width:var(--target-size);height:auto;aspect-ratio:1;margin-left:calc(var(--target-size) / -2);margin-top:calc(var(--target-size) / -2);border-radius:50%;border:3px solid rgba(14,103,58,.45);background:rgba(255,255,255,.3);display:flex;align-items:center;justify-content:center;transform:scale(.72);opacity:.5;transition:transform .25s ease,opacity .25s ease,background .25s ease,border-color .25s ease;box-shadow:0 3px 14px rgba(24,68,46,.18)}
  .target.current{transform:scale(1);opacity:1;border:6px solid #f2ad19;background:rgba(255,251,221,.52);box-shadow:0 0 0 10px rgba(255,208,65,.25),0 0 28px rgba(255,190,34,.85)}
  .target.done{transform:scale(.62);opacity:1;border:2px solid #19783e;background:#fff;box-shadow:0 3px 12px rgba(15,73,42,.24)}
  .target.done::after{content:"Done";font-size:12px;line-height:16px;font-weight:850;color:#176d3b;background:#fff;border:1px solid #2a7a4c;border-radius:8px;padding:3px 7px;white-space:nowrap}
  .targetLabel{padding:5px 8px;border-radius:8px;background:rgba(255,255,255,.94);border:1px solid #d08b12;font-size:13px;line-height:17px;font-weight:850;text-transform:capitalize;color:#8b5b08;white-space:nowrap}
  #cursor{position:absolute;width:46px;height:46px;margin-left:-23px;margin-top:-23px;border-radius:50%;background:#249a37;border:5px solid #fff;box-shadow:0 0 0 6px rgba(66,203,74,.42),0 0 25px rgba(53,218,75,.9);z-index:5;pointer-events:none;transition:opacity .2s ease}
  #cursor::after{content:"";position:absolute;inset:12px;border-radius:50%;background:#fff}
  #cursorLabel{position:absolute;left:50%;top:-42px;transform:translateX(-50%);padding:5px 9px;border-radius:8px;background:#fff;border:1px solid #276a4f;color:#174c38;font-size:12px;line-height:16px;font-weight:800;white-space:nowrap}
  #cameraState{position:absolute;left:12px;bottom:12px;padding:7px 10px;border-radius:8px;background:rgba(255,255,255,.92);border:1px solid rgba(22,88,61,.28);font-size:12px;line-height:16px;font-weight:750;color:#174c38;z-index:6}
  #gameFooter{min-height:92px;display:grid;grid-template-columns:minmax(180px,1fr) minmax(220px,1.5fr) minmax(260px,1.25fr);align-items:center;gap:22px;padding:14px 34px;border-top:1px solid #d7ddd6;background:#fff;z-index:4}
  #countLabel{font-size:24px;line-height:30px;font-weight:850;color:#0c4d37}
  #progress{display:flex;gap:10px}
  .progressSegment{height:18px;flex:1;border-radius:8px;background:#dfe6df;border:1px solid #d2dad2;transition:background .25s ease,border-color .25s ease}
  .progressSegment.done{background:#16723d;border-color:#16723d}
  #coaching{min-height:50px;display:flex;align-items:center;border-left:1px solid #d7ddd6;padding-left:22px;font-size:16px;line-height:23px;font-weight:750;color:#184d39}
  #overlay,#completeOverlay{position:absolute;inset:0;z-index:20;display:flex;align-items:center;justify-content:center;padding:24px;background:rgba(246,248,244,.96)}
  .overlayCard{width:100%;max-width:590px;border:1px solid #cdd6ce;border-radius:8px;background:#fff;padding:28px;text-align:center;box-shadow:0 18px 50px rgba(24,62,43,.18)}
  .overlayMark{width:68px;height:68px;margin:0 auto 18px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:#e3f0e5;color:#176d3b;font-size:29px;font-weight:900}
  .overlayCard h1{margin:0;font-size:30px;line-height:38px;color:#0c4d37}
  .overlayCard p{margin:12px auto 0;max-width:480px;font-size:16px;line-height:24px;color:#526159}
  .safetyLine{margin-top:16px;padding:12px;border:1px solid #e8c482;border-radius:8px;background:#fff8ea;color:#704b13;font-size:14px;line-height:21px;text-align:left}
  #startBtn{min-width:210px;min-height:54px;margin-top:22px;border:0;border-radius:8px;background:#135f3d;color:#fff;font-weight:850;font-size:17px;cursor:pointer;padding:0 24px}
  #completeOverlay{background:rgba(242,248,242,.97)}
  #completeOverlay .overlayMark{background:#176d3b;color:#fff}
  .hidden{display:none!important}
  #video{position:fixed;width:2px;height:2px;left:-10px;bottom:-10px;opacity:.01;pointer-events:none}
  @media (max-width:760px){
    #gameHeader{min-height:106px;grid-template-columns:1fr auto;grid-template-rows:auto auto;padding:8px 12px;gap:5px 8px}
    #brand span{display:none}
    #brand img{width:42px;height:42px}
    #gameIdentity{grid-column:1 / -1;grid-row:2;min-width:0;padding:0}
    #gameName{font-size:22px;line-height:27px}
    #gamePace{display:none}
    #controls{grid-column:2;grid-row:1;gap:6px}
    .controlBtn{min-width:58px;min-height:42px;padding:0 8px;font-size:12px}
    #instruction{min-height:60px;padding:8px 14px}
    #instructionText{font-size:18px;line-height:24px}
    #scene{width:100%;height:auto;max-height:100%;aspect-ratio:3/2}
    #cursor{width:36px;height:36px;margin-left:-18px;margin-top:-18px;border-width:4px}
    #cursor::after{inset:9px}
    #cursorLabel{display:none}
    #gameFooter{min-height:112px;grid-template-columns:1fr;padding:10px 14px;gap:7px}
    #countLabel{font-size:18px;line-height:23px}
    #progress{gap:6px}
    .progressSegment{height:12px}
    #coaching{min-height:0;border-left:0;padding-left:0;font-size:13px;line-height:18px}
    #cameraState{font-size:10px;padding:4px 6px}
    .overlayCard{padding:22px 18px}
    .overlayCard h1{font-size:24px;line-height:30px}
  }
  @media (max-height:560px) and (orientation:landscape){
    #gameHeader{min-height:54px;grid-template-columns:auto 1fr auto;grid-template-rows:1fr;gap:8px;padding:5px 10px}
    #brand{grid-column:1;grid-row:1}
    #brand span{display:none}
    #brand img{width:38px;height:38px}
    #gameIdentity{grid-column:2;grid-row:1;min-width:0;padding:0;text-align:center}
    #gameName{font-size:20px;line-height:24px}
    #gamePace{display:none}
    #controls{grid-column:3;grid-row:1;gap:5px}
    .controlBtn{min-width:60px;min-height:38px;padding:0 7px;font-size:11px}
    #instruction{min-height:48px;padding:5px 12px}
    #instructionText{font-size:18px;line-height:23px}
    #scene{width:min(100%,calc((100vh - 160px) * 2));height:100%;aspect-ratio:auto}
    #cursor{width:34px;height:34px;margin-left:-17px;margin-top:-17px;border-width:4px}
    #cursor::after{inset:8px}
    #cursorLabel{display:none}
    #gameFooter{min-height:58px;grid-template-columns:minmax(110px,.8fr) minmax(140px,1fr) minmax(170px,1.2fr);gap:12px;padding:6px 14px}
    #countLabel{font-size:15px;line-height:20px}
    #progress{gap:5px}
    .progressSegment{height:10px}
    #coaching{min-height:0;padding-left:12px;font-size:11px;line-height:15px}
    #cameraState{font-size:9px;padding:3px 5px}
  }
</style>
</head>
<body>
<div id="app">
  <header id="gameHeader">
    <div id="brand"><img src="/icons/icon-192.png" alt="" /><span>Rehyn</span></div>
    <div id="gameIdentity"><div id="gameName">Movement game</div><div id="gamePace">Move gently. Rest anytime.</div></div>
    <div id="controls">
      <button id="exitBtn" class="controlBtn" type="button">Exit</button>
      <button id="audioBtn" class="controlBtn" type="button">Sound on</button>
      <button id="pauseBtn" class="controlBtn" type="button">Pause</button>
    </div>
  </header>
  <section id="instruction" aria-live="polite"><div id="instructionText">Preparing your game...</div></section>
  <main id="sceneShell">
    <div id="scene">
      <img id="sceneImage" alt="" />
      <canvas id="trailCanvas"></canvas>
      <div id="targetLayer"></div>
      <div id="cursor" class="hidden"><div id="cursorLabel">Your dot</div></div>
      <div id="cameraState">Preparing camera</div>
    </div>
  </main>
  <footer id="gameFooter">
    <div id="countLabel">0 complete</div>
    <div id="progress" aria-label="Game progress"></div>
    <div id="coaching">Move at your own pace. Rest anytime.</div>
  </footer>
  <video id="video" playsinline autoplay muted></video>
</div>

<div id="overlay">
  <div class="overlayCard">
    <div class="overlayMark">R</div>
    <h1 id="overlayTitle">Ready to play?</h1>
    <p id="overlayBody"></p>
    <div class="safetyLine">Sit securely with both feet supported. Keep your usual support nearby. Stop for new pain, dizziness, marked fatigue, or loss of balance.</div>
    <button id="startBtn" type="button">Start game</button>
  </div>
</div>

<div id="completeOverlay" class="hidden">
  <div class="overlayCard">
    <div class="overlayMark">Done</div>
    <h1>Game complete</h1>
    <p id="completeText">Beautiful work. Returning to your plan.</p>
  </div>
</div>

<script type="module">
import { PoseLandmarker, FilesetResolver } from "/vendor/mediapipe/vision_bundle.mjs";

const CFG = __GAME_CONFIG__;
const PARAMS = new URLSearchParams(location.search);
const PREVIEW = PARAMS.get("preview") === "1";
const PREVIEW_HOLD = PARAMS.get("preview_hold") === "1";
let voiceEnabled = PARAMS.get("voice_guidance") !== "0" && !PREVIEW;
const LEVELS = {
  easy:{radius:0.105,holdMs:520},
  medium:{radius:0.078,holdMs:760},
  difficult:{radius:0.060,holdMs:980},
};
const level = LEVELS[CFG.difficulty] || LEVELS.medium;
const API_BASE = location.origin + "/api";

const scene = document.getElementById("scene");
const sceneImage = document.getElementById("sceneImage");
const targetLayer = document.getElementById("targetLayer");
const cursorEl = document.getElementById("cursor");
const cameraState = document.getElementById("cameraState");
const instructionText = document.getElementById("instructionText");
const countLabel = document.getElementById("countLabel");
const progress = document.getElementById("progress");
const coaching = document.getElementById("coaching");
const overlay = document.getElementById("overlay");
const overlayTitle = document.getElementById("overlayTitle");
const overlayBody = document.getElementById("overlayBody");
const startBtn = document.getElementById("startBtn");
const exitBtn = document.getElementById("exitBtn");
const audioBtn = document.getElementById("audioBtn");
const pauseBtn = document.getElementById("pauseBtn");
const completeOverlay = document.getElementById("completeOverlay");
const completeText = document.getElementById("completeText");
const video = document.getElementById("video");
const trailCanvas = document.getElementById("trailCanvas");
const trailCtx = trailCanvas.getContext("2d");

sceneImage.src = CFG.image + "?v=20260901";
document.getElementById("gameName").textContent = CFG.name;
overlayTitle.textContent = CFG.name;
overlayBody.textContent = CFG.setup_voice;
coaching.textContent = CFG.coaching;

let landmarker = null;
let running = false;
let paused = false;
let armed = false;
let index = 0;
let phase = "select";
let inTargetSince = null;
let lastFrameAt = -1;
let lastInstructionAt = 0;
let idlePrompted = false;
let cursor = {x:0.5,y:0.72,visible:false};
let trail = [];
let audioEl = new Audio();
let audioUnlocked = false;
const audioCache = new Map();
const targetEls = [];

function postRN(data){
  if(window.ReactNativeWebView) window.ReactNativeWebView.postMessage(JSON.stringify(data));
}

function currentTarget(){
  const item = CFG.targets[index];
  if(!item) return null;
  const sourcePoint = CFG.id === "set_the_table" && phase === "place"
    ? {x:item.to_x,y:item.to_y}
    : {x:item.x,y:item.y};
  return {...item,...mapImagePoint(sourcePoint)};
}

function mapImagePoint(point){
  const rect = scene.getBoundingClientRect();
  const width = Math.max(1,rect.width);
  const height = Math.max(1,rect.height);
  const imageAspect = 1.5;
  const containerAspect = width / height;
  let renderedWidth = width;
  let renderedHeight = height;
  let offsetX = 0;
  let offsetY = 0;
  if(containerAspect > imageAspect){
    renderedHeight = width / imageAspect;
    offsetY = (height-renderedHeight)/2;
  }else{
    renderedWidth = height * imageAspect;
    offsetX = (width-renderedWidth)/2;
  }
  return {
    x:(offsetX+point.x*renderedWidth)/width,
    y:(offsetY+point.y*renderedHeight)/height,
  };
}

function instructionForCurrent(){
  const item = CFG.targets[index];
  if(!item) return "";
  return CFG.id === "set_the_table" && phase === "place" ? item.place_voice : item.voice;
}

function visibleLabel(){
  const item = CFG.targets[index];
  if(!item) return "";
  if(CFG.id === "garden_reach") return `Move the green dot to water the ${item.label}.`;
  if(CFG.id === "lantern_trail") return `Guide the green light to the ${item.label}.`;
  return phase === "place"
    ? `Move the ${item.label} slowly to its place on the table.`
    : `Move the green dot to the ${item.label} and hold.`;
}

function syncCanvas(){
  const rect = scene.getBoundingClientRect();
  const scale = Math.max(1, window.devicePixelRatio || 1);
  trailCanvas.width = Math.round(rect.width * scale);
  trailCanvas.height = Math.round(rect.height * scale);
  trailCanvas.style.width = rect.width + "px";
  trailCanvas.style.height = rect.height + "px";
  trailCtx.setTransform(scale,0,0,scale,0,0);
}

function renderTargets(){
  targetLayer.innerHTML = "";
  targetEls.length = 0;
  CFG.targets.forEach((item,targetIndex) => {
    const el = document.createElement("div");
    el.className = "target";
    const isCurrent = targetIndex === index;
    const useDestination = CFG.id === "set_the_table" && isCurrent && phase === "place";
    const point = mapImagePoint(useDestination ? {x:item.to_x,y:item.to_y} : {x:item.x,y:item.y});
    const rect = scene.getBoundingClientRect();
    el.style.left = (point.x * rect.width) + "px";
    el.style.top = (point.y * rect.height) + "px";
    const visualRadius = Math.min(level.radius,0.065);
    el.style.setProperty("--target-size", `${Math.round(visualRadius * rect.width * 2)}px`);
    el.setAttribute("aria-label", item.label);
    if(targetIndex < index) el.classList.add("done");
    if(isCurrent){
      el.classList.add("current");
      if(CFG.id === "set_the_table"){
        const label = document.createElement("span");
        label.className = "targetLabel";
        label.textContent = phase === "place" ? `Place ${item.label}` : item.label;
        el.appendChild(label);
      }
    }
    targetLayer.appendChild(el);
    targetEls.push(el);
  });
}

function renderProgress(){
  progress.innerHTML = "";
  CFG.targets.forEach((_,targetIndex) => {
    const segment = document.createElement("div");
    segment.className = "progressSegment" + (targetIndex < index ? " done" : "");
    progress.appendChild(segment);
  });
  const noun = CFG.item_label || "items";
  countLabel.textContent = `${Math.min(index,CFG.targets.length)} of ${CFG.targets.length} ${noun}`;
}

function renderCursor(){
  cursorEl.classList.toggle("hidden", !cursor.visible);
  cursorEl.style.left = (cursor.x * 100) + "%";
  cursorEl.style.top = (cursor.y * 100) + "%";
  const rect = scene.getBoundingClientRect();
  trail.push({x:cursor.x*rect.width,y:cursor.y*rect.height});
  if(trail.length > 34) trail.shift();
  trailCtx.clearRect(0,0,rect.width,rect.height);
  if(trail.length > 2){
    trailCtx.beginPath();
    trail.forEach((point,i) => i ? trailCtx.lineTo(point.x,point.y) : trailCtx.moveTo(point.x,point.y));
    trailCtx.strokeStyle = "rgba(55,155,61,.48)";
    trailCtx.lineWidth = 6;
    trailCtx.lineCap = "round";
    trailCtx.setLineDash([3,13]);
    trailCtx.stroke();
    trailCtx.setLineDash([]);
  }
}

function updateCursorFromPose(landmarks){
  if(!landmarks) return;
  const target = currentTarget() || {x:0.5,y:0.5};
  const candidates = [landmarks[15],landmarks[16]].filter(point => point && (point.visibility == null || point.visibility > 0.35));
  if(!candidates.length){
    cursor.visible = false;
    return;
  }
  const chosen = candidates.sort((a,b) => {
    const ad = Math.hypot((1-a.x)-target.x,a.y-target.y);
    const bd = Math.hypot((1-b.x)-target.x,b.y-target.y);
    return ad-bd;
  })[0];
  const nextX = Math.max(0.03,Math.min(0.97,1-chosen.x));
  const nextY = Math.max(0.05,Math.min(0.95,chosen.y));
  const smoothing = CFG.difficulty === "easy" ? 0.24 : 0.32;
  cursor.x += (nextX-cursor.x)*smoothing;
  cursor.y += (nextY-cursor.y)*smoothing;
  cursor.visible = true;
}

function makeSilentWav(){
  const buffer = new ArrayBuffer(1644);
  const view = new DataView(buffer);
  const write = (at,text) => { for(let i=0;i<text.length;i++) view.setUint8(at+i,text.charCodeAt(i)); };
  write(0,"RIFF"); view.setUint32(4,1636,true); write(8,"WAVE"); write(12,"fmt ");
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
  view.setUint32(24,8000,true); view.setUint32(28,16000,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
  write(36,"data"); view.setUint32(40,1600,true);
  return URL.createObjectURL(new Blob([buffer],{type:"audio/wav"}));
}

async function unlockAudio(){
  if(audioUnlocked || !voiceEnabled) return;
  const url = makeSilentWav();
  try{
    audioEl.src = url;
    await audioEl.play();
    audioEl.pause();
    audioUnlocked = true;
  }catch(error){}
  URL.revokeObjectURL(url);
}

function browserVoice(text){
  return new Promise(resolve => {
    if(!window.speechSynthesis || !window.SpeechSynthesisUtterance){ resolve(false); return; }
    try{
      speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-GB";
      utterance.rate = 0.88;
      utterance.onend = () => resolve(true);
      utterance.onerror = () => resolve(false);
      speechSynthesis.speak(utterance);
      setTimeout(() => resolve(true),Math.min(16000,Math.max(3200,text.length*72)));
    }catch(error){ resolve(false); }
  });
}

function fetchVoice(text){
  if(audioCache.has(text)) return Promise.resolve(audioCache.get(text));
  return fetch(`${API_BASE}/tts/generate`,{
    method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text,voice_id:"nova"})
  }).then(async response => {
    if(!response.ok) throw new Error("tts unavailable");
    const data = await response.json();
    audioCache.set(text,data.audio_b64);
    return data.audio_b64;
  });
}

async function playVoice(text){
  if(!voiceEnabled || !text) return;
  try{
    const audio = await fetchVoice(text);
    audioEl.pause();
    audioEl.src = "data:audio/mpeg;base64," + audio;
    await audioEl.play();
    await new Promise(resolve => {
      const timeout = setTimeout(resolve,45000);
      audioEl.onended = () => { clearTimeout(timeout); resolve(); };
      audioEl.onerror = () => { clearTimeout(timeout); resolve(); };
    });
  }catch(error){
    await browserVoice(text);
  }
}

function prefetchVoices(){
  if(!voiceEnabled) return;
  [CFG.setup_voice,CFG.complete_voice,...CFG.targets.flatMap(item => [item.voice,item.place_voice].filter(Boolean))]
    .forEach(text => fetchVoice(text).catch(() => null));
}

async function announceCurrent(){
  armed = false;
  idlePrompted = false;
  inTargetSince = null;
  instructionText.textContent = visibleLabel();
  renderTargets();
  renderProgress();
  await playVoice(instructionForCurrent());
  lastInstructionAt = performance.now();
  armed = true;
}

async function setupTracking(){
  if(PREVIEW){
    cameraState.textContent = "Preview tracking";
    cursor.visible = true;
    cursor.x = 0.56;
    cursor.y = 0.66;
    return true;
  }
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    postRN({type:"camera_error",message:"Camera is unavailable"});
    return false;
  }
  try{
    const stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:1280},height:{ideal:720},frameRate:{ideal:24,max:30}},audio:false});
    video.srcObject = stream;
    await new Promise(resolve => video.onloadedmetadata = resolve);
    const files = await FilesetResolver.forVisionTasks("/vendor/mediapipe/wasm");
    landmarker = await PoseLandmarker.createFromOptions(files,{
      baseOptions:{modelAssetPath:"/vendor/mediapipe/models/pose_landmarker_lite.task"},
      runningMode:"VIDEO",numPoses:1,
    });
    cameraState.textContent = "Camera ready";
    return true;
  }catch(error){
    cameraState.textContent = "Camera unavailable";
    postRN({type:"camera_error",message:String(error)});
    return false;
  }
}

async function completeTarget(){
  armed = false;
  inTargetSince = null;
  if(navigator.vibrate) navigator.vibrate(60);
  const item = CFG.targets[index];
  if(CFG.id === "set_the_table" && phase === "select"){
    phase = "place";
    trail = [];
    renderTargets();
    await announceCurrent();
    return;
  }
  postRN({type:"game_checkpoint",game_id:CFG.id,index:index+1,total:CFG.targets.length,label:item.label});
  index += 1;
  phase = "select";
  trail = [];
  renderProgress();
  renderTargets();
  if(index >= CFG.targets.length){
    await finishGame();
    return;
  }
  coaching.textContent = index % 2 ? "Nice steady movement. Take a breath before the next one." : CFG.coaching;
  await playVoice("Well done. Take a breath when you need to.");
  await announceCurrent();
}

async function finishGame(){
  running = false;
  instructionText.textContent = "You completed " + CFG.name + ".";
  countLabel.textContent = `${CFG.targets.length} of ${CFG.targets.length} ${CFG.item_label}`;
  [...progress.children].forEach(segment => segment.classList.add("done"));
  completeText.textContent = CFG.complete_voice;
  completeOverlay.classList.remove("hidden");
  await playVoice(CFG.complete_voice);
  postRN({type:"game_complete",game_id:CFG.id,completed:CFG.targets.length,total:CFG.targets.length,difficulty:CFG.difficulty});
}

function checkCurrentTarget(now){
  if(!armed || paused || !cursor.visible) return;
  const target = currentTarget();
  if(!target) return;
  const rect = scene.getBoundingClientRect();
  const distance = Math.hypot((cursor.x-target.x)*rect.width,(cursor.y-target.y)*rect.height);
  if(distance <= level.radius*rect.width){
    if(inTargetSince == null) inTargetSince = now;
    if(now-inTargetSince >= level.holdMs) completeTarget();
  }else{
    inTargetSince = null;
    if(!idlePrompted && now-lastInstructionAt > 10000){
      idlePrompted = true;
      playVoice(CFG.coaching);
    }
  }
}

function loop(now){
  if(!running) return;
  if(!paused){
    if(PREVIEW){
      if(!PREVIEW_HOLD){
        const target = currentTarget();
        if(target){
          cursor.x += (target.x-cursor.x)*0.025;
          cursor.y += (target.y-cursor.y)*0.025;
        }
      }
    }else if(landmarker && video.readyState >= 2 && lastFrameAt !== video.currentTime){
      lastFrameAt = video.currentTime;
      try{
        const result = landmarker.detectForVideo(video,now);
        updateCursorFromPose(result && result.landmarks && result.landmarks[0]);
      }catch(error){}
    }
    renderCursor();
    checkCurrentTarget(now);
  }
  requestAnimationFrame(loop);
}

startBtn.addEventListener("click",async () => {
  startBtn.disabled = true;
  await unlockAudio();
  prefetchVoices();
  const ready = await setupTracking();
  if(!ready){
    startBtn.disabled = false;
    return;
  }
  overlay.classList.add("hidden");
  running = true;
  instructionText.textContent = "Listen for the first step.";
  await playVoice(CFG.setup_voice);
  await announceCurrent();
  requestAnimationFrame(loop);
});

audioBtn.addEventListener("click",async () => {
  voiceEnabled = !voiceEnabled;
  audioBtn.textContent = voiceEnabled ? "Sound on" : "Sound off";
  if(!voiceEnabled){
    audioEl.pause();
    if(window.speechSynthesis) speechSynthesis.cancel();
  }else if(running && !paused){
    await unlockAudio();
    await playVoice(instructionForCurrent());
  }
});

pauseBtn.addEventListener("click",async () => {
  if(!running) return;
  paused = !paused;
  pauseBtn.textContent = paused ? "Resume" : "Pause";
  cameraState.textContent = paused ? "Paused" : (PREVIEW ? "Preview tracking" : "Camera ready");
  if(paused){
    armed = false;
    audioEl.pause();
    if(window.speechSynthesis) speechSynthesis.cancel();
    instructionText.textContent = "Paused. Rest as long as you need.";
  }else{
    await announceCurrent();
  }
});

exitBtn.addEventListener("click",() => {
  running = false;
  armed = false;
  audioEl.pause();
  if(window.speechSynthesis) speechSynthesis.cancel();
  const stream = video.srcObject;
  if(stream && stream.getTracks) stream.getTracks().forEach(track => track.stop());
  if(window.ReactNativeWebView) postRN({type:"exit",game_id:CFG.id});
  else if(history.length > 1) history.back();
});

window.addEventListener("resize",() => { syncCanvas(); renderTargets(); },{passive:true});
if(window.ResizeObserver) new ResizeObserver(() => { syncCanvas(); renderTargets(); }).observe(scene);
syncCanvas();
renderTargets();
renderProgress();
postRN({type:"ready",game_id:CFG.id});

if(PREVIEW && PARAMS.get("autostart") === "1") setTimeout(() => startBtn.click(),80);
</script>
</body>
</html>
"""
