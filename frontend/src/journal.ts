import { storage } from "@/src/utils/storage";
import { getUserId } from "@/src/auth";
import { patientRequest } from "@/src/patientActivitySync";

const journalKey = (userId: string) => `rehyn_journal_entries_v2:${userId}`;

export type JournalEntry = {
  id: string;
  title: string;
  body: string;
  tag: string;
  createdAt: string;
};

export async function loadJournalEntries(): Promise<JournalEntry[]> {
  const userId = await getUserId();
  if (!userId) return [];
  try {
    const response = await patientRequest(userId, "/api/users/journal");
    if (!response.ok) throw new Error("Journal unavailable");
    const result = await response.json();
    if (!Array.isArray(result.entries)) throw new Error("Journal could not be read");
    await storage.setItem(journalKey(userId), JSON.stringify(result.entries));
    return result.entries;
  } catch {
    const raw = await storage.getItem(journalKey(userId), "");
    try { return JSON.parse(raw || "[]"); } catch { return []; }
  }
}

export async function addJournalEntry(body: string): Promise<JournalEntry[]> {
  const userId = await getUserId();
  if (!userId) throw new Error("Sign in to save your note.");
  const now = new Date();
  const draftKey = `pending_journal_entry_v1:${userId}`;
  const previous = JSON.parse(await storage.getItem(draftKey, "") || "null") as JournalEntry | null;
  const entry: JournalEntry = {
    id: previous?.body === body.trim() ? previous.id : `journal-${now.getTime()}-${Math.random().toString(36).slice(2)}`,
    title: "Recovery note",
    body: body.trim(),
    tag: "Personal note",
    createdAt: now.toISOString(),
  };
  await storage.setItem(draftKey, JSON.stringify(entry));
  const response = await patientRequest(userId, "/api/users/journal", { method: "POST", body: JSON.stringify(entry) });
  if (!response.ok || (await response.json()).ok !== true) {
    throw new Error("Your note could not be saved to your account. Please try again.");
  }
  await storage.removeItem(draftKey);
  const entries = (await loadJournalEntries()).filter((item) => item.id !== entry.id);
  const updated = [entry, ...entries];
  await storage.setItem(journalKey(userId), JSON.stringify(updated));
  return updated;
}
