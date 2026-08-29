import { Platform } from "react-native";

const MEDIAPIPE_ASSETS = [
  "/vendor/mediapipe/vision_bundle.mjs",
  "/vendor/mediapipe/wasm/vision_wasm_internal.js",
  "/vendor/mediapipe/wasm/vision_wasm_internal.wasm",
  "/vendor/mediapipe/wasm/vision_wasm_nosimd_internal.js",
  "/vendor/mediapipe/wasm/vision_wasm_nosimd_internal.wasm",
  "/vendor/mediapipe/models/pose_landmarker_lite.task",
  "/vendor/mediapipe/models/hand_landmarker.task",
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
