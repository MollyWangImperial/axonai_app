import { getUserId } from "@/src/auth";
import { API_BASE } from "@/src/config";
import { storage } from "@/src/utils/storage";
import AsyncStorage from "@react-native-async-storage/async-storage";

type ActivityPath = "/api/users/exercise-repetitions" | "/api/alira/activities" | "/api/users/daily-checkin/complete";
type PendingActivity = { id: string; path: ActivityPath; body: Record<string, unknown> };
const pendingKey = (userId: string) => `pending_patient_activity_v1:${API_BASE}:${encodeURIComponent(userId)}:`;
export const exerciseProgressKey = (userId: string, planId: string, exerciseId: string) =>
  `ex_progress_v2:${userId}:${planId}:${exerciseId}`;
const flushes = new Map<string, Promise<boolean>>();

async function readPending(userId: string): Promise<PendingActivity[]> {
  const keys = (await AsyncStorage.getAllKeys()).filter((key) => key.startsWith(pendingKey(userId)));
  const records = await AsyncStorage.multiGet(keys.sort());
  const priority: Record<ActivityPath, number> = {
    "/api/users/exercise-repetitions": 0, "/api/alira/activities": 1, "/api/users/daily-checkin/complete": 2,
  };
  return records.flatMap(([, raw]) => raw ? [JSON.parse(raw) as PendingActivity] : [])
    .sort((a, b) => priority[a.path] - priority[b.path]);
}

export async function patientRequest(userId: string, path: string, init: RequestInit = {}): Promise<Response> {
  if (await getUserId() !== userId) throw new Error("Sign in to the same account to save this activity.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    // Pin the account for the whole request, including if the user signs out.
    return await fetch(`${API_BASE}${path}`, {
      ...init, signal: controller.signal,
      headers: { "Content-Type": "application/json", "X-User-Id": userId },
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function queuePatientActivity(userId: string, activity: PendingActivity): Promise<void> {
  // One key per event avoids losing a repetition when two tabs write together.
  // Use the throwing storage API: a failed read/write must not look like an
  // empty queue and erase records that have not reached MongoDB yet.
  await AsyncStorage.setItem(pendingKey(userId) + encodeURIComponent(activity.id), JSON.stringify(activity));
}

export async function flushPatientActivities(): Promise<boolean> {
  const userId = await getUserId();
  if (!userId) return true;
  const running = flushes.get(userId);
  if (running) return running;
  const task = (async () => {
    try {
      const pending = await readPending(userId);
      for (const item of pending) {
        const response = await patientRequest(userId, item.path, { method: "POST", body: JSON.stringify(item.body) });
        if (!response.ok || (await response.json()).ok !== true) return false;
        await AsyncStorage.removeItem(pendingKey(userId) + encodeURIComponent(item.id));
      }
      return (await readPending(userId)).length === 0;
    } catch {
      // Keep unsent records until this same account reconnects. Never drop a
      // failed request or silently submit it using another account's identity.
      return false;
    } finally {
      flushes.delete(userId);
    }
  })();
  flushes.set(userId, task);
  return task;
}

export async function loadAccountExerciseProgress(planId: string, day: string) {
  const userId = await getUserId();
  if (!userId) throw new Error("Sign in required");
  if (!await flushPatientActivities()) throw new Error("Exercise progress is waiting to sync.");
  const response = await patientRequest(userId, `/api/users/exercise-progress?plan_id=${encodeURIComponent(planId)}&date=${encodeURIComponent(day)}`);
  if (!response.ok) throw new Error("Saved exercise progress is temporarily unavailable.");
  const result = await response.json();
  if (result.ok !== true || !result.progress) throw new Error("Saved exercise progress could not be read.");
  for (const [exerciseId, progress] of Object.entries(result.progress)) {
    await storage.setItem(exerciseProgressKey(userId, planId, exerciseId), JSON.stringify(progress));
  }
  return result.progress;
}
