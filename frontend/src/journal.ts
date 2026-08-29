import { storage } from "@/src/utils/storage";

const JOURNAL_KEY = "rehyn_journal_entries_v1";

export type JournalEntry = {
  id: string;
  title: string;
  body: string;
  tag: string;
  createdAt: string;
};

export async function loadJournalEntries(): Promise<JournalEntry[]> {
  const raw = await storage.getItem(JOURNAL_KEY, "");
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export async function addJournalEntry(body: string): Promise<JournalEntry[]> {
  const entries = await loadJournalEntries();
  const now = new Date();
  const entry: JournalEntry = {
    id: `journal-${now.getTime()}`,
    title: "Recovery note",
    body: body.trim(),
    tag: "Personal note",
    createdAt: now.toISOString(),
  };
  const updated = [entry, ...entries];
  await storage.setItem(JOURNAL_KEY, JSON.stringify(updated));
  return updated;
}
