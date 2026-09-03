import { storage } from "@/src/utils/storage";
import { clearScreenCache } from "@/src/screenCache";
import { API_BASE as BASE } from "@/src/config";
import AsyncStorage from "@react-native-async-storage/async-storage";

export type Me = {
  id: string;
  email: string;
  name: string;
  role: "patient" | "therapist";
  credits: number;
  trial_access_granted: boolean;
  // Account state stored in MongoDB, returned by /api/users/login and /api/users/me.
  // A returning account arrives with consent_accepted/onboarding_complete already
  // true, so the Terms and the initial survey are only shown to new accounts.
  is_new_account?: boolean;
  consent_accepted?: boolean;
  consent_required?: boolean;
  onboarding_complete?: boolean;
  profile?: Record<string, any> | null;
};

export const USER_KEY = "active_user_id_v2";
export const USER_OBJ = "active_user_obj_v2";
const BACKEND_USER_KEY = `backend_user_id_v1:${BASE}`;
const TRIAL_ACCESS_KEY = `trial_access_code_v1:${BASE}`;
const authStateListeners = new Set<() => void>();

export function subscribeAuthState(listener: () => void) {
  authStateListeners.add(listener);
  return () => authStateListeners.delete(listener);
}

export function notifyAuthStateChanged() {
  authStateListeners.forEach((listener) => listener());
}

export const onboardingCompleteKey = (userId: string) => `onboarding_complete_v2:${userId}`;
export const preferredNameKey = (userId: string) => `preferred_name_v2:${userId}`;
export const affectedSideKey = (userId: string) => `affected_side_v2:${userId}`;
export const patientProfileKey = (userId: string) => `patient_profile_v2:${userId}`;
export const completedTasksKey = (userId: string, packageId: string) => `assessment_completed_tasks_v2:${userId}:${packageId}`;
export const savedTaskVideosKey = (userId: string, packageId: string) => `assessment_saved_task_videos_v2:${userId}:${packageId}`;
const patientActivityKey = (userId: string) => `patient_activity_v1:${userId}`;

export type CachedPatientActivity = {
  initial_assessment_completed_at?: string;
  latest_assessment_id?: string;
  latest_assessment_created_at?: string;
  daily_check_ins?: Record<string, "in_progress" | "complete">;
};

export async function getCachedPatientActivity(userId: string): Promise<CachedPatientActivity> {
  const raw = await storage.getItem(patientActivityKey(userId), "");
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function updateCachedPatientActivity(userId: string, update: (current: CachedPatientActivity) => CachedPatientActivity) {
  const current = await getCachedPatientActivity(userId);
  await storage.setItem(patientActivityKey(userId), JSON.stringify(update(current)));
}

export async function cacheDailyCheckInActivity(userId: string, date: string, status: "in_progress" | "complete") {
  await updateCachedPatientActivity(userId, (current) => ({
    ...current,
    daily_check_ins: { ...(current.daily_check_ins || {}), [date]: status },
  }));
}

export async function cacheAssessmentActivity(
  userId: string,
  assessmentId: string,
  createdAt: string,
  marksInitialAssessmentComplete = false,
) {
  await updateCachedPatientActivity(userId, (current) => ({
    ...current,
    latest_assessment_id: assessmentId || current.latest_assessment_id,
    latest_assessment_created_at: createdAt || current.latest_assessment_created_at,
    initial_assessment_completed_at: marksInitialAssessmentComplete
      ? current.initial_assessment_completed_at || createdAt || new Date().toISOString()
      : current.initial_assessment_completed_at,
  }));
}

export async function cacheInitialAssessmentCompletion(userId: string, completedAt?: string) {
  await updateCachedPatientActivity(userId, (current) => ({
    ...current,
    initial_assessment_completed_at:
      current.initial_assessment_completed_at || completedAt || new Date().toISOString(),
  }));
}

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
    storage.getItem(preferredNameKey(userId), "" as string),
    storage.getItem(affectedSideKey(userId), "" as string),
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
  try {
    const user = JSON.parse(raw) as Me;
    return user?.trial_access_granted === true ? user : null;
  } catch {
    return null;
  }
}

