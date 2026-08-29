import { storage } from "@/src/utils/storage";
import { API_BASE as BASE } from "@/src/config";
import AsyncStorage from "@react-native-async-storage/async-storage";

export type Me = { id: string; email: string; name: string; role: "patient" | "therapist"; credits: number };

export const USER_KEY = "active_user_id_v1";
export const USER_OBJ = "active_user_obj_v1";
const BACKEND_USER_KEY = `backend_user_id_v1:${BASE}`;

export const onboardingCompleteKey = (userId: string) => `onboarding_complete_v2:${userId}`;
export const preferredNameKey = (userId: string) => `preferred_name_v2:${userId}`;
export const affectedSideKey = (userId: string) => `affected_side_v2:${userId}`;
export const patientProfileKey = (userId: string) => `patient_profile_v2:${userId}`;
export const completedTasksKey = (userId: string, packageId: string) => `assessment_completed_tasks_v2:${userId}:${packageId}`;
export const savedTaskVideosKey = (userId: string, packageId: string) => `assessment_saved_task_videos_v2:${userId}:${packageId}`;

export async function cachePatientOnboarding(userId: string, profile: Record<string, any> | null = null) {
  await storage.setItem(onboardingCompleteKey(userId), "1");
  if (profile) await storage.setItem(patientProfileKey(userId), JSON.stringify(profile));
  if (profile?.preferred_name) await storage.setItem(preferredNameKey(userId), String(profile.preferred_name));
  if (profile?.side_affected === "left" || profile?.side_affected === "right") {
    await storage.setItem(affectedSideKey(userId), profile.side_affected);
  }
}

export async function getCachedPatientProfile(userId: string): Promise<Record<string, any> | null> {
  const raw = await storage.getItem(patientProfileKey(userId), "");
  if (raw) {
    try {
      const profile = JSON.parse(raw);
      if (profile && typeof profile === "object") return profile;
    } catch {
      /* fall through to legacy account-scoped fields */
    }
  }
  const [preferredName, affectedSide] = await Promise.all([
    storage.getItem(preferredNameKey(userId), ""),
    storage.getItem(affectedSideKey(userId), ""),
  ]);
  if (!preferredName && affectedSide !== "left" && affectedSide !== "right") return null;
  return {
    ...(preferredName ? { preferred_name: preferredName } : {}),
    ...(affectedSide === "left" || affectedSide === "right" ? { side_affected: affectedSide } : {}),
  };
}

export async function getUserId(): Promise<string | null> {
  const userId = await storage.getItem(USER_KEY, "");
  return userId || null;
}

export async function getCachedUser(): Promise<Me | null> {
  const raw = await storage.getItem(USER_OBJ, "");
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export async function signIn(email: string, name: string, role: "patient" | "therapist"): Promise<Me> {
  const r = await fetch(`${BASE}/api/users/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, role }),
  });
  if (!r.ok) throw new Error("Sign-in failed");
  const u: Me = await r.json();
  await storage.setItem(USER_KEY, u.id);
  await storage.setItem(USER_OBJ, JSON.stringify(u));
  return u;
}

export async function signOut() {
  await storage.removeItem(USER_KEY);
  await storage.removeItem(USER_OBJ);
  // Retain account-scoped onboarding and assessment progress for the next sign-in.
  await storage.removeItem("onboarding_complete_v1");
  await storage.removeItem("preferred_name_v1");
}

export const consentAcceptedKey = (userId: string) => `medical_consent_accepted_v1:${userId}`;

export async function hasAcceptedConsent(userId: string): Promise<boolean> {
  const value = await storage.getItem(consentAcceptedKey(userId), "");
  return value === "1";
}

export async function setConsentAccepted(userId: string) {
  await storage.setItem(consentAcceptedKey(userId), "1");
}

// Requests account deletion (soft delete server-side), then clears the local session.
export async function deleteAccount(): Promise<void> {
  try {
    await authedFetch("/api/users/account", { method: "DELETE" });
  } finally {
    await signOut();
  }
}

async function migrateAccountCache(previousUserId: string, nextUserId: string) {
  if (!previousUserId || previousUserId === nextUserId) return;
  const packageIds = ["initial", "upper_limb", "hand", "lower_limb", "balance"];
  const keyPairs = [
    [onboardingCompleteKey(previousUserId), onboardingCompleteKey(nextUserId)],
    [preferredNameKey(previousUserId), preferredNameKey(nextUserId)],
    [affectedSideKey(previousUserId), affectedSideKey(nextUserId)],
    [patientProfileKey(previousUserId), patientProfileKey(nextUserId)],
    [`rehyn_profile_photo_v2:${previousUserId}`, `rehyn_profile_photo_v2:${nextUserId}`],
    [`rehyn_care_facility_v2:${previousUserId}`, `rehyn_care_facility_v2:${nextUserId}`],
    [`rehyn_care_circle_v1:${previousUserId}`, `rehyn_care_circle_v1:${nextUserId}`],
    ...packageIds.flatMap((packageId) => [
      [completedTasksKey(previousUserId, packageId), completedTasksKey(nextUserId, packageId)],
      [savedTaskVideosKey(previousUserId, packageId), savedTaskVideosKey(nextUserId, packageId)],
    ]),
  ];
  await Promise.all(keyPairs.map(async ([source, target]) => {
    const value = await storage.getItem(source, "");
    if (value !== "" && value != null) await storage.setItem(target, value);
  }));
}

export async function recoverSingleAccountCache(userId: string) {
  if (await storage.getItem(onboardingCompleteKey(userId), "")) return;
  try {
    const prefix = "onboarding_complete_v2:";
    const candidates = (await AsyncStorage.getAllKeys()).filter((key) => key.startsWith(prefix) && key !== onboardingCompleteKey(userId));
    const completed = [] as string[];
    for (const key of candidates) {
      const raw = await AsyncStorage.getItem(key);
      if (raw && JSON.parse(raw)) completed.push(key.slice(prefix.length));
    }
    if (completed.length === 1) await migrateAccountCache(completed[0], userId);
  } catch {
    /* Recovery is best-effort; normal backend onboarding remains the fallback. */
  }
}

export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const appUserId = await getUserId();
  const uid = await storage.getItem(BACKEND_USER_KEY, "") || appUserId;
  const headers = new Headers(init.headers as any);
  if (uid && !headers.has("X-User-Id")) headers.set("X-User-Id", uid);
  headers.set("Content-Type", "application/json");
  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  if (response.status !== 401 || path === "/users/login") return response;

  const cached = await getCachedUser();
  if (!cached?.email) return response;
  try {
    const [cachedProfile, onboardingComplete] = await Promise.all([
      getCachedPatientProfile(cached.id),
      storage.getItem(onboardingCompleteKey(cached.id), ""),
    ]);
    const login = await fetch(`${BASE}/api/users/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: cached.email, name: cached.name, role: cached.role }),
    });
    if (!login.ok) return response;
    const rebound: Me = await login.json();
    await storage.setItem(BACKEND_USER_KEY, rebound.id);
    if (onboardingComplete && cachedProfile) {
      await fetch(`${BASE}/api/users/onboarding`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-User-Id": rebound.id },
        body: JSON.stringify(cachedProfile),
      }).catch(() => null);
    }
    headers.set("X-User-Id", rebound.id);
    return fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    return response;
  }
}

export async function fetchBalance(): Promise<{ credits: number; user_id?: string; costs: Record<string, number> }> {
  const r = await authedFetch("/api/credits/balance");
  return r.json();
}
