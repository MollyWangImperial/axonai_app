import { Platform } from "react-native";

const MEDIAPIPE_ASSETS = [
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/vision_bundle.mjs",
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/vision_wasm_internal.js",
  "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm/vision_wasm_internal.wasm",
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
];

let preloadPromise: Promise<void> | null = null;

export function preloadAssessmentMediaPipe(): Promise<void> {
  if (Platform.OS !== "web" || typeof fetch !== "function") return Promise.resolve();
  if (preloadPromise) return preloadPromise;

  preloadPromise = Promise.allSettled(
    MEDIAPIPE_ASSETS.map((url) => fetch(url, {
      cache: "force-cache",
      credentials: "omit",
      mode: "cors",
    })),
  ).then(() => undefined);

  return preloadPromise;
}
