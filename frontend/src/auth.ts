import { storage } from "@/src/utils/storage";
import { API_BASE as BASE } from "@/src/config";

export type Me = { id: string; email: string; name: string; role: "patient" | "therapist"; credits: number };

export const USER_KEY = "active_user_id_v1";
export const USER_OBJ = "active_user_obj_v1";

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
  await storage.removeItem("onboarding_complete_v1");
  await storage.removeItem("preferred_name_v1");
}

export async function authedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const uid = await getUserId();
  const headers = new Headers(init.headers as any);
  if (uid) headers.set("X-User-Id", uid);
  headers.set("Content-Type", "application/json");
  return fetch(`${BASE}${path}`, { ...init, headers });
}

export async function fetchBalance(): Promise<{ credits: number; user_id?: string; costs: Record<string, number> }> {
  const r = await authedFetch("/api/credits/balance");
  return r.json();
}
