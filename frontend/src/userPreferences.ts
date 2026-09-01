import { storage } from "@/src/utils/storage";

export const DARK_MODE_KEY = "rehyn_dark_mode_v1";
export const TEXT_SIZE_KEY = "rehyn_text_size_v1";
export const VOICE_GUIDANCE_KEY = "rehyn_voice_guidance_v1";
export const SHARE_ASSESSMENTS_KEY = "rehyn_share_assessments_v1";
export const SHARE_CARE_CIRCLE_KEY = "rehyn_share_care_circle_v1";
export const USAGE_ANALYTICS_KEY = "rehyn_usage_analytics_v1";
export const DEMO_MODE_KEY = "rehyn_demo_mode_v1";
export const BRIGHTNESS_KEY = "rehyn_brightness_v1";
export const DARKNESS_KEY = "rehyn_dark_depth_v1";

export const TEXT_SIZES = ["Comfortable", "Large", "Extra large"] as const;
export type TextSizePreference = (typeof TEXT_SIZES)[number];

export type UserPreferences = {
  darkMode: boolean;
  textSize: TextSizePreference;
  voiceGuidance: boolean;
  shareAssessments: boolean;
  shareCareCircle: boolean;
  usageAnalytics: boolean;
  demoMode: boolean;
  brightness: number;
  darkness: number;
};

export const DEFAULT_USER_PREFERENCES: UserPreferences = {
  darkMode: false,
  textSize: "Comfortable",
  voiceGuidance: true,
  shareAssessments: true,
  shareCareCircle: false,
  usageAnalytics: false,
  demoMode: false,
  brightness: 94,
  darkness: 55,
};

const preferenceListeners = new Set<(preferences: UserPreferences) => void>();

export function subscribeUserPreferences(listener: (preferences: UserPreferences) => void) {
  preferenceListeners.add(listener);
  return () => preferenceListeners.delete(listener);
}

export async function loadUserPreferences(): Promise<UserPreferences> {
  const [darkMode, textSize, voiceGuidance, shareAssessments, shareCareCircle, usageAnalytics, demoMode, brightness, darkness] = await Promise.all([
    storage.getItem(DARK_MODE_KEY, DEFAULT_USER_PREFERENCES.darkMode),
    storage.getItem(TEXT_SIZE_KEY, DEFAULT_USER_PREFERENCES.textSize),
    storage.getItem(VOICE_GUIDANCE_KEY, DEFAULT_USER_PREFERENCES.voiceGuidance),
    storage.getItem(SHARE_ASSESSMENTS_KEY, DEFAULT_USER_PREFERENCES.shareAssessments),
    storage.getItem(SHARE_CARE_CIRCLE_KEY, DEFAULT_USER_PREFERENCES.shareCareCircle),
    storage.getItem(USAGE_ANALYTICS_KEY, DEFAULT_USER_PREFERENCES.usageAnalytics),
    storage.getItem(DEMO_MODE_KEY, DEFAULT_USER_PREFERENCES.demoMode),
    storage.getItem(BRIGHTNESS_KEY, DEFAULT_USER_PREFERENCES.brightness),
    storage.getItem(DARKNESS_KEY, DEFAULT_USER_PREFERENCES.darkness),
  ]);
  const darknessNumber = Number(darkness);
  return {
    darkMode: Boolean(darkMode),
    textSize: TEXT_SIZES.includes(textSize as TextSizePreference) ? textSize as TextSizePreference : "Comfortable",
    voiceGuidance: voiceGuidance !== false,
    shareAssessments: shareAssessments !== false,
    shareCareCircle: Boolean(shareCareCircle),
    usageAnalytics: Boolean(usageAnalytics),
    demoMode: Boolean(demoMode),
    brightness: Math.max(70, Math.min(100, Number(brightness) || DEFAULT_USER_PREFERENCES.brightness)),
    darkness: Number.isFinite(darknessNumber) ? Math.max(0, Math.min(100, darknessNumber)) : DEFAULT_USER_PREFERENCES.darkness,
  };
}

export async function saveUserPreference<K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) {
  const storageKeys: Record<keyof UserPreferences, string> = {
    darkMode: DARK_MODE_KEY,
    textSize: TEXT_SIZE_KEY,
    voiceGuidance: VOICE_GUIDANCE_KEY,
    shareAssessments: SHARE_ASSESSMENTS_KEY,
    shareCareCircle: SHARE_CARE_CIRCLE_KEY,
    usageAnalytics: USAGE_ANALYTICS_KEY,
    demoMode: DEMO_MODE_KEY,
    brightness: BRIGHTNESS_KEY,
    darkness: DARKNESS_KEY,
  };
  await storage.setItem(storageKeys[key], value);
  const preferences = await loadUserPreferences();
  preferenceListeners.forEach((listener) => listener(preferences));
}

export function textScaleFor(size: TextSizePreference) {
  if (size === "Extra large") return 1.22;
  if (size === "Large") return 1.1;
  return 1;
}

export const profilePhotoKey = (userId: string) => `rehyn_profile_photo_v2:${userId}`;
export const careFacilityKey = (userId: string) => `rehyn_care_facility_v2:${userId}`;
export const careCircleKey = (userId: string) => `rehyn_care_circle_v1:${userId}`;

export type CareCircleContact = {
  id: string;
  name: string;
  relationship: string;
  contact: string;
};

export async function loadCareCircle(userId: string): Promise<CareCircleContact[]> {
  const raw = await storage.getItem(careCircleKey(userId), "");
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((item) => item && typeof item.name === "string" && typeof item.id === "string")
      : [];
  } catch {
    return [];
  }
}

export async function saveCareCircle(userId: string, contacts: CareCircleContact[]) {
  return storage.setItem(careCircleKey(userId), JSON.stringify(contacts));
}
