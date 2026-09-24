const browserHost = typeof globalThis.location !== "undefined" ? globalThis.location.hostname : "";
const browserPort = typeof globalThis.location !== "undefined" ? globalThis.location.port : "";
const browserOrigin = typeof globalThis.location !== "undefined" ? globalThis.location.origin : "";
const localWebBase = ["localhost", "127.0.0.1"].includes(browserHost)
  ? ["4185", "4201", "8001"].includes(browserPort)
    ? browserOrigin
    : `${globalThis.location.protocol}//${browserHost}:8001`
  : "";
const configuredBase = process.env.EXPO_PUBLIC_BACKEND_URL?.replace(/\/+$/, "") || "";

// Hosted PWA requests remain same-origin. Expo/native builds use the configured backend.
export const API_BASE = localWebBase || configuredBase;