export async function signIn(email: string, name: string, role: "patient" | "therapist", trialCode?: string): Promise<Me> {
  const [previousUserRaw, legacyUserRaw] = await Promise.all([
    storage.getItem(USER_OBJ, ""),
    storage.getItem("active_user_obj_v1", ""),
  ]);
  const savedTrialCode = await storage.secureGet(TRIAL_ACCESS_KEY, "");
  const accessCode = (trialCode || savedTrialCode || "").trim();
  if (!accessCode) throw new Error("Enter your trial code to continue.");
  const r = await fetch(`${BASE}/api/users/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, role, trial_code: accessCode }),
  });
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    throw new Error(body?.detail || "Sign-in failed. Try again.");
  }
  const u: Me = await r.json();
  if (u.trial_access_granted !== true) throw new Error("Trial access could not be confirmed.");
  const normalizedEmail = email.trim().toLowerCase();
  for (const raw of [previousUserRaw, legacyUserRaw]) {
    try {
      const previous = JSON.parse(raw || "{}");
      if (
        previous?.id
        && previous.id !== u.id
        && String(previous.email || "").trim().toLowerCase() === normalizedEmail
      ) {
        await migrateAccountCache(String(previous.id), u.id);
      }
    } catch {
      // A malformed legacy session must not block a valid sign-in.
    }
  }
  await storage.setItem(USER_KEY, u.id);
  await storage.setItem(USER_OBJ, JSON.stringify(u));
  await storage.setItem(BACKEND_USER_KEY, u.id);
  await storage.secureSet(TRIAL_ACCESS_KEY, accessCode);
  await hydrateAccountStateFromServer(u);
  notifyAuthStateChanged();
  return u;
}

// The sign-in response carries the account state saved in MongoDB. Seeding the
// device caches from it means a returning patient is never asked to accept the
// Terms or repeat the initial survey - even on a new device or after clearing
// browser storage - and the routing gates keep working if a later request fails.
export async function hydrateAccountStateFromServer(user: Me) {
  if (!user?.id || user.role === "therapist") return;
  if (user.consent_accepted === true) {
    await storage.setItem(consentAcceptedKey(user.id), "1");
  }
  if (user.onboarding_complete === true) {
    await cachePatientOnboarding(user.id, user.profile && typeof user.profile === "object" ? user.profile : null);
  }
}

export async function signOut() {
  clearScreenCache();
  await storage.removeItem(USER_KEY);
  await storage.removeItem(USER_OBJ);
  await storage.removeItem(BACKEND_USER_KEY);
  await storage.removeItem("active_user_id_v1");
  await storage.removeItem("active_user_obj_v1");
  await storage.secureRemove(TRIAL_ACCESS_KEY);
  // Retain account-scoped onboarding and assessment progress for the next sign-in.
  await storage.removeItem("onboarding_complete_v1");
  await storage.removeItem("preferred_name_v1");
  notifyAuthStateChanged();
}

const CURRENT_TERMS_VERSION = "1.0";
const PENDING_CONSENT_KEY = `pending_legal_consent_v1:${CURRENT_TERMS_VERSION}`;
export const consentAcceptedKey = (userId: string) => `legal_consent_v2:${CURRENT_TERMS_VERSION}:${userId}`;

export async function setPendingConsentAccepted() {
  const saved = await storage.setItem(PENDING_CONSENT_KEY, "1");
  if (!saved) throw new Error("Consent could not be saved");
}

export async function hasPendingConsent(): Promise<boolean> {
  const value: string | null = await storage.getItem(PENDING_CONSENT_KEY, "" as string);
  return value === "1";
}

export async function clearPendingConsent() {
  await storage.removeItem(PENDING_CONSENT_KEY);
}

export async function hasAcceptedConsent(userId: string): Promise<boolean> {
  const value: string | null = await storage.getItem(consentAcceptedKey(userId), "" as string);
  const locallyAccepted = value === "1";
  try {
    const response = await authedFetch("/api/users/consent");
    // Only an authentication failure means "not accepted". A server hiccup
    // (cold start, 5xx) must not send an existing patient back to the Terms.
    if (response.status === 401 || response.status === 403) return false;
    if (!response.ok) return locallyAccepted;
    const result = await response.json();
    if (result.accepted) {
      await storage.setItem(consentAcceptedKey(userId), "1");
      return true;
    }
    // This account-scoped marker is written only after both required boxes are
    // accepted. Repair older consent saved against a stale backend identity.
    if (locallyAccepted) {
      await setConsentAccepted(userId);
      return true;
    }
    return false;
  } catch {
    return locallyAccepted;
  }
}

export async function setConsentAccepted(userId: string) {
  const response = await authedFetch("/api/users/consent", {
    method: "POST",
    body: JSON.stringify({ terms_version: CURRENT_TERMS_VERSION, terms_accepted: true, health_data_consent: true }),
  });
  if (!response.ok) throw new Error("Consent could not be saved");
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
    [consentAcceptedKey(previousUserId), consentAcceptedKey(nextUserId)],
    [onboardingCompleteKey(previousUserId), onboardingCompleteKey(nextUserId)],
    [preferredNameKey(previousUserId), preferredNameKey(nextUserId)],
    [affectedSideKey(previousUserId), affectedSideKey(nextUserId)],
    [patientProfileKey(previousUserId), patientProfileKey(nextUserId)],
    [patientActivityKey(previousUserId), patientActivityKey(nextUserId)],
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
  try {
    const [currentRaw, legacyRaw] = await Promise.all([
      storage.getItem(USER_OBJ, ""),
      storage.getItem("active_user_obj_v1", ""),
    ]);
    const current = JSON.parse(currentRaw || "{}");
    const legacy = JSON.parse(legacyRaw || "{}");
    if (
      current?.id === userId
      && legacy?.id
      && legacy.id !== userId
      && String(current.email || "").trim().toLowerCase()
        === String(legacy.email || "").trim().toLowerCase()
    ) {
      await migrateAccountCache(String(legacy.id), userId);
    }
  } catch {
    // Identity-bound legacy recovery is best-effort.
  }
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
  const uid = appUserId || await storage.getItem(BACKEND_USER_KEY, "");
  const headers = new Headers(init.headers as any);
  if (uid && !headers.has("X-User-Id")) headers.set("X-User-Id", uid);
  headers.set("Content-Type", "application/json");
  const response = await fetch(`${BASE}${path}`, { ...init, headers });
  if (response.status !== 401 || path === "/users/login") return response;

  const cached = await getCachedUser();
  if (!cached?.email) return response;
  try {
    const savedTrialCode = await storage.secureGet(TRIAL_ACCESS_KEY, "");
    if (!savedTrialCode) return response;
    const [cachedProfile, onboardingComplete] = await Promise.all([
      getCachedPatientProfile(cached.id),
      storage.getItem(onboardingCompleteKey(cached.id), ""),
    ]);
    const login = await fetch(`${BASE}/api/users/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: cached.email,
        name: cached.name,
        role: cached.role,
        trial_code: savedTrialCode,
      }),
    });
    if (!login.ok) return response;
    const rebound: Me = await login.json();
    if (rebound.id !== cached.id) await migrateAccountCache(cached.id, rebound.id);
    await storage.setItem(USER_KEY, rebound.id);
    await storage.setItem(USER_OBJ, JSON.stringify(rebound));
    await storage.setItem(BACKEND_USER_KEY, rebound.id);
    await hydrateAccountStateFromServer(rebound);
    if (onboardingComplete && cachedProfile && rebound.onboarding_complete !== true) {
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
