import { Platform } from "react-native";
import { API_BASE } from "@/src/config";

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

function assetUrl(path: string): string {
  return `${API_BASE}${path}`;
}

async function fetchCompletely(path: string): Promise<void> {
  const response = await fetch(assetUrl(path), {
    cache: "force-cache",
    credentials: "omit",
    mode: "cors",
  });
  if (!response.ok) throw new Error(`Could not preload ${path}: ${response.status}`);
  await response.arrayBuffer();
}

async function preloadPreparedExerciseVoice(): Promise<void> {
  const manifestResponse = await fetch(assetUrl("/audio/prepared/manifest.json"), {
    cache: "force-cache",
    credentials: "omit",
    mode: "cors",
  });
  if (!manifestResponse.ok) return;
  const manifest = await manifestResponse.json() as { assets?: { url?: string }[] };
  const urls = (manifest.assets || []).map((asset) => asset.url).filter((url): url is string => Boolean(url));
  await Promise.allSettled(urls.map(fetchCompletely));
}

export function preloadAssessmentMediaPipe(): Promise<void> {
  if (typeof fetch !== "function" || (Platform.OS !== "web" && !API_BASE)) return Promise.resolve();
  if (preloadPromise) return preloadPromise;

  preloadPromise = Promise.allSettled([
    // Consume each body so the browser/native HTTP cache receives the full
    // model file rather than only opening a response stream.
    (async () => {
      for (const url of MEDIAPIPE_ASSETS) await fetchCompletely(url);
    })(),
    preloadPreparedExerciseVoice(),
  ]).then(() => undefined);

  return preloadPromise;
}
